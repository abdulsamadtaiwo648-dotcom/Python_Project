"""FastAPI application: JSON API, server-rendered public pages, React app."""

import logging
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from server.database import init_db

from .deps import csrf_ok, ensure_csrf_token
from .settings import settings

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def error(message, status=400):
    return JSONResponse({"status": "error", "message": message}, status_code=status)


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="SoloBiz", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # Registered before SessionMiddleware so the session is available.
        if request.method in SAFE_METHODS:
            ensure_csrf_token(request)
        elif request.url.path.startswith("/api/") and not csrf_ok(request):
            return error("Invalid request token. Refresh the page and try again.", 400)
        return await call_next(request)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="session",
        max_age=settings.session_days * 86400,
        same_site="lax",
        https_only=settings.secure_cookie,
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        if exc.status_code == 404:
            message = "The requested resource was not found."
        return error(message, exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logging.error("Unhandled server exception: %s", exc, exc_info=True)
        return error("An internal server error occurred. Please try again later.", 500)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    from .routers import auth, push
    app.include_router(auth.router)
    app.include_router(push.router)
    return app


app = create_app()
