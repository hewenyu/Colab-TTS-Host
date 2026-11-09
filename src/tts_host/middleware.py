from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException


class BodyTooLarge(HTTPException):
    def __init__(self):
        super().__init__(413, "Request too large")


class RequestGuard:
    """Authenticate before multipart parsing and bound actual bytes, including chunked HTTP."""
    def __init__(self, app, authenticate, max_bytes):
        self.app, self.authenticate, self.max_bytes = app, authenticate, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        from fastapi import HTTPException
        from starlette.datastructures import Headers
        headers = Headers(scope=scope)
        if scope["path"].startswith("/v1/"):
            try:
                self.authenticate(headers)
            except HTTPException as exc:
                return await JSONResponse({"detail": exc.detail}, exc.status_code)(scope, receive, send)
        total = 0
        started = False
        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                raise BodyTooLarge()
            return message
        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        try:
            await self.app(scope, limited_receive, tracked_send)
        except BodyTooLarge:
            if not started:
                await JSONResponse({"detail": "Request too large"}, 413)(scope, receive, send)
