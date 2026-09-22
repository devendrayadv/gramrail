# Serverless relay contract

The helper in `sdk/javascript/relay.mjs` forwards a complete Telegram Update to
an authenticated GramRail API and checks the acknowledgment. It is tested with
an injected Fetch-like function. This is **not a verified Telegram-native
Serverless deployment** and does not include invented SDK import names.

Read `docs/serverless.md` and adapt the helper to the actual host. The relay must
be the bot's sole Telegram update receiver. Its backend calls GramRail's API,
not Telegram `getUpdates`. Keep runtime keys server-side and use HTTPS.

The helper does not provide a durable offline queue. A rejected or timed-out
handoff must not be acknowledged as successful; the platform's actual retry
behaviour needs live verification. The backend must be available to accept work.
Do not forward requests merely to add an extra network hop without a useful
separation of responsibilities.
