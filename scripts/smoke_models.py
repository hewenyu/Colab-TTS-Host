"""Opt-in integration test against REAL models via a localhost-only server.

Uses the upstream public reference recording, not user recordings. No training.
"""
import argparse
import asyncio
import base64
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import numpy as np
import websockets
import yaml

from tts_host.audio import decode_audio, pcm16


async def stream_test(url, key, voice_id):
    headers = {"Authorization": f"Bearer {key}"}
    async with websockets.connect(url + "/v1/tts/stream", additional_headers=headers,
                                  max_size=8 * 1024 * 1024, ping_timeout=None) as ws:
        await ws.send(json.dumps({"type": "session.start", "mode": "tts", "voice_id": voice_id}))
        assert json.loads(await ws.recv())["type"] == "session.ready"
        started = time.monotonic()
        await ws.send(json.dumps({"type": "text.delta", "text": "你好，欢迎使用我们的语音服务。这是一段较长的测试文字，用来验证文字仍在输入时，服务就能够生成并返回对应的声音。"}))
        first = json.loads(await asyncio.wait_for(ws.recv(), 600))
        assert first["type"] == "audio.chunk", first
        first_latency = time.monotonic() - started
        assert len(base64.b64decode(first["audio"])) > 0
        await ws.send(json.dumps({"type": "text.delta", "text": "现在测试结束，谢谢。"}))
        await ws.send(json.dumps({"type": "input.end"}))
        count = 1
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), 600))
            if event["type"] == "session.done":
                break
            assert event["type"] != "error", event
            count += event["type"] == "audio.chunk"
        return {"audio_before_input_end": True, "first_chunk_seconds": first_latency, "audio_chunks": count}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/server.yaml")
    parser.add_argument("--report", default="data/smoke-report.json")
    parser.add_argument("--skip-tts", action="store_true")
    args = parser.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    prompt = Path(cfg["tts"]["source_dir"]).resolve() / "asset/zero_shot_prompt.wav"
    key = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="speech-smoke-") as temp:
        cfg["data_dir"] = temp + "/data"
        cfg["limits"] = {"inference_seconds": 1800, "session_seconds": 3600, "idle_seconds": 300}
        config_path = Path(temp) / "config.yaml"
        config_path.write_text(yaml.safe_dump(cfg))
        env = {**os.environ, "SPEECH_CONFIG": str(config_path), "SPEECH_API_KEYS": json.dumps({"smoke": key}),
               "OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false"}
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with open(Path(temp) / "server.log", "w") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "tts_host.app:create_app", "--factory",
                                       "--host", "127.0.0.1", "--port", str(port), "--ws-max-size", "65536"],
                                      env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        report = {"hardware": "cuda" if cfg["asr"].get("device") == "cuda" else "cpu", "mock_models": False}
        try:
            url = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=url, headers={"Authorization": f"Bearer {key}"}, timeout=1800) as client:
                for _ in range(300):
                    try:
                        if client.get("/health/live").status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if server.poll() is not None:
                        raise RuntimeError("Server exited during startup")
                    time.sleep(0.2)
                audio = prompt.read_bytes()
                start = time.monotonic()
                res = client.post("/v1/asr/transcriptions", files={"file": ("sample.wav", audio)})
                res.raise_for_status()
                report["asr"] = {**res.json(), "seconds": time.monotonic() - start}
                print("ASR", report["asr"], flush=True)
                res = client.post("/v1/translations", json={"text": report["asr"]["text"]})
                res.raise_for_status()
                report["translation"] = res.json()
                print("TRANSLATION", report["translation"], flush=True)
                if not args.skip_tts:
                    res = client.post("/v1/voices", files={"file": ("sample.wav", audio)}, data={
                        "name": "upstream-smoke-reference", "transcript": "希望你以后能够做的比我还好呦。", "consent": True})
                    res.raise_for_status()
                    report["tts"] = asyncio.run(stream_test(url.replace("http:", "ws:"), key, res.json()["id"]))
                    print("TTS", report["tts"], flush=True)
            Path(args.report).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2))
        except BaseException:
            print((Path(temp) / "server.log").read_text()[-10000:], flush=True)
            raise
        finally:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGTERM)
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait()


if __name__ == "__main__":
    main()
