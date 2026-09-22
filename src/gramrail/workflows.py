"""Version-pinned, explicit state machines. Not arbitrary Python replay."""
from __future__ import annotations
import json
import sqlite3
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import Conflict, InvalidInput, NotFound
from .jobs import JobQueue
from .store import Store
from .utils import canonical, fingerprint, ident


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    version: int = Field(ge=1)
    initial: str
    states: dict[str, dict[str, str]]
    terminal: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_graph(self) -> "WorkflowSpec":
        if not self.states or len(self.states) > 100:
            raise ValueError("A workflow needs 1..100 states.")
        if self.initial not in self.states or not set(self.terminal) <= self.states.keys():
            raise ValueError("Initial and terminal states must exist.")
        for state, transitions in self.states.items():
            if not 1 <= len(state) <= 64 or len(transitions) > 100:
                raise ValueError("Invalid state name or too many transitions.")
            if state in self.terminal and transitions:
                raise ValueError("Terminal states cannot have outgoing transitions.")
            for event, target in transitions.items():
                if not 1 <= len(event) <= 64 or target not in self.states:
                    raise ValueError("Every event needs a valid target state.")
        return self


def decode(row: sqlite3.Row) -> dict[str, Any]:
    return {key: json.loads(row[key]) if key in ("definition", "data") else row[key]
            for key in row.keys() if key != "fingerprint"}


class WorkflowEngine:
    def __init__(self, store: Store):
        self.store = store
        self.jobs = JobQueue(store)

    def start(self, bot_id: str, spec: WorkflowSpec, data: dict[str, Any] | None = None,
              dedupe_key: str | None = None) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self._start(conn, bot_id, spec, data or {}, dedupe_key)

    def _start(self, conn: sqlite3.Connection, bot_id: str, spec: WorkflowSpec,
               data: dict[str, Any], dedupe_key: str | None = None) -> dict[str, Any]:
        if dedupe_key is not None and not 1 <= len(dedupe_key) <= 200:
            raise InvalidInput("Idempotency key must be 1..200 characters.")
        digest = fingerprint([spec.model_dump(), data])
        row = conn.execute("SELECT * FROM workflows WHERE bot_id=? AND dedupe_key=?", (bot_id, dedupe_key)).fetchone() if dedupe_key else None
        if row:
            if row["fingerprint"] != digest:
                raise Conflict("Workflow idempotency key was reused with different input.")
            return decode(row)
        run_id = ident()
        status = "completed" if spec.initial in spec.terminal else "active"
        conn.execute("INSERT INTO workflows VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (run_id, bot_id, canonical(spec.model_dump()), spec.initial, 0, canonical(data),
                      status, dedupe_key, digest, self.store.clock(), self.store.clock()))
        self.store.event(conn, bot_id, "workflow", run_id, "workflow.started", {"name": spec.name, "version": spec.version})
        return decode(conn.execute("SELECT * FROM workflows WHERE id=?", (run_id,)).fetchone())

    def get(self, bot_id: str, run_id: str) -> dict[str, Any]:
        with self.store.read() as conn:
            row = conn.execute("SELECT * FROM workflows WHERE bot_id=? AND id=?", (bot_id, run_id)).fetchone()
        if not row:
            raise NotFound("Workflow not found in this bot.")
        return decode(row)

    def list(self, bot_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.store.read() as conn:
            return [decode(row) for row in conn.execute("SELECT * FROM workflows WHERE bot_id=? ORDER BY created_at DESC,id LIMIT ?",
                                                       (bot_id, min(max(1, limit), 200)))]

    def signal(self, bot_id: str, run_id: str, event: str, event_key: str, *,
               expected_revision: int, patch: dict[str, Any] | None = None,
               jobs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self._signal(conn, bot_id, run_id, event, event_key,
                                expected_revision=expected_revision, patch=patch, jobs=jobs)

    def _signal(self, conn: sqlite3.Connection, bot_id: str, run_id: str, event: str,
                event_key: str, *, expected_revision: int, patch: dict[str, Any] | None = None,
                jobs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not 1 <= len(event_key) <= 200 or len(jobs or []) > 20:
            raise InvalidInput("Invalid event key or more than 20 transition jobs.")
        row = conn.execute("SELECT * FROM workflows WHERE bot_id=? AND id=?", (bot_id, run_id)).fetchone()
        if not row:
            raise NotFound("Workflow not found in this bot.")
        digest = fingerprint([event, expected_revision, patch or {}, jobs or []])
        prior = conn.execute("SELECT * FROM signals WHERE run_id=? AND event_key=?", (run_id, event_key)).fetchone()
        if prior:
            if prior["fingerprint"] != digest:
                raise Conflict("Event key was reused with different input.")
            return json.loads(prior["response"])
        if row["revision"] != expected_revision:
            raise Conflict("Workflow changed. Read its latest revision before deciding.")
        definition = WorkflowSpec.model_validate_json(row["definition"])
        target = definition.states[row["state"]].get(event)
        if row["status"] != "active" or target is None:
            raise Conflict("This event is not allowed in the current workflow state.")
        data = json.loads(row["data"])
        data.update(patch or {})
        status = "completed" if target in definition.terminal else "active"
        conn.execute("UPDATE workflows SET state=?,status=?,revision=revision+1,data=?,updated_at=? WHERE id=?",
                     (target, status, canonical(data), self.store.clock(), run_id))
        for index, job in enumerate(jobs or []):
            self.jobs._enqueue(conn, bot_id, dedupe_key=f"workflow:{run_id}:{fingerprint(event_key)}:{index}", **job)
        result = decode(conn.execute("SELECT * FROM workflows WHERE id=?", (run_id,)).fetchone())
        conn.execute("INSERT INTO signals VALUES(?,?,?,?)", (run_id, event_key, digest, canonical(result)))
        self.store.event(conn, bot_id, "workflow", run_id, "workflow.transitioned", {"from": row["state"], "to": target, "event": event})
        return result
