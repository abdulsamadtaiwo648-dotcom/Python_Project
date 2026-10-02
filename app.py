"""Compatibility entry point for hosts using `gunicorn app:app`."""

from server.app import app

__all__ = ["app"]
