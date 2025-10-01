"""FastAPI application exposing Whisper proxy with Firebase auth and usage guards."""
from __future__ import annotations

import asyncio
import io
import math
import time
import uuid
from typing import Any, Dict

try:  # pragma: no cover - used for runtime, tests patch the client
    import httpx  # type: ignore
except ImportError:  # pragma: no cover - fallback for offline testing
    class _StubHTTPError(Exception):
        ...

    class _StubHTTPStatusError(_StubHTTPError):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args)

    class _StubAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            self._error = RuntimeError("httpx is required for network operations")

        async def post(self, *args, **kwargs):
            raise self._error

        async def get(self, *args, **kwargs):
            raise self._error

        async def aclose(self) -> None:
            return None

    class _StubHttpxModule:  # minimal interface for tests
        AsyncClient = _StubAsyncClient
        HTTPError = _StubHTTPError
        HTTPStatusError = _StubHTTPStatusError

    httpx = _StubHttpxModule()  # type: ignore
try:  # pragma: no cover - prefer real FastAPI when available
    from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
    from fastapi.responses import JSONResponse
except ImportError:  # pragma: no cover - offline test fallback
    from .fastapi_stub import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
    from .fastapi_stub_responses import JSONResponse
try:  # pragma: no cover - prefer real google-auth
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token
except ImportError:  # pragma: no cover - offline fallback
    class _DummyRequestModule:  # minimal stub
        class Request:  # type: ignore
            def __call__(self, *args: Any, **kwargs: Any) -> None:
                return None

    class _DummyIdToken:
        @staticmethod
        def verify_oauth2_token(token: str, request: Any) -> dict[str, Any]:
            return {"uid": token, "aud": "", "iss": ""}

    google_requests = _DummyRequestModule()  # type: ignore
    id_token = _DummyIdToken()  # type: ignore

from config import get_settings
from limiter import RateLimiter, create_limiter
from usage_store import usage_store

app = FastAPI(title="Whisper Proxy")
settings = get_settings()
_google_request = google_requests.Request()
_idem_lock = asyncio.Lock()
_idem_cache: dict[tuple[str, str], dict[str, Any]] = {}


async def get_limiter() -> RateLimiter:
    limiter = getattr(app.state, "limiter", None)
    if limiter is None:
        limiter = await create_limiter(settings.limiter_backend, settings.redis_url)
        app.state.limiter = limiter
    return limiter


async def get_http_client() -> httpx.AsyncClient:
    client = getattr(app.state, "http_client", None)
    if client is None:
        client = httpx.AsyncClient(base_url=settings.whisper_api_base, timeout=120)
        app.state.http_client = client
    return client


@app.on_event("shutdown")
async def shutdown_event() -> None:
    client = getattr(app.state, "http_client", None)
    if client:
        await client.aclose()


def _extract_token(auth_header: str | None) -> str:
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_token")
    return auth_header.split(" ", 1)[1]


def verify_firebase_token(auth_header: str | None) -> dict[str, Any]:
    token = _extract_token(auth_header)
    try:
        decoded = id_token.verify_oauth2_token(token, _google_request)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=401, detail="invalid_token") from exc

    project_id = settings.firebase_project_id
    if decoded.get("aud") != project_id:
        raise HTTPException(status_code=401, detail="invalid_audience")
    issuer = decoded.get("iss")
    expected_issuer = f"https://securetoken.google.com/{project_id}"
    if issuer and issuer != expected_issuer:
        raise HTTPException(status_code=401, detail="invalid_issuer")
    if "uid" not in decoded:
        raise HTTPException(status_code=401, detail="missing_uid")
    return decoded


def _tenant_id(decoded: dict[str, Any]) -> str:
    firebase_info = decoded.get("firebase", {})
    return firebase_info.get("tenant") or decoded.get("tenant_id") or settings.firebase_project_id


def _estimate_minutes(filename: str | None, content_type: str | None, size_bytes: int) -> int:
    mb = max(1, math.ceil(size_bytes / (1024 * 1024)))
    lower = (filename or "").lower()
    ratio = 5 if lower.endswith((".wav", ".pcm")) or (content_type or "").endswith("wav") else 1
    minutes = max(1, math.ceil(mb / ratio))
    return minutes


async def _enforce_limits(user_id: str, tenant_id: str, limiter: RateLimiter) -> None:
    user_key = f"user:{user_id}"
    tenant_key = f"tenant:{tenant_id}"
    allowed_user = await limiter.hit(user_key, settings.rpm_per_user)
    if not allowed_user:
        raise HTTPException(status_code=429, detail="rate_limited_user")
    allowed_tenant = await limiter.hit(tenant_key, settings.rpm_per_tenant)
    if not allowed_tenant:
        raise HTTPException(status_code=429, detail="rate_limited_tenant")


