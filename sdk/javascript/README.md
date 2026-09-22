# GramRail JavaScript client

Dependency-free ES modules for Node 18+ or compatible server environments.
This package is **not published to npm**. Its package.json is private to prevent
accidental publication under an unverified package scope.

From this checkout:

```javascript
import { GramRail } from './sdk/javascript/index.mjs';

const rail = new GramRail({
  baseUrl: 'http://127.0.0.1:8080',
  apiKey: process.env.GRAMRAIL_BOT_KEY,
  botId: 'demo',
});
const job = await rail.enqueue('reports.generate', { report_id: 'r-1' }, {
  dedupe_key: 'r-1',
});
console.log(job.id);
```

Use HTTPS outside localhost. Never embed the key in a public browser or Mini App.
The client provides enqueue, claim, complete, fail, heartbeat, getJob, sendText,
and ingest. `request` accesses additional documented runtime endpoints. TypeScript
declarations accompany the client. Methods do not silently retry writes.

`relay.mjs` is a separate, smaller injected-Fetch helper. See the [experimental
native Serverless boundary](../../docs/serverless.md). A browser-compatible module
is not proof of compatibility with Telegram's own JavaScript SDK.

```bash
node --test sdk/javascript/test.mjs
```
