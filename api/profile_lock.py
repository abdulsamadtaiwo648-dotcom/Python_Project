"""Business profile lock rules, as decided by the owner.

Only name, phone and address are locked. They appear on receipts and identify the business.
Logo, brand colour, Instagram, WhatsApp and the receipt note are never locked.

Timeline:
- setup:  the first time the owner sets name, phone and address. No lock, no PIN.
- grace:  for 7 days after setup, locked fields can be corrected (each correction needs the PIN),
          and a correction does NOT start a lock.
- open:   after the grace period, with no lock running. A change needs the PIN and starts a 90-day lock.
- locked: 90 days after a locked field changed. Locked fields are read-only; no PIN is sent.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

LOCKED_FIELDS = ("company_name", "business_phone", "business_address")
GRACE_DAYS = 7
LOCK_DAYS = 90
PIN_LIFETIME_SECONDS = 10 * 60
RESEND_COOLDOWN_SECONDS = 60


def parse_stamp(value: Optional[str]) -> Optional[datetime]:
    """A stored timestamp as an aware UTC datetime, or None when it is missing or unreadable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def changed_locked_fields(existing: dict, new: dict) -> list[str]:
    """The locked fields whose value differs. Surrounding spaces are ignored."""
    return [
        field for field in LOCKED_FIELDS
        if str(existing.get(field) or "").strip() != str(new.get(field) or "").strip()
    ]


def lock_status(now: datetime, setup_at: Optional[str], identity_changed_at: Optional[str]) -> dict:
    """The state of the locked fields right now, and the date it ends (or the grace period ends)."""
    setup = parse_stamp(setup_at)
    if setup is None:
        return {"state": "setup", "until": None}
    changed = parse_stamp(identity_changed_at)
    if changed is None:
        grace_end = setup + timedelta(days=GRACE_DAYS)
        if now < grace_end:
            return {"state": "grace", "until": grace_end}
        return {"state": "open", "until": None}
    lock_end = changed + timedelta(days=LOCK_DAYS)
    if now < lock_end:
        return {"state": "locked", "until": lock_end}
    return {"state": "open", "until": None}


def date_text(moment: datetime) -> str:
    """'27 Feb 2027', without a leading zero on the day."""
    return f"{moment.day} {moment:%b %Y}"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
