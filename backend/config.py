"""Application configuration helpers without external dependencies."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal


def _get_env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    port: int = 8080
    whisper_api_base: str = "https://api.whisper-api.com"
    whisper_api_key: str = "sk-live-example-1234567890"
    firebase_project_id: str = "demo-whisper-th"
    limiter_backend: Literal["memory", "redis"] = "memory"
    redis_url: str | None = "redis://redis:6379/0"
    max_file_mb: int = 200
    max_clip_min: int = 90
    rpm_per_user: int = 30
    rpm_per_tenant: int = 120
    concurrent_user: int = 1
    concurrent_tenant: int = 5
    minutes_per_day: int = 120
    minutes_per_month: int = 0
    default_model: str = "large-v3"
    allow_diarization: bool = False

    def __post_init__(self) -> None:
        self.port = _get_int("PORT", self.port)
        self.whisper_api_base = _get_env("WHISPER_API_BASE", self.whisper_api_base)
        self.whisper_api_key = _get_env("WHISPER_API_KEY", self.whisper_api_key)
        self.firebase_project_id = _get_env("FIREBASE_PROJECT_ID", self.firebase_project_id)
        self.limiter_backend = _get_env("LIMITER_BACKEND", self.limiter_backend)
        self.redis_url = os.getenv("REDIS_URL", self.redis_url)
        self.max_file_mb = _get_int("MAX_FILE_MB", self.max_file_mb)
        self.max_clip_min = _get_int("MAX_CLIP_MIN", self.max_clip_min)
        self.rpm_per_user = _get_int("RPM_PER_USER", self.rpm_per_user)
        self.rpm_per_tenant = _get_int("RPM_PER_TENANT", self.rpm_per_tenant)
        self.concurrent_user = _get_int("CONCURRENT_USER", self.concurrent_user)
        self.concurrent_tenant = _get_int("CONCURRENT_TENANT", self.concurrent_tenant)
        self.minutes_per_day = _get_int("MINUTES_PER_DAY", self.minutes_per_day)
        self.minutes_per_month = _get_int("MINUTES_PER_MONTH", self.minutes_per_month)
        self.default_model = _get_env("DEFAULT_MODEL", self.default_model)
        self.allow_diarization = _get_bool("ALLOW_DIARIZATION", self.allow_diarization)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
