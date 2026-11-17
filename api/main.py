"""FastAPI application: JSON API, server-rendered public pages, React app."""

import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from server import websites
from server.database import get_db, init_db

from .deps import csrf_ok
from . import pages
from .settings import CLIENT_ROOT, WEB_DIST, settings

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def error(message, status=400):
    return JSONResponse({"status": "error", "message": message}, status_code=status)


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="SoloBiz", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        # Inside SessionMiddleware, so the session cookie is readable here.
        if request.method not in SAFE_METHODS and not csrf_ok(request):
            return error("Invalid request token. Refresh the page and try again.", 400)
        op_id = (request.headers.get("X-Client-Op") or "")[:80]
        user_id = request.session.get("user_id") if op_id and request.method not in SAFE_METHODS else None
        if user_id:
            with get_db() as db:
                seen = db.execute("SELECT 1 FROM client_ops WHERE user_id = ? AND op_id = ?", (str(user_id), op_id)).fetchone()
            if seen:
                return JSONResponse({"status": "success", "duplicate": True, "message": "Already saved."})
        response = await call_next(request)
        if user_id and response.status_code < 400:
            try:
                with get_db() as db:
                    db.execute("INSERT INTO client_ops (user_id, op_id, created_at) VALUES (?, ?, ?)",
                               (str(user_id), op_id, datetime.now(timezone.utc).isoformat()))
                    db.commit()
            except Exception:
                logging.exception("Could not remember offline operation %s", op_id)
        return response

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="session",
        max_age=settings.session_days * 86400,
        same_site="lax",
        https_only=settings.secure_cookie,
    )

    # Outermost: a business subdomain must never touch sessions or the app.
    app.add_middleware(BaseHTTPMiddleware, dispatch=pages.business_subdomain_middleware)

    def wants_json(request: Request):
        return request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", "")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404 and not wants_json(request):
            from .pages import render, site_404

            if websites.site_label_for_host(request.headers.get("host", "")):
                return site_404(request)
            return render(request, "404.html", status=404)
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        if exc.status_code == 404:
            message = "The requested resource was not found."
        return error(message, exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logging.error("Unhandled server exception: %s", exc, exc_info=True)
        if not wants_json(request):
            from .pages import render

            return render(request, "500.html", status=500)
        return error("An internal server error occurred. Please try again later.", 500)

    @app.get("/healthz")
    def healthz():
        try:
            with get_db() as db:
                db.execute("SELECT 1").fetchone()
        except Exception:
            logging.exception("Health check could not reach the database")
            return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
        return JSONResponse(
            {"status": "ok", "version": settings.app_version, "commit": (os.environ.get("RENDER_GIT_COMMIT") or "")[:7]},
            headers={"Cache-Control": "no-store"},
        )

    from .routers import auth, dashboard, expenses, inventory, profile, push, sales, website

    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(CLIENT_ROOT / "static")), name="static")
    if (WEB_DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="assets")
    app.include_router(pages.router)
    for module in (auth, push, dashboard, sales, expenses, inventory, profile, website):
        app.include_router(module.router)
    return app


app = create_app()
