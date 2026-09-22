/**
 * Minimal Fetch-subset relay, without Node, timers, or filesystem dependencies.
 * Native Telegram Serverless deployment must be verified separately.
 * The endpoint and API key are operator-provided, trusted server-side values.
 */
export function createRelay({endpoint, apiKey, fetch: fetchImpl}) {
  if (!/^https:\/\/[^/?#@\s]+\/api\/v1\/bots\/[a-z][a-z0-9_-]{0,63}\/updates$/.test(endpoint)) {
    throw new TypeError('Provide the exact HTTPS /api/v1/bots/{bot}/updates endpoint.');
  }
  if (typeof apiKey !== 'string' || apiKey.length < 24 || typeof fetchImpl !== 'function') {
    throw new TypeError('Provide a server-side bot-scoped API key and Fetch implementation.');
  }
  return async function relay(update) {
    if (!update || !Number.isSafeInteger(update.update_id) || update.update_id < 0) {
      throw new TypeError('Relay the complete Telegram update, including update_id.');
    }
    const response = await fetchImpl(endpoint, {
      method: 'POST', headers: {'Authorization': 'Bearer ' + apiKey, 'Content-Type': 'application/json'},
      body: JSON.stringify(update),
    });
    if (!response.ok) throw new Error('GramRail did not accept this update. Do not acknowledge it as completed.');
    const result = await response.json();
    if (result.accepted !== true || result.update_id !== update.update_id) throw new Error('Unexpected relay acknowledgment.');
    return result;
  };
}
