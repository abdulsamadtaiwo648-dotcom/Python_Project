"""Money amounts for accounts. Naira amounts are read as exact decimals and kept as whole kobo
(integers), so sums never drift the way binary floats can."""

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

MAX_KOBO = 10 ** 14  # ₦1 trillion: well beyond any real balance, and keeps the integers small


def parse_naira(text):
    """'1,234.5' -> 123450 kobo. None when the text is not an amount with at most two decimals."""
    s = str(text if text is not None else "").strip().replace(",", "")
    if not s or "e" in s.lower():
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    if not value.is_finite() or value.as_tuple().exponent < -2:
        return None
    kobo = int(value * 100)
    return kobo if abs(kobo) <= MAX_KOBO else None


def kobo_from_amount(amount):
    """A stored amount (a float or number from the database) rounded to the nearest kobo."""
    return int((Decimal(str(amount or 0)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def naira_text(kobo):
    """-123450 -> '-1234.50' (exact, for the API)."""
    sign = "-" if kobo < 0 else ""
    whole, cents = divmod(abs(int(kobo)), 100)
    return f"{sign}{whole}.{cents:02d}"


def today_iso(now=None):
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
