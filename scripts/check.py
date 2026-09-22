"""Run the baseline verification locally, without remote CI or live Telegram calls."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
commands = [
    ([sys.executable, "-m", "pytest", "-q"], root),
    ([sys.executable, "-m", "compileall", "-q", "src", "examples", "tests"], root),
    (["node", "--test", "sdk/javascript/test.mjs"], root),
    (["node", "--check", "src/gramrail/web/app.js"], root),
    (["go", "test", "-race", "./..."], root / "sdk/go"),
    (["go", "vet", "./..."], root / "sdk/go"),
]
for command, directory in commands:
    if not shutil.which(command[0]):
        print(f"Missing required tool: {command[0]}", file=sys.stderr)
        raise SystemExit(1)
    print("Running:", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=directory, env=os.environ.copy(), check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
print("Baseline checks passed. Optional lint/type checks and live deployment are separate.")
