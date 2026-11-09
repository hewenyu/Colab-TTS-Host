import asyncio
import threading

import numpy as np


class ParaformerASR:
    """Native online Paraformer; each stream owns its cache. Model access is serialized."""
    chunk_samples = 9600  # 600 ms @ 16 kHz, [0, 10, 5]

    def __init__(self, config):
        self.config = config
        self.model = None
        self.lock = threading.Lock()

    def _feed(self, samples, cache, final):
        with self.lock:
            if self.model is None:
                from funasr import AutoModel
                self.model = AutoModel(model=self.config.model, model_revision=self.config.revision,
                                       device=self.config.device, disable_update=True,
                                       disable_pbar=True, disable_log=True)
            result = self.model.generate(input=samples, cache=cache, is_final=final,
                                         chunk_size=[0, 10, 5], encoder_chunk_look_back=4,
                                         decoder_chunk_look_back=1, disable_pbar=True)
            return "".join(item.get("text", "") for item in result)

    async def feed(self, samples, cache, final=False):
        return await asyncio.to_thread(self._feed, samples, cache, final)

    async def transcribe(self, audio):
        cache, result = {}, []
        for start in range(0, len(audio), self.chunk_samples):
            chunk = audio[start:start + self.chunk_samples]
            result.append(await self.feed(chunk, cache, start + self.chunk_samples >= len(audio)))
        return "".join(result)
