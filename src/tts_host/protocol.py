import asyncio
import base64
import json
import uuid
from contextlib import aclosing
from typing import Literal

import numpy as np
from pydantic import Field
from starlette.websockets import WebSocketDisconnect

from .config import Strict


class Start(Strict):
    type: Literal["session.start"]
    mode: Literal["asr", "tts", "translate", "interpret"]
    voice_id: str | None = None
    source_language: str = Field("zh", pattern=r"^[a-z]{2,3}(-[A-Za-z]+)?$")
    target_language: str = Field("en", pattern=r"^[a-z]{2,3}(-[A-Za-z]+)?$")
    sample_rate: Literal[16000] = 16000


class SessionCancelled(Exception):
    pass


async def single_text(text):
    yield text


class Session:
    def __init__(self, ws, start, services, limits, voice=None):
        self.ws, self.start, self.services, self.limits, self.voice = ws, start, services, limits, voice
        self.inputs = asyncio.Queue(limits.queue_size)
        self.outputs = asyncio.Queue(limits.queue_size)
        self.segments = asyncio.Queue(limits.queue_size)
        self.id = uuid.uuid4().hex
        self.seq = 0
        self.total_chars = 0

    async def emit(self, kind, **data):
        await self.outputs.put({"type": kind, "session_id": self.id, **data})

    async def sender(self):
        while True:
            event = await self.outputs.get()
            event["seq"] = self.seq
            self.seq += 1
            try:
                await asyncio.wait_for(self.ws.send_json(event), 10)
            finally:
                self.outputs.task_done()

    def enqueue(self, item):
        try:
            self.inputs.put_nowait(item)
        except asyncio.QueueFull as exc:
            raise ValueError("input_overflow: send audio at real-time pace; pending input queue is full") from exc

    async def receiver(self):
        ended = False
        while True:
            message = await asyncio.wait_for(self.ws.receive(), None if ended else self.limits.idle_seconds)
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))
            raw = message.get("bytes")
            if raw is not None:
                if ended or self.start.mode == "tts":
                    raise ValueError("Audio is not accepted in this state")
                if not raw or len(raw) > 32000 or len(raw) % 2:
                    raise ValueError("Each audio frame must contain 1–16000 PCM16 mono samples")
                self.enqueue(raw)
                continue
            encoded = message.get("text", "")
            if len(encoded) > 8192:
                raise ValueError("Control message exceeds 8192 characters")
            event = json.loads(encoded)
            if not isinstance(event, dict):
                raise ValueError("Expected a JSON object")
            kind = event.get("type")
            if kind == "session.cancel":
                raise SessionCancelled()
            if ended:
                raise ValueError("Input has ended; only session.cancel is accepted")
            if kind == "input.end":
                ended = True
                self.enqueue(None)
            elif kind == "input.commit" and self.start.mode != "tts":
                self.enqueue("commit")
            elif kind == "text.delta" and self.start.mode == "tts":
                text = event.get("text")
                if not isinstance(text, str) or not text:
                    raise ValueError("text.delta requires nonempty text")
                self.total_chars += len(text)
                if self.total_chars > self.limits.text_chars:
                    raise ValueError("Session text limit exceeded")
                self.enqueue(text)
            else:
                raise ValueError("Unsupported message type for this mode")

    async def texts(self):
        while True:
            item = await self.inputs.get()
            if item is None:
                return
            yield item

    async def synthesize(self, texts, segment_id, *, text_input_streaming=True):
        tts = self.services.require("tts")
        async with aclosing(tts.stream(texts, self.voice, text_input_streaming=text_input_streaming)) as stream:
            index = 0
            async for rate, audio in stream:
                await self.emit("audio.chunk", segment_id=segment_id, chunk_index=index,
                                encoding="pcm_s16le", sample_rate=rate, channels=1,
                                audio=base64.b64encode(audio).decode())
                index += 1
        await self.emit("audio.done", segment_id=segment_id, chunks=index)

    async def recognize(self):
        asr = self.services.require("asr")
        buffer = np.empty(0, dtype=np.float32)
        cache, words = {}, []
        samples, silence, segment = 0, 0.0, 0

        async def feed(chunk, final):
            nonlocal samples, silence
            samples += len(chunk)
            part = await asr.feed(chunk, cache, final)
            if part:
                words.append(part)
            if not final and part:
                await self.emit("asr.partial", segment_id=segment, text="".join(words), revision=len(words))

        async def commit(tail):
            nonlocal cache, words, samples, silence, segment
            if samples or len(tail):
                # Online Paraformer accepts an empty final packet to flush retained frames.
                await feed(tail, True)
                text = "".join(words).strip()
                await self.emit("asr.final", segment_id=segment, text=text)
                if text and self.start.mode != "asr":
                    await self.segments.put((segment, text))
                segment += 1
            cache, words, samples, silence = {}, [], 0, 0.0

        while True:
            item = await self.inputs.get()
            if item is None or isinstance(item, str):
                await commit(buffer)
                buffer = np.empty(0, dtype=np.float32)
                if item is None:
                    await self.segments.put(None)
                    return
                continue
            audio = np.frombuffer(item, dtype="<i2").astype(np.float32) / 32768
            buffer = np.concatenate([buffer, audio])
            while len(buffer) >= asr.chunk_samples:
                chunk, buffer = buffer[:asr.chunk_samples], buffer[asr.chunk_samples:]
                rms = float(np.sqrt(np.mean(chunk ** 2)))
                silence = silence + len(chunk) / 16000 if rms < self.limits.silence_rms else 0
                boundary = silence >= self.limits.silence_seconds or (samples + len(chunk)) / 16000 >= self.limits.utterance_seconds
                if boundary:
                    await commit(chunk)
                else:
                    await feed(chunk, False)

    async def translate_segments(self):
        while True:
            item = await self.segments.get()
            if item is None:
                return
            segment, source = item
            translated = await self.services.require("translation").translate(
                source, self.start.source_language, self.start.target_language)
            await self.emit("translation.final", segment_id=segment, source_text=source, text=translated)
            if self.start.mode == "interpret" and translated:
                await self.synthesize(single_text(translated), segment, text_input_streaming=False)

    async def processor(self):
        await self.emit("session.ready", mode=self.start.mode, input_encoding="pcm_s16le",
                        sample_rate=16000, resume_supported=False)
        if self.start.mode == "tts":
            await self.synthesize(self.texts(), 0)
        elif self.start.mode == "asr":
            await self.recognize()
        else:
            jobs = [asyncio.create_task(self.recognize()), asyncio.create_task(self.translate_segments())]
            try:
                await asyncio.gather(*jobs)
            finally:
                for job in jobs:
                    job.cancel()
                await asyncio.gather(*jobs, return_exceptions=True)
        await self.emit("session.done")
        await self.outputs.join()

    async def run(self):
        tasks = [asyncio.create_task(self.receiver()), asyncio.create_task(self.processor()),
                 asyncio.create_task(self.sender())]
        try:
            done, _ = await asyncio.wait(tasks, timeout=self.limits.session_seconds,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise TimeoutError("Session duration limit exceeded")
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
