import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import InvalidInput
from .modules.forms import FormSpec
from .modules.manifest import resolve

ENV = r"^[A-Z][A-Z0-9_]{0,99}$"


class BotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    name: str = Field(default="My bot", min_length=1, max_length=100)
    token_env: str = Field(default="TELEGRAM_BOT_TOKEN", pattern=ENV)
    webhook_secret_env: str = Field(default="TELEGRAM_WEBHOOK_SECRET", pattern=ENV)
    api_key_env: str = Field(default="GRAMRAIL_BOT_KEY", pattern=ENV)
    admin_ids: list[int] = Field(default_factory=list, max_length=100)
    review_chat_id: int | None = None
    modules: list[str] = Field(default_factory=lambda: ["forms"])
    forms: list[FormSpec] = Field(default_factory=list, max_length=20)
    welcome: str = Field(default="Welcome. Use /submit to begin, /back to go back, or /cancel to stop.", max_length=4000)

    @model_validator(mode="after")
    def valid_bot(self) -> "BotConfig":
        self.modules = [module.name for module in resolve(self.modules)]
        if "forms" in self.modules and not self.forms:
            raise ValueError("The forms module needs at least one form definition.")
        if len({form.name for form in self.forms}) != len(self.forms):
            raise ValueError("Form names must be unique within a bot.")
        if "approvals" in self.modules and (not self.admin_ids or self.review_chat_id is None):
            raise ValueError("Approvals requires admin_ids and review_chat_id.")
        if any(user <= 0 or user > 2**53 - 1 for user in self.admin_ids):
            raise ValueError("Admin IDs must be positive Telegram user IDs.")
        return self


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database: str = ".gramrail/gramrail.sqlite"
    admin_key_env: str = Field(default="GRAMRAIL_ADMIN_KEY", pattern=ENV)
    bots: list[BotConfig] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_bots(self) -> "Config":
        if len({bot.id for bot in self.bots}) != len(self.bots):
            raise ValueError("Bot IDs must be unique.")
        env_names = [self.admin_key_env] + [bot.api_key_env for bot in self.bots]
        if len(set(env_names)) != len(env_names):
            raise ValueError("Each bot needs a separate API-key environment variable.")
        return self

    def bot(self, bot_id: str) -> BotConfig:
        from .errors import NotFound
        for bot in self.bots:
            if bot.id == bot_id:
                return bot
        raise NotFound("Unknown bot.")

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        location = Path(path).expanduser().resolve()
        value = cls.model_validate_json(location.read_text())
        value.database = str((location.parent / value.database).resolve())
        return value

    def credentials(self, live: bool = False) -> dict[str, str]:
        names = [self.admin_key_env] + [bot.api_key_env for bot in self.bots]
        secrets: dict[str, str] = {}
        for name in names:
            value = os.environ.get(name, "")
            if value:
                if not re.fullmatch(r"[!-~]{24,256}", value):
                    raise InvalidInput(f"{name} must contain 24..256 printable non-space ASCII characters.")
                if value in secrets.values():
                    raise InvalidInput("API keys must be different for every bot and administrator.")
                secrets[name] = value
        if not secrets:
            raise InvalidInput(f"Set {self.admin_key_env} or a bot API key before starting the API.")
        if live:
            for bot in self.bots:
                token = os.environ.get(bot.token_env, "")
                webhook = os.environ.get(bot.webhook_secret_env, "")
                if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{20,}", token):
                    raise InvalidInput(f"Set a valid bot token in {bot.token_env}.")
                if not re.fullmatch(r"[A-Za-z0-9_-]{24,256}", webhook):
                    raise InvalidInput(f"Set {bot.webhook_secret_env} to a 24..256 character webhook secret.")
                secrets[bot.token_env] = token
                secrets[bot.webhook_secret_env] = webhook
        return secrets


def starter(name: str = "my-bot") -> dict[str, Any]:
    return {
        "database": ".gramrail/gramrail.sqlite",
        "bots": [{"id": name, "name": name, "modules": ["forms", "approvals"],
                  "admin_ids": [1], "review_chat_id": 1,
                  "forms": [{"name": "submission", "title": "New submission",
                             "fields": [{"name": "title", "prompt": "What is its title?"},
                                        {"name": "url", "prompt": "What is its URL?", "kind": "url"}]}]}],
    }


def save(config: dict[str, Any], path: Path) -> None:
    Config.model_validate(config)
    path.write_text(json.dumps(config, indent=2) + "\n")
