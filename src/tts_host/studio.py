"""Same-origin studio assets and owner-scoped read APIs; no user files are static."""
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders

WEB = Path(__file__).parent / "web"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
       "frame-ancestors 'none'; form-action 'self'")


class StudioHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def headers_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                path = scope.get("path", "")
                if path == "/" or path.startswith("/studio/"):
                    headers["Content-Security-Policy"] = CSP
                if path.startswith("/v1/") or path == "/":
                    headers["Cache-Control"] = "no-store"
            await send(message)
        await self.app(scope, receive, headers_send)


def install_studio(app, store, settings, owner):
    app.add_middleware(StudioHeaders)

    @app.get("/", include_in_schema=False)
    async def index():
        if not (WEB / "index.html").is_file():
            raise HTTPException(503, "Studio not built. Run npm ci && npm run build in frontend/.")
        return FileResponse(WEB / "index.html")

    app.mount("/studio", StaticFiles(directory=WEB, check_dir=False), name="studio")

    @app.get("/v1/studio/config")
    async def config(user=Depends(owner)):
        return {"limits": settings.limits.model_dump(), "training_enabled": settings.training.enabled}

    @app.get("/v1/training/samples")
    async def samples(user=Depends(owner)):
        return {"samples": store.list("sample", user)}

    @app.get("/v1/training/samples/{sample_id}/audio")
    async def sample_audio(sample_id: str, user=Depends(owner)):
        try:
            store.get("sample", user, sample_id)
            path = store.asset(sample_id)
        except (KeyError, ValueError):
            raise HTTPException(404, "Sample not found")
        if not path.is_file():
            raise HTTPException(404, "Sample audio is unavailable")
        return FileResponse(path, media_type="audio/wav")

    @app.get("/v1/voice-training/jobs")
    async def jobs(user=Depends(owner)):
        return {"jobs": list(reversed(store.list("job", user)))}
