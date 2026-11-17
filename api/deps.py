"""Request dependencies: signed-cookie session, CSRF and the signed-in user."""

import hmac
import logging
import secrets

from fastapi import Depends, HTTPException, Request

from server.database import get_db


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def csrf_ok(request: Request, sent: str = "") -> bool:
    expected = request.session.get("csrf_token") or ""
    sent = request.headers.get("X-CSRFToken") or sent or ""
    return bool(expected) and hmac.compare_digest(str(sent), str(expected))


def current_user_id(request: Request):
    """The signed-in user's id, or None. A cookie can outlive its account row."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user_id = str(user_id)
    try:
        with get_db() as db:
            row = db.execute("SELECT account_status FROM users WHERE id = ?", (user_id,)).fetchone()
        if row and row["account_status"] == "active":
            return user_id
    except Exception:
        logging.exception("Could not validate the active user session")
        return None
    request.session.clear()
    return None


def require_user(request: Request) -> str:
    user_id = current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user_id


UserId = Depends(require_user)
