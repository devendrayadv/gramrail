"""Outbound Telegram Bot API adapter. Never logs token-bearing URLs."""
from typing import Any

import httpx


class TelegramFailure(Exception):
    def __init__(self, code: str, *, retry_in: float | None = None, uncertain: bool = False):
        super().__init__(code)
        self.code = code
        self.retry_in = retry_in
        self.uncertain = uncertain


class BotAPI:
    def __init__(self, token: str, client: httpx.Client | None = None):
        self.token = token
        self.client = client or httpx.Client(timeout=10, follow_redirects=False)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def call(self, method: str, params: dict[str, Any], timeout: float = 10) -> Any:
        try:
            response = self.client.post(f"https://api.telegram.org/bot{self.token}/{method}",
                                        json=params, timeout=timeout)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise TelegramFailure("telegram.connect_failed", retry_in=5) from exc
        except httpx.HTTPError as exc:
            raise TelegramFailure("telegram.network_uncertain", uncertain=True) from exc
        if response.status_code >= 500 or 300 <= response.status_code < 400:
            raise TelegramFailure("telegram.http_uncertain", uncertain=True)
        try:
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
                raise ValueError("Invalid envelope")
        except (ValueError, TypeError) as exc:
            raise TelegramFailure("telegram.invalid_response", uncertain=True) from exc
        if data["ok"]:
            return data.get("result")
        code = data.get("error_code", response.status_code)
        if code == 429:
            retry = data.get("parameters", {}).get("retry_after", 5)
            if not isinstance(retry, (float, int)) or not 0 <= retry <= 604800:
                raise TelegramFailure("telegram.invalid_retry_after")
            raise TelegramFailure("telegram.rate_limited", retry_in=float(retry) + 1)
        raise TelegramFailure(f"telegram.rejected_{code}" if isinstance(code, int) else "telegram.rejected")


class FakeBotAPI:
    """Offline substitute. Only the runtime result records simulated calls."""
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, method: str, params: dict[str, Any], timeout: float = 10) -> Any:
        self.calls.append((method, params))
        return {"simulated": True, "method": method, "params": params, "message_id": len(self.calls)}

    def close(self) -> None:
        pass
