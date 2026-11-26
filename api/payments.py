"""Sale payments: every payment a sale receives is one dated row in sale_payments. That ledger is
the source of truth. A sale's amount_paid is always the sum of its payments, updated in the same
transaction, so a payment is never counted twice."""

from . import accounts as acc
from .money import kobo_from_amount


def paid_kobo(db, owner_id, income_id):
    row = db.execute(
        "SELECT COALESCE(SUM(amount_kobo), 0) AS total FROM sale_payments WHERE user_id = ? AND income_id = ?",
        (owner_id, income_id),
    ).fetchone()
    return int(row["total"] or 0)


def sync_amount_paid(db, owner_id, income_id):
    """Keep the sale's stored amount_paid equal to its payments. Call inside the same transaction."""
    total = paid_kobo(db, owner_id, income_id)
    db.execute("UPDATE income SET amount_paid = ? WHERE id = ? AND user_id = ?",
               (total / 100.0, income_id, owner_id))
    return total


def record_sale_payment(db, owner_id, income_id, amount, payment_date, approximate=False):
    """Record a payment against a sale on the default account. Returns the amount recorded in kobo
    (0 when there is nothing to record). Call inside the same transaction as the sale change."""
    kobo = kobo_from_amount(amount)
    if kobo <= 0:
        return 0
    default = acc.default_account(db, owner_id)
    if default is None:
        acc.ensure_default(db, owner_id, commit=False)
        default = acc.default_account(db, owner_id)
    db.execute(
        "INSERT INTO sale_payments (user_id, income_id, account_id, amount_kobo, payment_date, is_approximate, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (owner_id, income_id, default["id"], kobo, payment_date, 1 if approximate else 0,
         _now()),
    )
    sync_amount_paid(db, owner_id, income_id)
    return kobo


def remove_sale_payments(db, owner_id, income_ids):
    """Delete the payments of sales that were deleted."""
    for income_id in income_ids:
        db.execute("DELETE FROM sale_payments WHERE user_id = ? AND income_id = ?", (owner_id, income_id))


def backfill_sale_payments(db):
    """One approximate payment for each existing sale that has a paid amount but no payment rows.
    It is dated to the sale and goes to the default account. Returns how many were added."""
    cursor = db.execute(
        """INSERT INTO sale_payments (user_id, income_id, account_id, amount_kobo, payment_date, is_approximate, created_at)
           SELECT i.user_id, i.id,
                  (SELECT a.id FROM accounts a WHERE a.user_id = i.user_id AND a.is_default = 1),
                  CAST(ROUND(i.amount_paid * 100) AS BIGINT),
                  COALESCE(i.entry_date, SUBSTR(i.date, 1, 10)),
                  1, ?
           FROM income i
           WHERE COALESCE(i.amount_paid, 0) > 0
             AND NOT EXISTS (SELECT 1 FROM sale_payments p WHERE p.income_id = i.id)""",
        (_now(),),
    )
    return cursor.rowcount or 0


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
