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
    """Every movement on one account, oldest first. Amounts are whole kobo."""
    out = []
    for r in db.execute(
        "SELECT id, income_id, amount_kobo, payment_date, is_approximate FROM sale_payments "
        "WHERE user_id = ? AND account_id = ?", (owner_id, account_id)).fetchall():
        out.append({"day": r["payment_date"], "direction": "in", "kobo": int(r["amount_kobo"]),
                    "source": SALE_PAYMENT, "ref": r["income_id"], "approximate": bool(r["is_approximate"])})
    for r in db.execute(
        "SELECT id, kind, amount, from_account_id, account_id, COALESCE(entry_date, SUBSTR(date, 1, 10)) AS day "
        "FROM money_in WHERE user_id = ? AND (account_id = ? OR from_account_id = ?)",
        (owner_id, account_id, account_id)).fetchall():
        kobo = kobo_from_amount(r["amount"])
        if r["kind"] == "Transfer":
            if r["account_id"] == account_id:
                out.append({"day": r["day"], "direction": "in", "kobo": kobo, "source": TRANSFER_IN, "ref": r["id"], "approximate": False})
            if r["from_account_id"] == account_id:
                out.append({"day": r["day"], "direction": "out", "kobo": kobo, "source": TRANSFER_OUT, "ref": r["id"], "approximate": False})
        elif r["account_id"] == account_id:
            out.append({"day": r["day"], "direction": "in", "kobo": kobo, "source": MONEY_IN, "ref": r["id"], "approximate": False})
    for r in db.execute(
        "SELECT id, amount, COALESCE(entry_date, SUBSTR(date, 1, 10)) AS day FROM expenses "
        "WHERE user_id = ? AND account_id = ?", (owner_id, account_id)).fetchall():
        out.append({"day": r["day"], "direction": "out", "kobo": kobo_from_amount(r["amount"]),
                    "source": EXPENSE, "ref": r["id"], "approximate": False})
    out.sort(key=lambda e: (e["day"] or "", e["source"], e["ref"] or 0))
    return out


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
