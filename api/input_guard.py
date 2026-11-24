"""Refuse JSON API input that carries script or active markup.

SoloBiz never stores HTML: names, notes, products and prices are plain text, and
the front end shows them as text. So a value that contains a script tag, an event
handler inside a tag, or a javascript: link is never legitimate. Refusing it at the
API boundary means such text is not stored, and cannot reach a page even if some
later code forgets to escape it. Output escaping remains the primary defence.
"""

import json
import re

from starlette.responses import JSONResponse

MAX_BODY_BYTES = 1_000_000
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Tags that run code or load active content, an event handler inside any tag,
# and script-style URLs. Plain tags such as <b> are not blocked.
UNSAFE = re.compile(
    r"<\s*/?\s*(script|iframe|object|embed|svg|math|img|link|meta|style|base|form|input|body|html)\b"
    r"|<[^>]{0,200}\son[a-z]+\s*="
    r"|javascript\s*:"
    r"|vbscript\s*:"
    r"|data\s*:\s*text/html",
    re.IGNORECASE,
)


def find_unsafe(value, path: str = "") -> str | None:
    """Return the location of the first unsafe string in a decoded JSON value."""
    if isinstance(value, str):
        return path or "value" if UNSAFE.search(value) else None
    if isinstance(value, dict):
        for key, item in value.items():
            hit = find_unsafe(item, f"{path}.{key}" if path else str(key))
            if hit:
                return hit
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hit = find_unsafe(item, f"{path}[{index}]")
            if hit:
                return hit
    return None


class InputGuard:
    """Pure ASGI middleware. It reads the JSON body once, then replays it to the app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] not in WRITE_METHODS
            or not scope["path"].startswith("/api/")
            or "application/json" not in dict(scope["headers"]).get(b"content-type", b"").decode("latin-1")
        ):
            return await self.app(scope, receive, send)

        messages = []
        body = b""
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            if len(body) > MAX_BODY_BYTES:
                response = JSONResponse(
                    {"status": "error", "message": "The request is too large."}, status_code=413
                )
                return await response(scope, receive, send)
            if not message.get("more_body", False):
                break

        try:
            decoded = json.loads(body or b"null")
        except ValueError:
            decoded = None  # Not valid JSON: the route's own parsing will reject it.

        location = find_unsafe(decoded)
        if location:
            response = JSONResponse(
                {"status": "error", "message": f"Remove script or markup from {location} and try again."},
                status_code=400,
            )
            return await response(scope, receive, send)

        pending = list(messages)

        async def replay():
            if pending:
                return pending.pop(0)
            return await receive()

        return await self.app(scope, replay, send)