def _limits_dict() -> dict[str, int | bool | str]:
    return {
        "max_file_mb": settings.max_file_mb,
        "max_clip_min": settings.max_clip_min,
        "rpm_per_user": settings.rpm_per_user,
        "rpm_per_tenant": settings.rpm_per_tenant,
        "concurrent_user": settings.concurrent_user,
        "concurrent_tenant": settings.concurrent_tenant,
        "minutes_per_day": settings.minutes_per_day,
        "minutes_per_month": settings.minutes_per_month,
        "default_model": settings.default_model,
        "allow_diarization": settings.allow_diarization,
    }


@app.post("/v1/transcribe")
async def transcribe(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form("th"),
    format: str = Form("text"),
    model_size: str = Form(default=settings.default_model),
    word_timestamps: bool = Form(False),
    diarization: bool = Form(False),
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    limiter: RateLimiter = Depends(get_limiter),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> JSONResponse:
    """Handle upload, enforce limits, proxy to Whisper API."""

    decoded = verify_firebase_token(authorization)
    user_id = decoded["uid"]
    tenant_id = _tenant_id(decoded)

    if diarization and not settings.allow_diarization:
        raise HTTPException(status_code=400, detail="diarization_not_allowed")

    await _enforce_limits(user_id, tenant_id, limiter)

    content = await file.read()
    size_bytes = len(content)
    max_bytes = settings.max_file_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")

    estimated_minutes = _estimate_minutes(file.filename, file.content_type, size_bytes)
    if estimated_minutes > settings.max_clip_min:
        raise HTTPException(status_code=400, detail="clip_too_long")

    limits = {
        "concurrent_user": settings.concurrent_user,
        "concurrent_tenant": settings.concurrent_tenant,
        "minutes_per_day": settings.minutes_per_day,
        "minutes_per_month": settings.minutes_per_month,
    }

    reservation_id = str(uuid.uuid4())
    try:
        await usage_store.reserve(user_id, tenant_id, estimated_minutes, reservation_id, limits)
    except RuntimeError as exc:
        reason = str(exc)
        if reason.startswith("concurrency"):
            raise HTTPException(status_code=409, detail=reason)
        raise HTTPException(status_code=429, detail=reason)

    if idempotency_key:
        cache_key = (user_id, idempotency_key)
        async with _idem_lock:
            cached = _idem_cache.get(cache_key)
            if cached:
                await usage_store.rollback(reservation_id)
                return JSONResponse(cached)

    data = {
        "language": language,
        "format": format,
        "model_size": model_size,
        "word_timestamps": word_timestamps,
        "diarization": diarization,
    }
    files = {
        "file": (file.filename or "upload", io.BytesIO(content), file.content_type or "application/octet-stream"),
    }
    headers = {"X-API-Key": settings.whisper_api_key}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        response = await client.post("/transcribe", data=data, files=files, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        await usage_store.rollback(reservation_id)
        raise HTTPException(status_code=exc.response.status_code, detail="whisper_error") from exc
    except httpx.HTTPError as exc:  # pragma: no cover - network issues
        await usage_store.rollback(reservation_id)
        raise HTTPException(status_code=502, detail="whisper_unreachable") from exc

    payload = response.json()
    task_id = payload.get("task_id")
    if not task_id:
        await usage_store.rollback(reservation_id)
        raise HTTPException(status_code=502, detail="missing_task_id")
    await usage_store.confirm(reservation_id, task_id)

    if idempotency_key:
        async with _idem_lock:
            _idem_cache[(user_id, idempotency_key)] = payload
    return JSONResponse(payload)


@app.get("/v1/status/{task_id}")
async def status(
    task_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
    limiter: RateLimiter = Depends(get_limiter),
    client: httpx.AsyncClient = Depends(get_http_client),
) -> JSONResponse:
    decoded = verify_firebase_token(authorization)
    user_id = decoded["uid"]
    tenant_id = _tenant_id(decoded)
    await _enforce_limits(user_id, tenant_id, limiter)

    headers = {"X-API-Key": settings.whisper_api_key}
    try:
        response = await client.get(f"/status/{task_id}", headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail="whisper_error") from exc

    payload = response.json()
    status_value = payload.get("status")
    if status_value == "completed":
        duration = payload.get("duration") or payload.get("duration_seconds") or 0
        if isinstance(duration, (int, float)) and duration > 0:
            minutes_actual = max(1, math.ceil(float(duration) / 60))
        else:
            minutes_actual = 1
        await usage_store.commit(task_id, minutes_actual)
    elif status_value in {"failed", "cancelled"}:
        await usage_store.rollback(task_id)
    return JSONResponse(payload)


@app.get("/v1/me/usage")
async def me_usage(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    decoded = verify_firebase_token(authorization)
    user_id = decoded["uid"]
    tenant_id = _tenant_id(decoded)
    usage = await usage_store.get_usage(user_id, tenant_id)
    response = {
        "minutes_today": usage["user"]["minutes_today"],
        "minutes_month": usage["user"]["minutes_month"],
        "limits": _limits_dict(),
    }
    return JSONResponse(response)
