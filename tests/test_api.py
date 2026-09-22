import json

import pytest
from fastapi.testclient import TestClient

from gramrail.api import create_app
from gramrail.errors import InvalidInput
from conftest import message

BASE = "/api/v1/bots/demo"


def test_health_has_no_secrets(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "simulation"
    assert "key" not in response.text


def test_authentication_and_scope(client, auth):
    assert client.get("/api/v1/bots").status_code == 403
    assert client.get("/api/v1/bots", headers={"Authorization": "Bearer invalid"}).status_code == 403
    assert [bot["id"] for bot in client.get("/api/v1/bots", headers=auth).json()["bots"]] == ["demo"]
    assert client.get("/api/v1/bots/other/jobs", headers=auth).status_code == 403
    assert len(client.get("/api/v1/bots", headers={"Authorization": "Bearer " + "a" * 32}).json()["bots"]) == 2


@pytest.mark.parametrize("path", ["jobs", "workflows", "events"])
def test_reads_cannot_cross_bot_boundary(client, auth, path):
    assert client.get("/api/v1/bots/other/" + path, headers=auth).status_code == 403


def test_http_job_lifecycle_and_hidden_lease(client, auth):
    first = client.post(BASE + "/jobs", headers=auth, json={"kind": "report", "payload": {"x": 1}, "dedupe_key": "one"})
    assert first.status_code == 202
    job_id = first.json()["id"]
    claim = client.post(BASE + "/jobs/claim", headers=auth, json={"kinds": ["report"]}).json()
    assert claim["id"] == job_id
    assert "lease_token" in claim
    assert "lease_token" not in client.get(BASE + "/jobs/" + job_id, headers=auth).json()
    token = claim["lease_token"]
    assert client.post(BASE + f"/jobs/{job_id}/heartbeat", headers=auth, json={"lease_token": token, "progress": {"done": 1}}).status_code == 200
    response = client.post(BASE + f"/jobs/{job_id}/complete", headers=auth, json={"lease_token": token, "result": {"ok": True}})
    assert response.json()["state"] == "succeeded"
    assert client.post(BASE + f"/jobs/{job_id}/complete", headers=auth, json={"lease_token": token}).status_code == 409


def test_update_and_message_api(client, auth):
    assert client.post(BASE + "/updates", headers=auth, json=message(1, "/start")).status_code == 200
    queued = client.post(BASE + "/messages", headers=auth, json={"chat_id": 1001, "text": "Hello", "dedupe_key": "hello"})
    assert queued.status_code == 202
    assert queued.json()["kind"] == "telegram.sendMessage"
    assert queued.json()["recovery"] == "uncertain"


@pytest.mark.parametrize("body", [{"kind": "telegram.sendMessage", "payload": {}}, {"kind": "gramrail.internal", "payload": {}}])
def test_generic_api_cannot_impersonate_delivery(client, auth, body):
    assert client.post(BASE + "/jobs", headers=auth, json=body).status_code == 403
    assert client.post(BASE + "/jobs/claim", headers=auth, json={"kinds": [body["kind"]]}).status_code == 403


def test_error_schema_does_not_echo_input(client, auth):
    response = client.post(BASE + "/messages", headers=auth, json={"chat_id": "secret-value", "text": "Hello"})
    assert response.status_code == 422
    assert "secret-value" not in response.text
    assert response.json()["error"]["code"] == "validation_error"


def test_request_size_limit(client, auth):
    response = client.post(BASE + "/updates", headers=auth, content=json.dumps({"update_id": 1, "padding": "x" * 300000}))
    assert response.status_code == 413


def test_webhook_disabled_in_simulation(client):
    assert client.post("/webhooks/demo", json=message(1, "/start")).status_code == 403


def test_webhook_auth_and_duplicate_handling(config, store, credentials, app):
    credentials["TELEGRAM_WEBHOOK_SECRET"] = "s" * 32
    real = create_app(config, store=store, live=True, background=False,
                      credentials=credentials, adapters=app.state.delivery.adapters)
    with TestClient(real) as client:
        assert client.post("/webhooks/demo", json=message(1, "/start")).status_code == 403
        headers = {"X-Telegram-Bot-Api-Secret-Token": "s" * 32}
        first = client.post("/webhooks/demo", json=message(1, "/start"), headers=headers)
        assert first.status_code == 200
        assert not first.json()["duplicate"]
        assert client.post("/webhooks/demo", json=message(1, "/start"), headers=headers).json()["duplicate"]


def test_workflow_api_with_transactional_effect(client, auth):
    response = client.post(BASE + "/workflows", headers=auth, json={
        "definition": {"name": "flow", "version": 1, "initial": "pending", "states": {"pending": {"go": "done"}, "done": {}}, "terminal": ["done"]},
        "data": {"x": 1}})
    assert response.status_code == 201
    run_id = response.json()["id"]
    body = {"event": "go", "event_key": "one", "expected_revision": 0,
            "jobs": [{"kind": "report", "payload": {"x": 1}}]}
    assert client.post(BASE + f"/workflows/{run_id}/signals", headers=auth, json=body).json()["status"] == "completed"
    assert len(client.get(BASE + "/jobs", headers=auth).json()) == 1
    assert client.post(BASE + f"/workflows/{run_id}/signals", headers=auth, json=body).status_code == 200
    assert len(client.get(BASE + "/jobs", headers=auth).json()) == 1


def test_console_assets_and_security_headers(client):
    assert client.get("/console").status_code == 200
    assert "frame-ancestors 'none'" in client.get("/console").headers["Content-Security-Policy"]
    assert client.get("/console/app.js").status_code == 200
    assert client.get("/console/style.css").status_code == 200
    assert client.get("/console/not-allowed").status_code == 422
    assert client.get("/health").headers["Cache-Control"] == "no-store"


def test_openapi_contract_generated(client):
    schema = client.get("/openapi.json").json()
    assert "/api/v1/bots/{bot_id}/jobs/claim" in schema["paths"]
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"


def test_distinct_keys_required(config, store):
    with pytest.raises(InvalidInput):
        create_app(config, store=store, credentials={"GRAMRAIL_ADMIN_KEY": "a" * 32, "GRAMRAIL_BOT_KEY": "a" * 32})


def test_text_unicode_limit(client, auth):
    response = client.post(BASE + "/messages", headers=auth, json={"chat_id": 1, "text": "\U0001f642" * 3000})
    assert response.status_code == 400
