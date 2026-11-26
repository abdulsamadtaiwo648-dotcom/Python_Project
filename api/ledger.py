"""The account ledger: every movement of money into or out of an account, and the balance at any
date. Balances always come from the full history, never from the plan's history window.

Receipts into an account:  sale payments, Money In (not transfers), and transfers in.
Payments out of an account: expenses paid from it, and transfers out.
An account's opening balance applies from its opening date onward, once."""

from . import accounts as acc
from .money import kobo_from_amount

SALE_PAYMENT = "sale_payment"
MONEY_IN = "money_in"
TRANSFER_IN = "transfer_in"
TRANSFER_OUT = "transfer_out"
EXPENSE = "expense"


def entries(db, owner_id, account_id):
    """Every movement on one account, oldest first. Amounts are whole kobo. Each entry has a short
    label, and transfers name the other account."""
    out = []
    for r in db.execute(
        "SELECT p.id, p.income_id, p.amount_kobo, p.payment_date, p.is_approximate, i.description, i.customer_name "
        "FROM sale_payments p LEFT JOIN income i ON i.id = p.income_id AND i.user_id = p.user_id "
        "WHERE p.user_id = ? AND p.account_id = ?", (owner_id, account_id)).fetchall():
        out.append({"day": r["payment_date"], "direction": "in", "kobo": int(r["amount_kobo"]),
                    "source": SALE_PAYMENT, "ref": r["income_id"], "approximate": bool(r["is_approximate"]),
                    "label": f"Sale payment · {r['description'] or 'Sale'}" + (f" · {r['customer_name']}" if r["customer_name"] else ""),
                    "counterpart": None})
    names = {a["id"]: a["name"] for a in db.execute("SELECT id, name FROM accounts WHERE user_id = ?", (owner_id,)).fetchall()}
    for r in db.execute(
        "SELECT id, kind, amount, description, from_account_id, account_id, COALESCE(entry_date, SUBSTR(date, 1, 10)) AS day "
        "FROM money_in WHERE user_id = ? AND (account_id = ? OR from_account_id = ?)",
        (owner_id, account_id, account_id)).fetchall():
        kobo = kobo_from_amount(r["amount"])
        if r["kind"] == "Transfer":
            if r["account_id"] == account_id:
                out.append({"day": r["day"], "direction": "in", "kobo": kobo, "source": TRANSFER_IN, "ref": r["id"],
                            "approximate": False, "label": "Transfer in", "counterpart": names.get(r["from_account_id"])})
            if r["from_account_id"] == account_id:
                out.append({"day": r["day"], "direction": "out", "kobo": kobo, "source": TRANSFER_OUT, "ref": r["id"],
                            "approximate": False, "label": "Transfer out", "counterpart": names.get(r["account_id"])})
        elif r["account_id"] == account_id:
            out.append({"day": r["day"], "direction": "in", "kobo": kobo, "source": MONEY_IN, "ref": r["id"],
                        "approximate": False, "label": f"{r['kind']}" + (f" · {r['description']}" if r["description"] else ""),
                        "counterpart": None})
    for r in db.execute(
        "SELECT id, amount, category, description, COALESCE(entry_date, SUBSTR(date, 1, 10)) AS day FROM expenses "
        "WHERE user_id = ? AND account_id = ?", (owner_id, account_id)).fetchall():
        out.append({"day": r["day"], "direction": "out", "kobo": kobo_from_amount(r["amount"]),
                    "source": EXPENSE, "ref": r["id"], "approximate": False,
                    "label": f"{r['category']}" + (f" · {r['description']}" if r["description"] else ""),
                    "counterpart": None})
    out.sort(key=lambda e: (e["day"] or "", e["source"], e["ref"] or 0))
    return out


def week_bounds(anchor):
    """Monday to Sunday of the week containing `anchor` (a date)."""
    from datetime import timedelta
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def month_bounds(anchor):
    """The first to the last day of the month containing `anchor`."""
    from datetime import date, timedelta
    start = anchor.replace(day=1)
    nxt = date(start.year + (start.month // 12), start.month % 12 + 1, 1)
    return start, nxt - timedelta(days=1)


def period_bounds(kind, anchor):
    return week_bounds(anchor) if kind == "week" else month_bounds(anchor)


def balance_on(db, owner_id, account_row, day):
    """The balance of an account at the end of `day` (YYYY-MM-DD), in kobo. The opening balance counts
    once, from its opening date. Money on later days is not included."""
    total = 0
    if account_row["opening_date"] and account_row["opening_date"] <= day:
        total += int(account_row["opening_kobo"] or 0)
    for e in entries(db, owner_id, account_row["id"]):
        if e["day"] and e["day"] <= day:
            total += e["kobo"] if e["direction"] == "in" else -e["kobo"]
    return total


def balance_for(db, owner_id, account_id, day):
    row = acc.account_for_business(db, owner_id, account_id)
    if row is None:
        raise ValueError("account not found")
    return balance_on(db, owner_id, row, day)


def statement(db, owner_id, account_row, kind, anchor):
    """One account for one week (Monday to Sunday) or one month, with its opening, receipts,
    payments and closing balance. Closing = Opening + Receipts - Payments.

    The opening is the balance at the end of the day before the period. A starting balance is counted
    once, from its opening date. If that date falls inside the period, it is shown as the opening of
    that period and is not counted as a receipt."""
    from datetime import timedelta
    start, end = period_bounds(kind, anchor)
    s, e = start.isoformat(), end.isoformat()
    before = balance_on(db, owner_id, account_row, (start - timedelta(days=1)).isoformat())
    starting = int(account_row["opening_kobo"] or 0)
    od = account_row["opening_date"]
    starting_in_period = starting if (od and s <= od <= e) else 0
    opening = before + starting_in_period
    within = [x for x in entries(db, owner_id, account_row["id"]) if x["day"] and s <= x["day"] <= e]
    receipts = [x for x in within if x["direction"] == "in"]
    payments = [x for x in within if x["direction"] == "out"]
    receipts_total = sum(x["kobo"] for x in receipts)
    payments_total = sum(x["kobo"] for x in payments)
    closing = opening + receipts_total - payments_total
    return {
        "start": s, "end": e,
        "previous_anchor": (start - timedelta(days=1)).isoformat(),
        "next_anchor": (end + timedelta(days=1)).isoformat(),
        "opening": opening,
        "starting_balance": starting,
        "starting_balance_in_period": starting_in_period,
        "activity_before": before - (starting if od and od <= (start - timedelta(days=1)).isoformat() else 0),
        "receipts": receipts,
        "payments": payments,
        "receipts_total": receipts_total,
        "payments_total": payments_total,
        "closing": closing,
    }
