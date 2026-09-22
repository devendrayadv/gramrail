# Security

GramRail is an alpha foundation. It has not received an independent security
audit or production load validation. Do not rely on it for financial custody,
regulated records, or irreversible business actions without a separate review.

## Reporting

Use GitHub private vulnerability reporting when enabled on this repository. If
it is not enabled, ask the maintainer to enable a private reporting channel
without disclosing the vulnerability publicly. Never post credentials or
production user data in issues.

## Trust model

Runtime API keys are trusted service/operator credentials. A bot key can submit
updates and jobs for that bot, including updates that assert a Telegram user ID.
Therefore, it must never be shipped to a public frontend, browser Mini App,
untrusted customer, or mobile client. A root key can access all configured bots.
The console is an operator tool, not a customer-facing administration product.

Only Telegram-authenticated webhooks should accept public Telegram updates. Use
a distinct webhook secret, TLS at a reverse proxy, request/rate controls, and a
private network where possible. The body cap does not replace edge rate limiting.

Bot tokens and API keys come from environment variables and are not stored in
SQLite. User answers and job payloads are stored in SQLite and backups. Restrict
filesystem access, use encrypted storage where appropriate, define retention,
and treat backups as sensitive. SQLite is not encrypted by this application.

The browser console keeps its key only in memory and uses textContent for data
rendering. It contains no third-party scripts. Do not expose it over plaintext
HTTP outside localhost.

Trusted built-ins run in the runtime process. Module capability declarations
are documentation and validation, not an isolation sandbox for untrusted code.

## Known boundaries

There is no production rate-limit middleware for inbound callers, per-user
customer login, key rotation API, or audit-log tamper protection yet. Keep the
runtime behind a controlled ingress and limit its exposure accordingly.
