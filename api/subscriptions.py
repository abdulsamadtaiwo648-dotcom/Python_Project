"""Subscription state: trial, paid periods, grace, and what an account may use.

State is derived from dates (no background job): a trial ends, a paid period
runs out, a 7-day grace period follows a missed renewal, then the account is on
the Free plan. Nothing is ever deleted when a plan drops; features just stop.
"""

import logging
from datetime import datetime, timedelta, timezone

from server.database import get_db

from . import plans as catalogue

log = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat() if value else None


def _parse(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def get_row(db, user_id):
    row = db.execute("SELECT * FROM subscriptions WHERE user_id = ?", (str(user_id),)).fetchone()
    return dict(row) if row else None


def ensure_subscription(user_id, now=None):
    """Every account has a row. A new (or pre-existing) account starts a Pro trial."""
    now = now or utcnow()
    with get_db() as db:
        row = get_row(db, user_id)
        if row:
            return row
        stamp = _iso(now)
        try:
            db.execute(
                "INSERT INTO subscriptions (user_id, plan, trial_ends_at, period_end, cancel_at_period_end, created_at, updated_at) "
                "VALUES (?, ?, ?, NULL, 0, ?, ?)",
                (str(user_id), catalogue.TRIAL_PLAN, _iso(now + timedelta(days=catalogue.TRIAL_DAYS)), stamp, stamp),
            )
            db.commit()
        except Exception:
            # Two requests raced to create it: the other one won.
            db.conn.rollback()
        return get_row(db, user_id)


def status_for(row, now=None):
    """What the account is entitled to right now, from its stored dates."""
    now = now or utcnow()
    all_plans = catalogue.plans()
    trial_end = _parse(row.get("trial_ends_at"))
    period_end = _parse(row.get("period_end"))
    paid_plan = row.get("plan") if row.get("plan") in catalogue.PAID else None
    cancelling = bool(row.get("cancel_at_period_end"))

    state, plan_key, ends = "free", "free", None
    if period_end and paid_plan:
        grace_end = period_end + timedelta(days=catalogue.GRACE_DAYS)
        if now <= period_end:
            state, plan_key, ends = "active", paid_plan, period_end
        elif not cancelling and now <= grace_end:
            state, plan_key, ends = "grace", paid_plan, grace_end
    if state == "free" and trial_end and now < trial_end:
        state, plan_key, ends = "trial", catalogue.TRIAL_PLAN, trial_end

    plan = all_plans[plan_key]
    seconds = (ends - now).total_seconds() if ends else None
    return {
        "plan": plan_key,
        "plan_name": plan.name,
        "state": state,                       # trial | active | grace | free
        "ends_at": _iso(ends),
        "days_left": max(0, int(-(-seconds // 86400))) if seconds is not None else None,
        "cancel_at_period_end": cancelling and state == "active",
        "paid_plan": paid_plan,
        "period_end": _iso(period_end),
        "trial_ends_at": _iso(trial_end),
        "trial_used": bool(trial_end and now >= trial_end),
        "features": sorted(plan.features),
        "max_products": plan.max_products,
        "history_days": plan.history_days,
    }


def entitlements(user_id, now=None):
    return status_for(ensure_subscription(user_id, now), now)


def has_feature(user_id, feature):
    return feature in entitlements(user_id)["features"]


def activate(user_id, plan_key, now=None):
    """A payment for `plan_key` succeeded: start or extend a 30-day paid period."""
    if plan_key not in catalogue.PAID:
        raise ValueError("Unknown plan")
    now = now or utcnow()
    ensure_subscription(user_id, now)
    with get_db() as db:
        row = get_row(db, user_id)
        current_end = _parse(row.get("period_end"))
        same_plan = row.get("plan") == plan_key
        # Paying early extends the current period; a late or first payment starts today.
        start = current_end if (current_end and current_end > now and same_plan) else now
        db.execute(
            "UPDATE subscriptions SET plan = ?, period_end = ?, cancel_at_period_end = 0, updated_at = ? WHERE user_id = ?",
            (plan_key, _iso(start + timedelta(days=catalogue.PERIOD_DAYS)), _iso(now), str(user_id)),
        )
        db.commit()


def set_cancel(user_id, cancel, now=None):
    now = now or utcnow()
    ensure_subscription(user_id, now)
    with get_db() as db:
        db.execute(
            "UPDATE subscriptions SET cancel_at_period_end = ?, updated_at = ? WHERE user_id = ?",
            (1 if cancel else 0, _iso(now), str(user_id)),
        )
        db.commit()


# --- limits ------------------------------------------------------------------
def product_limit_message(user_id):
    ent = entitlements(user_id)
    return ent["max_products"], (
        f"The {ent['plan_name']} plan allows {ent['max_products']} products. Upgrade to add more."
        if ent["max_products"] is not None else ""
    )


def history_cutoff(user_id, now=None):
    """Oldest date (YYYY-MM-DD) whose records are shown, or None for everything."""
    days = entitlements(user_id, now)["history_days"]
    if days is None:
        return None
    return ((now or utcnow()) - timedelta(days=days)).strftime("%Y-%m-%d")
