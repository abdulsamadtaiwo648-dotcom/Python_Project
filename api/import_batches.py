"""Import batches: every record an import creates is tied to its batch with a fingerprint of how it
was when imported. Undo removes only the batch's records that are still exactly as imported; records
changed since, or sales that gained later payments, are kept and reported.

An import with the same batch key as an earlier one is never applied again, and an undo can run once."""

import hashlib
import json
from datetime import datetime, timezone

from .money import kobo_from_amount

TABLES = ("sale_payments", "income", "expenses", "money_in")


def fingerprint(table, row):
    """A fingerprint of the fields that define a record. Computed the same way when the record is
    created and when undo checks it, so any edit shows up as a change."""
    if table == "expenses":
        parts = ("expense", kobo_from_amount(row["amount"]), row["category"], row["description"] or "",
                 row["entry_date"] or "", row["account_id"])
    elif table == "income":
        parts = ("sale", kobo_from_amount(row["total_value"]), row["description"] or "", row["customer_name"] or "",
                 row["entry_date"] or "", row["payment_mode"] or "", row["receipt_id"] or "")
    elif table == "money_in":
        parts = ("money_in", row["kind"], kobo_from_amount(row["amount"]), row["description"] or "",
                 row["entry_date"] or "", row["account_id"], row["from_account_id"])
    elif table == "sale_payments":
        parts = ("payment", int(row["amount_kobo"]), row["payment_date"], row["account_id"], row["income_id"])
    else:
        raise ValueError(table)
    return hashlib.sha256(json.dumps([str(p) for p in parts]).encode()).hexdigest()[:24]


def create_batch(db, owner_id, kind, batch_key):
    """A new batch, or None if this key was already used (the import must not be applied again)."""
    existing = db.execute("SELECT id FROM import_batches WHERE user_id = ? AND batch_key = ?", (owner_id, batch_key)).fetchone()
    if existing:
        return None
    cursor = db.execute(
        "INSERT INTO import_batches (user_id, kind, batch_key, status, created_at) VALUES (?, ?, ?, 'committed', ?)",
        (owner_id, kind, batch_key, datetime.now(timezone.utc).isoformat()),
    )
    return cursor.lastrowid


def record(db, owner_id, batch_id, table, record_id):
    """Tie a record created by the import to its batch, with its fingerprint as created."""
    row = db.execute(f"SELECT * FROM {table} WHERE id = ? AND user_id = ?", (record_id, owner_id)).fetchone()
    db.execute(
        "INSERT INTO import_batch_rows (batch_id, table_name, record_id, fingerprint) VALUES (?, ?, ?, ?)",
        (batch_id, table, record_id, fingerprint(table, dict(row))),
    )


def batch_for(db, owner_id, batch_id):
    return db.execute("SELECT * FROM import_batches WHERE id = ? AND user_id = ?", (batch_id, owner_id)).fetchone()


def undo_plan(db, owner_id, batch_id):
    """What undo will do: the records it will remove, and those it will keep and why."""
    batch = batch_for(db, owner_id, batch_id)
    rows = db.execute("SELECT * FROM import_batch_rows WHERE batch_id = ?", (batch_id,)).fetchall()
    in_batch_payments = {r["record_id"] for r in rows if r["table_name"] == "sale_payments"}
    remove = {t: [] for t in TABLES}
    keep = []
    kept_sales = set()

    # Sales first: a sale stays if it changed, or if payments were made on it after the import.
    for r in rows:
        if r["table_name"] != "income":
            continue
        current = db.execute("SELECT * FROM income WHERE id = ? AND user_id = ?", (r["record_id"], owner_id)).fetchone()
        if current is None:
            continue
        if fingerprint("income", dict(current)) != r["fingerprint"]:
            keep.append({"table": "income", "id": r["record_id"], "reason": "Changed after the import"})
            kept_sales.add(r["record_id"])
            continue
        later = db.execute(
            "SELECT id FROM sale_payments WHERE user_id = ? AND income_id = ?", (owner_id, r["record_id"])).fetchall()
        if any(p["id"] not in in_batch_payments for p in later):
            keep.append({"table": "income", "id": r["record_id"], "reason": "Payments were made on this sale after the import"})
            kept_sales.add(r["record_id"])
            continue
        remove["income"].append(r["record_id"])

    for r in rows:
        if r["table_name"] not in ("sale_payments", "expenses", "money_in"):
            continue
        current = db.execute(f"SELECT * FROM {r['table_name']} WHERE id = ? AND user_id = ?", (r["record_id"], owner_id)).fetchone()
        if current is None:
            continue
        if fingerprint(r["table_name"], dict(current)) != r["fingerprint"]:
            keep.append({"table": r["table_name"], "id": r["record_id"], "reason": "Changed after the import"})
            continue
        if r["table_name"] == "sale_payments" and current["income_id"] in kept_sales:
            keep.append({"table": "sale_payments", "id": r["record_id"], "reason": "Its sale is kept"})
            continue
        remove[r["table_name"]].append(r["record_id"])

    return {"batch": dict(batch), "remove": {t: len(ids) for t, ids in remove.items()},
            "remove_ids": remove, "keep": keep}


def undo(db, owner_id, batch_id):
    """Remove the batch's records that are still as imported. Runs once: a second call changes nothing.
    Returns the plan that was applied, or None if the batch was already undone."""
    claimed = db.execute(
        "UPDATE import_batches SET status = 'undoing' WHERE id = ? AND user_id = ? AND status = 'committed'",
        (batch_id, owner_id),
    )
    if not claimed.rowcount:
        return None
    plan = undo_plan(db, owner_id, batch_id)
    for table in ("sale_payments", "income", "expenses", "money_in"):
        for record_id in plan["remove_ids"][table]:
            db.execute(f"DELETE FROM {table} WHERE id = ? AND user_id = ?", (record_id, owner_id))
    db.execute(
        "UPDATE import_batches SET status = 'undone', undone_at = ?, kept_count = ? WHERE id = ? AND user_id = ?",
        (datetime.now(timezone.utc).isoformat(), len(plan["keep"]), batch_id, owner_id),
    )
    return plan
