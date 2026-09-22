"""SQLite storage for a single-host runtime, with short, serialized writes.

Never perform HTTP calls or execute untrusted plugins inside a transaction.
SQLite is not the distributed/multi-host storage adapter.
"""
import contextlib
import importlib.resources
import json
import os
import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .errors import InvalidInput
from .utils import canonical


def _enable_wal(conn: sqlite3.Connection) -> None:
    """Journal-mode changes can return BUSY without honoring busy_timeout."""
    deadline = time.monotonic() + 10
    while True:
        try:
            mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode.lower() != "wal":
                raise InvalidInput("The database filesystem must support SQLite WAL mode.")
            return
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
            if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


class Store:
    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        if str(path) == ":memory:":
            raise InvalidInput("Use a temporary database file for an isolated test runtime.")
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with contextlib.closing(self.connect()) as conn:
            _enable_wal(conn)
            conn.execute("BEGIN IMMEDIATE")
            try:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version > 1:
                    raise InvalidInput("Database was created by a newer GramRail version.")
                schema = importlib.resources.files("gramrail").joinpath("schema.sql").read_text()
                for statement in schema.split(";"):
                    if statement.strip():
                        conn.execute(statement)
                conn.execute("PRAGMA user_version=1")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with contextlib.closing(self.connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    @contextlib.contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        with contextlib.closing(self.connect()) as conn:
            yield conn

    def event(self, conn: sqlite3.Connection, bot_id: str, resource: str,
              resource_id: str, name: str, data: dict[str, Any] | None = None) -> None:
        conn.execute(
            "INSERT INTO events(bot_id,resource,resource_id,name,data,created_at) VALUES(?,?,?,?,?,?)",
            (bot_id, resource, resource_id, name, canonical(data or {}), self.clock()),
        )

    def events(self, bot_id: str, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        with self.read() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE bot_id=? AND seq>? ORDER BY seq LIMIT ?",
                (bot_id, max(0, after), min(max(1, limit), 200)),
            ).fetchall()
        return [{**dict(row), "data": json.loads(row["data"])} for row in rows]

    def backup(self, destination: str | Path) -> Path:
        target = Path(destination).expanduser().resolve()
        if target == self.path or target.exists():
            raise InvalidInput("Backup destination must be a new file.")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with self.read() as source, contextlib.closing(sqlite3.connect(target)) as backup:
                source.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise InvalidInput("Backup integrity check failed.")
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
