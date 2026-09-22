# Reliability contract

These are the implemented mechanics and their limits, not a production SLA.

## Incoming updates

The built-in router stores a fingerprint of the complete update with a unique
`(bot_id, update_id)` key. The receipt, state changes, and outgoing jobs commit
in one transaction. A matching retry is acknowledged without replaying effects.
Reusing the same update ID with different input is a conflict.

This prevents duplicate committed effects in this local database. It does not
promise update ordering across concurrent requests or indefinite source retention.
The runtime acknowledges unsupported update types without application-specific
handling. The supported built-in application inputs are text messages and
callback buttons.

## Jobs

```text
queued -> running -> succeeded
                   -> failed
                   -> queued (explicit bounded retry)
                   -> uncertain
queued -> cancelled
```

Claims are atomic and limited to requested kinds. Every claim creates a new
lease token and increments the attempt count. A heartbeat extends a live lease.
Expired tokens cannot complete, fail, or extend a replacement worker's lease.
Expired claims are recovered when claim processing runs; no worker means no
automatic recovery loop for that kind.

`recovery=retry` may execute the job more than once. Use stable operation IDs at
external services. `recovery=uncertain` stops automatic retries after an expired
claim because the side effect may already have happened. Telegram delivery uses
this conservative mode. No user-triggered uncertain-job resolution UI is shipped
yet: inspect the records and external result before deliberately creating new work.

Queued jobs can be cancelled. Running cancellation is not implemented. An
application that requires cancellation during execution must coordinate its own
cooperative cancellation protocol until that feature is added.

## Workflows and forms

Workflows are explicit state machines with a saved definition/version, revision,
and data. A transition requires the current revision. Its optional jobs are
created atomically. This is not transparent replay of arbitrary application code.

Forms save their definition and progress, scope by bot/chat/user, and validate
before advancement. Expiry is checked on interaction, not by an autonomous timer.
Approvals check configured administrator IDs on each action. Competing decisions
are serialized by the database; only one transition is accepted.

## Delivery

The sender respects conservative per-bot and per-chat gates and Telegram's
reported `retry_after`. These are not throughput guarantees or a bypass of
Telegram limits. The defaults intentionally leave headroom: approximately 25
requests/second per bot, one private-chat send per 1.05 seconds, and one group
send per 3.1 seconds. Real limits can vary by operation.

Definite connection failures can be retried. Read timeouts, malformed responses,
server errors, and expired in-flight send leases are recorded as uncertain.
A successful send means Telegram accepted the request, not that a user read it.
In simulation, success only means the fake adapter accepted it.

Callback answers have a short expiry and are prioritized. This foundation is
not a payment processor and does not implement deadline-sensitive payment events.

## Failure boundaries

Durability relies on the operating system, local disk, SQLite, backups, and
correct operation. Disk loss, full storage, clock jumps, schema bugs, compromised
keys, and operators repeating external actions can still cause failures.
Single-host SQLite is not a replicated distributed engine. Database leases use
wall-clock time: keep host time synchronized and handle lost leases conservatively.

There is no built-in retention cleanup. Monitor disk usage, back up, and define
an application-specific retention/export policy before keeping sensitive data.

References: [Telegram Bot API](https://core.telegram.org/bots/api),
[SQLite isolation](https://sqlite.org/isolation.html),
[SQLite WAL](https://sqlite.org/wal.html).
