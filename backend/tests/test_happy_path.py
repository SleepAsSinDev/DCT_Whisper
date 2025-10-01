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
    async def hit(self, scope: str, rate: int) -> bool:
        return True


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
def setup(monkeypatch):
    usage_store._user_records.clear()
    usage_store._tenant_records.clear()
    usage_store._jobs.clear()
    main._idem_cache.clear()
    main.app.state.limiter = FakeLimiter()
    client = FakeHTTPClient()
    client.queue_post({"task_id": "task-xyz"})
    client.queue_get({"status": "completed", "duration": 120, "text": "สวัสดี"})
    main.app.state.http_client = client
    def fake_verify(header):
        if header is None:
            raise main.HTTPException(status_code=401, detail="missing_token")
        return {"uid": "user-1", "firebase": {"tenant": "tenant-1"}}

    monkeypatch.setattr(main, "verify_firebase_token", fake_verify)
    yield


def test_transcribe_status_and_usage_flow():
    response = asyncio.run(
        main.transcribe(
            Request(),
            file=UploadFile("sample.wav", b"0" * 1024 * 1024, "audio/wav"),
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
    task_id = response.json()["task_id"]

    status_resp = asyncio.run(
        main.status(
            task_id=task_id,
            authorization="Bearer t",
            limiter=main.app.state.limiter,
            client=main.app.state.http_client,
        )
    )
    assert status_resp.json()["status"] == "completed"

    usage_resp = asyncio.run(main.me_usage(authorization="Bearer t"))
    body = usage_resp.json()
    assert body["minutes_today"] >= 2
    assert body["limits"]["default_model"] == main.settings.default_model
