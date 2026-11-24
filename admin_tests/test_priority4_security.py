"""Sign-in limits, refused-input records, security headers and removed pages on the main app.
Called through ASGI, so these run without the FastAPI test client."""

import asyncio
import base64
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
os.environ.setdefault("SQLITE_DATABASE_PATH", os.path.join(tempfile.mkdtemp(prefix="solobiz-p4-"), "p4.db"))
os.environ.setdefault("SECRET_KEY", "priority-four-test-secret-key-long-enough-0123456789")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("RENDER", None)

import pytest  # noqa: E402
from itsdangerous import TimestampSigner  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from api import core  # noqa: E402
from api.main import app  # noqa: E402
from api.settings import settings  # noqa: E402
from server.database import get_db  # noqa: E402

CSRF = "p4-csrf-token"
PASSWORD = "Password123"


def cookie_for(user_id):
    data = {"csrf_token": CSRF}
    if user_id:
        data["user_id"] = user_id
    payload = base64.b64encode(json.dumps(data).encode())
    return TimestampSigner(settings.secret_key).sign(payload).decode()


async def _call(method, path, body=None, user_id=None, client_ip="127.0.0.1", extra=()):
    raw = json.dumps(body).encode() if body is not None else b""
    headers = [(b"host", b"testserver.local"), (b"content-type", b"application/json"),
               (b"content-length", str(len(raw)).encode())]
    headers += [(b"cookie", f"session={cookie_for(user_id)}".encode()), (b"x-csrftoken", CSRF.encode())]
    headers += [(k.encode(), v.encode()) for k, v in extra]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
             "headers": headers, "client": (client_ip, 50000), "server": ("testserver.local", 80)}
    sent, delivered = [], [False]

    async def receive():
        if not delivered[0]:
            delivered[0] = True
            return {"type": "http.request", "body": raw, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    text = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    headers_out = {k.decode(): v.decode() for k, v in start["headers"]}
    try:
        payload = json.loads(text) if text else None
    except ValueError:
        payload = text.decode("utf-8", "replace")  # an HTML page, such as the 404 page
    return start["status"], payload, headers_out


def call(*args, **kwargs):
    return asyncio.run(_call(*args, **kwargs))


@pytest.fixture(autouse=True)
def clear_sign_in_counters():
    with get_db() as db:
        db.execute("DELETE FROM user_login_attempts")
        db.commit()


@pytest.fixture
def account():
    user_id = "p4-" + uuid.uuid4().hex[:10]
    email = f"{user_id}@example.test"
    with get_db() as db:
        db.execute("INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                   (user_id, email, generate_password_hash(PASSWORD), "P4", "Tester"))
        db.commit()
    return user_id, email


LOGIN = "/api/login"  # the sign-in POST; GET /login is the page


def login_call(email, password, ip):
    return call("POST", LOGIN, {"email": email, "password": password}, client_ip=ip)


# --- Sign-in limits ---------------------------------------------------------------

def test_an_account_locks_after_five_wrong_passwords(account):
    _, email = account
    for _ in range(5):
        assert login_call(email, "nope", "198.51.100.1")[0] == 401
    status, body, _ = login_call(email, "nope", "198.51.100.2")
    assert status == 429
    assert "Too many sign-in attempts" in body["message"]


def test_an_address_locks_after_thirty_failures_across_accounts(account):
    ip = "198.51.100.50"
    for index in range(30):
        status, _, _ = login_call(f"nobody-{index}@example.test", "nope", ip)
        assert status == 401
    assert login_call("someone-new@example.test", "nope", ip)[0] == 429
    # A different address is not affected.
    assert login_call("someone-else@example.test", "nope", "198.51.100.51")[0] == 401


def test_a_successful_sign_in_clears_the_account_counter_but_not_the_address_counter(account):
    user_id, email = account
    ip = "198.51.100.77"
    for _ in range(4):
        login_call(email, "nope", ip)
    status, body, _ = login_call(email, PASSWORD, ip)
    assert status == 200, body
    with get_db() as db:
        rows = {row["attempts"] for row in db.execute("SELECT attempts FROM user_login_attempts").fetchall()}
    assert 4 in rows  # the address still has its four failures
    assert core._locked_until_key(core._attempt_key("email", email)) is None


# --- Removed pages and headers ---------------------------------------------------------

def test_user_count_is_not_served(account):
    status, body, _ = call("GET", "/user-count")
    assert status == 404


def test_responses_carry_the_security_headers(account):
    status, _, headers = call("GET", "/login")
    assert status == 200
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "SAMEORIGIN"
    assert headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_a_refused_request_still_carries_the_headers(account):
    user_id, _ = account
    _, _, headers = call("POST", "/api/income", {"description": "<script>x</script>"}, user_id)
    assert headers["x-content-type-options"] == "nosniff"


# --- Refused input is recorded, without its value --------------------------------------

def events_for(user_id, event_type):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT event_type, summary FROM user_activity_logs WHERE user_id = ? AND event_type = ?",
            (user_id, event_type)).fetchall()]


def test_markup_refusal_is_recorded_against_the_account_without_the_value(account):
    user_id, _ = account
    status, _, _ = call("POST", "/api/income", {"description": "<img src=x onerror=alert(1)>", "total_value": 5,
                                                 "amount_paid": 5, "payment_mode": "Cash"}, user_id)
    assert status == 400
    rows = events_for(user_id, "input_rejected")
    assert len(rows) == 1
    assert "description" in rows[0]["summary"]
    assert "<img" not in rows[0]["summary"] and "alert" not in rows[0]["summary"]


def test_a_limit_refusal_is_recorded_against_the_account(account):
    user_id, _ = account
    status, _, _ = call("POST", "/api/income", {"description": "d" * 201, "total_value": 5, "amount_paid": 5,
                                                 "payment_mode": "Cash"}, user_id)
    assert status == 400
    rows = events_for(user_id, "input_rejected")
    assert rows and "description too long" in rows[0]["summary"]
    assert "ddddd" not in rows[0]["summary"]


def test_a_refusal_with_no_signed_in_account_is_not_recorded(account):
    before = len(events_for("nobody", "input_rejected"))
    call("POST", "/api/income", {"description": "<script>x</script>"})
    assert len(events_for("nobody", "input_rejected")) == before
