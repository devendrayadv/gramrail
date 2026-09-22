from concurrent.futures import ThreadPoolExecutor

import pytest

from gramrail import JobQueue, Store
from gramrail.errors import Conflict, InvalidInput, LeaseLost, NotFound


def test_jobs_survive_a_new_store(store):
    first = JobQueue(store).enqueue("demo", "reports.generate", {"file": "reference"}, dedupe_key="order-1")
    other = JobQueue(Store(store.path, clock=store.clock))
    assert other.get("demo", first["id"])["payload"] == {"file": "reference"}
    assert other.enqueue("demo", "reports.generate", {"file": "reference"}, dedupe_key="order-1")["id"] == first["id"]


def test_deduplication_is_bot_scoped(store):
    queue = JobQueue(store)
    a = queue.enqueue("demo", "work", {}, dedupe_key="same")
    b = queue.enqueue("other", "work", {}, dedupe_key="same")
    assert a["id"] != b["id"]
    with pytest.raises(NotFound):
        queue.get("other", a["id"])


def test_idempotency_rejects_changed_intent(store):
    queue = JobQueue(store)
    queue.enqueue("demo", "work", {"a": 1}, dedupe_key="key")
    with pytest.raises(Conflict):
        queue.enqueue("demo", "work", {"a": 2}, dedupe_key="key")
    assert len(queue.list("demo")) == 1


def test_claim_priority_due_time_and_kind(store, clock):
    queue = JobQueue(store)
    low = queue.enqueue("demo", "work", {}, priority=5)
    high = queue.enqueue("demo", "work", {}, priority=90)
    future = queue.enqueue("demo", "work", {}, priority=100, run_after=clock() + 20)
    queue.enqueue("demo", "unrelated", {}, priority=100)
    assert queue.claim("demo", ["work"])["id"] == high["id"]
    assert queue.claim("demo", ["work"])["id"] == low["id"]
    assert queue.claim("demo", ["work"]) is None
    clock.advance(20)
    assert queue.claim("demo", ["work"])["id"] == future["id"]


def test_concurrent_workers_never_share_a_live_claim(store):
    queue = JobQueue(store)
    for index in range(20):
        queue.enqueue("demo", "work", {"i": index})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: queue.claim("demo", ["work"]), range(30)))
    claimed = [item for item in results if item]
    assert len(claimed) == len({item["id"] for item in claimed}) == 20
    assert len({item["lease_token"] for item in claimed}) == 20


def test_expired_worker_cannot_complete_reclaimed_job(store, clock):
    queue = JobQueue(store)
    item = queue.enqueue("demo", "work", {})
    old = queue.claim("demo", ["work"], 5)
    clock.advance(6)
    current = queue.claim("demo", ["work"], 5)
    assert current["id"] == item["id"]
    assert current["attempts"] == 2
    with pytest.raises(LeaseLost):
        queue.complete("demo", item["id"], old["lease_token"], {})
    queue.complete("demo", item["id"], current["lease_token"], {"done": True})
    assert queue.get("demo", item["id"])["state"] == "succeeded"


def test_expired_lease_is_invalid_even_before_recovery(store, clock):
    queue = JobQueue(store)
    queue.enqueue("demo", "work", {})
    item = queue.claim("demo", ["work"], 5)
    clock.advance(5)
    with pytest.raises(LeaseLost):
        queue.complete("demo", item["id"], item["lease_token"])


def test_heartbeat_extends_owned_lease(store, clock):
    queue = JobQueue(store)
    queue.enqueue("demo", "work", {})
    item = queue.claim("demo", ["work"], 5)
    clock.advance(4)
    updated = queue.heartbeat("demo", item["id"], item["lease_token"], lease_seconds=20, progress={"percent": 40})
    clock.advance(10)
    assert updated["progress"] == {"percent": 40}
    queue.complete("demo", item["id"], item["lease_token"])


def test_retry_budget_and_delay(store, clock):
    queue = JobQueue(store)
    queue.enqueue("demo", "work", {}, max_attempts=2)
    first = queue.claim("demo", ["work"])
    queued = queue.fail("demo", first["id"], first["lease_token"], "temporary", retry_in=10)
    assert queued["state"] == "queued"
    assert queue.claim("demo", ["work"]) is None
    clock.advance(10)
    last = queue.claim("demo", ["work"])
    failed = queue.fail("demo", last["id"], last["lease_token"], "temporary", retry_in=10)
    assert failed["state"] == "failed"


def test_ambiguous_send_is_not_automatically_retried(store, clock):
    queue = JobQueue(store)
    queue.enqueue("demo", "telegram.sendMessage", {}, recovery="uncertain")
    item = queue.claim("demo", ["telegram.sendMessage"], 5)
    clock.advance(6)
    assert queue.claim("demo", ["telegram.sendMessage"]) is None
    assert queue.get("demo", item["id"])["state"] == "uncertain"


def test_last_expired_attempt_fails(store, clock):
    queue = JobQueue(store)
    item = queue.enqueue("demo", "work", {}, max_attempts=1)
    queue.claim("demo", ["work"], 5)
    clock.advance(6)
    assert queue.claim("demo", ["work"]) is None
    assert queue.get("demo", item["id"])["state"] == "failed"


def test_cancel_only_queued_jobs(store):
    queue = JobQueue(store)
    one = queue.enqueue("demo", "work", {})
    assert queue.cancel("demo", one["id"])["state"] == "cancelled"
    assert queue.cancel("demo", one["id"])["state"] == "cancelled"
    queue.enqueue("demo", "work", {})
    running = queue.claim("demo", ["work"])
    with pytest.raises(Conflict):
        queue.cancel("demo", running["id"])


@pytest.mark.parametrize("options", [{"priority": -1}, {"priority": 101}, {"max_attempts": 0},
                                      {"recovery": "magical"}, {"run_after": float("nan")}, {"dedupe_key": ""}])
def test_invalid_enqueue_options(store, options):
    with pytest.raises(InvalidInput):
        JobQueue(store).enqueue("demo", "work", {}, **options)


@pytest.mark.parametrize("kind", ["", "bad kind", "../shell", "x" * 101])
def test_rejects_bad_job_kinds(store, kind):
    with pytest.raises(InvalidInput):
        JobQueue(store).enqueue("demo", kind, {})


@pytest.mark.parametrize("lease", [0, 4, 3601, float("inf")])
def test_rejects_bad_leases(store, lease):
    with pytest.raises(InvalidInput):
        JobQueue(store).claim("demo", ["work"], lease)


def test_no_secrets_in_error_codes(store):
    queue = JobQueue(store)
    queue.enqueue("demo", "work", {})
    job = queue.claim("demo", ["work"])
    with pytest.raises(InvalidInput):
        queue.fail("demo", job["id"], job["lease_token"], "https://secret.example/token")


def test_no_non_finite_payloads(store):
    with pytest.raises(InvalidInput):
        JobQueue(store).enqueue("demo", "work", {"bad": float("nan")})


def test_defer_does_not_consume_an_attempt(store, clock):
    queue = JobQueue(store)
    queue.enqueue("demo", "work", {})
    job = queue.claim("demo", ["work"])
    queue.defer("demo", job["id"], job["lease_token"], clock() + 5)
    assert queue.get("demo", job["id"])["attempts"] == 0
