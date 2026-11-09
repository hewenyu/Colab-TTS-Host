import numpy as np
import pytest
from starlette.websockets import WebSocketDisconnect

from conftest import KEY_B
from tts_host.audio import decode_audio, wav_bytes
from tts_host.config import Settings


def test_authentication_before_upload(setup):
    client, _, _ = setup
    client.headers.clear()
    assert client.post("/v1/voices", content=b"malformed multipart").status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/stream"):
            pass


def test_voice_isolation_and_consent(setup, voice, audio):
    client, _, _ = setup
    assert client.post("/v1/voices", files={"file": ("a.wav", audio)},
                       data={"name": "x", "transcript": "x", "consent": False}).status_code == 422
    client.headers["Authorization"] = f"Bearer {KEY_B}"
    assert client.get("/v1/voices").json() == {"voices": []}
    assert client.post("/v1/tts/speech", json={"voice_id": voice, "text": "hi"}).status_code == 404


def test_independent_http_services(setup, voice, audio):
    client, _, _ = setup
    assert client.post("/v1/asr/transcriptions", files={"file": ("a.wav", audio)}).json()["text"] == "你好"
    assert client.post("/v1/translations", json={"text": "你好"}).json()["text"] == "Hello."
    pcm = client.post("/v1/tts/speech", json={"voice_id": voice, "text": "你好"})
    assert pcm.headers["x-sample-rate"] == "24000" and len(pcm.content) == 480
    wav = client.post("/v1/tts/speech", json={"voice_id": voice, "text": "你好", "stream": False})
    assert wav.content[:4] == b"RIFF"


def test_tts_emits_before_input_end(setup, voice):
    client, _, services = setup
    with client.websocket_connect("/v1/tts/stream") as ws:
        ws.send_json({"type": "session.start", "mode": "tts", "voice_id": voice})
        assert ws.receive_json()["type"] == "session.ready"
        ws.send_json({"type": "text.delta", "text": "第一句"})
        first = ws.receive_json()
        assert first["type"] == "audio.chunk" and first["seq"] == 1
        # The first audio chunk arrived while input was still open.
        ws.send_json({"type": "text.delta", "text": "第二句"})
        assert ws.receive_json()["chunk_index"] == 1
        ws.send_json({"type": "input.end"})
        assert ws.receive_json()["type"] == "audio.done"
        assert ws.receive_json()["type"] == "session.done"
    assert services.tts.seen == ["第一句", "第二句"]
    assert services.tts.input_modes == [True]


def test_interpret_commits_and_drains(setup, voice):
    client, _, services = setup
    with client.websocket_connect("/v1/interpret/stream") as ws:
        ws.send_json({"type": "session.start", "mode": "interpret", "voice_id": voice})
        ws.receive_json()
        ws.send_bytes((np.ones(9600) * 3000).astype("<i2").tobytes())
        assert ws.receive_json()["type"] == "asr.partial"
        ws.send_json({"type": "input.end"})
        events = [ws.receive_json() for _ in range(5)]
        assert [e["type"] for e in events] == ["asr.final", "translation.final", "audio.chunk", "audio.done", "session.done"]
        assert len({e["seq"] for e in events}) == 5
    assert services.tts.input_modes == [False]


def test_cancel_closes_generator(setup, voice):
    client, _, services = setup
    with client.websocket_connect("/v1/tts/stream") as ws:
        ws.send_json({"type": "session.start", "mode": "tts", "voice_id": voice})
        ws.receive_json()
        ws.send_json({"type": "text.delta", "text": "hello"})
        ws.receive_json()
        ws.send_json({"type": "session.cancel"})
        assert ws.receive_json()["type"] == "session.cancelled"
    assert services.tts.closed == 1


def test_protocol_rejects_bad_pcm(setup):
    client, _, _ = setup
    with client.websocket_connect("/v1/asr/stream") as ws:
        ws.send_json({"type": "session.start", "mode": "asr"})
        ws.receive_json()
        ws.send_bytes(b"odd")
        assert ws.receive_json()["type"] == "error"


def test_invalid_model_and_missing_auth_rejected(tmp_path):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path)
    with pytest.raises(ValueError):
        Settings(development=True, tts={"backend": "invented_model"})


def test_audio_metadata_limit_and_resampling():
    raw = wav_bytes(np.zeros(48000 * 2), 48000)
    with pytest.raises(ValueError):
        decode_audio(raw, 1)
    assert len(decode_audio(raw, 3)) == 32000


def test_training_auth_and_validation(setup, voice):
    client, _, _ = setup
    assert client.post("/v1/voice-training/jobs", json={"voice_id": voice,
                       "sample_ids": ["missing"] * 5}).status_code == 422
    assert client.post("/v1/voice-training/jobs", json={"voice_id": voice,
                       "sample_ids": [str(i) for i in range(5)]}).status_code == 404


def test_http_tts_uses_complete_text_with_both_output_formats(setup, voice):
    client, _, services = setup
    for stream in (True, False):
        response = client.post('/v1/tts/speech', json={'text': '今天下午一起散步。', 'voice_id': voice, 'stream': stream})
        assert response.status_code == 200
        assert services.tts.input_modes[-1] is False
        assert services.tts.seen[-1] == '今天下午一起散步。'
