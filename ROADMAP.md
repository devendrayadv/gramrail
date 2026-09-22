# Roadmap

This is the intended product direction, not a list of shipped features.

## Working alpha foundation

- [x] SQLite-backed jobs, deadlines for callback delivery, schedules via run_after, leases, retry budgets, and progress.
- [x] Bot-scoped records, per-bot API keys, and root operator access.
- [x] Explicit version-pinned workflow state machines and atomic transition/job creation.
- [x] Persisted forms and review/approval module.
- [x] Transactional Telegram ingress, guarded polling, conservative delivery.
- [x] Offline operator console and CLI.
- [x] Python, JavaScript, and basic Go API clients.
- [x] Fetch-subset relay with local contract tests.

## Reliability and deployment expansion

- [ ] PostgreSQL storage adapter and multi-host correctness tests.
- [ ] Explicit uncertain-outcome reconciliation tools and operator-reviewed retries.
- [ ] Durable per-chat ordering for ingress across multiple receiver instances.
- [ ] Cooperative cancellation and worker shutdown protocol.
- [ ] Recurring calendar-aware schedules, time zones, and DST rules.
- [ ] Workflow migration procedures, definition registry, and effect reconciliation.
- [ ] Retention controls, exports, redaction policies, and audited access.
- [ ] Load tests, independent security review, and documented resource envelopes.

## Reusable feature ecosystem

- [ ] Support inbox and staff assignment.
- [ ] Opt-in notifications, preferences, and resumable broadcast campaigns.
- [ ] Catalog/search modules and media-reference helpers.
- [ ] Role-based application actions shared across chat, Mini Apps, and the console.
- [ ] Structured third-party plugin SDK with migrations and a reviewed trust model.
- [ ] Integrations for existing Python/Go/JavaScript bot frameworks.

## Serverless and fleet management

- [ ] Verify native Telegram Serverless SDK, update context, networking, retry behavior, and limits using a separate test bot.
- [ ] Publish a verified native Serverless adapter only after recording these tests.
- [ ] Other serverless-host adapters with a capability matrix.
- [ ] Managed-bot onboarding, protected credentials, fleet rollout, and customer offboarding.
- [ ] Narrow key scopes, key rotation, and customer-facing operator roles.

## Developer experience

- [ ] Redacted incident capture and isolated replay.
- [ ] Multi-user scenario runner with declared expected outcomes.
- [ ] Interactive documentation and generated typed clients from the API contract.
- [ ] Registry publication after package-name checks and an explicit release decision.

A feature graduates from this file only when implemented, documented, and tested.
