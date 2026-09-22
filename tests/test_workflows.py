from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from gramrail import JobQueue, Store, WorkflowEngine, WorkflowSpec
from gramrail.errors import Conflict, InvalidInput, NotFound


def spec(version=1):
    return WorkflowSpec(name="review", version=version, initial="pending",
                        states={"pending": {"approve": "approved", "reject": "rejected"}, "approved": {}, "rejected": {}}, terminal=["approved", "rejected"])


def test_persisted_definition_and_progress(store):
    engine = WorkflowEngine(store)
    run = engine.start("demo", spec(), {"title": "one"}, dedupe_key="submission1")
    other = WorkflowEngine(Store(store.path, clock=store.clock))
    assert other.get("demo", run["id"])["definition"]["version"] == 1
    assert engine.start("demo", spec(), {"title": "one"}, dedupe_key="submission1")["id"] == run["id"]
    finished = other.signal("demo", run["id"], "approve", "decision1", expected_revision=0, patch={"by": 9})
    assert finished["state"] == "approved"
    assert finished["data"] == {"title": "one", "by": 9}
    assert finished["status"] == "completed"


def test_exact_signal_replay_returns_recorded_response(store):
    engine = WorkflowEngine(store)
    run = engine.start("demo", spec())
    first = engine.signal("demo", run["id"], "approve", "decision1", expected_revision=0)
    second = engine.signal("demo", run["id"], "approve", "decision1", expected_revision=0)
    assert first == second
    with pytest.raises(Conflict):
        engine.signal("demo", run["id"], "reject", "decision1", expected_revision=0)


def test_atomic_state_transition_and_job_creation(store):
    engine = WorkflowEngine(store)
    run = engine.start("demo", spec())
    jobs = [{"kind": "publish", "payload": {"id": run["id"]}}]
    engine.signal("demo", run["id"], "approve", "key", expected_revision=0, jobs=jobs)
    engine.signal("demo", run["id"], "approve", "key", expected_revision=0, jobs=jobs)
    assert len(JobQueue(store).list("demo")) == 1


def test_invalid_effect_rolls_back_the_transition(store):
    engine = WorkflowEngine(store)
    run = engine.start("demo", spec())
    with pytest.raises(InvalidInput):
        engine.signal("demo", run["id"], "approve", "key", expected_revision=0,
                      jobs=[{"kind": "work", "payload": {}}, {"kind": "bad kind", "payload": {}}])
    assert engine.get("demo", run["id"])["state"] == "pending"
    assert JobQueue(store).list("demo") == []


def test_simultaneous_decisions_have_one_winner(store):
    engine = WorkflowEngine(store)
    run = engine.start("demo", spec())

    def decide(index):
        try:
            engine.signal("demo", run["id"], "approve" if index % 2 else "reject", str(index), expected_revision=0)
            return True
        except Conflict:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(decide, range(20))) == 1
    assert engine.get("demo", run["id"])["revision"] == 1


def test_workflow_scope_and_changed_idempotency(store):
    engine = WorkflowEngine(store)
    run = engine.start("demo", spec(), dedupe_key="same")
    with pytest.raises(NotFound):
        engine.signal("other", run["id"], "approve", "x", expected_revision=0)
    with pytest.raises(Conflict):
        engine.start("demo", spec(2), dedupe_key="same")
    with pytest.raises(NotFound):
        engine.get("other", run["id"])


@pytest.mark.parametrize("body", [
    {"name": "x", "version": 1, "initial": "missing", "states": {"a": {}}},
    {"name": "x", "version": 1, "initial": "a", "states": {"a": {"next": "missing"}}},
    {"name": "x", "version": 1, "initial": "a", "states": {"a": {"again": "a"}}, "terminal": ["a"]},
])
def test_invalid_definitions(body):
    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(body)
