"""Validated Telegram ingress and transactional built-in feature dispatch."""
import json
import re
import sqlite3
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import BotConfig, Config
from .errors import Conflict, InvalidInput
from .jobs import JobQueue
from .modules.forms import Forms
from .store import Store
from .utils import fingerprint
from .workflows import WorkflowEngine, WorkflowSpec


class User(BaseModel):
    id: int = Field(strict=True, gt=0, le=2**53 - 1)
    is_bot: bool = False


class Chat(BaseModel):
    id: int = Field(strict=True, ge=-(2**53 - 1), le=2**53 - 1)
    type: str = "private"


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    message_id: int = Field(strict=True, ge=0)
    chat: Chat
    sender: User | None = Field(default=None, alias="from")
    text: str | None = Field(default=None, max_length=16384)


class Callback(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str = Field(min_length=1, max_length=256)
    sender: User = Field(alias="from")
    data: str | None = Field(default=None, max_length=256)
    message: Message | None = None


class TelegramUpdate(BaseModel):
    update_id: int = Field(strict=True, ge=0, le=2**53 - 1)
    message: Message | None = None
    callback_query: Callback | None = None


APPROVAL = WorkflowSpec(name="approval", version=1, initial="pending",
                        states={"pending": {"approve": "approved", "reject": "rejected"},
                                "approved": {}, "rejected": {}}, terminal=["approved", "rejected"])


class TelegramRouter:
    def __init__(self, store: Store, config: Config):
        self.store = store
        self.config = config
        self.jobs = JobQueue(store)
        self.forms = Forms(store)
        self.workflows = WorkflowEngine(store)

    def ingest(self, bot_id: str, raw: dict[str, Any]) -> dict[str, Any]:
        bot = self.config.bot(bot_id)
        try:
            update = TelegramUpdate.model_validate(raw)
        except ValidationError as exc:
            raise InvalidInput("Malformed Telegram update.") from exc
        digest = fingerprint(raw)
        with self.store.transaction() as conn:
            prior = conn.execute("SELECT fingerprint FROM updates WHERE bot_id=? AND update_id=?", (bot_id, update.update_id)).fetchone()
            if prior:
                if prior["fingerprint"] != digest:
                    raise Conflict("An update ID was reused with different content.")
                return {"accepted": True, "duplicate": True, "update_id": update.update_id}
            conn.execute("INSERT INTO updates VALUES(?,?,?,?)", (bot_id, update.update_id, digest, self.store.clock()))
            effects: list[tuple[str, dict[str, Any], int]] = []
            if update.message is not None:
                self._message(conn, bot, update, effects)
            elif update.callback_query is not None:
                self._callback(conn, bot, update, effects)
            for index, (method, params, priority) in enumerate(effects):
                expires = self.store.clock() + 10 if method == "answerCallbackQuery" else None
                self.jobs._enqueue(conn, bot_id, "telegram." + method,
                                   {"params": params, "expires_at": expires},
                                   dedupe_key=f"update:{update.update_id}:effect:{index}",
                                   priority=priority, recovery="uncertain")
            self.store.event(conn, bot_id, "update", str(update.update_id), "update.accepted", {"effects": len(effects)})
        return {"accepted": True, "duplicate": False, "update_id": update.update_id, "effects": len(effects)}

    def _message(self, conn: sqlite3.Connection, bot: BotConfig, update: TelegramUpdate,
                 effects: list[tuple[str, dict[str, Any], int]]) -> None:
        message = update.message
        if message is None or message.sender is None or message.text is None or message.sender.is_bot:
            return
        chat_id, user_id = message.chat.id, message.sender.id
        text = message.text.strip()
        command = text.split(maxsplit=1)[0].split("@")[0] if text else ""

        def reply(value: str) -> None:
            effects.append(("sendMessage", {"chat_id": chat_id, "text": value}, 80))

        if command == "/start":
            reply(bot.welcome)
            return
        if "forms" not in bot.modules:
            return
        row = conn.execute("SELECT * FROM forms WHERE bot_id=? AND chat_id=? AND user_id=?", (bot.id, chat_id, user_id)).fetchone()
        if command == "/submit":
            parts = text.split(maxsplit=1)
            spec = next((form for form in bot.forms if len(parts) == 1 or form.name == parts[1]), None)
            if spec is None:
                reply("Available forms: " + ", ".join(form.name for form in bot.forms))
                return
            try:
                current = self.forms._start(conn, bot.id, chat_id, user_id, spec)
                reply(current["prompt"])
            except Conflict as exc:
                reply(str(exc))
            return
        if not row or row["state"] != "active":
            if command in ("/cancel", "/back"):
                reply("No form in progress. Use /submit to begin.")
            return
        if command.startswith("/") and command not in ("/back", "/cancel"):
            reply("Finish the current answer, use /back, or /cancel.")
            return
        try:
            current = self.forms._answer(conn, bot.id, chat_id, user_id,
                                         command if command in ("/back", "/cancel") else text,
                                         row["revision"])
        except InvalidInput as exc:
            reply(str(exc))
            return
        if current["state"] == "active":
            reply(current["prompt"])
        elif current["state"] == "cancelled":
            reply("Cancelled. Use /submit to start again.")
        elif current["state"] == "expired":
            reply("This form expired. Use /submit to start again.")
        else:
            if "approvals" in bot.modules:
                run = self.workflows._start(conn, bot.id, APPROVAL,
                                            {"form": current["definition"]["name"], "answers": current["answers"],
                                             "chat_id": chat_id, "user_id": user_id}, f"submission:{update.update_id}")
                summary = "\n".join(f"{key}: {value}" for key, value in current["answers"].items())
                review_text = (current["definition"]["title"] + "\n\n" + summary)[:3700]
                effects.append(("sendMessage", {
                    "chat_id": bot.review_chat_id, "text": review_text,
                    "reply_markup": {"inline_keyboard": [[
                        {"text": "Approve", "callback_data": "gr:a:" + run["id"]},
                        {"text": "Reject", "callback_data": "gr:r:" + run["id"]}]]},
                }, 70))
                reply("Submission saved for review.")
            else:
                reply("Your answers have been saved.")

    def _callback(self, conn: sqlite3.Connection, bot: BotConfig, update: TelegramUpdate,
                  effects: list[tuple[str, dict[str, Any], int]]) -> None:
        callback = update.callback_query
        if callback is None:
            return

        def answer(text: str) -> None:
            effects.append(("answerCallbackQuery", {"callback_query_id": callback.id, "text": text}, 100))

        match = re.fullmatch(r"gr:([ar]):([a-f0-9]{32})", callback.data or "")
        if not match or "approvals" not in bot.modules:
            answer("This action is not available.")
            return
        if callback.sender.id not in bot.admin_ids:
            answer("You are not authorized to review submissions.")
            return
        run_id = match[2]
        row = conn.execute("SELECT * FROM workflows WHERE bot_id=? AND id=?", (bot.id, run_id)).fetchone()
        if not row or json.loads(row["definition"])["name"] != "approval":
            answer("This submission is not available.")
            return
        if row["status"] == "completed":
            answer("Already " + row["state"] + ".")
            return
        event = "approve" if match[1] == "a" else "reject"
        run = self.workflows._signal(conn, bot.id, run_id, event, f"telegram:{update.update_id}",
                                     expected_revision=row["revision"], patch={"decided_by": callback.sender.id})
        answer("Submission " + run["state"] + ".")
        effects.append(("sendMessage", {"chat_id": run["data"]["chat_id"], "text": "Your submission was " + run["state"] + "."}, 80))
        if callback.message is not None:
            effects.append(("editMessageReplyMarkup", {"chat_id": callback.message.chat.id,
                                                       "message_id": callback.message.message_id,
                                                       "reply_markup": {"inline_keyboard": []}}, 60))

    def offset(self, bot_id: str) -> int:
        with self.store.read() as conn:
            row = conn.execute("SELECT offset FROM cursors WHERE bot_id=?", (bot_id,)).fetchone()
        return row[0] if row else 0

    def save_offset(self, bot_id: str, offset: int) -> None:
        with self.store.transaction() as conn:
            conn.execute("INSERT INTO cursors VALUES(?,?) ON CONFLICT(bot_id) DO UPDATE SET offset=MAX(cursors.offset,excluded.offset)", (bot_id, offset))
