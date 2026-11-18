"""Plans, checkout, cancellation and the Flutterwave callback and webhook."""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from server import websites
from server.database import get_db

from .. import flutterwave as flw
from .. import plans as catalogue
from .. import subscriptions as subs
from ..deps import require_user

router = APIRouter()
log = logging.getLogger(__name__)


def _catalogue():
    out = []
    for key, plan in catalogue.plans().items():
        out.append({
            "key": key, "name": plan.name, "price": plan.price, "tagline": plan.tagline,
            "max_products": plan.max_products, "history_days": plan.history_days,
            "features": {f: (f in plan.features) for f in catalogue.FEATURE_LABELS},
        })
    return out


@router.get("/api/subscription")
def subscription(user_id: str = Depends(require_user)):
    ent = subs.entitlements(user_id)
    with get_db() as db:
        rows = db.execute(
            "SELECT plan, amount, currency, status, created_at FROM payments WHERE user_id = ? AND status = 'successful' ORDER BY id DESC LIMIT 12",
            (user_id,),
        ).fetchall()
    return {
        "status": "success",
        "current": ent,
        "plans": _catalogue(),
        "feature_labels": catalogue.FEATURE_LABELS,
        "trial_days": catalogue.TRIAL_DAYS,
        "grace_days": catalogue.GRACE_DAYS,
        "payments_ready": flw.configured(),
        "payments": [dict(r) for r in rows],
    }


class Checkout(BaseModel):
    plan: str = ""


def _fail(message, status=400):
    return JSONResponse({"status": "error", "message": message}, status_code=status)


@router.post("/api/subscription/checkout")
def checkout(body: Checkout, user_id: str = Depends(require_user)):
    if body.plan not in catalogue.PAID:
        return _fail("Choose Basic or Pro.")
    if not flw.configured():
        return _fail("Payments are not set up yet. Please try again soon.", 503)
    with get_db() as db:
        user = db.execute("SELECT email, first_name, last_name FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return _fail("Account not found.", 404)
    name = f"{user['first_name'] or ''} {user['last_name'] or ''}".strip()
    try:
        link = flw.create_checkout(user_id, user["email"], name, body.plan, f"{websites.main_origin()}/billing/callback")
    except flw.FlutterwaveError as exc:
        return _fail(str(exc), 502)
    return {"status": "success", "link": link}


@router.post("/api/subscription/cancel")
def cancel(user_id: str = Depends(require_user)):
    ent = subs.entitlements(user_id)
    if ent["state"] not in ("active", "grace") or not ent["paid_plan"]:
        return _fail("There is no paid plan to cancel.")
    subs.set_cancel(user_id, True)
    with get_db() as db:
        user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
    if user and flw.configured():
        flw.cancel_provider_subscription(user["email"], ent["paid_plan"])
    return {"status": "success", "message": "Renewal cancelled. Your plan stays until the end of the period.",
            "current": subs.entitlements(user_id)}


@router.get("/billing/callback", include_in_schema=False)
def callback(request: Request, status: str = "", tx_ref: str = ""):
    """Flutterwave sends the customer back here. The result is checked with
    Flutterwave rather than trusted from the address."""
    if status.lower() == "cancelled" or not tx_ref:
        return RedirectResponse("/plans?payment=cancelled", status_code=303)
    try:
        result = flw.settle(flw.verify_by_reference(tx_ref))
    except flw.FlutterwaveError:
        log.exception("Could not verify %s", tx_ref)
        return RedirectResponse("/plans?payment=pending", status_code=303)
    ok = result in ("activated", "already")
    return RedirectResponse(f"/plans?payment={'success' if ok else 'failed'}", status_code=303)


@router.post("/api/billing/webhook", include_in_schema=False)
async def webhook(request: Request):
    if not flw.valid_webhook_signature(request.headers.get("verif-hash")):
        return JSONResponse({"status": "error", "message": "Bad signature."}, status_code=401)
    try:
        event = await request.json()
    except Exception:
        return JSONResponse({"status": "ignored"})
    data = event.get("data") if isinstance(event, dict) else None
    if isinstance(data, dict) and str(event.get("event", "")).startswith("charge.") and data.get("id"):
        try:
            # Never trust the body: ask Flutterwave about this transaction.
            flw.settle(flw.verify_by_id(data["id"]))
        except flw.FlutterwaveError:
            log.exception("Webhook verification failed for %s", data.get("id"))
            return JSONResponse({"status": "retry"}, status_code=500)
    return JSONResponse({"status": "ok"})
