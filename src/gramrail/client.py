"""Small Python HTTP SDK; works without replacing the caller's bot framework."""
import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


class Client:
    def __init__(self, base_url: str, api_key: str, bot_id: str, *,
                 http: httpx.Client | None = None):
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("Provide an http(s) runtime URL without credentials, query, or fragment.")
        if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Non-local runtime connections require HTTPS.")
        if not api_key or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", bot_id):
            raise ValueError("Provide an API key and a valid bot slug.")
        self.base_url = base_url.rstrip("/") + "/api/v1/bots/" + quote(bot_id, safe="")
        self.api_key = api_key
        self.http = http or httpx.Client(timeout=15, follow_redirects=False)
        self._owns_http = http is None

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        if not re.fullmatch(r"/[A-Za-z0-9_/-]+", path) or any(segment in (".", "..") for segment in path.split("/")):
            raise ValueError("Provide a relative API resource path without query or dot segments.")
        response = self.http.request(method, self.base_url + path,
                                     headers={"Authorization": "Bearer " + self.api_key}, json=body,
                                     follow_redirects=False)
        if not response.is_success:
            try:
                envelope = response.json()
                error = envelope.get("error", {}) if isinstance(envelope, dict) else {}
                if not isinstance(error, dict):
                    error = {}
            except ValueError:
                error = {}
            raise APIError(response.status_code, error.get("code", "http_error"),
                           error.get("message", "GramRail request failed."))
        return response.json()

    def enqueue(self, kind: str, payload: dict[str, Any], **options: Any) -> dict[str, Any]:
        return self.request("POST", "/jobs", {"kind": kind, "payload": payload, **options})

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.request("GET", "/jobs/" + quote(job_id, safe=""))

    def claim(self, kinds: list[str], lease_seconds: float = 30) -> dict[str, Any] | None:
        return self.request("POST", "/jobs/claim", {"kinds": kinds, "lease_seconds": lease_seconds})

    def complete(self, job_id: str, lease_token: str, result: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/jobs/" + quote(job_id, safe="") + "/complete",
                            {"lease_token": lease_token, "result": result})

    def fail(self, job_id: str, lease_token: str, error: str, **options: Any) -> dict[str, Any]:
        return self.request("POST", "/jobs/" + quote(job_id, safe="") + "/fail",
                            {"lease_token": lease_token, "error": error, **options})

    def heartbeat(self, job_id: str, lease_token: str, **options: Any) -> dict[str, Any]:
        return self.request("POST", "/jobs/" + quote(job_id, safe="") + "/heartbeat",
                            {"lease_token": lease_token, **options})

    def send_text(self, chat_id: int, text: str, **options: Any) -> dict[str, Any]:
        return self.request("POST", "/messages", {"chat_id": chat_id, "text": text, **options})

    def ingest(self, update: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/updates", update)
