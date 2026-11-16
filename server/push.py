"""Web Push notifications (VAPID) for SoloBiz alerts.

Push is enabled when these environment variables are set:
  VAPID_PUBLIC_KEY   base64url uncompressed P-256 public key (given to browsers)
  VAPID_PRIVATE_KEY  base64url raw 32-byte P-256 private key (kept secret)
  VAPID_SUBJECT      contact for push services, e.g. mailto:you@example.com
Generate a key pair with `python -m server.tools.generate_vapid_keys`.
"""

import json
import logging
import os
import threading
from urllib.parse import urlsplit

from .database import get_db

try:
    from pywebpush import WebPushException, webpush
    HAS_WEBPUSH = True
except ImportError:  # pragma: no cover - the dependency is in requirements.txt
    HAS_WEBPUSH = False

# Browsers hand out endpoints on these push services only. Refusing anything
# else stops a crafted "subscription" from making the server call other hosts.
ALLOWED_PUSH_HOST_SUFFIXES = (
    ".googleapis.com",      # Chrome, Edge (FCM), Android
    ".mozilla.com",         # Firefox
    ".mozaws.net",          # Firefox (legacy)
    ".notify.windows.com",  # Edge on Windows (WNS)
    ".push.apple.com",      # Safari / iOS home-screen apps
)

# When True (tests), notifications are sent before the request returns.
SEND_INLINE = False


def vapid_public_key():
    return (os.environ.get("VAPID_PUBLIC_KEY") or "").strip()


def push_enabled():
    return HAS_WEBPUSH and bool(vapid_public_key() and (os.environ.get("VAPID_PRIVATE_KEY") or "").strip())


def _vapid_claims():
    subject = (os.environ.get("VAPID_SUBJECT") or "https://solobiz.dev").strip()
    return {"sub": subject}


def is_allowed_endpoint(endpoint):
    try:
        parts = urlsplit(str(endpoint or ""))
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and len(str(endpoint)) <= 1000
        and any(host == suffix[1:] or host.endswith(suffix) for suffix in ALLOWED_PUSH_HOST_SUFFIXES)
    )


def _subscriptions_for(user_id):
    with get_db() as db:
        rows = db.execute(
            "SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?",
            (str(user_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def _remove_subscription(subscription_id):
    with get_db() as db:
        db.execute("DELETE FROM push_subscriptions WHERE id = ?", (subscription_id,))
        db.commit()


def _deliver(user_id, notifications):
    """Send each notification to every device the user subscribed. Returns the
    number of successful deliveries."""
    delivered = 0
    for subscription in _subscriptions_for(user_id):
        info = {
            "endpoint": subscription["endpoint"],
            "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
        }
        for notification in notifications:
            try:
                webpush(
                    subscription_info=info,
                    data=json.dumps(notification),
                    vapid_private_key=os.environ["VAPID_PRIVATE_KEY"].strip(),
                    vapid_claims=_vapid_claims(),
                    ttl=24 * 60 * 60,
                    timeout=10,
                )
                delivered += 1
            except WebPushException as error:
                status = getattr(getattr(error, "response", None), "status_code", None)
                if status in (404, 410):
                    # The browser revoked this subscription; stop sending to it.
                    _remove_subscription(subscription["id"])
                    break
                logging.warning("Push to subscription %s failed: %s", subscription["id"], error)
            except Exception:
                logging.exception("Push to subscription %s failed", subscription["id"])
    return delivered


def send_to_user(user_id, notifications, background=True):
    """Queue notifications for a user. Each notification is a dict with
    title, body, url and tag. Never raises."""
    if not notifications or not push_enabled():
        return 0
    if background and not SEND_INLINE:
        threading.Thread(target=_deliver, args=(user_id, notifications), daemon=True).start()
        return None
    try:
        return _deliver(user_id, notifications)
    except Exception:
        logging.exception("Could not send push notifications for user %s", user_id)
        return 0


def stock_level(stock, threshold):
    stock = int(stock or 0)
    if stock <= 0:
        return "out"
    return "low" if stock <= int(threshold if threshold is not None else 3) else "ok"


def low_stock_notifications(changes):
    """Build alerts for products whose stock just crossed into low or out.

    `changes` is an iterable of dicts: id, item_name, before, after, threshold.
    """
    notifications = []
    for change in changes:
        before = stock_level(change["before"], change["threshold"])
        after = stock_level(change["after"], change["threshold"])
        if after == before or after == "ok":
            continue
        if after == "low" and before != "ok":
            continue
        name = change["item_name"]
        if after == "out":
            notifications.append({
                "title": f"Out of stock: {name}",
                "body": f"{name} has sold out. Tap to restock.",
                "url": "/inventory",
                "tag": f"stock-{change['id']}",
            })
        else:
            notifications.append({
                "title": f"Low stock: {name}",
                "body": f"Only {int(change['after'])} left (alert at {int(change['threshold'])}). Tap to restock.",
                "url": "/inventory",
                "tag": f"stock-{change['id']}",
            })
    return notifications
