import json
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ASRConfig(Strict):
    backend: Literal["disabled", "paraformer"] = "disabled"
    model: str = "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"
    revision: str = "v2.0.4"
    device: str = "cpu"


class TTSConfig(Strict):
    backend: Literal["disabled", "cosyvoice3"] = "disabled"
    source_dir: Path = Path("vendor/CosyVoice")
    model_dir: Path = Path("models/cosyvoice3")
    revision: str = "unrecorded"
    fp16: bool = False


class TranslationConfig(Strict):
    backend: Literal["disabled", "transformers", "openai"] = "disabled"
    model: str = "Qwen/Qwen2.5-0.5B-Instruct"
    revision: str = "main"
    device: str = "cpu"
    base_url: str = "http://localhost:8001/v1"
    api_key_env: str = "TRANSLATION_API_KEY"
    max_new_tokens: int = Field(512, ge=32, le=4096)


class Limits(Strict):
    upload_mb: int = Field(20, ge=1, le=100)
    audio_seconds: int = Field(120, ge=1, le=600)
    max_sessions: int = Field(4, ge=1, le=64)
    queue_size: int = Field(16, ge=2, le=128)
    idle_seconds: int = Field(30, ge=5, le=300)
    session_seconds: int = Field(600, ge=10, le=3600)
    inference_seconds: int = Field(180, ge=10, le=1800)
    utterance_seconds: float = Field(15, ge=1.2, le=30)
    silence_seconds: float = Field(0.8, ge=0.6, le=3)
    silence_rms: float = Field(0.008, ge=0, le=0.2)
    text_chars: int = Field(4000, ge=100, le=16000)
    stored_samples_per_user: int = Field(2000, ge=5, le=10000)


class TrainingConfig(Strict):
    enabled: bool = False
    max_pending: int = Field(8, ge=1, le=100)
    max_seconds: int = Field(3600, ge=60, le=86400)


class Settings(Strict):
    data_dir: Path = Path("data")
    asr: ASRConfig = Field(default_factory=ASRConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    limits: Limits = Field(default_factory=Limits)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    api_keys: dict[str, str] = Field(default_factory=dict, exclude=True, repr=False)
    development: bool = False

    @model_validator(mode="after")
    def validate_auth(self):
        if not self.development and not self.api_keys:
            raise ValueError("Set SPEECH_API_KEYS to a JSON object mapping user IDs to secret keys")
        if any(len(k) < 24 for k in self.api_keys.values()):
            raise ValueError("API keys must contain at least 24 characters")
        if len(set(self.api_keys.values())) != len(self.api_keys):
            raise ValueError("Each user must have a different API key")
        return self

    @classmethod
    def load(cls):
        path = Path(os.environ.get("SPEECH_CONFIG", "config/server.yaml"))
        obj = yaml.safe_load(path.read_text()) if path.exists() else {}
        obj = obj or {}
        obj["api_keys"] = json.loads(os.environ.get("SPEECH_API_KEYS", "{}"))
        if "SPEECH_DATA_DIR" in os.environ:
            obj["data_dir"] = os.environ["SPEECH_DATA_DIR"]
        return cls.model_validate(obj)
