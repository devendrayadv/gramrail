from concurrent.futures import ThreadPoolExecutor

import pytest

from gramrail import JobQueue, WorkflowEngine
from gramrail.errors import Conflict, InvalidInput
from gramrail.modules.forms import FormField, Forms, FormSpec
from gramrail.telegram import TelegramRouter
from conftest import message


def finish(router, bot="demo", user=1001, start=1):
    for number, text in enumerate(["/submit", "Example bot", "https://example.com"], start):
        router.ingest(bot, message(number, text, user))
    return WorkflowEngine(router.store).list(bot)[0]


def test_full_submission_and_authorized_approval(store, config):
    router = TelegramRouter(store, config)
    run = finish(router)
    router.ingest("demo", {"update_id": 4, "callback_query": {"id": "cb1", "from": {"id": 1}, "data": "gr:a:" + run["id"]}})
    result = WorkflowEngine(store).get("demo", run["id"])
    assert result["state"] == "approved"
    assert result["data"]["decided_by"] == 1
    jobs = JobQueue(store).list("demo", limit=100)
    assert any("was approved" in job["payload"]["params"].get("text", "") for job in jobs)
    assert all(job["recovery"] == "uncertain" for job in jobs)


def test_duplicate_update_creates_no_extra_effect(store, config):
    router = TelegramRouter(store, config)
    first = router.ingest("demo", message(1, "/start"))
    second = router.ingest("demo", message(1, "/start"))
    assert first["duplicate"] is False and second["duplicate"] is True
    assert len(JobQueue(store).list("demo")) == 1
    with pytest.raises(Conflict):
        router.ingest("demo", message(1, "/submit"))


def test_untrusted_admin_click_and_cross_bot_reference(store, config):
    router = TelegramRouter(store, config)
    run = finish(router)
    router.ingest("demo", {"update_id": 4, "callback_query": {"id": "cb1", "from": {"id": 222}, "data": "gr:a:" + run["id"]}})
    router.ingest("other", {"update_id": 5, "callback_query": {"id": "cb2", "from": {"id": 1}, "data": "gr:a:" + run["id"]}})
    assert WorkflowEngine(store).get("demo", run["id"])["state"] == "pending"


def test_two_reviewers_cannot_apply_two_decisions(store, config):
    config.bots[0].admin_ids = [1, 2]
    router = TelegramRouter(store, config)
    run = finish(router)
    callbacks = [{"update_id": index + 10, "callback_query": {"id": str(index), "from": {"id": index},
                  "data": ("gr:a:" if index == 1 else "gr:r:") + run["id"]}} for index in (1, 2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda raw: router.ingest("demo", raw), callbacks))
    assert WorkflowEngine(store).get("demo", run["id"])["revision"] == 1
    notices = [job for job in JobQueue(store).list("demo", limit=100) if job["payload"]["params"].get("text", "").startswith("Your submission was")]
    assert len(notices) == 1


def test_ingress_transaction_rolls_back_all_effects(store, config, monkeypatch):
    router = TelegramRouter(store, config)

    def broken(conn, bot, update, effects):
        router.jobs._enqueue(conn, bot.id, "test", {})
        raise RuntimeError("test failure")
    monkeypatch.setattr(router, "_message", broken)
    with pytest.raises(RuntimeError):
        router.ingest("demo", message(1, "/start"))
    with store.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM updates").fetchone()[0] == 0
    assert JobQueue(store).list("demo") == []


def test_same_chat_users_and_bots_are_isolated(store, config):
    router = TelegramRouter(store, config)
    router.ingest("demo", message(1, "/submit", user=10, chat=-100))
    router.ingest("demo", message(2, "/submit", user=11, chat=-100))
    router.ingest("demo", message(3, "First user's title", user=10, chat=-100))
    forms = Forms(store)
    assert forms.get("demo", -100, 10)["step"] == 1
    assert forms.get("demo", -100, 11)["step"] == 0
    assert forms.get("other", -100, 10) is None


def test_forms_pin_definition_back_cancel_and_expiry(store, config, clock):
    forms = Forms(store)
    spec = config.bots[0].forms[0]
    current = forms.start("demo", 10, 10, spec)
    spec.fields[0].prompt = "New prompt only for new sessions"
    assert forms.get("demo", 10, 10)["prompt"] == "What is its title?"
    current = forms.answer("demo", 10, 10, "Title", current["revision"])
    current = forms.answer("demo", 10, 10, "/back", current["revision"])
    assert current["answers"] == {}
    assert forms.answer("demo", 10, 10, "/cancel", current["revision"])["state"] == "cancelled"
    current = forms.start("demo", 10, 10, spec)
    clock.advance(spec.expires_in + 1)
    assert forms.answer("demo", 10, 10, "too late", current["revision"])["state"] == "expired"


def test_form_revision_and_active_start_protection(store, config):
    forms = Forms(store)
    first = forms.start("demo", 1, 1, config.bots[0].forms[0])
    with pytest.raises(Conflict):
        forms.start("demo", 1, 1, config.bots[0].forms[0])
    forms.answer("demo", 1, 1, "Title", first["revision"])
    with pytest.raises(Conflict):
        forms.answer("demo", 1, 1, "https://example.com", first["revision"])


@pytest.mark.parametrize("kind,value", [("integer", "abc"), ("integer", str(2**55)), ("url", "not-a-url"),
                                         ("url", "https://user:pass@example.com"), ("url", "ftp://example.com"), ("choice", "unknown")])
def test_field_validation(kind, value):
    field = FormField(name="test", prompt="Question", kind=kind, choices=["one", "two"] if kind == "choice" else [])
    with pytest.raises(InvalidInput):
        field.parse(value)


def test_integer_and_choice_success():
    assert FormField(name="n", prompt="Number", kind="integer").parse("42") == 42
    assert FormField(name="c", prompt="Choice", kind="choice", choices=["a"]).parse("a") == "a"


def test_unknown_types_are_accepted_without_false_effects(store, config):
    result = TelegramRouter(store, config).ingest("demo", {"update_id": 1, "channel_post": {"text": "ignored"}})
    assert result["effects"] == 0


@pytest.mark.parametrize("raw", [{}, {"update_id": True}, {"update_id": -1}, {"update_id": 1, "message": {"text": "bad"}}])
def test_malformed_updates(store, config, raw):
    with pytest.raises(InvalidInput):
        TelegramRouter(store, config).ingest("demo", raw)
