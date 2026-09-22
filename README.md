# GramRail

**Build a feature once. Reuse it across Telegram bots.**

An open-source framework and self-hosted runtime by **dev**. Add saved forms,
approvals, background jobs, and reliable execution records to an existing bot,
or use the integrated runtime for a new one.

**Status: 0.1.0 alpha.** This repository contains a working foundation, not a
claim that the entire platform roadmap is finished. Review [current limits](docs/limitations.md)
before using it with real users. No package has been published to PyPI or npm.

## Try it without a Telegram token

Requires Python 3.11 or newer. From this repository:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
gramrail dev
```

Open **http://127.0.0.1:8080/console** and paste the temporary development key
printed by the command. The key stays in browser memory. No Telegram API calls
are made in this mode, and a separate simulation database is used.

Try this conversation as user **1001**:

```text
/start
/submit
My useful bot
https://example.com
```

Then change the simulator's user ID to **1** and press **Approve** on the review
message. Inspect the saved workflow, queued notifications, and activity timeline.
A queued or simulated message is not proof of real delivery or a read receipt.

## Already have a bot?

Keep its framework and business database. Start with one component:

```python
from gramrail import JobQueue, Store

queue = JobQueue(Store(".gramrail/runtime.sqlite"))
job = queue.enqueue(
    "my-bot",
    "reports.generate",
    {"report_id": "report-1042"},
    dedupe_key="report-1042",
)
print(job["id"])
```

Use the HTTP SDK when the runtime and worker are separate processes or services:

```python
import os
from gramrail.client import Client

with Client(
    "http://127.0.0.1:8080",
    os.environ["GRAMRAIL_BOT_KEY"],
    "my-bot",
) as rail:
    job = rail.enqueue("reports.generate", {"report_id": "report-1042"}, dedupe_key="report-1042")
```

Python, [JavaScript](sdk/javascript/README.md), and [Go](sdk/go/README.md) clients
speak the same API. SDKs provide access to the runtime; they do not make every
language execute inside Telegram Serverless.

## What works now

| Capability | What it does |
|---|---|
| Durable job queue | Bot-scoped idempotency keys, priorities, scheduled availability, retry budgets, leases, heartbeat, and progress. |
| Fenced job completion | Rejects completion from expired or replaced workers. External side effects still require application-level idempotency. |
| Explicit workflows | Version-pinned state-machine definitions, revision checks, idempotent signals, and atomic transition/job creation. |
| Forms module | Saved questions, text/integer/URL/choice validation, isolated user sessions, back/cancel, and expiry checks. |
| Approvals module | Form-to-review flow, configured administrator checks, one accepted decision, and recorded notification jobs. |
| Telegram delivery | Text, callback answers, and keyboard removal; conservative throttling, `retry_after`, and explicit uncertain outcomes. |
| Ingress | Authenticated webhook or guarded polling; transactional update deduplication and effects. |
| Multi-bot API | Separate keys and bot-scoped records. A root key is intentionally cross-bot. |
| Local console | Offline conversation simulation, jobs, workflow inspection, and activity. |
| CLI | `init`, `add`, `dev`, `serve`, `doctor`, `poll`, `backup`, and local `test`. |
| SDKs | Python and JavaScript clients; a smaller Go client plus a generic request method. |
| Serverless relay | A tested Fetch-subset relay contract; native Telegram Serverless deployment is **not verified**. |

**Not yet shipped:** distributed storage, arbitrary-code durable replay, hosted
fleet provisioning, Mini App interfaces, customer-facing staff roles, custom
plugin installation, broadcast campaigns, media processing, support inboxes,
and production incident replay. These remain in [ROADMAP.md](ROADMAP.md).

## How it fits together

```text
Your webhook / guarded polling / compatible serverless relay
                         |
                   GramRail API
                         |
          +--------------+---------------+
          |              |               |
        Forms         Workflows      Custom jobs
          |              |               |
      Approvals      Saved state     Python / JS / Go workers
          |              |               |
          +--------------+---------------+
                         |
               Telegram delivery queue
                         |
                  Telegram Bot API
```

There is one Telegram Bot API update receiver per token. Workers claim jobs
from GramRail; they do not compete with the receiver through `getUpdates`.
The SQLite backend runs on one host. Do not mount its database over a network
filesystem or advertise it as a distributed cluster.

## Create a new bot application

```bash
gramrail init my-bot
cd my-bot
gramrail dev
```

The generated config includes demo reviewer IDs. Replace those before using a
real bot. Environment files are **not loaded automatically**.

```bash
gramrail add approvals --bot my-bot
gramrail doctor
gramrail doctor --telegram
```

`doctor --telegram` calls only `getMe` and `getWebhookInfo`. Startup and diagnosis
never silently set/delete webhooks or discard pending updates.

See [live setup](docs/getting-started.md) before `gramrail serve --live`.

## Documentation

- [Getting started](docs/getting-started.md): simulation, existing-bot adoption, and explicit live setup.
- [Architecture](docs/architecture.md): boundaries, data ownership, trust, and transaction design.
- [API guide](docs/api.md): authentication, request examples, jobs, workflows, and error semantics.
- [Reliability contract](docs/reliability.md): leases, duplicates, uncertain sends, and recovery.
- [Modules](docs/modules.md): built-ins, dependency resolution, and extension direction.
- [Deployment](docs/deployment.md): single-host operation, secrets, backups, and restoration.
- [Serverless](docs/serverless.md): what is actually supported and what still needs live verification.
- [Limitations](docs/limitations.md): current boundaries and unsupported claims.
- [Verification](docs/verification.md): checks actually run and checks not run.

The runtime exposes an OpenAPI schema at `/openapi.json` and interactive API
reference at `/api/docs`. The interactive reference uses upstream Swagger UI
assets; the application console itself has no external assets.

## Examples

| Example | What it demonstrates |
|---|---|
| [Directory submissions](examples/directory/README.md) | Reuse forms and approvals for a bot directory. |
| [Report worker](examples/report-worker/README.md) | Enqueue background work, claim it from Python, and save a result. |
| [Multiple bots](examples/multi-bot/README.md) | Separate API keys, admins, sessions, jobs, and decisions. |
| [Serverless relay](examples/serverless/README.md) | Delegate complete updates without starting a second Telegram listener. |

## Contribute

```bash
python -m pytest
node --test sdk/javascript/test.mjs
(cd sdk/go && go test -race ./... && go vet ./...)
python scripts/check.py
```

Tests run locally. This repository contains no GitHub Actions workflows.
See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## License and attribution

MIT. Copyright 2026 **dev**. See [LICENSE](LICENSE) and [AUTHORS.md](AUTHORS.md).
This project is independent and is not affiliated with Telegram.
