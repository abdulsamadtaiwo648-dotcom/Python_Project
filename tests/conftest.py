"""Shared fixtures. The app initialises its database at import time, so the
environment must point at a throwaway SQLite file before `server.app` loads."""

import os
import tempfile
import uuid

import pytest

_TEMP_DIR = tempfile.mkdtemp(prefix="solobiz-tests-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("RENDER", None)
os.environ["SQLITE_DATABASE_PATH"] = os.path.join(_TEMP_DIR, "solobiz.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ["ALLOW_DEV_OTP"] = "1"

from werkzeug.security import generate_password_hash  # noqa: E402

from server.app import app as flask_app, get_db  # noqa: E402

PASSWORD = "Password123"


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def user():
    """Create a fresh active account and return (user_id, email)."""
    user_id = f"user_test_{uuid.uuid4().hex[:10]}"
    email = f"{user_id}@example.com"
    with get_db() as db:
        db.execute(
            "INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, generate_password_hash(PASSWORD), "Test", "User"),
        )
        db.commit()
    return user_id, email


def csrf_token(client):
    """Load a page so the session holds a CSRF token, then return it."""
    client.get("/privacy")
    with client.session_transaction() as sess:
        return sess["csrf_token"]


@pytest.fixture
def signed_in(client, user):
    """Sign `user` in on `client`; return (user_id, csrf_token)."""
    token = csrf_token(client)
    with client.session_transaction() as sess:
        sess["user_id"] = user[0]
    return user[0], token
