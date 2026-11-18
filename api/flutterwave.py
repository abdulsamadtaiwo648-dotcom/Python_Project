"""Flutterwave (hosted checkout, payment plans, verification).

Needs FLW_SECRET_KEY (API key) and FLW_SECRET_HASH (the value you set as the
webhook "secret hash" in the Flutterwave dashboard). Without them the plans
screens still work but starting a payment answers "not set up yet".
"""

import hmac
import logging
import os
import uuid
from datetime import datetime, timezone

import requests

from server.database import get_db

from . import plans as catalogue
from . import subscriptions as subs

log = logging.getLogger(__name__)
TIMEOUT = 20


class FlutterwaveError(Exception):
    pass


def base_url():
    return os.environ.get("FLW_BASE_URL", "https://api.flutterwave.com/v3").rstrip("/")


def configured():
    return bool(os.environ.get("FLW_SECRET_KEY"))


def valid_webhook_signature(sent):
    expected = os.environ.get("FLW_SECRET_HASH") or ""
    return bool(expected) and hmac.compare_digest(str(sent or ""), expected)


def _call(method, path, **kwargs):
    if not configured():
        raise FlutterwaveError("Payments are not set up yet.")
    try:
        response = requests.request(
            method, base_url() + path, timeout=TIMEOUT,
            headers={"Authorization": f"Bearer {os.environ['FLW_SECRET_KEY']}", "Content-Type": "application/json"},
            **kwargs,
        )
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        log.error("Flutterwave %s %s failed: %s", method, path, exc)
        raise FlutterwaveError("Could not reach the payment service. Please try again.") from exc
    if response.status_code >= 400 or body.get("status") != "success":
        log.error("Flutterwave %s %s said %s: %s", method, path, response.status_code, body.get("message"))
        raise FlutterwaveError(body.get("message") or "The payment service refused the request.")
    return body.get("data")


def ensure_payment_plan(plan_key, amount):
    """The recurring plan on Flutterwave for this SoloBiz plan and price (created once)."""
    with get_db() as db:
        row = db.execute("SELECT provider_plan_id FROM provider_plans WHERE plan = ? AND amount = ?", (plan_key, float(amount))).fetchone()
    if row:
        return row["provider_plan_id"]
    data = _call("POST", "/payment-plans", json={
        "amount": amount, "name": f"SoloBiz {catalogue.plans()[plan_key].name} (monthly)",
        "interval": "monthly", "currency": catalogue.CURRENCY,
    })
    plan_id = str(data["id"])
    with get_db() as db:
        db.execute("INSERT INTO provider_plans (plan, amount, provider_plan_id) VALUES (?, ?, ?)", (plan_key, float(amount), plan_id))
        db.commit()
    return plan_id


def create_checkout(user_id, email, name, plan_key, redirect_url):
    """Start a payment: remember the attempt, return Flutterwave's hosted payment link."""
    plan = catalogue.plans().get(plan_key)
    if not plan or plan_key not in catalogue.PAID:
        raise FlutterwaveError("Choose Basic or Pro.")
    tx_ref = f"sb_{uuid.uuid4().hex}"
    payment_plan = ensure_payment_plan(plan_key, plan.price)
    with get_db() as db:
        db.execute(
            "INSERT INTO payments (user_id, plan, amount, currency, tx_ref, provider_tx_id, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, NULL, 'pending', ?)",
            (str(user_id), plan_key, float(plan.price), catalogue.CURRENCY, tx_ref, datetime.now(timezone.utc).isoformat()),
        )
        db.commit()
    data = _call("POST", "/payments", json={
        "tx_ref": tx_ref, "amount": plan.price, "currency": catalogue.CURRENCY, "redirect_url": redirect_url,
        "payment_plan": payment_plan, "customer": {"email": email, "name": name or email},
        "customizations": {"title": f"SoloBiz {plan.name}", "description": "Monthly subscription"},
        "meta": {"user_id": str(user_id), "plan": plan_key},
    })
    return data["link"]


def verify_by_reference(tx_ref):
    return _call("GET", "/transactions/verify_by_reference", params={"tx_ref": tx_ref})


def verify_by_id(tx_id):
    return _call("GET", f"/transactions/{tx_id}/verify")


def settle(tx):
    """Apply a transaction that Flutterwave itself confirmed. Returns a short
    result string: 'activated', 'already', 'failed' or 'ignored'. Safe to call
    twice for the same transaction (callback and webhook both do)."""
    if not tx:
        return "ignored"
    tx_id = str(tx.get("id") or "")
    tx_ref = str(tx.get("tx_ref") or "")
    status = str(tx.get("status") or "").lower()
    amount = float(tx.get("amount") or 0)
    currency = str(tx.get("currency") or "").upper()

    with get_db() as db:
        if tx_id and db.execute("SELECT 1 FROM payments WHERE provider_tx_id = ?", (tx_id,)).fetchone():
            return "already"
        mine = db.execute("SELECT * FROM payments WHERE tx_ref = ?", (tx_ref,)).fetchone()
        mine = dict(mine) if mine else None

        if mine:
            if status != "successful":
                if mine["status"] == "pending":
                    db.execute("UPDATE payments SET status = 'failed', provider_tx_id = ? WHERE tx_ref = ?", (tx_id or None, tx_ref))
                    db.commit()
                return "failed"
            if currency != mine["currency"] or amount + 0.005 < float(mine["amount"]):
                log.error("Flutterwave amount mismatch for %s: got %s %s, expected %s", tx_ref, amount, currency, mine["amount"])
                return "failed"
            db.execute("UPDATE payments SET status = 'successful', provider_tx_id = ? WHERE tx_ref = ?", (tx_id or None, tx_ref))
            db.commit()
            user_id, plan_key = mine["user_id"], mine["plan"]
        else:
            # A renewal Flutterwave charged on its own schedule: find the account by plan id and e-mail.
            if status != "successful":
                return "ignored"
            provider_plan = str(tx.get("payment_plan") or "")
            email = str((tx.get("customer") or {}).get("email") or "").strip().lower()
            plan_row = db.execute("SELECT plan, amount FROM provider_plans WHERE provider_plan_id = ?", (provider_plan,)).fetchone() if provider_plan else None
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,)).fetchone() if email else None
            if not plan_row or not user:
                return "ignored"
            if currency != catalogue.CURRENCY or amount + 0.005 < float(plan_row["amount"]):
                return "failed"
            user_id, plan_key = user["id"], plan_row["plan"]
            db.execute(
                "INSERT INTO payments (user_id, plan, amount, currency, tx_ref, provider_tx_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'successful', ?)",
                (str(user_id), plan_key, amount, currency, tx_ref or f"flw_{tx_id}", tx_id or None, datetime.now(timezone.utc).isoformat()),
            )
            db.commit()
    subs.activate(user_id, plan_key)
    return "activated"


def cancel_provider_subscription(email, plan_key):
    """Stop automatic renewals on Flutterwave. Best effort: never raises."""
    try:
        plan_id = ensure_payment_plan(plan_key, catalogue.plans()[plan_key].price)
        found = _call("GET", "/subscriptions", params={"email": email, "plan": plan_id, "status": "active"}) or []
        for item in found:
            _call("PUT", f"/subscriptions/{item['id']}/cancel")
        return True
    except Exception:
        log.exception("Could not cancel the Flutterwave subscription for %s", email)
        return False
