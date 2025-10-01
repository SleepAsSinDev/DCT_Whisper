import asyncio
import os

os.environ.setdefault("WHISPER_API_KEY", "sk-live-example-1234567890")
os.environ.setdefault("FIREBASE_PROJECT_ID", "demo-whisper-th")

import pytest

from backend import main
from backend.fastapi_stub import Request, UploadFile
from backend.usage_store import usage_store
from backend.tests.utils import build_response


class FakeLimiter:
    def __init__(self) -> None:
        from collections import defaultdict

        self.counts = defaultdict(int)
        self.thresholds = {}

    def set_limit(self, scope: str, limit: int) -> None:
        self.thresholds[scope] = limit

    async def hit(self, scope: str, rate: int) -> bool:
        self.counts[scope] += 1
        limit = self.thresholds.get(scope, rate)
        return self.counts[scope] <= limit


class FakeHTTPClient:
    def __init__(self) -> None:
        self.post_responses = []

    def queue_post(self, payload):
        self.post_responses.append(payload)

    async def post(self, *args, **kwargs):
        return build_response(self.post_responses.pop(0))

    async def aclose(self):
        return None


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    usage_store._user_records.clear()
    usage_store._tenant_records.clear()
    usage_store._jobs.clear()
    main._idem_cache.clear()
    limiter = FakeLimiter()
    main.app.state.limiter = limiter
    client = FakeHTTPClient()
    client.queue_post({"task_id": "task-a"})
    client.queue_post({"task_id": "task-b"})
    main.app.state.http_client = client
    def fake_verify(header):
        if header is None:
            raise main.HTTPException(status_code=401, detail="missing_token")
        return {"uid": "user-1", "firebase": {"tenant": "tenant-1"}}

    monkeypatch.setattr(main, "verify_firebase_token", fake_verify)
    yield limiter


def test_rate_limit_exceeded(setup):
    limiter = setup
    limiter.set_limit("user:user-1", 1)
    upload = UploadFile("a.wav", b"1" * 1024 * 1024, "audio/wav")
    response = asyncio.run(
        main.transcribe(
            Request(),
            file=upload,
            language="th",
            format="text",
            model_size=main.settings.default_model,
            word_timestamps=False,
            diarization=False,
            authorization="Bearer t",
            limiter=main.app.state.limiter,
            client=main.app.state.http_client,
        )
    )
    assert response.json()["task_id"] == "task-a"
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(
            main.transcribe(
                Request(),
                file=UploadFile("a.wav", b"1" * 1024 * 1024, "audio/wav"),
                language="th",
                format="text",
                model_size=main.settings.default_model,
                word_timestamps=False,
                diarization=False,
                authorization="Bearer t",
                limiter=main.app.state.limiter,
                client=main.app.state.http_client,
            )
        )
    assert exc.value.status_code == 429
    assert exc.value.detail == "rate_limited_user"


def test_quota_exceeded(monkeypatch):
    monkeypatch.setattr(main.settings, "minutes_per_day", 1)
    monkeypatch.setattr(main.settings, "concurrent_user", 2)
    first = asyncio.run(
        main.transcribe(
            Request(),
            file=UploadFile("a.wav", b"1" * 1024 * 1024, "audio/wav"),
            language="th",
            format="text",
            model_size=main.settings.default_model,
            word_timestamps=False,
            diarization=False,
            authorization="Bearer t",
            limiter=main.app.state.limiter,
            client=main.app.state.http_client,
        )
    )
    assert first.json()["task_id"] == "task-a"
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(
            main.transcribe(
                Request(),
                file=UploadFile("a.wav", b"1" * 1024 * 1024, "audio/wav"),
                language="th",
                format="text",
                model_size=main.settings.default_model,
                word_timestamps=False,
                diarization=False,
                authorization="Bearer t",
                limiter=main.app.state.limiter,
                client=main.app.state.http_client,
            )
        )
    assert exc.value.status_code == 429
    assert exc.value.detail == "quota_day"


def test_concurrency_exceeded():
    asyncio.run(
        main.transcribe(
            Request(),
            file=UploadFile("a.wav", b"1" * 1024 * 1024, "audio/wav"),
            language="th",
            format="text",
            model_size=main.settings.default_model,
            word_timestamps=False,
            diarization=False,
            authorization="Bearer t",
            limiter=main.app.state.limiter,
            client=main.app.state.http_client,
        )
    )
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(
            main.transcribe(
                Request(),
                file=UploadFile("b.wav", b"1" * 1024 * 1024, "audio/wav"),
                language="th",
                format="text",
                model_size=main.settings.default_model,
                word_timestamps=False,
                diarization=False,
                authorization="Bearer t",
                limiter=main.app.state.limiter,
                client=main.app.state.http_client,
            )
        )
    assert exc.value.status_code == 409
    assert exc.value.detail == "concurrency_user"
