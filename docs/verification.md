# Verification of the initial alpha

Verified locally on Linux with Python 3.13.5, Node.js 22.16.0, and Go 1.23.2.
No GitHub Actions workflows were created or used. No production credentials,
real Telegram messages, or native Telegram Serverless deployment were used.

| Check | Result |
|---|---|
| Python unit/integration tests | 113 passed. Includes simultaneous claims/decisions, scoped keys, repeated updates, leases, state transitions, and example configuration. |
| Python statement coverage | 85% in this local run. Coverage is not a correctness guarantee. |
| JavaScript SDK and relay | 12 tests passed against controlled request mocks. |
| Go SDK | Tests and race detector passed; go vet passed. |
| Python compilation / JavaScript syntax | Passed. |
| Real local HTTP runtime | Startup, console asset serving, OpenAPI, form submission, approval, duplicate update handling, Python SDK worker, and saved results passed. |
| Python wheel | Built without network access; checked package data includes schema and console assets. |
| Markdown links | Repository-relative file links checked. External URLs are references, not availability guarantees. |

The concurrency suite exposed a journal-mode initialization race under coverage.
WAL initialization now retries only SQLite BUSY/LOCKED errors with a bounded
wait; tests cover that retry and ensure unrelated storage errors are not hidden.

## Reproduce

```bash
python scripts/check.py
python -m pytest --cov=gramrail --cov-report=term-missing
python scripts/smoke_http.py
python -m pip wheel . --no-build-isolation --no-deps --no-index -w dist
```

Install the development dependencies first. The HTTP smoke test starts a
separate local simulation runtime on port 8096 and removes its temporary data.
It never calls Telegram. Keep that port free before running it.

## Checks not completed

- Ruff and mypy were not installed; dependency retrieval failed because network
  name resolution was unavailable. They are configured development tools, not
  claimed passing checks.
- Chromium browser automation was attempted, but navigation to the local console
  was blocked by the execution environment's administrator policy. Browser
  interaction and responsive layout are therefore not verified. HTTP asset
  checks and JavaScript syntax checks do not replace a rendered-browser test.
- No live Telegram, native Serverless deployment, load benchmark, independent
  security audit, Windows/macOS runtime test, or external database integration.
- Python 3.11/3.12 compatibility is declared but was not executed in this session.

The roadmap is not a completed-features list. See the reliability contract and
limitations before connecting a real bot.
