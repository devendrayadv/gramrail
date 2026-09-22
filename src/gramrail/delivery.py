"""Bounded Telegram delivery with shared throttling and explicit uncertain sends."""
import sqlite3
from typing import Any

from .adapters.bot_api import BotAPI, FakeBotAPI, TelegramFailure
from .errors import InvalidInput, LeaseLost
from .jobs import JobQueue
from .store import Store

METHODS = ("sendMessage", "answerCallbackQuery", "editMessageReplyMarkup")


class Delivery:
    def __init__(self, store: Store, adapters: dict[str, BotAPI | FakeBotAPI]):
        self.store = store
        self.queue = JobQueue(store)
        self.adapters = adapters

    def send_text(self, bot_id: str, chat_id: int, text: str, *,
                  dedupe_key: str | None = None, priority: int = 80,
                  run_after: float | None = None) -> dict[str, Any]:
        if not text or len(text.encode("utf-16-le")) // 2 > 4096:
            raise InvalidInput("Text must be nonempty and at most 4096 UTF-16 units.")
        return self.queue.enqueue(bot_id, "telegram.sendMessage",
                                  {"params": {"chat_id": chat_id, "text": text}, "expires_at": None},
                                  dedupe_key=dedupe_key, priority=priority, run_after=run_after,
                                  recovery="uncertain")

    @staticmethod
    def _value(conn: sqlite3.Connection, key: str) -> float:
        row = conn.execute("SELECT next_at FROM rate_limits WHERE key=?", (key,)).fetchone()
        return row[0] if row else 0

    def _reserve(self, bot_id: str, method: str, params: dict[str, Any]) -> float:
        now = self.store.clock()
        with self.store.transaction() as conn:
            until = self._value(conn, f"{bot_id}:blocked")
            if method == "sendMessage":
                until = max(until, self._value(conn, f"{bot_id}:global"),
                            self._value(conn, f"{bot_id}:chat:{params['chat_id']}"))
            if until > now:
                return until
            if method == "sendMessage":
                for key, delay in [(f"{bot_id}:global", 0.04),
                                   (f"{bot_id}:chat:{params['chat_id']}", 3.1 if int(params['chat_id']) < 0 else 1.05)]:
                    conn.execute("INSERT INTO rate_limits VALUES(?,?) ON CONFLICT(key) DO UPDATE SET next_at=excluded.next_at", (key, now + delay))
        return now

    def _block(self, bot_id: str, delay: float) -> None:
        with self.store.transaction() as conn:
            conn.execute("INSERT INTO rate_limits VALUES(?,?) ON CONFLICT(key) DO UPDATE SET next_at=MAX(rate_limits.next_at,excluded.next_at)", (f"{bot_id}:blocked", self.store.clock() + delay))

    def tick(self, bot_id: str) -> bool:
        job = self.queue.claim(bot_id, ["telegram." + method for method in METHODS], lease_seconds=30)
        if job is None:
            return False
        token = job["lease_token"]
        try:
            payload = job["payload"]
            deadline = payload.get("expires_at")
            if deadline is not None and deadline <= self.store.clock():
                self.queue.fail(bot_id, job["id"], token, "telegram.response_expired")
                return True
            method = job["kind"].split(".", 1)[1]
            until = self._reserve(bot_id, method, payload["params"])
            if until > self.store.clock():
                self.queue.defer(bot_id, job["id"], token, until)
                return True
            try:
                result = self.adapters[bot_id].call(method, payload["params"])
            except TelegramFailure as exc:
                if exc.code == "telegram.rate_limited" and exc.retry_in is not None:
                    self._block(bot_id, exc.retry_in)
                self.queue.fail(bot_id, job["id"], token, exc.code,
                                retry_in=exc.retry_in, uncertain=exc.uncertain)
            except Exception:
                # Do not retry an unexpected adapter error: the external action may have happened.
                self.queue.fail(bot_id, job["id"], token, "telegram.adapter_uncertain", uncertain=True)
            else:
                self.queue.complete(bot_id, job["id"], token, {"telegram": result})
        except LeaseLost:
            # A different worker or recovery pass now owns the record. Never send again here.
            return True
        return True
