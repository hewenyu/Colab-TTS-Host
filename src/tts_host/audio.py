import io
import math

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly


def decode_audio(raw: bytes, max_seconds: int, target_rate: int = 16000) -> np.ndarray:
    """Inspect metadata before decoding so small compressed uploads cannot inflate unboundedly."""
    try:
        with sf.SoundFile(io.BytesIO(raw)) as f:
            if f.samplerate < 8000 or f.samplerate > 96000 or f.channels > 2:
                raise ValueError("Audio must have 1–2 channels and a sample rate of 8–96 kHz")
            if f.frames <= 0 or f.frames / f.samplerate > max_seconds:
                raise ValueError(f"Audio must be nonempty and at most {max_seconds} seconds")
            rate = f.samplerate
            audio = f.read(dtype="float32", always_2d=True).mean(axis=1)
    except (RuntimeError, sf.LibsndfileError) as exc:
        raise ValueError("Unsupported audio: upload WAV or FLAC") from exc
    if not np.isfinite(audio).all():
        raise ValueError("Audio contains non-finite samples")
    if rate != target_rate:
        gcd = math.gcd(rate, target_rate)
        audio = resample_poly(audio, target_rate // gcd, rate // gcd)
    return np.clip(audio, -1, 1).astype(np.float32)


def pcm16(audio: np.ndarray) -> bytes:
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()
