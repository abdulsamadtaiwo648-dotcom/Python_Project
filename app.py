"""ASGI entry point: `uvicorn app:app` (the same app as `api.main:app`)."""

from api.main import app

__all__ = ["app"]
