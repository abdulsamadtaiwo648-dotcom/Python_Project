"""Request telemetry for the SoloBiz app.

What is recorded for each request (never the raw path, query, headers, cookies or body):

* request_minutes: one row per minute, route template and status class, with the
  number of requests and how many fell into each duration bucket.
* request_errors: one row per server error (status 500 or above), with its request ID,
  route template, status and duration, so a failure can be traced.

The admin System status page reads these tables. Old rows are removed automatically:
errors after 30 days, minute totals after 90 days.
"""

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from starlette.routing import Match

from .database import get_db

SKIP_PREFIXES = ("/static/", "/assets/", "/healthz", "/favicon")
ERROR_RETENTION = timedelta(days=30)
MINUTE_RETENTION = timedelta(days=90)
PRUNE_EVERY = timedelta(hours=1)

# Duration buckets, in milliseconds. The column names are constants, never user input.
BUCKETS = (
    (250, "ms_lt_250"),
    (500, "ms_lt_500"),
    (1000, "ms_lt_1000"),
    (2500, "ms_lt_2500"),
    (5000, "ms_lt_5000"),
    (None, "ms_gte_5000"),
)
BUCKET_COLUMNS = tuple(column for _, column in BUCKETS)

_last_prune = None


def bucket_column(elapsed_ms):
    for limit, column in BUCKETS:
        if limit is None or elapsed_ms < limit:
            return column
    return BUCKETS[-1][1]


def status_class(status):
    return f"{int(status) // 100}xx"


def route_template(routes, scope):
    """The route pattern that handled this request, such as /api/sales/{sale_id}.
    Routers included with include_router are nested, so the search descends into them."""
    for route in routes:
        try:
            match, _ = route.matches(scope)
        except Exception:
            continue
        if match != Match.FULL:
            continue
        path = getattr(route, "path", None)
        if path:
            return path
        nested = getattr(route, "routes", None) or getattr(getattr(route, "original_router", None), "routes", None)
        if nested:
            found = route_template(nested, scope)
            if found != "unmatched":
                return found
    return "unmatched"


def _minute_key(when):
    return when.strftime("%Y-%m-%dT%H:%M")


def record(route, status, elapsed_ms, request_id, when):
    column = bucket_column(elapsed_ms)
    minute = _minute_key(when)
    cls = status_class(status)
    with get_db() as db:
        db.execute(
            "INSERT INTO request_minutes (minute, route, status_class, n, total_ms, " + column + ") "
            "VALUES (?, ?, ?, 1, ?, 1) "
            "ON CONFLICT (minute, route, status_class) DO UPDATE SET "
            "n = request_minutes.n + 1, "
            "total_ms = request_minutes.total_ms + excluded.total_ms, "
            + column + " = request_minutes." + column + " + 1",
            (minute, route, cls, int(elapsed_ms)),
        )
        if int(status) >= 500:
            db.execute(
                "INSERT INTO request_errors (request_id, created_at, route, status, duration_ms) "
                "VALUES (?, ?, ?, ?, ?)",
                (request_id, when.isoformat(), route, int(status), int(elapsed_ms)),
            )
        db.commit()


def prune(now):
    global _last_prune
    if _last_prune and now - _last_prune < PRUNE_EVERY:
        return
    _last_prune = now
    try:
        with get_db() as db:
            db.execute("DELETE FROM request_errors WHERE created_at < ?", ((now - ERROR_RETENTION).isoformat(),))
            db.execute("DELETE FROM request_minutes WHERE minute < ?", (_minute_key(now - MINUTE_RETENTION),))
            db.commit()
    except Exception:
        logging.exception("Could not remove old request telemetry")


class RequestTelemetry:
    """Pure ASGI middleware. It never changes the response, except to add an X-Request-ID header."""

    def __init__(self, app, routes_getter):
        self.app = app
        self.routes_getter = routes_getter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith(SKIP_PREFIXES):
            return await self.app(scope, receive, send)

        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        routing_scope = dict(scope)  # the path as requested, before any routing changes it
        state = {"status": 500}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            self._save(routing_scope, state["status"], elapsed_ms, request_id)

    def _save(self, routing_scope, status, elapsed_ms, request_id):
        now = datetime.now(timezone.utc)
        try:
            route = route_template(self.routes_getter(), routing_scope)
            record(route, status, elapsed_ms, request_id, now)
            prune(now)
        except Exception:
            logging.exception("Could not record request telemetry")
