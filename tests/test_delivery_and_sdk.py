import httpx
import pytest

from gramrail.adapters.bot_api import BotAPI, FakeBotAPI, TelegramFailure
from gramrail.client import APIError, Client
from gramrail.delivery import Delivery
from gramrail.jobs import JobQueue


def test_fake_delivery_records_no_network_call(store):
    fake = FakeBotAPI()
    delivery = Delivery(store, {"demo": fake})
    item = delivery.send_text("demo", 1, "Hello", dedupe_key="first")
    assert delivery.tick("demo")
    assert fake.calls == [("sendMessage", {"chat_id": 1, "text": "Hello"})]
    assert delivery.queue.get("demo", item["id"])["result"]["telegram"]["simulated"]


def test_shared_chat_throttling_survives_adapter_recreation(store, clock):
    fake = FakeBotAPI()
    first = Delivery(store, {"demo": fake})
    first.send_text("demo", 1, "One")
    first.send_text("demo", 1, "Two")
    first.tick("demo")
    Delivery(store, {"demo": fake}).tick("demo")
    assert len(fake.calls) == 1
    clock.advance(1.1)
    assert first.tick("demo")
    assert len(fake.calls) == 2


def test_rate_limit_schedules_retry_and_shared_cooldown(store, clock):
    calls = []

    def endpoint(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, json={"ok": False, "error_code": 429, "parameters": {"retry_after": 10}})
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    adapter = BotAPI("123:fake", httpx.Client(transport=httpx.MockTransport(endpoint)))
    delivery = Delivery(store, {"demo": adapter})
    job = delivery.send_text("demo", 1, "Hello")
    delivery.tick("demo")
    assert delivery.queue.get("demo", job["id"])["state"] == "queued"
    clock.advance(5)
    assert not delivery.tick("demo")
    clock.advance(6)
    delivery.tick("demo")
    assert len(calls) == 2
    assert delivery.queue.get("demo", job["id"])["state"] == "succeeded"


@pytest.mark.parametrize("kind", ["read_timeout", "server_error", "bad_json"])
def test_ambiguous_network_results_stop_automatic_resending(store, kind):
    def endpoint(request):
        if kind == "read_timeout":
            raise httpx.ReadTimeout("connection lost", request=request)
        if kind == "server_error":
            return httpx.Response(503)
        return httpx.Response(200, text="not json")
    adapter = BotAPI("123:fake", httpx.Client(transport=httpx.MockTransport(endpoint)))
    delivery = Delivery(store, {"demo": adapter})
    job = delivery.send_text("demo", 1, "Hello")
    delivery.tick("demo")
    assert delivery.queue.get("demo", job["id"])["state"] == "uncertain"
    assert not delivery.tick("demo")


def test_permanent_telegram_failure_is_not_retried(store):
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, json={"ok": False, "error_code": 403, "description": "Forbidden"})))
    delivery = Delivery(store, {"demo": BotAPI("123:fake", http)})
    job = delivery.send_text("demo", 1, "Hello")
    delivery.tick("demo")
    assert delivery.queue.get("demo", job["id"])["state"] == "failed"


def test_expired_callback_answer_is_not_sent(store, clock):
    fake = FakeBotAPI()
    delivery = Delivery(store, {"demo": fake})
    item = delivery.queue.enqueue("demo", "telegram.answerCallbackQuery", {"params": {"callback_query_id": "q"}, "expires_at": clock() - 1}, recovery="uncertain")
    delivery.tick("demo")
    assert fake.calls == []
    assert delivery.queue.get("demo", item["id"])["error"] == "telegram.response_expired"


def test_python_sdk_envelope_and_authentication():
    calls = []

    def endpoint(request):
        calls.append(request)
        return httpx.Response(202, json={"id": "one", "state": "queued"})
    with Client("http://127.0.0.1:8080", "a" * 32, "my-bot", http=httpx.Client(transport=httpx.MockTransport(endpoint))) as client:
        assert client.enqueue("work", {"x": 1}, dedupe_key="key")["id"] == "one"
    assert calls[0].headers["Authorization"] == "Bearer " + "a" * 32
    assert calls[0].url.path == "/api/v1/bots/my-bot/jobs"


def test_python_sdk_preserves_api_errors():
    http = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(409, json={"error": {"code": "conflict", "message": "Already changed"}})))
    client = Client("https://runtime.example.com", "key", "demo", http=http)
    with pytest.raises(APIError) as failure:
        client.get_job("one")
    assert failure.value.code == "conflict"
    assert failure.value.status == 409


@pytest.mark.parametrize("url", ["http://external.example", "file:///etc/passwd", "https://key:secret@example.com", "https://example.com?key=secret", "https://example.com#fragment"])
def test_sdk_rejects_unsafe_base_urls(url):
    with pytest.raises(ValueError):
        Client(url, "key", "demo")


@pytest.mark.parametrize("bot_id", ["..", ".", "demo/../other", "demo?x=y"])
def test_python_sdk_rejects_unsafe_bot_ids(bot_id):
    from gramrail.client import Client
    with pytest.raises(ValueError):
        Client("http://127.0.0.1:8080", "test-key", bot_id)


def test_python_sdk_never_follows_redirects_in_injected_client():
    from gramrail.client import APIError, Client
    seen = []
    def transport(request):
        seen.append(request.url)
        return httpx.Response(307, headers={"Location": "https://other.example/collect"})
    with httpx.Client(transport=httpx.MockTransport(transport), follow_redirects=True) as http:
        with Client("http://127.0.0.1:8080", "test-key", "demo", http=http) as client:
            with pytest.raises(APIError):
                client.get_job("job-one")
    assert len(seen) == 1


def test_python_sdk_rejects_path_escape():
    from gramrail.client import Client
    with Client("http://127.0.0.1:8080", "test-key", "demo") as client:
        with pytest.raises(ValueError):
            client.request("GET", "/../../../health")
