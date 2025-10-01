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
        self.allowed = True

    async def hit(self, scope: str, rate: int) -> bool:
        return self.allowed


class FakeHTTPClient:
    def __init__(self) -> None:
        self.post_responses = []
        self.get_responses = []

    def queue_post(self, payload):
        self.post_responses.append(payload)

    def queue_get(self, payload):
        self.get_responses.append(payload)

    async def post(self, *args, **kwargs):
        return build_response(self.post_responses.pop(0))

    async def get(self, *args, **kwargs):
        return build_response(self.get_responses.pop(0))

    async def aclose(self):
        return None


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    usage_store._user_records.clear()
    usage_store._tenant_records.clear()
    usage_store._jobs.clear()
    main._idem_cache.clear()
    main.app.state.limiter = FakeLimiter()
    client = FakeHTTPClient()
    client.queue_post({"task_id": "task-123"})
    client.queue_get({"status": "completed", "duration": 60})
    main.app.state.http_client = client
    def fake_verify(header):
        if header is None:
            raise main.HTTPException(status_code=401, detail="missing_token")
        return {"uid": "user-1", "firebase": {"tenant": "tenant-1"}}

    monkeypatch.setattr(main, "verify_firebase_token", fake_verify)
    yield


def test_missing_token_returns_401():
    upload = UploadFile("sample.wav", b"1234", "audio/wav")
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(
            main.transcribe(
                Request(),
                file=upload,
                language="th",
                format="text",
                model_size=main.settings.default_model,
                word_timestamps=False,
                diarization=False,
                authorization=None,
                limiter=main.app.state.limiter,
                client=main.app.state.http_client,
            )
        )
    assert exc.value.status_code == 401


def test_valid_token_allows_request():
    upload = UploadFile("sample.wav", b"1234", "audio/wav")
    response = asyncio.run(
        main.transcribe(
            Request(),
            file=upload,
            language="th",
            format="text",
            model_size=main.settings.default_model,
            word_timestamps=False,
            diarization=False,
            authorization="Bearer test",
            limiter=main.app.state.limiter,
            client=main.app.state.http_client,
        )
    )
    assert response.json()["task_id"] == "task-123"
