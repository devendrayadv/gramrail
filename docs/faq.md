# GramRail FAQ: Telegram Bot Workflows, Jobs, and Serverless Integration

[GramRail overview](../README.md) · [Setup](getting-started.md) · [API](api.md)

These answers describe **GramRail 0.1.0a1**, the current alpha implementation.
Planned capabilities are listed separately in the [roadmap](../ROADMAP.md).

## What is GramRail?

GramRail is an open-source Telegram bot framework and self-hosted Python runtime
for saved forms, approvals, background jobs, explicit workflows, and queued
message delivery. It provides Python library components and HTTP clients for
Python, JavaScript, and Go. It is an independent MIT-licensed project by **dev**,
not Telegram's Bot API server, an MTProto client, or a hosted bot service.

See the [architecture](architecture.md) and [license](../LICENSE).

## Can I use GramRail with an existing bot framework?

Yes, through an explicit integration. An existing Python application can import
the job or workflow components. A backend in Python, JavaScript, or Go can use
the HTTP client to submit and process work through a running GramRail service.
Your existing application can keep responsibility for its commands and replies.

This is not an automatic migration or a claim that every framework has a tested,
ready-made adapter. If you also forward updates to GramRail's built-in forms and
approvals router, decide which component owns each action to avoid two handlers
performing the same work.

See the [integration example](../README.md#add-background-jobs-to-an-existing-bot)
and [HTTP API](api.md).

## How do I run a slow task without keeping a Telegram handler waiting?

Enqueue a job with its kind, input, and stable `dedupe_key`, then return from the
message handler. A worker claims jobs of that kind, executes the application
function, and records progress or completion through its current lease token.
The application decides how to notify the user about the result.

GramRail does not execute a function merely because its name appears in a job.
A worker process must be running and must implement the job's processing logic.
The [report-worker example](../examples/report-worker/README.md) demonstrates the
handoff without introducing a second Telegram update listener.

## What happens when a worker restarts or its lease expires?

Job records persist in the local SQLite database. Each claim has an expiry and
a token identifying the current worker's claim. Completion, heartbeat, and failure
updates reject expired or replaced tokens.

For `recovery="retry"`, claim processing can return expired work to the queue
while its attempt budget remains. For `recovery="uncertain"`, an expired claim
is held for investigation instead of being automatically repeated. Recovery
requires claim processing to run; it is not an independent always-on service.
A stale worker may already have performed an external action, so fencing the
job record does not undo that action.

See [job implementation](../src/gramrail/jobs.py),
[job tests](../tests/test_jobs.py), and [recovery rules](reliability.md).

## Does GramRail prevent duplicate updates and duplicate messages?

The built-in ingress deduplicates committed updates by `(bot_id, update_id)` and
checks their content fingerprints. Custom job keys are also scoped to a bot:
repeating identical input returns the existing job, while changed input under
the same key is a conflict. Workflow signals have their own event keys.

These protections are not an exactly-once message-delivery guarantee. A network
failure after an external service accepts a request may leave the result
unknown. GramRail's Telegram delivery records ambiguous outcomes as `uncertain`
rather than blindly resending. Operators and applications still need a policy
for reconciling external actions.

See [transaction and delivery guarantees](reliability.md),
[ingress tests](../tests/test_forms_and_telegram.py), and
[delivery tests](../tests/test_delivery_and_sdk.py).

## What do the forms and approvals modules actually do?

Forms save progress separately for each bot, chat, and user. They validate text,
integers, URLs, and choices, support `/back` and `/cancel`, and check expiry when
an interaction occurs. An active form must be cancelled or completed before
another begins in the same scope.

The approvals module sends completed submissions for review and checks the
reviewer's Telegram user ID against configured administrators. A decision updates
the saved workflow and queues notifications. It does not automatically publish
a website entry, process a payment, or copy an uploaded document to a channel.
Those business actions require an explicit integration.

See [module behaviour](modules.md) and the
[directory-submission example](../examples/directory/README.md).

## Can I keep MongoDB or MySQL?

Yes, for your application's business data. GramRail does not require you to move
existing user, product, or order records out of that database. Jobs can refer to
business records by ID while your backend continues to read and update them.

GramRail itself currently persists its jobs, workflows, forms, and activity in
**local SQLite**. There is no native MongoDB, MySQL, or PostgreSQL storage adapter
in this alpha. A business-database write and a GramRail write are not one shared
transaction; applications must handle that cross-system boundary explicitly.

See [data ownership](architecture.md) and [deployment](deployment.md).

## Can one runtime manage multiple Telegram bots?

Yes. Configure different bot IDs, credentials, administrators, and API keys.
API access and stored records are scoped to the bot; a root operator key is
intentionally authorized across all configured bots.

This is not full customer-facing fleet management. Automated provisioning,
staff roles, customer login, and third-party plugin isolation are not included.
Bot keys are trusted backend credentials and must not be embedded in public
frontends or Mini Apps. The configured bots share the runtime host and its
SQLite failure domain.

See the [multiple-bot example](../examples/multi-bot/README.md) and
[security model](../SECURITY.md).

## Does GramRail use webhooks or long polling?

The integrated runtime supports a secret-protected webhook endpoint and a
separate guarded polling command. Select one receiver per Telegram bot token;
workers consume GramRail jobs rather than calling Telegram `getUpdates`.

`gramrail poll` refuses to start when Telegram reports a configured webhook.
`gramrail doctor --telegram` inspects bot identity and webhook information without
setting or deleting a webhook. An empty webhook URL does not prove that no other
polling process is running. GramRail does not silently take over update delivery.

See [setup](getting-started.md), [CLI implementation](../src/gramrail/cli.py), and
[Telegram's update-delivery documentation](https://core.telegram.org/bots/api#getting-updates).

## Can I deploy GramRail directly to Telegram Serverless?

**Native Telegram Serverless deployment is not verified.** The working runtime
in this repository is a self-hosted Python service using SQLite. Its Python and
Go clients do not make those languages execute in Telegram's JavaScript runtime.

The JavaScript relay helper demonstrates forwarding a complete update to an
external GramRail API and checking its acknowledgement. Local tests of that
helper do not establish native SDK, secret handling, network, timeout, or retry
compatibility. The relay has no durable offline queue; if the backend cannot
accept the update, the handoff has not completed.

See the [Serverless compatibility checklist](serverless.md) and
[relay example](../examples/serverless/README.md). A hybrid deployment still
requires a host for the GramRail runtime.

## Can I schedule jobs or cancel running work?

Jobs can have a `run_after` timestamp, which makes them eligible to be claimed
at or after that time. A worker must be running; the timestamp does not wake an
otherwise stopped host. Recurring calendar schedules, time zones, and daylight
saving rules are not implemented.

Only queued jobs can currently be cancelled through the queue/API. GramRail does
not forcibly terminate running work. Form expiry is checked on interaction,
not delivered as an automatic timed notification.

See [job parameters](api.md) and [current limitations](limitations.md).

## How do I test a bot without messaging real users?

Run `gramrail dev` to use the local console and fake Telegram adapter. You can
simulate a conversation, change the simulated user ID, review submissions, and
inspect recorded jobs and workflow state without a Telegram bot token.

Simulation uses a separate database and a temporary operator key. It is not a
complete emulator of Telegram's production environment. Live permissions,
network behaviour, throughput, and native Serverless compatibility still need
separate validation. Do not confuse a simulated success with real delivery.

See [quick start](../README.md#quick-start-without-a-telegram-token) and
[verification scope](verification.md).

## Is GramRail free and ready for production?

GramRail's source is MIT-licensed; operating the runtime still requires hosting,
and external APIs or paid Telegram features may cost money. It is not an offer
of free managed hosting. This repository is the installation source; no GramRail
package has been published to PyPI or npm.

Version `0.1.0a1` is an alpha to evaluate, not a production-certified release.
Single-host SQLite, the current backend-key trust model, unverified deployment
surfaces, and missing operational features matter when assessing suitability.
The [verification report](verification.md) records the checks performed and
remaining gaps; it is not a capacity benchmark or security audit.

For critical deployments, review [security](../SECURITY.md),
[backup and restore procedures](deployment.md), and [limitations](limitations.md).
