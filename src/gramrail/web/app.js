'use strict';
const $ = (id) => document.getElementById(id);
let key = '', bot = '', simulation = false, bots = [], events = [], eventCursor = 0;
let sequence = Math.floor(Date.now() * 100), activeTab = 'overview', loading = false;
function element(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function notice(message) { $('notice').textContent = message; }
async function request(path, body) {
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST',
    headers: {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error'});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error?.message || 'Request failed.');
  return value;
}
function base() { return '/api/v1/bots/' + encodeURIComponent(bot); }
function status(value) { return element('span', value, 'badge' + (['failed', 'uncertain'].includes(value) ? ' alert' : '')); }
function details(title, state, value) {
  const item = element('details'), summary = element('summary');
  summary.append(element('strong', title), status(state));
  item.append(summary, element('pre', JSON.stringify(value, null, 2)));
  return item;
}
async function refresh() {
  if (!key || !bot || loading) return;
  loading = true;
  const selectedBot = bot;
  try {
    const [jobs, workflows, newEvents] = await Promise.all([
      request(base() + '/jobs?limit=100'), request(base() + '/workflows?limit=100'),
      request(base() + '/events?limit=200&after=' + eventCursor)]);
    if (selectedBot !== bot || !key) return;
    events = [...events, ...newEvents].slice(-200);
    if (newEvents.length) eventCursor = newEvents[newEvents.length - 1].seq;
    $('queued-count').textContent = jobs.filter(j => j.state === 'queued').length;
    $('running-count').textContent = jobs.filter(j => j.state === 'running').length;
    $('attention-count').textContent = jobs.filter(j => ['uncertain','failed'].includes(j.state)).length;
    const jobList = $('job-list'); jobList.replaceChildren();
    for (const job of jobs) jobList.append(details(job.kind + ' · ' + job.id.slice(0, 8), job.state, job));
    if (!jobs.length) jobList.textContent = 'No jobs yet. Try a conversation or enqueue work through an SDK.';
    const workflowList = $('workflow-list'); workflowList.replaceChildren();
    for (const run of workflows) workflowList.append(details(run.definition.name + ' · v' + run.definition.version + ' · ' + run.id.slice(0, 8), run.state, run));
    if (!workflows.length) workflowList.textContent = 'No workflows yet. Complete a form to create an approval.';
    const eventList = $('event-list'); eventList.replaceChildren();
    for (const event of [...events].reverse()) {
      const row = element('div', undefined, 'event'), detail = element('div');
      detail.append(element('strong', event.name), element('small', event.resource + ': ' + event.resource_id));
      row.append(element('time', new Date(event.created_at * 1000).toLocaleString()), detail); eventList.append(row);
    }
    if (!events.length) eventList.textContent = 'No recorded activity yet.';
    const messages = $('messages'); messages.replaceChildren();
    for (const job of jobs.filter(j => j.kind === 'telegram.sendMessage').slice(0, 12).reverse()) {
      const card = element('div', undefined, 'message-card');
      card.append(element('small', 'Chat ' + job.payload.params.chat_id + ' · ' + job.id.slice(0, 8) + '  '), status(job.state));
      card.append(element('div', job.payload.params.text, 'message-text'));
      if (simulation && job.payload.params.reply_markup) {
        const actions = element('div', undefined, 'message-actions');
        for (const row of job.payload.params.reply_markup.inline_keyboard) for (const button of row) {
          const control = element('button', button.text, 'secondary');
          control.addEventListener('click', async () => {
            control.disabled = true;
            try { await request(base() + '/updates', {update_id: ++sequence, callback_query: {id: String(sequence),
              from: {id: Number($('user-id').value), is_bot: false}, data: button.callback_data}}); notice(''); await refresh(); }
            catch (error) { notice(error.message); } finally { control.disabled = false; }
          }); actions.append(control);
        }
        card.append(actions);
      }
      messages.append(card);
    }
    if (!messages.children.length) messages.textContent = 'Messages will appear here when an update queues a reply.';
    $('freshness').textContent = 'Updated ' + new Date().toLocaleTimeString() + ' · showing latest 100 jobs';
  } catch (error) { notice(error.message); } finally { loading = false; }
}
$('connect-form').addEventListener('submit', async (event) => {
  event.preventDefault(); key = $('api-key').value.trim();
  try {
    const result = await request('/api/v1/bots'); bots = result.bots; simulation = result.mode === 'simulation';
    $('bot-select').replaceChildren(...bots.map(item => { const option = element('option', item.name); option.value = item.id; return option; }));
    bot = bots[0]?.id || ''; $('bot-select').disabled = !bot;
    $('mode').textContent = simulation ? 'Simulation mode' : 'Live runtime';
    $('mode').className = 'badge' + (simulation ? '' : ' alert');
    $('connect-panel').hidden = true; $('toolbar').hidden = false;
    $('simulation-panel').hidden = !simulation; $('simulate-send').disabled = !simulation;
    $('api-key').value = ''; notice(''); updateModules(); await refresh();
  } catch (error) { key = ''; notice(error.message); }
});
function updateModules() {
  $('modules').replaceChildren();
  for (const name of bots.find(item => item.id === bot)?.modules || []) {
    const box = element('div', undefined, 'module'); box.append(element('strong', name));
    box.append(element('p', name === 'forms' ? 'Saved questions, validation, back and cancel.' : 'Authorized decisions with recorded state and notifications.')); $('modules').append(box);
  }
}
$('bot-select').addEventListener('change', async () => { bot = $('bot-select').value; events = []; eventCursor = 0; updateModules(); await refresh(); });
$('refresh').addEventListener('click', refresh);
$('disconnect').addEventListener('click', () => { key = ''; location.reload(); });
$('simulate-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if (!simulation) return;
  const id = Number($('user-id').value);
  if (!Number.isSafeInteger(id) || id <= 0) { notice('Enter a valid positive user ID.'); return; }
  $('simulate-send').disabled = true;
  try { await request(base() + '/updates', {update_id: ++sequence, message: {message_id: sequence,
    from: {id, is_bot: false}, chat: {id, type: 'private'}, text: $('message').value}});
    $('message').value = ''; notice(''); await refresh();
  } catch (error) { notice(error.message); } finally { $('simulate-send').disabled = false; }
});
for (const button of document.querySelectorAll('[data-message]')) button.addEventListener('click', () => { $('message').value = button.dataset.message; $('message').focus(); });
for (const button of document.querySelectorAll('[data-tab]')) button.addEventListener('click', () => {
  activeTab = button.dataset.tab;
  for (const panel of document.querySelectorAll('.view')) panel.hidden = panel.id !== activeTab;
  for (const item of document.querySelectorAll('.nav')) item.classList.toggle('active', item === button);
  $('page-title').textContent = activeTab === 'overview' ? 'Your bot, in focus.' : button.textContent;
});
setInterval(() => { if (key && !document.hidden) refresh(); }, 3000);
