# Architecture

## A library boundary and a service boundary

The Python core provides storage, jobs, explicit workflows, and forms without
requiring the HTTP server. The FastAPI runtime adds authenticated HTTP access,
Telegram ingress, a delivery loop, and the operator console. SDKs use that API
rather than accessing the runtime database from another host.

```text
Telegram webhook OR one polling process OR a compatible relay
                              |
                    complete Telegram Update
                              |
                    transactional built-in router
                              |
           forms + workflow state + notification jobs
                              |
              SQLite on the runtime's local disk
                  |                         |
         delivery loop                 custom workers
                  |                         |
           Telegram Bot API          HTTP claim/complete
```

## Data ownership

GramRail stores its own update fingerprints, forms, workflow definitions and
state, jobs, polling offsets, rate-limit timestamps, and activity records.
It does not migrate or take ownership of an application's MongoDB or MySQL data.
A job should reference a business record by ID rather than copy unnecessary
personal data into multiple systems.

Every API resource lookup is scoped to a configured bot. Job idempotency keys
are unique within a bot. A workflow ID from another bot is not enough to access
it. The direct Python library and raw database connection are trusted interfaces;
they are not security boundaries against an operator with disk access.

## Transactions

SQLite connections enable foreign keys, a busy timeout, and WAL mode. Writes
use short `BEGIN IMMEDIATE` transactions. Schema version 1 is initialized
transactionally. A newer schema version causes startup to fail rather than guess.
No HTTP requests run within these transactions.

Incoming update deduplication, form advancement, approval creation, and outgoing
notification jobs commit together. Workflow transitions can also insert custom
jobs atomically. Failed validation rolls back the entire operation.

Workers claim jobs with a lease token and expiry. Completion and heartbeat must
present the current live token. This fences state changes by stale workers;
it cannot undo an external action already performed by an expired worker.

## Trust model

Runtime root keys authorize all configured bots. A bot key authorizes that bot's
backend operations, including ingestion with supplied Telegram user IDs. These
are trusted service keys, not public user login credentials. The live Telegram
webhook uses a separate per-bot secret header.

The console is an operator interface. Keys stay in page memory. There is no
customer-facing staff RBAC or public Mini App authentication in this alpha.
Built-in module manifests declare requirements but do not sandbox Python code.

## Extension boundaries

Add a transport adapter without changing job semantics. Add a feature module by
reusing existing workflow, state, and delivery APIs. Add a storage implementation
only when it can pass the same transaction, fencing, idempotency, and isolation
contract tests. Avoid extracting an interface without a proven second use case.

Explicit state machines are the implemented workflow model. Arbitrary-code
replay, cross-host storage, fleet provisioning, and a third-party module registry
are roadmap work, not hidden capabilities of the current runtime.
