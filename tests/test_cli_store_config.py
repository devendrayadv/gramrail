import json
import os
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from gramrail import JobQueue, Store
from gramrail.cli import doctor, main
from gramrail.config import Config, starter
from gramrail.errors import InvalidInput
from gramrail.modules.manifest import resolve


def test_init_and_doctor_are_safe(tmp_path, capsys, monkeypatch):
    path = tmp_path / "example-bot"
    assert main(["init", str(path)]) == 0
    assert (path / "gramrail.json").exists()
    assert not (path / ".env").exists()
    assert main(["init", str(path)]) == 1
    monkeypatch.delenv("GRAMRAIL_ADMIN_KEY", raising=False)
    monkeypatch.delenv("GRAMRAIL_BOT_KEY", raising=False)
    config = Config.load(path / "gramrail.json")
    checks = doctor(config)
    assert any(check["check"] == "database" for check in checks)
    assert not Path(config.database).exists()


def test_modules_install_dependencies():
    assert [module.name for module in resolve(["approvals", "forms"])] == ["forms", "approvals"]
    with pytest.raises(InvalidInput):
        resolve(["imaginary"])


def test_config_strictness():
    value = starter()
    value["undocumented"] = True
    with pytest.raises(ValidationError):
        Config.model_validate(value)


def test_config_bot_keys_cannot_be_shared():
    value = starter()
    value["bots"].append({**value["bots"][0], "id": "other"})
    with pytest.raises(ValidationError):
        Config.model_validate(value)


def test_credentials_do_not_accept_short_keys(config, monkeypatch):
    monkeypatch.setenv("GRAMRAIL_ADMIN_KEY", "too-short")
    with pytest.raises(InvalidInput):
        config.credentials()


def test_backup_is_consistent_and_restorable(store, tmp_path):
    job = JobQueue(store).enqueue("demo", "work", {"safe": True})
    target = store.backup(tmp_path / "backups" / "snapshot.sqlite")
    restored = Store(target)
    assert JobQueue(restored).get("demo", job["id"])["payload"] == {"safe": True}
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(InvalidInput):
        store.backup(target)
    with pytest.raises(InvalidInput):
        store.backup(store.path)


def test_database_integrity_and_version(store):
    with store.read() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with store.transaction() as conn:
        conn.execute("PRAGMA user_version=99")
    with pytest.raises(InvalidInput):
        Store(store.path)


def test_memory_path_is_explicitly_unsupported():
    with pytest.raises(InvalidInput):
        Store(":memory:")


def test_concurrent_database_initialization(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from gramrail import Store
    path = tmp_path / "shared.sqlite"
    with ThreadPoolExecutor(max_workers=8) as workers:
        stores = list(workers.map(lambda _: Store(path), range(16)))
    assert all(store.path == path for store in stores)
    with stores[0].read() as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("key", ["x" * 24 + "\n", " " * 32, "x" * 257])
def test_api_key_rejects_controls_spaces_and_excess_length(config, monkeypatch, key):
    monkeypatch.setenv("GRAMRAIL_ADMIN_KEY", key)
    with pytest.raises(InvalidInput):
        config.credentials()


def test_wal_initialization_retries_busy(monkeypatch):
    from unittest.mock import MagicMock
    from gramrail.store import _enable_wal
    import sqlite3
    conn = MagicMock()
    busy = sqlite3.OperationalError("database is locked")
    busy.sqlite_errorcode = sqlite3.SQLITE_BUSY
    row = MagicMock()
    row.fetchone.return_value = ("wal",)
    conn.execute.side_effect = [busy, row]
    monkeypatch.setattr("gramrail.store.time.sleep", lambda delay: None)
    _enable_wal(conn)
    assert conn.execute.call_count == 2


def test_wal_initialization_does_not_hide_other_errors():
    from unittest.mock import MagicMock
    from gramrail.store import _enable_wal
    import sqlite3
    conn = MagicMock()
    conn.execute.side_effect = sqlite3.OperationalError("disk I/O error")
    with pytest.raises(sqlite3.OperationalError, match="disk I/O"):
        _enable_wal(conn)
