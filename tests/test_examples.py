import runpy
from pathlib import Path

from gramrail.config import Config


ROOT = Path(__file__).resolve().parents[1]


def test_example_configs():
    for path in (ROOT / "examples").glob("*/gramrail.json"):
        assert Config.load(path).bots


def test_worker_import_has_no_network_effect():
    assert callable(runpy.run_path(str(ROOT / "examples/report-worker/worker.py"))["main"])
