# Deployment and operations

## Supported shape

One runtime host, a local SQLite file, and one or more workers using the HTTP
API. Start with a single API process. Workers can run remotely; the SQLite file
must not be shared over a network filesystem. Native Telegram Serverless is not
a replacement for the runtime host in this implementation.

Use Python 3.11+, a dedicated unprivileged OS account, a process supervisor, and
an HTTPS reverse proxy. Bind the API to localhost behind the proxy. Keep the
console on a private operator network when possible. Apply request rate limits,
connection limits, and timeouts at the proxy; those controls are not built in.

```bash
gramrail serve --live --config /srv/gramrail/gramrail.json --host 127.0.0.1 --port 8080
```

Secrets are read from environment variables. Configure them in the supervisor's
protected environment, not in the command line. Tokens are never stored in the
GramRail database by the default configuration. Payloads and form answers are
stored, unencrypted; use encrypted disks and a suitable retention policy.

Create separate keys per bot. A root key is cross-bot. Bot keys are backend
credentials, not staff/user authentication. Protect the public webhook using
its separate secret header. The runtime never calls setWebhook/deleteWebhook.

## Back up and restore

```bash
gramrail backup --config gramrail.json /secure/backups/gramrail-001.sqlite
```

The destination must not exist. The command uses SQLite's online backup API and
checks backup integrity. A raw copy of only the live `.sqlite` file may miss WAL
state; do not use it as the backup procedure.

To restore, stop every process that accesses the old database, including polling
and delivery. Keep the old database and sidecars for recovery. Put the backup at
a **new path**, point a copied configuration at that path, check ownership and
permissions, and run `doctor`. Test the restored copy in an isolated environment
with no live tokens before making it authoritative.

Restoring old state can replay external work that happened after the backup.
Resolve running/uncertain jobs and compare external operation IDs before enabling
live workers. Backups are not an exactly-once solution.

## Upgrades

Back up first. Review the changelog and compatibility notes. Current schema
version is 1; later migrations must be explicit and tested. A newer unknown
schema is rejected. Rolling back application code does not automatically reverse
database changes. No general rollback command is shipped.

## Monitor

Check `/health`, queue age, uncertain/failed jobs, worker heartbeat behaviour,
SQLite disk usage, and runtime logs. `/health` verifies database connectivity;
it is not an end-to-end Telegram or worker health guarantee. The console shows
the latest 100 jobs and a bounded event window, not complete analytics.

Do not use this alpha for critical payment/accounting workflows without a
separate reliability and security review. No capacity, uptime, or free-hosting
guarantee has been established.
