"""Runtime configuration, read once from the environment."""

import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIENT_ROOT = PROJECT_ROOT / "client"
WEB_DIST = PROJECT_ROOT / "web" / "dist"


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    secret_key: str
    is_hosted: bool
    secure_cookie: bool
    app_version: str
    max_upload_bytes: int = 3 * 1024 * 1024
    session_days: int = 30


def load_settings() -> Settings:
    hosted = bool(os.environ.get("DATABASE_URL") or os.environ.get("RENDER"))
    key = os.environ.get("SECRET_KEY")
    if not key:
        if hosted:
            # A known key would let anyone forge a session cookie.
            raise RuntimeError("Set the SECRET_KEY environment variable before starting SoloBiz.")
        key = secrets.token_urlsafe(48)
        logging.warning("SECRET_KEY is not set; using a random development key. Sessions will not survive a restart.")
    secure = os.environ.get("SESSION_COOKIE_SECURE")
    return Settings(
        secret_key=key,
        is_hosted=hosted,
        secure_cookie=hosted if secure is None else _truthy(secure),
        app_version=os.environ.get("APP_VERSION", "20261111.1"),
    )


settings = load_settings()
