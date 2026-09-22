export class GramRailError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = 'GramRailError';
    this.status = status;
    this.code = code;
  }
}

function segment(value) {
  if (typeof value !== 'string' || !value || value === '.' || value === '..') {
    throw new TypeError('A nonempty resource identifier is required.');
  }
  return encodeURIComponent(value);
}

export class GramRail {
  constructor({baseUrl, apiKey, botId, fetch: fetchImpl = globalThis.fetch, timeoutMs = 15000}) {
    const url = new URL(baseUrl);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new TypeError('Provide an http(s) URL without credentials, query, or fragment.');
    }
    if (url.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
      throw new TypeError('Non-local runtime connections require HTTPS.');
    }
    if (!/^[a-z][a-z0-9_-]{0,63}$/.test(botId) || !apiKey || typeof fetchImpl !== 'function') {
      throw new TypeError('A valid bot ID, API key, and Fetch implementation are required.');
    }
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new TypeError('timeoutMs must be positive.');
    this.baseUrl = url.toString().replace(/\/$/, '') + '/api/v1/bots/' + segment(botId);
    this.apiKey = apiKey;
    this.fetch = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  async request(method, path, body) {
    const response = await this.fetch(this.baseUrl + path, {
      method, headers: {'Authorization': 'Bearer ' + this.apiKey, 'Content-Type': 'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body),
      redirect: 'error', signal: AbortSignal.timeout(this.timeoutMs),
    });
    let value;
    try { value = await response.json(); } catch { value = null; }
    if (!response.ok) {
      throw new GramRailError(response.status, value?.error?.code || 'http_error', value?.error?.message || 'GramRail request failed.');
    }
    return value;
  }

  enqueue(kind, payload, options = {}) { return this.request('POST', '/jobs', {kind, payload, ...options}); }
  getJob(id) { return this.request('GET', '/jobs/' + segment(id)); }
  claim(kinds, leaseSeconds = 30) { return this.request('POST', '/jobs/claim', {kinds, lease_seconds: leaseSeconds}); }
  complete(id, leaseToken, result = {}) { return this.request('POST', '/jobs/' + segment(id) + '/complete', {lease_token: leaseToken, result}); }
  fail(id, leaseToken, error, options = {}) { return this.request('POST', '/jobs/' + segment(id) + '/fail', {lease_token: leaseToken, error, ...options}); }
  heartbeat(id, leaseToken, options = {}) { return this.request('POST', '/jobs/' + segment(id) + '/heartbeat', {lease_token: leaseToken, ...options}); }
  sendText(chatId, text, options = {}) { return this.request('POST', '/messages', {chat_id: chatId, text, ...options}); }
  ingest(update) { return this.request('POST', '/updates', update); }
}
