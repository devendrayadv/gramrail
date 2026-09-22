# Working on GramRail

Owner and maintainer: dev. Primary repository: devendrayadv/gramrail.

## Product boundaries

Keep the framework reusable. Do not put application-specific logic in the queue,
store, or workflow engine. Add complete examples that exercise shared primitives.
Only advertise implemented and verified capabilities. Native Telegram Serverless
compatibility is experimental until live verification is recorded.

## Safety and correctness

- Never commit bot tokens, runtime API keys, user databases, .env files, or logs containing secrets.
- Keep database transactions short. No HTTP calls or arbitrary plugin execution inside them.
- All public operations must verify bot scope. Runtime keys are trusted backend credentials, not Mini App user sessions.
- Ingress deduplication, state mutation, and outbox creation must commit together.
- Preserve lease fencing. Do not turn uncertain sends into blind automatic retries.
- Never silently replace a webhook, start a competing poller, or discard pending updates.
- Keep simulation isolated from live credentials and production storage.
- Do not claim exactly-once external side effects, unlimited hosting, or distributed SQLite.

## Workflow

Run tests locally. Do not add, trigger, rerun, or rely on GitHub Actions unless
dev explicitly changes that instruction. Check the exact revision with Python
tests, JavaScript tests, Go tests/race detector, and applicable lint/type/build
checks. Report any check that could not run instead of marking it passed.

Use small logical branches and commits for future changes. Do not deploy a live
service or publish a registry package without explicit authorization. Public
source publication does not authorize using a production Telegram token.

Use plain language in documentation. No emojis in code, comments, documentation,
or shipped interfaces. Preserve dev's author credit and contributor attribution.
