# Telegram Serverless integration status

**Experimental; not deployed or verified on Telegram's native runtime.**

The working runtime in this repository is Python plus SQLite on your own host.
Python and Go SDKs call that runtime. They do not run inside Telegram Serverless.

## What is provided

`sdk/javascript/relay.mjs` implements a small injected-Fetch contract: forward a
complete Telegram Update to an exact HTTPS GramRail ingestion endpoint and require
an explicit acknowledgement of the same update ID. Its contract is covered by
local fake-transport tests. It imports no Node APIs and creates no timers.

The [reference example](../examples/serverless/README.md) shows the integration
boundary. It is not a deployable, verified native Telegram Serverless package.
Do not upload the whole repository to Telegram's JavaScript runtime.

## Hybrid shape

```text
Telegram -> one managed Serverless handler -> HTTPS GramRail update API
                                              -> saved forms / jobs / workers
                                              -> outbound Bot API delivery
```

Only the handler receives Telegram updates. GramRail does not register another
Telegram webhook or start polling in this design. A direct native handler can
also keep selected interactions locally and submit only custom jobs instead of
forwarding every update.

A relay adds a network dependency. It is useful only when the shared runtime
provides features you actually need; it is not inherently faster or cheaper.
An unavailable runtime causes forwarding to fail. This helper has no offline
queue and does not promise Telegram will retry indefinitely.

## Requirements before native support can be advertised

1. Verify the current handler payload and full-update context API.
2. Verify the SDK Fetch response interface and redirects; never forward a key
   through a redirected untrusted origin.
3. Verify secure secret injection. Do not hardcode runtime keys in deployed
   public source or use a full management token for ordinary job access.
4. Verify timeout, update retry, payload-size, and exception semantics live.
5. Verify authentication, repeated updates, failures, and database writes against
   a dedicated test bot. Record platform versions and observed limits.

The official [Serverless documentation](https://core.telegram.org/bots/serverless)
was not retrievable during implementation. The product does not assume undocumented
scheduling, background execution, package imports, resource allowances, or pricing.
