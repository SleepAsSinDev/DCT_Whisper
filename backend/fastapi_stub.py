"""Minimal FastAPI-compatible stubs for offline testing."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any | None = None) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class Depends:  # pragma: no cover - placeholder
    def __init__(self, dependency: Callable[..., Any]) -> None:
        self.dependency = dependency


def File(default: Any = None) -> Any:  # pragma: no cover - placeholder
    return default


def Form(default: Any = None) -> Any:  # pragma: no cover - placeholder
    return default


def Header(default: Any = None, alias: str | None = None) -> Any:  # pragma: no cover
    return default


class Request:  # pragma: no cover - minimal request stub
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


class UploadFile:
    def __init__(self, filename: str, content: bytes, content_type: str | None = None) -> None:
        self.filename = filename
        self.content_type = content_type
        self._buffer = BytesIO(content)

    async def read(self) -> bytes:
        return self._buffer.getvalue()


class _State:
    pass


class FastAPI:
    def __init__(self, *args, **kwargs) -> None:  # pragma: no cover
        self.routes: dict[tuple[str, str], Callable[..., Any]] = {}
        self.state = _State()

    def post(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.routes[("POST", path)] = func
            return func

        return decorator

    def get(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.routes[("GET", path)] = func
            return func

        return decorator

    def on_event(self, event: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator
