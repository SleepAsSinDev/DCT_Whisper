"""Testing helpers for mocking Whisper API responses."""
from __future__ import annotations

from typing import Any

from backend import main


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int, method: str) -> None:
        self._payload = payload
        self.status_code = status_code
        self._method = method
        self._request = getattr(main, "httpx", None)

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            httpx_module = getattr(main, "httpx", None)
            if httpx_module and hasattr(httpx_module, "HTTPStatusError"):
                raise httpx_module.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]
            raise RuntimeError("HTTP error")


def build_response(payload: dict[str, Any], status_code: int = 200, method: str = "POST") -> _FakeResponse:
    return _FakeResponse(payload, status_code, method)
