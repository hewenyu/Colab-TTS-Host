import asyncio

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tts_host.app import create_app
from tts_host.audio import wav_bytes
from tts_host.config import Settings

KEY_A = "a" * 32
KEY_B = "b" * 32


class FakeASR:
    chunk_samples = 9600

    async def feed(self, audio, cache, final=False):
        cache["n"] = cache.get("n", 0) + 1
        return "你好" if cache["n"] == 1 else "。" if final else "世界"

    async def transcribe(self, audio):
        return "你好"


class FakeTTS:
    def __init__(self):
        self.closed = 0
        self.seen = []
        self.input_modes = []

    async def stream(self, texts, voice, *, text_input_streaming=True):
        self.input_modes.append(text_input_streaming)
        try:
            async for text in texts:
                self.seen.append(text)
                yield 24000, b"\x01\x00" * 240
        finally:
            self.closed += 1


class FakeTranslator:
    async def translate(self, text, source, target):
        return "Hello."


class FakeServices:
    def __init__(self):
        self.asr = FakeASR()
        self.tts = FakeTTS()
        self.translation = FakeTranslator()

    def require(self, name):
        return getattr(self, name)

    async def close(self):
        pass

    def capabilities(self):
        return {"test_double": True}


@pytest.fixture
def setup(tmp_path):
    settings = Settings(data_dir=tmp_path, api_keys={"alice": KEY_A, "bob": KEY_B},
                        training={"enabled": True})
    services = FakeServices()
    app = create_app(settings, services)
    with TestClient(app) as client:
        client.headers["Authorization"] = f"Bearer {KEY_A}"
        yield client, app, services


@pytest.fixture
def audio():
    return wav_bytes(np.sin(np.arange(16000 * 4) * 0.1).astype(np.float32) * 0.1, 16000)


@pytest.fixture
def voice(setup, audio):
    client, _, _ = setup
    response = client.post("/v1/voices", files={"file": ("voice.wav", audio)},
                           data={"transcript": "你好世界", "name": "test", "consent": "true"})
    assert response.status_code == 200, response.text
    return response.json()["id"]
