"""Limits and rules for sales and expenses that arrive from the app, including offline replays."""

from datetime import datetime, timedelta, timezone

PAYMENT_MODES = ("Cash", "Transfer", "POS", "Card", "Other")
MAX_DESCRIPTION = 200
MAX_CUSTOMER_NAME = 120
MAX_RECEIPT_ID = 64
MAX_CATEGORY = 80
MAX_SYNC_SALES = 100
SALE_DATE_FORMAT = "%Y-%m-%d %I:%M %p"
CLOCK_SKEW = timedelta(minutes=5)
MAX_SALE_AGE = timedelta(days=730)


def payment_mode_or_none(value):
    """The canonical payment mode for a value like 'cash' or 'POS', or None if it is not allowed."""
    text = str(value or "").strip()
    if not text:
        return "Cash"
    for mode in PAYMENT_MODES:
        if text.lower() == mode.lower():
            return mode
    return None


def sale_date_label(value, now=None):
    """The date to store for a sale. A client date is kept only when it parses, is not in the
    future (beyond clock skew) and is not older than two years. Otherwise the server's time is used."""
    now = now or datetime.now(timezone.utc)
    text = str(value or "").strip()[:40]
    try:
        when = datetime.strptime(text, SALE_DATE_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return now.strftime(SALE_DATE_FORMAT)
    if when > now + CLOCK_SKEW or when < now - MAX_SALE_AGE:
        return now.strftime(SALE_DATE_FORMAT)
    return when.strftime(SALE_DATE_FORMAT)


def too_long(value, limit):
    return len(str(value or "")) > limit
