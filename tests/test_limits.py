import asyncio

import httpx
import pytest

from conftest import KEY_A
from tts_host.protocol import Session, Start


async def test_chunked_body_is_bounded(setup):
    _, app, _ = setup
    async def body():
        for _ in range(24):
            yield b"x" * 1024 * 1024
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                 headers={"Authorization": f"Bearer {KEY_A}"}) as client:
        # Invalid JSON is irrelevant: actual bytes must be limited before parsing completes.
        response = await client.post("/v1/translations", content=body(),
                                     headers={"Content-Type": "application/json"})
        assert response.status_code == 413


def test_backpressure_rejects_overflow(setup):
    _, app, services = setup
    session = Session(None, Start(type="session.start", mode="asr"), services, app.state.settings.limits)
    for _ in range(app.state.settings.limits.queue_size):
        session.enqueue(b"\0\0")
    with pytest.raises(ValueError, match="input_overflow"):
        session.enqueue(b"\0\0")


def test_asr_cache_does_not_cross_sessions(setup):
    client, _, _ = setup
    for _ in range(2):
        with client.websocket_connect("/v1/asr/stream") as ws:
            ws.send_json({"type": "session.start", "mode": "asr"})
            ws.receive_json()
            ws.send_bytes(b"\0\1" * 100)
            ws.send_json({"type": "input.end"})
            assert ws.receive_json()["text"] == "你好"
            assert ws.receive_json()["type"] == "session.done"


def test_disabled_backend_returns_actionable_error(tmp_path):
    from fastapi.testclient import TestClient
    from tts_host.app import create_app
    from tts_host.config import Settings
    with TestClient(create_app(Settings(data_dir=tmp_path, development=True))) as client:
        result = client.post("/v1/translations", json={"text": "hello"})
        assert result.status_code == 503
        assert "disabled" in result.json()["detail"]
