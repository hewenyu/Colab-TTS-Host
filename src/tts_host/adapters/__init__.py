from .asr import ParaformerASR
from .translation import Translator
from .tts import CosyVoiceTTS


class Unavailable(RuntimeError):
    pass


class Services:
    def __init__(self, settings):
        self.settings = settings
        self.asr = ParaformerASR(settings.asr) if settings.asr.backend == "paraformer" else None
        self.translation = Translator(settings.translation) if settings.translation.backend != "disabled" else None
        self.tts = CosyVoiceTTS(settings.tts, settings.limits) if settings.tts.backend == "cosyvoice3" else None

    def require(self, name):
        service = getattr(self, name)
        if service is None:
            raise Unavailable(f"{name} backend is disabled; configure it in server.yaml")
        return service

    async def close(self):
        if self.tts:
            await self.tts.close()

    def capabilities(self):
        return {
            "asr": {"enabled": self.asr is not None, "backend": self.settings.asr.backend,
                    "input_streaming": self.asr is not None, "languages": ["zh"] if self.asr else []},
            "translation": {"enabled": self.translation is not None,
                            "backend": self.settings.translation.backend, "commit_policy": "utterance"},
            "tts": {"enabled": self.tts is not None, "backend": self.settings.tts.backend,
                    "text_input_streaming": self.tts is not None, "audio_output_streaming": self.tts is not None},
            "training": {"enabled": self.settings.training.enabled, "recipe": "cosyvoice3-llm-sft",
                         "requires_worker": True},
        }
