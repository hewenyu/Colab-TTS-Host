import asyncio
import hmac
import json
import logging
import time
import uuid
from contextlib import aclosing, asynccontextmanager

import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import Field, ValidationError
from starlette.websockets import WebSocketDisconnect

from .adapters import Services, Unavailable
from .audio import decode_audio, wav_bytes
from .config import Settings, Strict
from .middleware import BodyTooLarge, RequestGuard
from .protocol import Session, SessionCancelled, Start, single_text
from .store import Store

log = logging.getLogger(__name__)


class TranslationRequest(Strict):
    text: str = Field(min_length=1, max_length=4000)
    source_language: str = Field("zh", pattern=r"^[a-z]{2,3}(-[A-Za-z]+)?$")
    target_language: str = Field("en", pattern=r"^[a-z]{2,3}(-[A-Za-z]+)?$")


class SpeechRequest(Strict):
    text: str = Field(min_length=1, max_length=4000)
    voice_id: str
    stream: bool = True


class TrainingRequest(Strict):
    voice_id: str
    sample_ids: list[str] = Field(min_length=5, max_length=2000)
    epochs: int = Field(1, ge=1, le=20)
    learning_rate: float = Field(1e-5, ge=1e-7, le=1e-4)


def create_app(settings=None, services=None):
    settings = settings or Settings.load()
    store = Store(settings.data_dir)
    services = services or Services(settings)
    active = 0

    @asynccontextmanager
    async def lifespan(app):
        yield
        await services.close()

    app = FastAPI(title="Colab TTS Host", version="0.1.0", lifespan=lifespan,
                  docs_url="/docs", redoc_url=None)
    app.state.settings, app.state.services, app.state.store = settings, services, store

    def authenticate(headers):
        auth = headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        for owner, key in settings.api_keys.items():
            if hmac.compare_digest(token.encode(), key.encode()):
                return owner
        if settings.development and not settings.api_keys:
            return "development"
        raise HTTPException(401, "Valid Authorization: Bearer API_KEY required")

    async def owner(request: Request):
        return authenticate(request.headers)

    app.add_middleware(RequestGuard, authenticate=authenticate,
                       max_bytes=(settings.limits.upload_mb + 1) * 1024 * 1024)

    @app.exception_handler(BodyTooLarge)
    async def too_large(request, exc):
        return JSONResponse({"detail": "Request too large"}, 413)

    @asynccontextmanager
    async def slot():
        nonlocal active
        if active >= settings.limits.max_sessions:
            raise HTTPException(429, "Server is busy; retry later")
        active += 1
        try:
            yield
        finally:
            active -= 1

    def lookup(kind, user, rid):
        try:
            return store.get(kind, user, rid)
        except (KeyError, ValueError):
            raise HTTPException(404, f"{kind} not found")

    def voice_for(user, rid):
        voice = lookup("voice", user, rid)
        return {**voice, "audio_path": str(store.asset(voice["sample_id"]))}

    async def upload(file, max_seconds):
        data = await file.read(settings.limits.upload_mb * 1024 * 1024 + 1)
        await file.close()
        if len(data) > settings.limits.upload_mb * 1024 * 1024:
            raise HTTPException(413, "Audio upload too large")
        try:
            return await asyncio.to_thread(decode_audio, data, max_seconds)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def persist_sample(user, audio, transcript):
        if not transcript.strip():
            raise HTTPException(422, "Transcript cannot be whitespace")
        if len(store.list("sample", user)) >= settings.limits.stored_samples_per_user:
            raise HTTPException(429, "Stored sample quota reached")
        rid = uuid.uuid4().hex
        path = store.asset(rid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(wav_bytes(audio, 16000))
        return store.create("sample", user, {"transcript": transcript, "duration": len(audio) / 16000}, rid)

    @app.middleware("http")
    async def upload_limit(request, call_next):
        # Fast path for declared sizes; RequestGuard also counts chunked body bytes.
        length = request.headers.get("content-length")
        try:
            if length and int(length) > (settings.limits.upload_mb + 1) * 1024 * 1024:
                return JSONResponse({"detail": "Request too large"}, 413)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, 400)
        return await call_next(request)

    @app.exception_handler(Unavailable)
    async def unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, 503)

    @app.exception_handler(TimeoutError)
    async def deadline(request, exc):
        return JSONResponse({"detail": "Model execution deadline exceeded"}, 504)

    @app.get("/health/live")
    async def health():
        return {"status": "ok", "active_requests": active}

    @app.get("/v1/capabilities")
    async def capabilities(user=Depends(owner)):
        return services.capabilities()

    @app.post("/v1/asr/transcriptions")
    async def transcription(file: UploadFile = File(...), user=Depends(owner)):
        asr = services.require("asr")
        async with slot():
            audio = await upload(file, settings.limits.audio_seconds)
            text = await asyncio.wait_for(asr.transcribe(audio), settings.limits.inference_seconds)
            return {"text": text, "language": "zh", "duration": len(audio) / 16000}

    @app.post("/v1/translations")
    async def translate(body: TranslationRequest, user=Depends(owner)):
        async with slot():
            text = await asyncio.wait_for(services.require("translation").translate(
                body.text, body.source_language, body.target_language), settings.limits.inference_seconds)
            return {"text": text, "source_language": body.source_language, "target_language": body.target_language}

    @app.post("/v1/voices")
    async def create_voice(file: UploadFile = File(...), transcript: str = Form(..., min_length=1, max_length=1000),
                           name: str = Form(..., min_length=1, max_length=100),
                           consent: bool = Form(...), user=Depends(owner)):
        if not consent:
            raise HTTPException(422, "Confirm ownership or permission to clone this voice")
        audio = await upload(file, 30)
        if len(audio) < 3 * 16000:
            raise HTTPException(422, "Reference audio must be 3–30 seconds")
        sample = persist_sample(user, audio, transcript.strip())
        return store.create("voice", user, {"name": name, "sample_id": sample["id"],
                            "transcript": sample["transcript"], "kind": "zero_shot", "version": 1,
                            "base_revision": settings.tts.revision, "consent_at": time.time()})

    @app.get("/v1/voices")
    async def voices(user=Depends(owner)):
        return {"voices": store.list("voice", user)}

    @app.post("/v1/tts/speech")
    async def speech(body: SpeechRequest, user=Depends(owner)):
        tts = services.require("tts")
        voice = voice_for(user, body.voice_id)
        # Acquire capacity before sending response headers.
        admission = slot()
        await admission.__aenter__()
        stream = tts.stream(single_text(body.text), voice)
        try:
            first = await asyncio.wait_for(anext(stream), settings.limits.inference_seconds)
        except BaseException:
            await stream.aclose()
            await admission.__aexit__(None, None, None)
            raise
        async def chunks():
            try:
                yield first[1]
                async for rate, chunk in stream:
                    if rate != first[0]:
                        raise RuntimeError("TTS sample rate changed within a response")
                    yield chunk
            finally:
                await stream.aclose()
                await admission.__aexit__(None, None, None)
        output = chunks()
        if body.stream:
            return StreamingResponse(output, media_type="application/octet-stream", headers={
                "X-Audio-Encoding": "pcm_s16le", "X-Sample-Rate": str(first[0]), "X-Audio-Channels": "1"})
        async with aclosing(output):
            raw = bytearray()
            async for chunk in output:
                raw.extend(chunk)
                if len(raw) > first[0] * 2 * settings.limits.audio_seconds:
                    raise HTTPException(413, "Generated audio too long; use streaming")
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
        return Response(wav_bytes(samples, first[0]), media_type="audio/wav")

    @app.post("/v1/training/samples")
    async def sample(file: UploadFile = File(...), transcript: str = Form(..., min_length=1, max_length=1000),
                     consent: bool = Form(...), user=Depends(owner)):
        if not consent:
            raise HTTPException(422, "Confirm permission to train this audio")
        audio = await upload(file, 30)
        if len(audio) < 16000:
            raise HTTPException(422, "Training clips must be 1–30 seconds")
        return persist_sample(user, audio, transcript.strip())

    @app.post("/v1/voice-training/jobs", status_code=202)
    async def training(body: TrainingRequest, user=Depends(owner)):
        if not settings.training.enabled:
            raise HTTPException(503, "Training is disabled; enable it and start speech-worker")
        lookup("voice", user, body.voice_id)
        if len(set(body.sample_ids)) != len(body.sample_ids):
            raise HTTPException(422, "sample_ids must be unique")
        for sid in body.sample_ids:
            lookup("sample", user, sid)
        pending = [j for j in store.list("job", user) if j["status"] in ("queued", "running")]
        if len(pending) >= settings.training.max_pending:
            raise HTTPException(429, "Too many pending training jobs")
        return store.create("job", user, {**body.model_dump(), "status": "queued", "stage": "queued",
                                          "base_revision": settings.tts.revision})

    @app.get("/v1/voice-training/jobs/{job_id}")
    async def training_status(job_id: str, user=Depends(owner)):
        return lookup("job", user, job_id)

    @app.post("/v1/voice-training/jobs/{job_id}/cancel")
    async def cancel_training(job_id: str, user=Depends(owner)):
        job = lookup("job", user, job_id)
        if job["status"] in ("succeeded", "failed", "cancelled", "interrupted"):
            return job
        return store.update("job", user, job_id, cancel_requested=True)

    async def websocket(ws: WebSocket):
        try:
            user = authenticate(ws.headers)
        except HTTPException:
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            async with slot():
                raw = await asyncio.wait_for(ws.receive_text(), settings.limits.idle_seconds)
                if len(raw) > 8192:
                    raise ValueError("session.start too large")
                start = Start.model_validate_json(raw)
                route_mode = {"asr": "asr", "tts": "tts", "interpret": "interpret"}.get(ws.url.path.split("/")[2])
                if route_mode and route_mode != start.mode:
                    raise ValueError("Mode does not match endpoint")
                if start.mode != "tts":
                    services.require("asr")
                    if start.source_language != "zh":
                        raise ValueError("The paraformer adapter currently supports Chinese ASR only")
                if start.mode in ("interpret", "translate"):
                    services.require("translation")
                voice = None
                if start.mode in ("tts", "interpret"):
                    services.require("tts")
                    voice = voice_for(user, start.voice_id)
                await Session(ws, start, services, settings.limits, voice).run()
            await ws.close(code=1000)
        except WebSocketDisconnect:
            return
        except SessionCancelled:
            await ws.send_json({"type": "session.cancelled"})
            await ws.close(code=1000)
        except (ValueError, ValidationError, HTTPException, Unavailable, TimeoutError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            await ws.send_json({"type": "error", "message": detail[:500]})
            await ws.close(code=1008)
        except Exception:
            log.exception("Streaming request failed")
            try:
                await ws.send_json({"type": "error", "message": "Backend execution failed"})
                await ws.close(code=1011)
            except (WebSocketDisconnect, RuntimeError):
                pass

    for path in ("/v1/stream", "/v1/asr/stream", "/v1/tts/stream", "/v1/interpret/stream"):
        app.websocket(path)(websocket)
    return app
