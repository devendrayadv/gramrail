"""Conversation forms with per-user isolation and persisted definition snapshots."""
import json
import sqlite3
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..errors import Conflict, InvalidInput, NotFound
from ..store import Store
from ..utils import canonical


class FormField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    prompt: str = Field(min_length=1, max_length=2000)
    kind: Literal["text", "integer", "url", "choice"] = "text"
    choices: list[str] = Field(default_factory=list, max_length=30)
    min_length: int = Field(default=1, ge=0, le=4000)
    max_length: int = Field(default=1000, ge=1, le=4000)

    @model_validator(mode="after")
    def valid_field(self) -> "FormField":
        if self.min_length > self.max_length:
            raise ValueError("min_length cannot exceed max_length.")
        if self.kind == "choice" and (not self.choices or len(set(self.choices)) != len(self.choices)):
            raise ValueError("Choice fields require unique choices.")
        if any(not choice or len(choice) > self.max_length for choice in self.choices):
            raise ValueError("Choices must be nonempty and fit max_length.")
        return self

    def parse(self, text: str) -> str | int:
        value = text.strip()
        if not self.min_length <= len(value) <= self.max_length:
            raise InvalidInput(f"Enter {self.min_length} to {self.max_length} characters.")
        if self.kind == "integer":
            try:
                number = int(value)
            except ValueError as exc:
                raise InvalidInput("Enter a whole number.") from exc
            if not -(2**53 - 1) <= number <= 2**53 - 1:
                raise InvalidInput("Number is outside the portable JSON integer range.")
            return number
        if self.kind == "url":
            try:
                url = urlsplit(value)
                valid = url.scheme in ("https", "http") and bool(url.hostname) and not url.username and not url.password
            except ValueError:
                valid = False
            if not valid:
                raise InvalidInput("Enter a complete http(s) URL without embedded credentials.")
        if self.kind == "choice" and value not in self.choices:
            raise InvalidInput("Choose one of: " + ", ".join(self.choices))
        return value


class FormSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    version: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=200)
    fields: list[FormField] = Field(min_length=1, max_length=20)
    expires_in: int = Field(default=86400, ge=60, le=2592000)

    @model_validator(mode="after")
    def unique_fields(self) -> "FormSpec":
        if len({field.name for field in self.fields}) != len(self.fields):
            raise ValueError("Form field names must be unique.")
        return self


def decode(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    for key in ("definition", "answers"):
        value[key] = json.loads(value[key])
    fields = value["definition"]["fields"]
    value["prompt"] = fields[value["step"]]["prompt"] if value["state"] == "active" else None
    if value["state"] == "active" and fields[value["step"]]["choices"]:
        value["prompt"] += "\nOptions: " + ", ".join(fields[value["step"]]["choices"])
    return value


class Forms:
    def __init__(self, store: Store):
        self.store = store

    def start(self, bot_id: str, chat_id: int, user_id: int, spec: FormSpec) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self._start(conn, bot_id, chat_id, user_id, spec)

    def _start(self, conn: sqlite3.Connection, bot_id: str, chat_id: int, user_id: int,
               spec: FormSpec) -> dict[str, Any]:
        existing = conn.execute("SELECT * FROM forms WHERE bot_id=? AND chat_id=? AND user_id=?", (bot_id, chat_id, user_id)).fetchone()
        if existing and existing["state"] == "active" and existing["expires_at"] > self.store.clock():
            raise Conflict("A form is already in progress. Use /cancel before starting another.")
        conn.execute("""INSERT INTO forms VALUES(?,?,?,?,0,?,'active',0,?,?)
                        ON CONFLICT(bot_id,chat_id,user_id) DO UPDATE SET definition=excluded.definition,
                        step=0,answers=excluded.answers,state='active',revision=forms.revision+1,
                        expires_at=excluded.expires_at,updated_at=excluded.updated_at""",
                     (bot_id, chat_id, user_id, canonical(spec.model_dump()), "{}", self.store.clock() + spec.expires_in, self.store.clock()))
        self.store.event(conn, bot_id, "form", f"{chat_id}:{user_id}", "form.started", {"name": spec.name, "version": spec.version})
        return decode(conn.execute("SELECT * FROM forms WHERE bot_id=? AND chat_id=? AND user_id=?", (bot_id, chat_id, user_id)).fetchone())

    def answer(self, bot_id: str, chat_id: int, user_id: int, text: str,
               expected_revision: int) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return self._answer(conn, bot_id, chat_id, user_id, text, expected_revision)

    def _answer(self, conn: sqlite3.Connection, bot_id: str, chat_id: int, user_id: int,
                text: str, expected_revision: int) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM forms WHERE bot_id=? AND chat_id=? AND user_id=?", (bot_id, chat_id, user_id)).fetchone()
        if not row:
            raise NotFound("No form in progress.")
        if row["state"] != "active" or row["revision"] != expected_revision:
            raise Conflict("Form changed. Read its latest state before answering.")
        if row["expires_at"] <= self.store.clock():
            conn.execute("UPDATE forms SET state='expired',revision=revision+1 WHERE bot_id=? AND chat_id=? AND user_id=?", (bot_id, chat_id, user_id))
            return decode(conn.execute("SELECT * FROM forms WHERE bot_id=? AND chat_id=? AND user_id=?", (bot_id, chat_id, user_id)).fetchone())
        spec = FormSpec.model_validate_json(row["definition"])
        answers = json.loads(row["answers"])
        step = row["step"]
        state = "active"
        if text == "/cancel":
            state = "cancelled"
        elif text == "/back":
            step = max(0, step - 1)
            for field in spec.fields[step:]:
                answers.pop(field.name, None)
        else:
            answers[spec.fields[step].name] = spec.fields[step].parse(text)
            step += 1
            state = "completed" if step == len(spec.fields) else "active"
        conn.execute("UPDATE forms SET step=?,answers=?,state=?,revision=revision+1,updated_at=? WHERE bot_id=? AND chat_id=? AND user_id=?",
                     (step, canonical(answers), state, self.store.clock(), bot_id, chat_id, user_id))
        self.store.event(conn, bot_id, "form", f"{chat_id}:{user_id}", "form." + state)
        return decode(conn.execute("SELECT * FROM forms WHERE bot_id=? AND chat_id=? AND user_id=?", (bot_id, chat_id, user_id)).fetchone())

    def get(self, bot_id: str, chat_id: int, user_id: int) -> dict[str, Any] | None:
        with self.store.read() as conn:
            row = conn.execute("SELECT * FROM forms WHERE bot_id=? AND chat_id=? AND user_id=?", (bot_id, chat_id, user_id)).fetchone()
        return decode(row) if row else None
