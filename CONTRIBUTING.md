# Contributing

Start with the README and the reliability contract. Reproduce a problem with a
small offline test before changing implementation. Keep examples running against
the public API or library interfaces, rather than undocumented database tables.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/check.py
```

The baseline check runs Python tests, JavaScript tests, Go tests and race detection,
Go vet, Python syntax checks, and JavaScript syntax checks. Install Node 18+ and
Go 1.22+ to check all SDKs. Missing required tools cause the command to fail rather
than being reported as a pass.

Additional development checks:

```bash
python -m ruff check .
python -m mypy src/gramrail
python -m build
```

Do not substitute GitHub Actions for local verification. No workflow is included.
The initial environment did not have every optional tool; consult the recorded
verification report rather than assuming all checks have run.

## Design expectations

Use stable error codes, explicit scopes, and recorded state transitions. Test
repeated input, unauthorized callers, stale workers, concurrency, expired forms,
and restart behavior. Add a migration for persistent changes; never drop data
as an incidental effect of removing a model declaration.

A module needs a useful example, documented requirements, and tests. The current
module registry contains trusted built-ins only. Do not add dynamic code loading
until a reviewed trust and permissions model exists.

## Pull requests

Explain the problem, changes, tests, migration implications, and remaining limits.
Do not attach real tokens or raw production user updates. Preserve attribution.
