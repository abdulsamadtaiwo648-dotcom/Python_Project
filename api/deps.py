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


def _load_actor(request: Request):
    """Resolve the signed-in account once: the owner, or a staff member working for one."""
    from . import permissions as perm  # local import: permissions imports this module's database helpers

    login_id = request.session.get("user_id")
    if not login_id:
        return None
    login_id = str(login_id)
    try:
        with get_db() as db:
            row = db.execute("SELECT account_status FROM users WHERE id = ?", (login_id,)).fetchone()
            if not row or row["account_status"] != "active":
                request.session.clear()
                return None
            staff = perm.staff_row(db, login_id)
            if not staff:
                return {"user_id": login_id, "owner_id": login_id, "is_staff": False,
                        "pages": set(perm.PAGES), "role": "owner"}
            owner = db.execute("SELECT account_status FROM users WHERE id = ?", (staff["owner_id"],)).fetchone()
    except Exception:
        logging.exception("Could not validate the active user session")
        return None
    if not owner or owner["account_status"] != "active":
        return {"user_id": login_id, "owner_id": staff["owner_id"], "is_staff": True,
                "pages": set(), "role": staff["role"]}
    # Staff are switched off if the owner's plan has no seat for them.
    pages = set(perm.staff_pages(staff)) if perm.staff_in_seats(staff["owner_id"], login_id) else set()
    return {"user_id": login_id, "owner_id": staff["owner_id"], "is_staff": True,
            "pages": pages, "role": staff["role"]}


def current_user_id(request: Request):
    """The business id this request works on: the owner's own id, or the owner's
    id for a staff member. None when nobody is signed in."""
    who = actor_for(request)
    return who["owner_id"] if who else None


def actor_for(request: Request):
    from .permissions import actor
    return actor(request)


def require_user(request: Request) -> str:
    user_id = current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return user_id


UserId = Depends(require_user)


def upgrade_required(feature, message):
    """The answer when a plan does not include what was asked for."""
    from fastapi.responses import JSONResponse

    return JSONResponse({"status": "error", "code": "upgrade_required", "feature": feature, "message": message}, status_code=403)
