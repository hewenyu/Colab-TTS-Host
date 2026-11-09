"""CLI client example; upload a WAV as paced PCM while receiving results concurrently."""
import argparse
import asyncio
import base64
import json
import os
from pathlib import Path

import websockets

from tts_host.audio import decode_audio, pcm16


async def main(args):
    key = os.environ["SPEECH_API_KEY"]
    audio = pcm16(decode_audio(Path(args.audio).read_bytes(), 600))
    async with websockets.connect(args.url, additional_headers={"Authorization": f"Bearer {key}"},
                                  max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"type": "session.start", "mode": args.mode,
                                  "voice_id": args.voice_id, "target_language": args.target}))
        ready = json.loads(await ws.recv())
        if ready.get("type") != "session.ready":
            raise RuntimeError(ready)
        async def send():
            for offset in range(0, len(audio), 3200):
                await ws.send(audio[offset:offset + 3200])
                await asyncio.sleep(0.1)
            await ws.send(json.dumps({"type": "input.end"}))
        sender = asyncio.create_task(send())
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        rates = {}
        try:
            while True:
                event = json.loads(await ws.recv())
                if event["type"] == "audio.chunk":
                    segment = event["segment_id"]
                    rates[str(segment)] = event["sample_rate"]
                    with (output / f'{ready["session_id"]}-{segment}.pcm').open("ab") as file:
                        file.write(base64.b64decode(event["audio"]))
                    print("audio chunk", segment, event["chunk_index"])
                else:
                    print(json.dumps(event, ensure_ascii=False))
                if event["type"] == "error":
                    raise RuntimeError(event["message"])
                if event["type"] in ("session.done", "session.cancelled"):
                    break
            (output / f'{ready["session_id"]}-sample-rates.json').write_text(json.dumps(rates))
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--url", default="ws://127.0.0.1:8000/v1/stream")
    parser.add_argument("--mode", choices=["asr", "translate", "interpret"], default="asr")
    parser.add_argument("--voice-id")
    parser.add_argument("--target", default="en")
    parser.add_argument("--output", default="data/client-output")
    asyncio.run(main(parser.parse_args()))
