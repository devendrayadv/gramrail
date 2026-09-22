from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gramrail.api import create_app
from gramrail.config import Config, starter
from gramrail.store import Store


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return Store(tmp_path / "runtime.sqlite", clock=clock)


@pytest.fixture
def config(tmp_path):
    value = starter("demo")
    other = starter("other")["bots"][0]
    other.update(token_env="OTHER_TOKEN", webhook_secret_env="OTHER_WEBHOOK", api_key_env="OTHER_KEY")
    value["bots"].append(other)
    value["database"] = str(tmp_path / "runtime.sqlite")
    return Config.model_validate(value)


@pytest.fixture
def credentials():
    return {"GRAMRAIL_ADMIN_KEY": "a" * 32, "GRAMRAIL_BOT_KEY": "b" * 32, "OTHER_KEY": "c" * 32}


@pytest.fixture
def app(config, store, credentials):
    return create_app(config, store=store, credentials=credentials, background=False)


@pytest.fixture
def client(app):
    with TestClient(app) as value:
        yield value


@pytest.fixture
def auth():
    return {"Authorization": "Bearer " + "b" * 32}


def message(update_id, text, user=1001, chat=None):
    return {"update_id": update_id, "message": {"message_id": update_id,
            "from": {"id": user, "is_bot": False}, "chat": {"id": chat or user, "type": "private"}, "text": text}}
