"""Fixtures for the FastAPI backend. The database is a throwaway SQLite file
chosen before `api.main` imports, because the app initialises it on import."""

import base64
import contextlib
import json
import os
import tempfile
import uuid

import pytest

_TEMP_DIR = tempfile.mkdtemp(prefix="solobiz-api-tests-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("RENDER", None)
os.environ["SQLITE_DATABASE_PATH"] = os.path.join(_TEMP_DIR, "solobiz.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ["ALLOW_DEV_OTP"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from itsdangerous import TimestampSigner  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from api import pages  # noqa: E402
from api.main import app as fastapi_app  # noqa: E402
from api.settings import settings  # noqa: E402
from server.database import get_db  # noqa: E402

PASSWORD = "Password123"


class Client(TestClient):
    """TestClient with a Flask-style `base_url=` and `data={"file": (io, name)}`."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("follow_redirects", False)
        super().__init__(*args, **kwargs)

    @contextlib.contextmanager
    def session_transaction(self):
        """Read and rewrite the signed session cookie, like Flask's test client."""
        signer = TimestampSigner(settings.secret_key)
        session, domain = {}, "testserver.local"
        for cookie in list(self.cookies.jar):
            if cookie.name == "session":
                domain = cookie.domain
                try:
                    session = json.loads(base64.b64decode(signer.unsign(cookie.value.encode())))
                except Exception:
                    session = {}
                self.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
        yield session
        value = signer.sign(base64.b64encode(json.dumps(session).encode())).decode()
        self.cookies.set("session", value, domain=domain)

    def request(self, method, url, *args, base_url=None, data=None, content_type=None, **kwargs):
        if base_url:
            kwargs.setdefault("headers", {})
            kwargs["headers"] = {**kwargs["headers"], "host": base_url.split("://", 1)[-1]}
        if isinstance(data, dict) and any(isinstance(v, tuple) for v in data.values()):
            files = {k: (v[1], v[0]) for k, v in data.items() if isinstance(v, tuple)}
            data = {k: v for k, v in data.items() if not isinstance(v, tuple)}
            kwargs["files"] = files
        return super().request(method, url, *args, data=data, **kwargs)


for _verb in ("get", "post", "put", "delete", "patch", "head"):
    setattr(Client, _verb, (lambda verb: lambda self, url, **kw: self.request(verb.upper(), url, **kw))(_verb))


def new_client():
    return Client(fastapi_app)


def csrf_token(client):
    """Load the session so the cookie holds a CSRF token, then return it."""
    return client.get("/api/session").json()["csrf_token"]


def make_user(password=PASSWORD):
    user_id = f"user_test_{uuid.uuid4().hex[:10]}"
    email = f"{user_id}@example.com"
    with get_db() as db:
        db.execute(
            "INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, generate_password_hash(password), "Test", "User"),
        )
        db.commit()
    return user_id, email


def sign_in(client, email, password=PASSWORD):
    token = csrf_token(client)
    response = client.post("/api/login", json={"email": email, "password": password}, headers={"X-CSRFToken": token})
    return response, token


@pytest.fixture
def client():
    with new_client() as test_client:
        yield test_client


@pytest.fixture
def user():
    return make_user()


@pytest.fixture
def signed_in(client, user):
    """Sign `user` in on `client`; return (user_id, csrf_token)."""
    response, token = sign_in(client, user[1])
    assert response.status_code == 200, response.text
    # Signing in keeps the same CSRF token.
    return user[0], csrf_token(client)


# --- Compatibility shims so the Flask-era test bodies run unchanged ---------
import httpx  # noqa: E402

httpx.Response.get_json = lambda self: self.json()
httpx.Response.get_data = lambda self, as_text=False: self.text if as_text else self.content
# Starlette's test client now returns httpx2 responses, so give those the same helpers.
try:
    import httpx2

    httpx2.Response.get_json = lambda self: self.json()
    httpx2.Response.get_data = lambda self, as_text=False: self.text if as_text else self.content
except ImportError:  # httpx2 is only needed by newer Starlette versions
    pass


class _AppShim:
    """Stand-in for the Flask app fixture: hands out independent clients."""

    @staticmethod
    def test_client():
        return new_client()


@pytest.fixture
def app():
    return _AppShim()


def sign_in_as(user_id_email):
    """A fresh client signed in as the given (user_id, email); returns (client, token)."""
    other = new_client()
    response, token = sign_in(other, user_id_email[1])
    assert response.status_code == 200
    return other, token


@pytest.fixture(autouse=True)
def built_app_shell(tmp_path, monkeypatch):
    """Pretend the React build exists so page routes can be checked on their own."""
    (tmp_path / "index.html").write_text("<!doctype html><title>SoloBiz</title><div id=root></div>")
    monkeypatch.setattr(pages, "WEB_DIST", tmp_path)
