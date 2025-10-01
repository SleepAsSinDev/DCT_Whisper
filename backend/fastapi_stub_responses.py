"""Minimal response types for FastAPI stubs."""
from __future__ import annotations

from typing import Any


class JSONResponse:
    def __init__(self, content: Any, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def json(self) -> Any:
        return self.content
