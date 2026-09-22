# HTTP API

The generated contract is `/openapi.json`. Interactive documentation is at
`/api/docs`. Send `Authorization: Bearer <key>` over HTTPS outside localhost.
The examples use environment variables; never substitute production secrets
into committed files. Write requests are capped at 256 KiB.

## Scope

`GET /api/v1/bots` lists only bots accessible to the key. Root keys deliberately
see every bot; bot keys cannot read or mutate another bot. All following paths
are relative to `/api/v1/bots/{bot_id}`.

| Method / path | Result |
|---|---|
| `POST /updates` | Accept a complete Telegram Update; returns its ID and duplicate flag. |
| `POST /messages` | Enqueue plain text; HTTP 202 means queued, not delivered. |
| `POST /jobs` | Enqueue custom work. |
| `GET /jobs?state=queued&limit=50` | Latest job snapshot, maximum 200; not full pagination. |
| `GET /jobs/{id}` | One job, without its live lease token. |
| `POST /jobs/claim` | One leased job, including its token, or JSON `null`. |
| `POST /jobs/{id}/heartbeat` | Extend a live lease and optionally save progress. |
| `POST /jobs/{id}/complete` | Save a result using a valid lease token. |
| `POST /jobs/{id}/fail` | Fail, defer a retry, or record an uncertain outcome. |
| `POST /jobs/{id}/cancel` | Cancel queued work; running work is not force-cancelled. |
| `POST /workflows` | Start an explicit, version-pinned state machine. |
| `GET /workflows` and `/workflows/{id}` | Read workflow snapshots. |
| `POST /workflows/{id}/signals` | Transition with revision and idempotency checks. |
| `GET /events?after=0&limit=100` | Activity after a monotonic sequence cursor. |

Runtime-wide endpoints include `/health` (no secrets), `/api/v1/modules`, and
the authenticated live webhook `/webhooks/{bot_id}`. The webhook uses
`X-Telegram-Bot-Api-Secret-Token` rather than a runtime Bearer key.

## Enqueue and execute

```bash
curl -sS "$GRAMRAIL_URL/api/v1/bots/demo/jobs" \
  -H "Authorization: Bearer $GRAMRAIL_BOT_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"kind":"reports.generate","payload":{"report_id":"r-1"},"dedupe_key":"r-1"}'
```

A job request accepts `kind`, object `payload`, optional `dedupe_key`, `priority`
(0..100, higher first), `run_after` (Unix seconds), `max_attempts` (1..100), and
`recovery` (`retry` or `uncertain`). The default attempt budget is 5. There is no
implicit TTL for idempotency records in this version.

Claim with `{"kinds":["reports.generate"],"lease_seconds":30}`. Complete with
`{"lease_token":"<from-claim>","result":{"report_id":"r-1"}}`.
Heartbeat accepts the token, `lease_seconds`, and optional object `progress`.
Failure accepts the token and a short `error` code; optional `retry_in` schedules
a retry, while `uncertain:true` prevents an automatic retry.

Kinds prefixed `telegram.` and `gramrail.` are reserved. Public custom-job APIs
cannot enqueue or claim them. Use the messages API for outbound Telegram text.
Keep lease tokens private. Ordinary list/get responses omit them.

## Workflow signals

Start a workflow with a `definition`, object `data`, and optional `dedupe_key`:

```json
{
  "definition": {
    "name": "report", "version": 1, "initial": "waiting",
    "states": {"waiting": {"generate": "processing"}, "processing": {"finish": "done"}, "done": {}},
    "terminal": ["done"]
  },
  "data": {"report_id": "r-1"},
  "dedupe_key": "r-1"
}
```

Signal the run with an `event`, stable `event_key`, `expected_revision`, optional
object `patch`, and optional `jobs`. The transition and inserted jobs share one
transaction. Transition-job keys are generated from the run/event; do not supply
your own job `dedupe_key` inside a signal. Repeating the same event with the same
input returns its originally recorded response, not necessarily the run's newest
state. Fetch the workflow to see its current revision.

## Errors and retries

Errors use `{"error":{"code":"...","message":"..."}}`. Validation errors also
include field locations but do not echo invalid input. Authentication failures
are 403; missing scoped resources 404; conflicts and lost leases 409; invalid
operations 400; schema validation 422; oversized bodies 413.

SDKs do not automatically retry writes. After a lost enqueue response, retry
with the same idempotency key and identical intent. After an ambiguous completion,
read the job state before making another external side effect. There is no
universal exactly-once guarantee for external services.

JSON IDs use strings for jobs/workflows and safe integers for Telegram IDs.
Payloads must be finite JSON values. Do not place bot tokens or service secrets
inside job payloads, results, or error text.
