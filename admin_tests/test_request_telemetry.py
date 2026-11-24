"""Request telemetry: what the app records for each request.

These run without the FastAPI test client. They call the ASGI middleware directly
against a small Starlette app and a temporary SQLite database.
"""

import asyncio
import os
import re
import sys
import tempfile

_DB_DIR = tempfile.mkdtemp(prefix="solobiz-telemetry-tests-")
os.environ.setdefault("SQLITE_DATABASE_PATH", os.path.join(_DB_DIR, "telemetry.db"))
os.environ.setdefault("ADMIN_SECRET_KEY", "test-admin-secret-key-that-is-long-enough-0123456789")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from starlette.applications import Starlette  # noqa: E402
from starlette.responses import PlainTextResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402

from server.database import get_db, init_db  # noqa: E402
from server.telemetry import RequestTelemetry  # noqa: E402

init_db()


def clear():
    with get_db() as db:
        db.execute("DELETE FROM request_minutes")
        db.execute("DELETE FROM request_errors")
        db.commit()


async def item(request):
    return PlainTextResponse("ok")


async def boom(request):
    raise RuntimeError("deliberate failure for the telemetry test")


async def static_like(request):
    return PlainTextResponse("file")


def build():
    inner = Starlette(routes=[
        Route("/items/{item_id}", item),
        Route("/boom", boom),
        Route("/static/{name}", static_like),
    ])
    return RequestTelemetry(inner, routes_getter=lambda: inner.router.routes)


async def call(app, path):
    sent = []
    body_sent = {"done": False}

    async def receive():
        if body_sent["done"]:
            return {"type": "http.disconnect"}
        body_sent["done"] = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "method": "GET", "path": path, "raw_path": path.encode(),
        "root_path": "", "query_string": b"token=secret-value", "headers": [],
        "scheme": "http", "server": ("test", 80), "client": ("test", 1), "http_version": "1.1",
    }
    await app(scope, receive, send)
    return sent


def rows(sql):
    with get_db() as db:
        return [dict(r) for r in db.execute(sql).fetchall()]


def test_successful_request_is_recorded_with_its_route_template_and_request_id():
    clear()
    sent = asyncio.run(call(build(), "/items/42"))
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 200
    header = dict(start["headers"])[b"x-request-id"].decode()
    assert re.fullmatch(r"[0-9a-f]{32}", header)
    recorded = rows("SELECT route, status_class, n FROM request_minutes")
    assert recorded == [{"route": "/items/{item_id}", "status_class": "2xx", "n": 1}]


def test_raw_path_and_query_values_are_never_stored():
    clear()
    asyncio.run(call(build(), "/items/12345"))
    stored = repr(rows("SELECT * FROM request_minutes")) + repr(rows("SELECT * FROM request_errors"))
    assert "12345" not in stored
    assert "token" not in stored
    assert "secret-value" not in stored


def test_server_error_is_recorded_in_full_and_the_exception_still_propagates():
    clear()
    try:
        asyncio.run(call(build(), "/boom"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("the application error should not be swallowed")
    errors = rows("SELECT route, status, duration_ms, request_id FROM request_errors")
    assert len(errors) == 1
    assert errors[0]["route"] == "/boom"
    assert errors[0]["status"] == 500
    assert re.fullmatch(r"[0-9a-f]{32}", errors[0]["request_id"])
    minutes = rows("SELECT status_class, n FROM request_minutes")
    assert minutes == [{"status_class": "5xx", "n": 1}]


def test_static_files_and_health_checks_are_not_counted():
    clear()
    asyncio.run(call(build(), "/static/logo.svg"))
    assert rows("SELECT * FROM request_minutes") == []


def test_repeat_requests_in_the_same_minute_are_added_together():
    clear()
    app = build()
    for _ in range(3):
        asyncio.run(call(app, "/items/1"))
    assert rows("SELECT n FROM request_minutes") == [{"n": 3}]
