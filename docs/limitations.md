# Current limitations

Version 0.1.0a1 is an alpha foundation. Local tests are useful evidence, not a
production certification. See [verification](verification.md).

| Area | Boundary |
|---|---|
| Storage | Local, single-host SQLite; no distributed or PostgreSQL backend. |
| Workflows | Explicit state machines only; no arbitrary-code replay or automatic run migration. |
| Scheduling | Jobs become claimable at run_after; a running worker must claim them. Form expiry is lazy. |
| Cancellation | Queued jobs only. No forced running-task cancellation. |
| Uncertain work | Recorded and visible, but no audited resolution/reconciliation UI yet. |
| Updates | Built-in text and callback handling; unsupported update types have no module effects. |
| Ordering | Deduplication does not guarantee per-chat arrival ordering across concurrent requests. |
| Delivery | Plain text, callback answers, keyboard removal; no full media/broadcast engine. |
| Authentication | Static root/bot backend keys. No public-user login, staff RBAC, or Mini App validation. |
| Multiple bots | Scoped storage and API access, not automatic managed-bot provisioning. |
| Plugins | Two trusted built-ins; no third-party sandbox or package registry. |
| Console | Operator view with bounded snapshots; not complete analytics or incident replay. |
| Safety | No built-in perimeter rate limiter, data encryption, or automatic retention cleanup. |
| SDKs | Python/JS plus a smaller Go client; no framework-specific drop-in integrations claimed. |
| Serverless | Relay contract only; native Telegram deployment unverified. |
| Publishing | Source repository and registry publication require the owner's authenticated tooling. |

The Telegram adapter never promises exactly-once sends. A timed-out external
request can have succeeded. A user can still see duplicate effects when an
operator or application chooses to retry an uncertain operation.

Not included yet: support inboxes, rich catalog interfaces, Mini Apps, automatic
fleet onboarding, notification preferences, cost budgets, third-party integration
catalogues, structured media processing, or production incident replay. Their
intended direction is preserved in [ROADMAP.md](../ROADMAP.md).
