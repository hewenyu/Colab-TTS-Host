import asyncio
import multiprocessing as mp
import time
from contextlib import aclosing

from tts_host.adapters.tts import CosyVoiceTTS, text_pieces
from tts_host.config import Limits, TTSConfig


def blocked_worker(commands, inputs, outputs):
    commands.get()
    inputs.get()
    outputs.put(("audio", 24000, b"\0\0"))
    while True:
        time.sleep(1)


def test_bistream_turns_preserve_mixed_language_text():
    text = "你好，hello world!\n今天 123.45 元。"
    pieces = list(text_pieces(text))
    assert ''.join(pieces) == text
    assert any(piece.endswith("hello ") for piece in pieces) and "world!\n" in pieces
    assert len(pieces) > 5


async def test_cancellation_terminates_native_worker(monkeypatch):
    backend = CosyVoiceTTS(TTSConfig(), Limits())
    spawned = []

    def start():
        ctx = mp.get_context("spawn")
        backend.commands = ctx.Queue(1)
        backend.inputs = ctx.Queue(2)
        backend.outputs = ctx.Queue(2)
        backend.process = ctx.Process(target=blocked_worker,
                                      args=(backend.commands, backend.inputs, backend.outputs), daemon=True)
        backend.process.start()
        spawned.append(backend.process.pid)

    monkeypatch.setattr(backend, "_start", start)
    async def text():
        yield "hello"
        await asyncio.Event().wait()

    async with aclosing(backend.stream(text(), {})) as stream:
        assert await asyncio.wait_for(anext(stream), 10) == (24000, b"\0\0")
        process = backend.process
        assert process.is_alive()
    assert backend.process is None
    assert spawned[0] not in {p.pid for p in mp.active_children()}
