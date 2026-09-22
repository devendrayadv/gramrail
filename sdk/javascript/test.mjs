import test from 'node:test';
import assert from 'node:assert/strict';
import {GramRail, GramRailError} from './index.mjs';
import {createRelay} from './relay.mjs';

const reply = (data, status = 200) => new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}});

test('enqueues with a bot-scoped URL, bearer key and stable idempotency field', async () => {
  let recorded;
  const client = new GramRail({baseUrl: 'http://127.0.0.1:8080', apiKey: 'test', botId: 'demo',
    fetch: async (url, options) => { recorded = {url, options}; return reply({id: 'job'}, 202); }});
  assert.equal((await client.enqueue('report', {x: 1}, {dedupe_key: 'one'})).id, 'job');
  assert.equal(recorded.url, 'http://127.0.0.1:8080/api/v1/bots/demo/jobs');
  assert.equal(recorded.options.headers.Authorization, 'Bearer test');
  assert.equal(recorded.options.redirect, 'error');
  assert.equal(JSON.parse(recorded.options.body).dedupe_key, 'one');
});

test('claim can return null', async () => {
  const client = new GramRail({baseUrl: 'https://runtime.example', apiKey: 'key', botId: 'demo', fetch: async () => reply(null)});
  assert.equal(await client.claim(['report']), null);
});

test('preserves API conflict information', async () => {
  const client = new GramRail({baseUrl: 'https://runtime.example', apiKey: 'key', botId: 'demo', fetch: async () => reply({error: {code: 'conflict', message: 'Changed'}}, 409)});
  await assert.rejects(client.getJob('one'), error => error instanceof GramRailError && error.status === 409 && error.code === 'conflict');
});

for (const baseUrl of ['http://external.example', 'https://user:secret@example.com', 'https://example.com?token=secret', 'file:///etc/passwd']) {
  test('rejects unsafe base URL ' + baseUrl.split('?')[0], () => {
    assert.throws(() => new GramRail({baseUrl, apiKey: 'key', botId: 'demo'}), TypeError);
  });
}

test('rejects invalid bot names and traversal IDs', () => {
  assert.throws(() => new GramRail({baseUrl: 'https://runtime.example', apiKey: 'key', botId: '..'}));
  const client = new GramRail({baseUrl: 'https://runtime.example', apiKey: 'key', botId: 'demo'});
  assert.throws(() => client.getJob('..'));
});

test('relay forwards complete updates and checks acknowledgment', async () => {
  let saved;
  const relay = createRelay({endpoint: 'https://runtime.example/api/v1/bots/demo/updates', apiKey: 'k'.repeat(32),
    fetch: async (_, options) => { saved = JSON.parse(options.body); return reply({accepted: true, update_id: saved.update_id}); }});
  const update = {update_id: 123, message: {text: 'hello'}};
  assert.equal((await relay(update)).accepted, true);
  assert.deepEqual(saved, update);
});

test('relay does not silently acknowledge backend rejection', async () => {
  const relay = createRelay({endpoint: 'https://runtime.example/api/v1/bots/demo/updates', apiKey: 'k'.repeat(32), fetch: async () => reply({}, 503)});
  await assert.rejects(relay({update_id: 1}));
});

test('relay rejects mismatched acknowledgment', async () => {
  const relay = createRelay({endpoint: 'https://runtime.example/api/v1/bots/demo/updates', apiKey: 'k'.repeat(32), fetch: async () => reply({accepted: true, update_id: 2})});
  await assert.rejects(relay({update_id: 1}));
});

test('relay validates complete update and endpoint', async () => {
  assert.throws(() => createRelay({endpoint: 'http://runtime.example/api/v1/bots/demo/updates', apiKey: 'k'.repeat(32), fetch: async () => {}}));
  const relay = createRelay({endpoint: 'https://runtime.example/api/v1/bots/demo/updates', apiKey: 'k'.repeat(32), fetch: async () => reply({})});
  await assert.rejects(relay({message: {text: 'missing update id'}}));
});
