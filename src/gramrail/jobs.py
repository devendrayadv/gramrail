"""Durable jobs with scoped idempotency, scheduled availability, and fenced leases."""
from __future__ import annotations
import json
import re
import sqlite3
from typing import Any

from .errors import Conflict, InvalidInput, LeaseLost, NotFound
from .store import Store
from .utils import canonical, finite, fingerprint, ident, slug

KIND = re.compile(r"^[a-z][a-zA-Z0-9_.-]{0,99}$")
JSON_COLUMNS = ("payload", "result", "progress")


def unpack(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for column in JSON_COLUMNS:
        if result.get(column) is not None:
            result[column] = json.loads(result[column])
    result.pop("fingerprint", None)
    return result


class JobQueue:
    def __init__(self, store: Store):
        self.store = store

    def enqueue(self, bot_id: str, kind: str, payload: dict[str, Any], *,
                dedupe_key: str | None = None, priority: int = 50,
                run_after: float | None = None, max_attempts: int = 5,
                recovery: str = "retry") -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self._enqueue(conn, bot_id, kind, payload, dedupe_key=dedupe_key,
                                 priority=priority, run_after=run_after,
                                 max_attempts=max_attempts, recovery=recovery)

    def _enqueue(self, conn: sqlite3.Connection, bot_id: str, kind: str,
                 payload: dict[str, Any], *, dedupe_key: str | None = None,
                 priority: int = 50, run_after: float | None = None,
                 max_attempts: int = 5, recovery: str = "retry") -> dict[str, Any]:
        slug(bot_id)
        if not KIND.fullmatch(kind) or not isinstance(payload, dict):
            raise InvalidInput("A valid job kind and object payload are required.")
        if dedupe_key is not None and not 1 <= len(dedupe_key) <= 200:
            raise InvalidInput("Idempotency keys must contain 1 to 200 characters.")
        if not 0 <= priority <= 100 or not 1 <= max_attempts <= 100:
            raise InvalidInput("Priority must be 0..100 and max_attempts 1..100.")
        if recovery not in ("retry", "uncertain"):
            raise InvalidInput("Recovery must be retry or uncertain.")
        if run_after is not None:
            finite(run_after, "run_after")
        intent = fingerprint([kind, payload, priority, run_after, max_attempts, recovery])
        if dedupe_key is not None:
            existing = conn.execute("SELECT * FROM jobs WHERE bot_id=? AND dedupe_key=?",
                                    (bot_id, dedupe_key)).fetchone()
            if existing:
                if existing["fingerprint"] != intent:
                    raise Conflict("This idempotency key belongs to a different job request.")
                return unpack(existing)
        now = self.store.clock()
        job_id = ident()
        conn.execute(
            """INSERT INTO jobs(id,bot_id,kind,payload,fingerprint,dedupe_key,state,priority,
               run_after,max_attempts,recovery,created_at,updated_at)
               VALUES(?,?,?,?,?,?,'queued',?,?,?,?,?,?)""",
            (job_id, bot_id, kind, canonical(payload), intent, dedupe_key, priority,
             now if run_after is None else run_after, max_attempts, recovery, now, now),
        )
        self.store.event(conn, bot_id, "job", job_id, "job.queued", {"kind": kind})
        return unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def get(self, bot_id: str, job_id: str) -> dict[str, Any]:
        with self.store.read() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=? AND bot_id=?", (job_id, bot_id)).fetchone()
        if not row:
            raise NotFound("Job not found in this bot.")
        return unpack(row)

    def list(self, bot_id: str, state: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.read() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE bot_id=? AND (? IS NULL OR state=?) ORDER BY created_at DESC,id LIMIT ?",
                (bot_id, state, state, min(max(1, limit), 200)),
            ).fetchall()
        return [unpack(row) for row in rows]

    def _recover(self, conn: sqlite3.Connection, bot_id: str) -> None:
        now = self.store.clock()
        rows = conn.execute(
            "SELECT * FROM jobs WHERE bot_id=? AND state='running' AND lease_until<=? LIMIT 200",
            (bot_id, now),
        ).fetchall()
        for row in rows:
            state = "uncertain" if row["recovery"] == "uncertain" else (
                "queued" if row["attempts"] < row["max_attempts"] else "failed")
            conn.execute(
                "UPDATE jobs SET state=?,lease_token=NULL,lease_until=NULL,error=?,updated_at=? WHERE id=?",
                (state, "lease_expired", now, row["id"]),
            )
            self.store.event(conn, bot_id, "job", row["id"], "job.lease_expired", {"state": state})

    def claim(self, bot_id: str, kinds: list[str], lease_seconds: float = 30) -> dict[str, Any] | None:
        if not kinds or len(kinds) > 50 or any(not KIND.fullmatch(k) for k in kinds):
            raise InvalidInput("Specify 1 to 50 valid job kinds.")
        if not 5 <= finite(lease_seconds, "lease_seconds") <= 3600:
            raise InvalidInput("Lease must be 5..3600 seconds.")
        with self.store.transaction() as conn:
            self._recover(conn, bot_id)
            marks = ",".join("?" for _ in kinds)
            row = conn.execute(
                f"SELECT * FROM jobs WHERE bot_id=? AND state='queued' AND run_after<=? AND kind IN ({marks}) ORDER BY priority DESC,run_after,id LIMIT 1",  # noqa: S608
                (bot_id, self.store.clock(), *kinds),
            ).fetchone()
            if not row:
                return None
            token = ident()
            conn.execute(
                "UPDATE jobs SET state='running',attempts=attempts+1,lease_token=?,lease_until=?,updated_at=? WHERE id=?",
                (token, self.store.clock() + lease_seconds, self.store.clock(), row["id"]),
            )
            self.store.event(conn, bot_id, "job", row["id"], "job.claimed")
            return unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def _leased(self, conn: sqlite3.Connection, bot_id: str, job_id: str, token: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM jobs WHERE bot_id=? AND id=?", (bot_id, job_id)).fetchone()
        if not row:
            raise NotFound("Job not found in this bot.")
        if row["state"] != "running" or not token or row["lease_token"] != token or row["lease_until"] <= self.store.clock():
            raise LeaseLost("Lease expired or is no longer owned by this worker. Do not repeat external effects.")
        return row

    def heartbeat(self, bot_id: str, job_id: str, token: str, *, lease_seconds: float = 30,
                  progress: dict[str, Any] | None = None) -> dict[str, Any]:
        if not 5 <= finite(lease_seconds, "lease_seconds") <= 3600:
            raise InvalidInput("Lease must be 5..3600 seconds.")
        with self.store.transaction() as conn:
            self._leased(conn, bot_id, job_id, token)
            conn.execute("UPDATE jobs SET lease_until=?,progress=COALESCE(?,progress),updated_at=? WHERE id=?",
                         (self.store.clock() + lease_seconds, canonical(progress) if progress is not None else None,
                          self.store.clock(), job_id))
            return unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def complete(self, bot_id: str, job_id: str, token: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.store.transaction() as conn:
            self._leased(conn, bot_id, job_id, token)
            conn.execute("UPDATE jobs SET state='succeeded',result=?,error=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                         (canonical(result or {}), self.store.clock(), job_id))
            self.store.event(conn, bot_id, "job", job_id, "job.succeeded")
            return unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def fail(self, bot_id: str, job_id: str, token: str, error: str, *,
             retry_in: float | None = None, uncertain: bool = False) -> dict[str, Any]:
        if retry_in is not None and not 0 <= finite(retry_in, "retry_in") <= 604800:
            raise InvalidInput("Retry delay must be 0..604800 seconds.")
        if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,100}", error):
            raise InvalidInput("Use a short error code, not an exception string or secret-bearing URL.")
        with self.store.transaction() as conn:
            row = self._leased(conn, bot_id, job_id, token)
            state = "uncertain" if uncertain else (
                "queued" if retry_in is not None and row["attempts"] < row["max_attempts"] else "failed")
            conn.execute("UPDATE jobs SET state=?,error=?,run_after=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                         (state, error, self.store.clock() + (retry_in or 0), self.store.clock(), job_id))
            self.store.event(conn, bot_id, "job", job_id, "job." + state, {"error": error})
            return unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def defer(self, bot_id: str, job_id: str, token: str, until: float) -> None:
        """Return an unattempted, locally throttled send to the queue."""
        finite(until, "until")
        with self.store.transaction() as conn:
            self._leased(conn, bot_id, job_id, token)
            conn.execute("UPDATE jobs SET state='queued',attempts=MAX(0,attempts-1),run_after=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                         (max(until, self.store.clock()), self.store.clock(), job_id))

    def cancel(self, bot_id: str, job_id: str) -> dict[str, Any]:
        with self.store.transaction() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE bot_id=? AND id=?", (bot_id, job_id)).fetchone()
            if not row:
                raise NotFound("Job not found in this bot.")
            if row["state"] == "cancelled":
                return unpack(row)
            if row["state"] != "queued":
                raise Conflict("Only queued jobs can be cancelled. Running work is not forcibly terminated.")
            conn.execute("UPDATE jobs SET state='cancelled',updated_at=? WHERE id=?", (self.store.clock(), job_id))
            self.store.event(conn, bot_id, "job", job_id, "job.cancelled")
            return unpack(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
