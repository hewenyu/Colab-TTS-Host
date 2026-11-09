"""CosyVoice runs in a restartable child process.

Upstream generation owns background threads without cancellation/finally cleanup.
On disconnect/deadline we terminate that child, not merely abandon a Python thread.
The next request reloads weights. All IPC queues are bounded.
"""
import asyncio
import logging
import multiprocessing as mp
import os
import queue
import sys
import time
import zipfile
from contextlib import contextmanager

from ..audio import pcm16


@contextmanager
def mapped_checkpoints():
    """Avoid an extra anonymous-RAM copy of upstream torch checkpoints while loading.

    Scoped to initialization inside this isolated process; restore torch.load even on error.
    Legacy non-zip checkpoints retain upstream loading behavior.
    """
    import torch
    original = torch.load
    def load(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)) and zipfile.is_zipfile(path):
            kwargs.setdefault("mmap", True)
        return original(path, *args, **kwargs)
    torch.load = load
    try:
        yield
    finally:
        torch.load = original


def _worker(config, commands, inputs, outputs):
    # Colab exports an inline notebook backend unavailable inside our isolated runtime.
    os.environ["MPLBACKEND"] = "Agg"
    if config.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    sys.path.insert(0, str(config.source_dir.resolve()))
    sys.path.insert(0, str(config.source_dir.resolve() / "third_party/Matcha-TTS"))
    logging.disable(logging.WARNING)
    from cosyvoice.cli.cosyvoice import AutoModel
    if config.device == "cuda":
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("TTS is configured for CUDA but no CUDA device is available")
    model, loaded_dir = None, None
    while True:
        voice = commands.get()
        if voice is None:
            return
        try:
            directory = voice.get("model_dir") or str(config.model_dir.resolve())
            if model is None or loaded_dir != directory:
                if model is not None:
                    del model
                    import gc
                    import torch
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                with mapped_checkpoints():
                    model = AutoModel(model_dir=directory, fp16=config.fp16)
                if model.__class__.__name__ != "CosyVoice3":
                    raise ValueError("cosyvoice3 adapter requires CosyVoice3 weights")
                loaded_dir = directory
            def text_chunks():
                while True:
                    chunk = inputs.get()
                    if chunk is None:
                        return
                    yield chunk
            chunks = text_chunks()
            first = next(chunks, None)
            if first is not None:
                def combined():
                    yield first
                    yield from chunks
                prompt = "You are a helpful assistant.<|endofprompt|>" + voice["transcript"]
                # Pass a generator: this invokes upstream inference_bistream, not sentence batching.
                for result in model.inference_zero_shot(combined(), prompt, voice["audio_path"],
                                                        stream=True, text_frontend=False):
                    outputs.put(("audio", model.sample_rate,
                                 pcm16(result["tts_speech"].detach().cpu().numpy().reshape(-1))))
            outputs.put(("done",))
        except Exception:
            logging.exception("CosyVoice worker failed")
            outputs.put(("error",))
            return


class CosyVoiceTTS:
    def __init__(self, config, limits):
        self.config, self.limits = config, limits
        self.lock = asyncio.Lock()
        self.process = None

    def _start(self):
        context = mp.get_context("spawn")
        self.commands = context.Queue(1)
        self.inputs = context.Queue(self.limits.queue_size)
        self.outputs = context.Queue(self.limits.queue_size)
        self.process = context.Process(target=_worker,
                                       args=(self.config, self.commands, self.inputs, self.outputs), daemon=True)
        self.process.start()

    def _stop(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=5)
            self.process.close()
            self.process = None
            for q in (self.commands, self.inputs, self.outputs):
                q.cancel_join_thread()
                q.close()

    async def close(self):
        await asyncio.to_thread(self._stop)

    async def stream(self, text, voice):
        async with self.lock:
            if self.process is None or not self.process.is_alive():
                await self.close()
                self._start()
            self.commands.put_nowait(voice)
            async def feed():
                async for chunk in text:
                    while True:
                        try:
                            self.inputs.put_nowait(chunk)
                            break
                        except queue.Full:
                            await asyncio.sleep(0.02)
                while True:
                    try:
                        self.inputs.put_nowait(None)
                        break
                    except queue.Full:
                        await asyncio.sleep(0.02)
            feeder = asyncio.create_task(feed())
            finished = False
            started = time.monotonic()
            try:
                while True:
                    if time.monotonic() - started > self.limits.inference_seconds:
                        raise TimeoutError("TTS generation exceeded its deadline")
                    if feeder.done() and not feeder.cancelled() and feeder.exception():
                        raise feeder.exception()
                    try:
                        item = self.outputs.get_nowait()
                    except queue.Empty:
                        if not self.process.is_alive():
                            raise RuntimeError(f"TTS worker exited while generating audio (exit {self.process.exitcode})")
                        await asyncio.sleep(0.02)
                        continue
                    if item[0] == "error":
                        raise RuntimeError("TTS model failed; verify model files and prompt audio")
                    if item[0] == "done":
                        await feeder
                        finished = True
                        return
                    yield item[1], item[2]
            finally:
                feeder.cancel()
                await asyncio.gather(feeder, return_exceptions=True)
                if not finished:
                    await self.close()
