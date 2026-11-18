"""Web-push subscription endpoints."""

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from server import push as push_service
from server.database import get_db

from .. import core
from ..deps import current_user_id, upgrade_required
from ..plans import ALERTS
from ..subscriptions import has_feature

router = APIRouter(prefix="/api/push")
_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")


def _err(message, status):
    return JSONResponse({"status": "error", "message": message}, status_code=status)


@router.get("/config")
def config(request: Request):
    if not current_user_id(request):
        return _err("Unauthorized", 401)
    enabled = push_service.push_enabled()
    return {"status": "success", "enabled": enabled, "public_key": push_service.vapid_public_key() if enabled else None}


@router.post("/subscribe")
async def subscribe(request: Request):
    user_id = current_user_id(request)
    if not user_id:
        return _err("Unauthorized", 401)
    if not push_service.push_enabled():
        return _err("Notifications are not set up on this server yet.", 503)
    if not has_feature(user_id, ALERTS):
        return upgrade_required("alerts", "Stock alerts are part of the Basic and Pro plans.")
    try:
        data = await request.json()
    except Exception:
        data = {}
    subscription = data.get("subscription") if isinstance(data, dict) else None
    subscription = subscription if isinstance(subscription, dict) else {}
    keys = subscription.get("keys") if isinstance(subscription.get("keys"), dict) else {}
    endpoint = str(subscription.get("endpoint") or "")
    p256dh = str(keys.get("p256dh") or "")
    auth = str(keys.get("auth") or "")
    if not push_service.is_allowed_endpoint(endpoint):
        return _err("This browser's notification service is not supported.", 400)
    if not (_KEY_PATTERN.match(p256dh) and 80 <= len(p256dh) <= 100 and _KEY_PATTERN.match(auth) and 16 <= len(auth) <= 32):
        return _err("The notification subscription is invalid.", 400)
    with get_db() as db:
        existing = db.execute("SELECT user_id FROM push_subscriptions WHERE endpoint = ?", (endpoint,)).fetchone()
        # A device belongs to whoever is signed in on it now.
        db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        db.execute(
            "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, endpoint, p256dh, auth, datetime.now(timezone.utc).isoformat()),
        )
        if not existing or existing["user_id"] != user_id:
            core.record_user_activity(db, user_id, "push_enabled", "Turned on stock alert notifications on a device")
        db.commit()
    request.session["push_endpoint"] = endpoint
    return {"status": "success", "message": "Notifications are on for this device."}


@router.post("/unsubscribe")
async def unsubscribe(request: Request):
    user_id = current_user_id(request)
    if not user_id:
        return _err("Unauthorized", 401)
    try:
        data = await request.json()
    except Exception:
        data = {}
    endpoint = str(data.get("endpoint") or "") if isinstance(data, dict) else ""
    with get_db() as db:
        db.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))
        core.record_user_activity(db, user_id, "push_disabled", "Turned off stock alert notifications on a device")
        db.commit()
    request.session.pop("push_endpoint", None)
    return {"status": "success", "message": "Notifications are off for this device."}


@router.post("/test")
def test(request: Request):
    user_id = current_user_id(request)
    if not user_id:
        return _err("Unauthorized", 401)
    if not push_service.push_enabled():
        return _err("Notifications are not set up on this server yet.", 503)
    delivered = push_service.send_to_user(user_id, [{
        "title": "SoloBiz alerts are on",
        "body": "You'll get a notification here when a product runs low or sells out.",
        "url": "/inventory",
        "tag": "solobiz-test",
    }], background=False)
    if not delivered:
        return _err("No device received the test. Turn notifications off and on again.", 502)
    return {"status": "success", "message": "Test notification sent.", "delivered": delivered}


def remove_session_push_subscription(request: Request):
    endpoint = request.session.get("push_endpoint")
    user_id = request.session.get("user_id")
    if not endpoint or not user_id:
        return
    with get_db() as db:
        db.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (str(user_id), endpoint))
        db.commit()
