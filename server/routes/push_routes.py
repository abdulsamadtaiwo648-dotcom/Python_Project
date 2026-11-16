"""Push notification subscription routes."""

from datetime import datetime, timezone
import re

from flask import jsonify, request, session

from .. import push
from ..app import app, get_current_user_id, get_db, record_user_activity

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")


def _unauthorized():
    return jsonify({"status": "error", "message": "Unauthorized"}), 401


@app.route("/api/push/config", methods=["GET"])
def push_config():
    if not get_current_user_id():
        return _unauthorized()
    return jsonify({
        "status": "success",
        "enabled": push.push_enabled(),
        "public_key": push.vapid_public_key() if push.push_enabled() else None,
    })


@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    user_id = get_current_user_id()
    if not user_id:
        return _unauthorized()
    if not push.push_enabled():
        return jsonify({"status": "error", "message": "Notifications are not set up on this server yet."}), 503

    data = request.get_json(silent=True) or {}
    subscription = data.get("subscription") if isinstance(data, dict) else None
    subscription = subscription if isinstance(subscription, dict) else {}
    keys = subscription.get("keys") if isinstance(subscription.get("keys"), dict) else {}
    endpoint = str(subscription.get("endpoint") or "")
    p256dh = str(keys.get("p256dh") or "")
    auth = str(keys.get("auth") or "")

    if not push.is_allowed_endpoint(endpoint):
        return jsonify({"status": "error", "message": "This browser's notification service is not supported."}), 400
    if not (_KEY_PATTERN.match(p256dh) and 80 <= len(p256dh) <= 100 and _KEY_PATTERN.match(auth) and 16 <= len(auth) <= 32):
        return jsonify({"status": "error", "message": "The notification subscription is invalid."}), 400

    with get_db() as db:
        existing = db.execute("SELECT user_id FROM push_subscriptions WHERE endpoint = ?", (endpoint,)).fetchone()
        # A device belongs to whoever is signed in on it now.
        db.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
        db.execute(
            "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, endpoint, p256dh, auth, datetime.now(timezone.utc).isoformat()),
        )
        if not existing or existing["user_id"] != user_id:
            record_user_activity(db, user_id, "push_enabled", "Turned on stock alert notifications on a device")
        db.commit()
    # Remembered so signing out stops this device receiving this account's alerts.
    session["push_endpoint"] = endpoint
    return jsonify({"status": "success", "message": "Notifications are on for this device."})


@app.route("/api/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    user_id = get_current_user_id()
    if not user_id:
        return _unauthorized()
    data = request.get_json(silent=True) or {}
    endpoint = str(data.get("endpoint") or "") if isinstance(data, dict) else ""
    with get_db() as db:
        db.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint))
        record_user_activity(db, user_id, "push_disabled", "Turned off stock alert notifications on a device")
        db.commit()
    session.pop("push_endpoint", None)
    return jsonify({"status": "success", "message": "Notifications are off for this device."})


@app.route("/api/push/test", methods=["POST"])
def push_test():
    user_id = get_current_user_id()
    if not user_id:
        return _unauthorized()
    if not push.push_enabled():
        return jsonify({"status": "error", "message": "Notifications are not set up on this server yet."}), 503
    delivered = push.send_to_user(user_id, [{
        "title": "SoloBiz alerts are on",
        "body": "You'll get a notification here when a product runs low or sells out.",
        "url": "/inventory",
        "tag": "solobiz-test",
    }], background=False)
    if not delivered:
        return jsonify({"status": "error", "message": "No device received the test. Turn notifications off and on again."}), 502
    return jsonify({"status": "success", "message": "Test notification sent.", "delivered": delivered})


def remove_session_push_subscription():
    """Called on sign-out so this device stops getting the account's alerts."""
    endpoint = session.get("push_endpoint")
    user_id = session.get("user_id")
    if not endpoint or not user_id:
        return
    with get_db() as db:
        db.execute("DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (str(user_id), endpoint))
        db.commit()
