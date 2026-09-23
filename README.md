# GramRail — Telegram Bot Framework for Workflows and Background Jobs

**Build a feature once. Reuse it across Telegram bots.**

GramRail is an MIT-licensed, open-source Telegram bot framework and self-hosted
Python runtime for **saved forms, approval workflows, background jobs, and queued
message delivery**. Use its Python components inside an existing application, or
connect a separate backend through the Python, JavaScript, or Go HTTP client.

Created and maintained by **dev** ([devendrayadv](https://github.com/devendrayadv)).
GramRail is an independent project, not an official Telegram product.

[Quick start](#quick-start-without-a-telegram-token) ·
[Examples](#example-applications) ·
[API guide](docs/api.md) ·
[FAQ](docs/faq.md) ·
[Limitations](docs/limitations.md) ·
[Roadmap](ROADMAP.md)

> **Alpha: `0.1.0a1`.** The features below describe the current implementation,
> not the full roadmap. Native Telegram Serverless deployment is **not verified**.
> Install from this repository; GramRail has not been published to PyPI or npm.

## What problem does GramRail solve?

A bot often needs more than a reply handler: remember a user's answers, send a
submission to an administrator, hand slow work to another process, and record
whether the result was delivered. GramRail provides reusable components for those
steps without requiring your business logic to live inside a new bot framework.

| Your application needs to… | GramRail provides | Read the implementation contract |
|---|---|---|
| Remember a multi-step conversation | Saved forms with validation, back/cancel, and expiry checks | [Forms and approvals](docs/modules.md) |
| Collect and review submissions | Administrator-checked approval decisions and queued notifications | [Directory example](examples/directory/README.md) |
| Run work outside a message handler | Persistent jobs with priorities, claim leases, progress, and bounded retries | [Job API](docs/api.md) |
| Save a process before waiting for its next event | Version-pinned state machines with revision checks and transactional job creation | [Workflow implementation](src/gramrail/workflows.py) |
| Handle repeated requests and interrupted workers | Bot-scoped deduplication and rejection of stale worker completions | [Reliability contract](docs/reliability.md) |
| See what happened to a request | A local console for jobs, workflow state, and recorded activity | [Offline quick start](#quick-start-without-a-telegram-token) |

**Enqueuing a job is not the same as completing it.** A worker must claim and
execute custom jobs. An accepted Telegram send is not a read receipt, and an
uncertain network result is not silently treated as a safe automatic resend.

## Quick start without a Telegram token

Requires **Git and Python 3.11+**. These shell commands are for macOS or Linux;
Windows activation instructions are in the [setup guide](docs/getting-started.md).

```bash
git clone https://github.com/devendrayadv/gramrail.git
cd gramrail
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
gramrail dev
```

Open **http://127.0.0.1:8080/console** and paste the temporary development key
printed in the terminal. The key stays in the page's memory. Simulation uses a
separate local database and does not call the Telegram Bot API.

As simulated user **1001**, send these messages one at a time:

```text
/start
/submit
My useful bot
https://example.com
```

Switch the simulator's user ID to **1** and press **Approve** on the review
message. Inspect the saved decision, notification jobs, and activity timeline.
Those IDs are demonstration values, not your real administrator configuration.

**Before live use:** configure real administrator IDs, credentials, and exactly
one update receiver. Follow [live setup](docs/getting-started.md) and
[security guidance](SECURITY.md); do not expose runtime keys in a public app.

## Add background jobs to an existing bot

You can keep your current bot framework and business database. This Python
example adds a persistent job without starting an HTTP server or sending a
Telegram message:

```python
from gramrail import JobQueue, Store

queue = JobQueue(Store(".gramrail/runtime.sqlite"))
job = queue.enqueue(
    "my-bot",
    "reports.generate",
    {"report_id": "report-1042"},
    dedupe_key="report-1042",
)
print(job["id"], job["state"])
```

Reusing the same key with identical job input returns the existing job within
that bot's scope; changing the input produces a conflict. This does not make
external processing or message sending exactly once.

To execute work in a separate process, follow the
[Python report-worker example](examples/report-worker/README.md). Its HTTP client
claims a job, reports progress, and saves completion. It is a finite example,
not a production worker supervisor.

| Integration | Current scope |
|---|---|
| [Python library](src/gramrail/__init__.py) | Storage, job queue, and workflow components on one host |
| [Python HTTP client](src/gramrail/client.py) | Submit and inspect work through a running GramRail API |
| [JavaScript client](sdk/javascript/README.md) | ES-module HTTP client with TypeScript declarations |
| [Go client](sdk/go/README.md) | Standard-library HTTP client; fewer convenience methods than Python/JavaScript |
| [Serverless relay](docs/serverless.md) | Experimental forwarding helper; native Telegram runtime compatibility is unverified |

**Keeping MongoDB or MySQL:** your application can retain them for business data.
GramRail's own state currently uses SQLite; native MongoDB/MySQL storage adapters
are not included. Remote workers use the HTTP API, not a shared SQLite file.

## How GramRail fits into a Telegram bot

```text
One update receiver: webhook, polling, or compatible relay
                            |
                 GramRail API and modules
                            |
             Forms / approvals / saved workflows
                            |
              Persistent jobs on local SQLite
                   /                    \
        Custom backend workers      Telegram delivery
        Python / JavaScript / Go    Text and callbacks
                   \                    /
                    Console and activity records
```

Polling and webhooks are alternative ways to receive Telegram Bot API updates.
GramRail workers claim **GramRail jobs**; they do not run competing Telegram
polling listeners. See the [delivery FAQ](docs/faq.md#does-gramrail-use-webhooks-or-long-polling)
and [architecture](docs/architecture.md).

For the service deployment, the current storage design is **one runtime host with
local SQLite**. Workers may connect remotely over HTTPS. This is not a distributed
database, and the SQLite file must not be mounted over a network filesystem.

## Create and inspect a new bot project

After installing GramRail, create a project in a new directory:

```bash
gramrail init my-bot
cd my-bot
gramrail dev
```

`init` includes the forms-and-approvals demo. `add` enables supported built-ins
and their dependencies; it is not a third-party package installer.

| Command | What it does |
|---|---|
| `gramrail add approvals --bot my-bot` | Enable the built-in approval module and its forms dependency |
| `gramrail doctor` | Inspect configuration, configured key requirements, and local database state |
| `gramrail doctor --telegram` | Also call `getMe` and `getWebhookInfo`; no webhook changes |
| `gramrail backup snapshot.sqlite` | Create a new SQLite backup without overwriting an existing file |
| `gramrail test` | Run local pytest after development dependencies are installed |

Environment files are **not loaded automatically**. Live delivery is explicit;
startup and diagnosis never silently replace a webhook or discard pending updates.

## Example applications

| Example | What you can learn | What it does not claim |
|---|---|---|
| [Directory submissions](examples/directory/README.md) | Collect a title and URL, then approve or reject the submission | No automatic website publishing or safety checks of submitted URLs |
| [Report worker](examples/report-worker/README.md) | Enqueue, claim, heartbeat, and complete a background job | No real report generation or worker supervision |
| [Multiple bots](examples/multi-bot/README.md) | Reuse one runtime with separate bot keys, records, and reviewers | No automated customer onboarding or staff-role platform |
| [Serverless relay](examples/serverless/README.md) | Forward a complete update to the runtime through an HTTP boundary | No verified native Telegram deployment or offline relay queue |

## Current limits and reliability

GramRail is a foundation to evaluate, not a production-certified platform.

**Implemented:** saved forms, administrator approvals, explicit state-machine
workflows, persistent jobs, text/callback delivery, bot-scoped API access, and
local simulation. Job records distinguish queued, running, succeeded, failed,
cancelled, and uncertain outcomes.

**Not implemented:** distributed storage, arbitrary-code durable replay,
recurring calendar schedules, running-task cancellation, full broadcast campaigns,
media processing, support inboxes, Mini App interfaces, fleet provisioning, or
third-party plugin installation. See the [roadmap](ROADMAP.md).

**Important boundaries:** no exactly-once external side-effect guarantee; no
unlimited hosting or throughput promise. Bot API keys are trusted backend
credentials, not public-user authentication. The root operator key can access
all configured bots.

Read [limitations](docs/limitations.md), the
[reliability contract](docs/reliability.md), and the
[recorded verification report](docs/verification.md) before connecting real users.
The report separates completed checks from unverified environments and features.

## Frequently asked questions

**Can I use GramRail with an existing Python or Go bot?** Yes, through explicit
library or HTTP-client integration. It does not automatically convert an existing
project or provide a drop-in adapter for every framework.

**Does GramRail run Python inside Telegram Serverless?** No. The runtime is
self-hosted Python. The experimental relay is a separate integration boundary;
it does not change the language supported by Telegram's hosted runtime.

**Is GramRail free?** The source is available under the MIT license. Hosting,
external APIs, and any paid Telegram features are separate costs.

**When might I not need it?** A simple bot that only responds to commands may
not need another runtime. Evaluate GramRail when you need its saved forms,
approvals, job processing, or execution records.

Read the [full FAQ](docs/faq.md) for restart recovery, duplicate input, database
choices, multi-bot boundaries, scheduling, and message-delivery guarantees.

## Documentation and source

| Start here | Deeper references |
|---|---|
| [Getting started](docs/getting-started.md) | [Architecture](docs/architecture.md) |
| [Forms and approvals](docs/modules.md) | [HTTP API and errors](docs/api.md) |
| [FAQ](docs/faq.md) | [Reliability contract](docs/reliability.md) |
| [Deployment and backups](docs/deployment.md) | [Serverless integration status](docs/serverless.md) |
| [Limitations](docs/limitations.md) | [Verification](docs/verification.md) |

A running runtime serves its OpenAPI schema at `/openapi.json` and interactive
API documentation at `/api/docs`. Source and tests are in
[`src/gramrail`](src/gramrail) and [`tests`](tests).

## Contributing and license

From the repository root, install development dependencies and run local checks:

```bash
python -m pip install -e '.[dev]'
python scripts/check.py
```

The check script also requires Node.js and Go for their SDK tests. It does not
use GitHub Actions. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[SECURITY.md](SECURITY.md) for contribution and reporting guidelines.

MIT. Copyright 2026 **dev**. See [LICENSE](LICENSE), [AUTHORS.md](AUTHORS.md), and
[CHANGELOG.md](CHANGELOG.md). GramRail is not affiliated with Telegram.
