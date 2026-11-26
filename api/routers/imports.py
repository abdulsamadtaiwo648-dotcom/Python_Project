"""CSV imports for expenses, sales and money in: preview, commit, and undo by batch.

Preview checks every row and changes nothing. Commit checks again, imports the rows that pass, and
imports the duplicates the owner chose to keep. A batch key makes a retried commit change nothing."""

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request

from server.database import get_db

from .. import accounts as acc
from .. import core
from .. import expense_categories as cats
from .. import import_batches as batches
from .. import money_in as mi
from .. import record_rules as rules
from ..compat import JsonRouter, jsonify
from ..deps import current_user_id
from ..money import parse_naira
from ..payments import record_sale_payment

record_user_activity = core.record_user_activity
router = JsonRouter()

MAX_IMPORT_ROWS = 500
KINDS = ("expenses", "sales", "money_in")


def _text(row, key):
    return str(row.get(key) or "").strip()


def _account_by_name(db, owner_id, name):
    key = name.lower()
    for a in acc.all_accounts(db, owner_id):
        if a["name"].lower() == key:
            return a
    return None


def _check_amount(row):
    kobo = parse_naira(_text(row, "amount"))
    if kobo is None:
        return None, "The amount is not a number with at most two decimals."
    if kobo <= 0:
        return None, "The amount must be more than zero."
    return kobo, None


def _check_day(row):
    day, error = rules.check_entry_date(_text(row, "date"))
    return (day, None) if day else (None, f"The date: {error}.")


def normalise(db, owner_id, kind, row):
    """(data, None) for a row that can be imported, or (None, [reasons]). Nothing is written here."""
    problems = []
    kobo, error = _check_amount(row)
    if error:
        problems.append(error)
    day, error = _check_day(row)
    if error:
        problems.append(error)
    description = _text(row, "description")
    if kind == "sales" and not description:
        problems.append("The item description is missing.")
    if description and rules.too_long(description, rules.MAX_DESCRIPTION):
        problems.append("The description is too long.")

    if kind == "expenses":
        category = _text(row, "category") or "Others"
        if rules.too_long(category, rules.MAX_CATEGORY):
            problems.append("The category name is too long.")
        account_name = _text(row, "paid_from")
        account_id = None
        if account_name:
            account = _account_by_name(db, owner_id, account_name)
            if account is None:
                problems.append(f"The account “{account_name}” is not on your list. Add it on the Accounts page first.")
            elif account["archived"]:
                problems.append(f"The account “{account_name}” is archived. Restore it or choose another.")
            else:
                account_id = account["id"]
        else:
            account_id = acc.default_account(db, owner_id)["id"] if acc.default_account(db, owner_id) else None
        if not description:
            problems.append("The description is missing.")
        if problems:
            return None, problems
        stored = cats.choice_for_expense(db, owner_id, category)
        if stored is None and cats.find_by_name(db, owner_id, category):
            return None, [f"The category “{category}” is archived. Restore it first."]
        return {"amount": kobo, "day": day, "description": description, "category": stored or category,
                "account_id": account_id, "new_category": stored is None}, None

    if kind == "sales":
        mode = rules.payment_mode_or_none(_text(row, "payment_mode"))
        customer = _text(row, "customer") or "Walk-in Customer"
        if mode is None:
            problems.append("The payment mode is not one the app accepts.")
        if rules.too_long(customer, rules.MAX_CUSTOMER_NAME):
            problems.append("The customer name is too long.")
        if problems:
            return None, problems
        return {"amount": kobo, "day": day, "description": description, "customer": customer, "mode": mode}, None

    # money_in
    type_text = _text(row, "type") or _text(row, "kind")
    matches = {k.lower(): k for k in mi.KINDS}
    kind_value = matches.get(type_text.lower())
    if kind_value is None:
        problems.append("Choose a type: Owner contribution, Loan, Refund received, Other income or Transfer.")
    received = _text(row, "received_into")
    from_name = _text(row, "from_account")
    received_row = _account_by_name(db, owner_id, received) if received else None
    from_row = _account_by_name(db, owner_id, from_name) if from_name else None
    if received and received_row is None:
        problems.append(f"The account “{received}” is not on your list.")
    if from_name and from_row is None:
        problems.append(f"The account “{from_name}” is not on your list.")
    if kind_value == mi.TRANSFER:
        if not received or not from_name:
            problems.append("A transfer needs both the account it came from and the account it went into.")
        elif received_row and from_row and received_row["id"] == from_row["id"]:
            problems.append("A transfer needs two different accounts.")
        for a in (received_row, from_row):
            if a is not None and a["archived"]:
                problems.append(f"The account “{a['name']}” is archived.")
        if problems:
            return None, problems
        return {"amount": kobo, "day": day, "description": description, "kind": mi.TRANSFER,
                "account_id": received_row["id"], "from_account_id": from_row["id"]}, None
    if from_name:
        problems.append("Only a transfer has a 'from' account.")
    if received_row is None and received:
        pass  # already flagged above
    if received_row is not None and received_row["archived"]:
        problems.append(f"The account “{received_row['name']}” is archived. Restore it or choose another.")
    if not received:
        default = acc.default_account(db, owner_id)
        received_row = default
    if problems or kind_value is None:
        return None, problems
    return {"amount": kobo, "day": day, "description": description, "kind": kind_value,
            "account_id": received_row["id"] if received_row else None, "from_account_id": None}, None


def duplicate_of(db, owner_id, kind, data):
    """The existing record this row would repeat, or None."""
    if kind == "expenses":
        row = db.execute(
            "SELECT id FROM expenses WHERE user_id = ? AND entry_date = ? AND amount = ? AND category = ? AND description = ?",
            (owner_id, data["day"], data["amount"] / 100.0, data["category"], data["description"])).fetchone()
    elif kind == "sales":
        row = db.execute(
            "SELECT id FROM income WHERE user_id = ? AND entry_date = ? AND total_value = ? AND description = ? AND customer_name = ?",
            (owner_id, data["day"], data["amount"] / 100.0, data["description"], data["customer"])).fetchone()
    else:
        row = db.execute(
            "SELECT id FROM money_in WHERE user_id = ? AND entry_date = ? AND amount = ? AND kind = ? "
            "AND COALESCE(description, '') = ? AND account_id IS ? AND from_account_id IS ?",
            (owner_id, data["day"], data["amount"] / 100.0, data["kind"], data["description"],
             data["account_id"], data.get("from_account_id"))).fetchone()
    return row["id"] if row else None


def key_of(kind, data):
    if kind == "expenses":
        return (data["day"], data["amount"], data["category"], data["description"])
    if kind == "sales":
        return (data["day"], data["amount"], data["description"], data["customer"])
    return (data["day"], data["amount"], data["kind"], data["description"], data["account_id"], data.get("from_account_id"))


def preview_rows(db, owner_id, kind, rows):
    """Check every row. Returns one entry per row, in order, with a status:
    ok, error (fix the row), or duplicate (already recorded, or repeated in this file)."""
    seen = {}
    out = []
    for number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            out.append({"row": number, "status": "error", "reasons": ["Not a row of values."], "duplicate_of": None})
            continue
        data, problems = normalise(db, owner_id, kind, row)
        if problems:
            out.append({"row": number, "status": "error", "reasons": problems, "duplicate_of": None})
            continue
        existing = duplicate_of(db, owner_id, kind, data)
        key = key_of(kind, data)
        if existing is not None:
            out.append({"row": number, "status": "duplicate", "reasons": ["Already recorded."],
                        "duplicate_of": {"kind": "existing", "id": existing}, "data": data})
        elif key in seen:
            out.append({"row": number, "status": "duplicate", "reasons": [f"Repeats row {seen[key]} in this file."],
                        "duplicate_of": {"kind": "file", "row": seen[key]}, "data": data})
        else:
            seen.setdefault(key, number)
            out.append({"row": number, "status": "ok", "reasons": [], "duplicate_of": None, "data": data})
    return out


def _add_record(db, owner_id, kind, data, batch_id, stamp):
    if kind == "expenses":
        if data["new_category"]:
            db.execute("INSERT INTO expense_categories (user_id, name, archived, created_at) VALUES (?, ?, 0, ?)",
                       (owner_id, data["category"], stamp))
        cursor = db.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date, entry_date, entered_at, account_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (owner_id, data["amount"] / 100.0, data["category"], data["description"], rules.display_stamp(data["day"]),
             data["day"], stamp, data["account_id"]))
        batches.record(db, owner_id, batch_id, "expenses", cursor.lastrowid)
    elif kind == "sales":
        cursor = db.execute(
            "INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id, entry_date, entered_at) "
            "VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?)",
            (owner_id, data["description"], data["amount"] / 100.0, data["customer"], data["mode"],
             rules.display_stamp(data["day"]), f"IMP-{uuid.uuid4().hex[:10].upper()}", data["day"], stamp))
        income_id = cursor.lastrowid
        batches.record(db, owner_id, batch_id, "income", income_id)
        record_sale_payment(db, owner_id, income_id, data["amount"] / 100.0, data["day"])
        payment = db.execute("SELECT MAX(id) AS id FROM sale_payments WHERE income_id = ?", (income_id,)).fetchone()
        batches.record(db, owner_id, batch_id, "sale_payments", payment["id"])
    else:
        cursor = db.execute(
            "INSERT INTO money_in (user_id, amount, kind, description, date, entry_date, entered_at, account_id, from_account_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (owner_id, data["amount"] / 100.0, data["kind"], data["description"], rules.display_stamp(data["day"]),
             data["day"], stamp, data["account_id"], data.get("from_account_id")))
        batches.record(db, owner_id, batch_id, "money_in", cursor.lastrowid)


def _commit(db, owner_id, kind, rows, keep_rows, batch_key):
    """Import the rows that pass, plus the duplicates the owner kept. Returns (result, status)."""
    if batch_key:
        already = db.execute("SELECT id FROM import_batches WHERE user_id = ? AND batch_key = ?", (owner_id, batch_key)).fetchone()
        if already:
            return {"status": "success", "already_imported": True, "batch_id": already["id"], "imported": 0, "skipped": []}, 200
    acc.ensure_default(db, owner_id, commit=False)
    entries = preview_rows(db, owner_id, kind, rows)
    keep = set(keep_rows or [])
    batch_id = batches.create_batch(db, owner_id, kind, batch_key or uuid.uuid4().hex)
    stamp = datetime.now(timezone.utc).isoformat()
    imported, skipped = 0, []
    for entry in entries:
        if entry["status"] == "error":
            skipped.append({"row": entry["row"], "reason": "; ".join(entry["reasons"])})
        elif entry["status"] == "duplicate" and entry["row"] not in keep:
            skipped.append({"row": entry["row"], "reason": entry["reasons"][0]})
        else:
            _add_record(db, owner_id, kind, entry["data"], batch_id, stamp)
            imported += 1
    record_user_activity(db, owner_id, f"{kind}_imported", f"Imported {imported} {kind.replace('_', ' ')}")
    db.commit()
    return {"status": "success", "already_imported": False, "batch_id": batch_id, "imported": imported, "skipped": skipped}, 200


def _rows_from(payload):
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None, "Send the rows to import."
    if len(rows) > MAX_IMPORT_ROWS:
        return None, f"Import at most {MAX_IMPORT_ROWS} rows at a time."
    return rows, None


@router.api_route("/api/import/preview", methods=['POST'])
def import_preview(request: Request, payload: Any = Body(None)):
    owner_id = current_user_id(request)
    if not owner_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    kind = (payload or {}).get("kind") if isinstance(payload, dict) else None
    if kind not in KINDS:
        return jsonify({"status": "error", "message": "Choose expenses, sales or money in."}), 400
    rows, error = _rows_from(payload)
    if error:
        return jsonify({"status": "error", "message": error}), 400
    with get_db() as db:
        acc.ensure_default(db, owner_id)
        entries = preview_rows(db, owner_id, kind, rows)
    counts = {s: sum(1 for e in entries if e["status"] == s) for s in ("ok", "error", "duplicate")}
    public = [{k: v for k, v in e.items() if k != "data"} for e in entries]
    return jsonify({"status": "success", "kind": kind, "rows": public, "counts": counts}), 200


@router.api_route("/api/import/commit", methods=['POST'])
def import_commit(request: Request, payload: Any = Body(None)):
    owner_id = current_user_id(request)
    if not owner_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    body = payload if isinstance(payload, dict) else {}
    kind = body.get("kind")
    if kind not in KINDS:
        return jsonify({"status": "error", "message": "Choose expenses, sales or money in."}), 400
    rows, error = _rows_from(body)
    if error:
        return jsonify({"status": "error", "message": error}), 400
    batch_key = str(body.get("batch_key") or "").strip()[:80]
    keep = [int(n) for n in body.get("keep_rows") or [] if str(n).isdigit()]
    with get_db() as db:
        result, status = _commit(db, owner_id, kind, rows, keep, batch_key)
    return jsonify({"status": "success", **result}), status


@router.api_route("/api/import/expenses", methods=['POST'])
def import_expenses(request: Request, payload: Any = Body(None)):
    return _legacy(request, payload, "expenses")


@router.api_route("/api/import/sales", methods=['POST'])
def import_sales(request: Request, payload: Any = Body(None)):
    return _legacy(request, payload, "sales")


def _legacy(request, payload, kind):
    """The earlier endpoints: commit with the default choices, and the same response shape."""
    owner_id = current_user_id(request)
    if not owner_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    rows, error = _rows_from(payload)
    if error:
        return jsonify({"status": "error", "message": error}), 400
    with get_db() as db:
        result, _ = _commit(db, owner_id, kind, rows, [], None)
    return jsonify({"status": "success", "imported": result["imported"], "skipped": result["skipped"],
                    "batch_id": result["batch_id"]}), 200


@router.api_route("/api/import-batches", methods=['GET'])
def list_batches(request: Request, payload: Any = Body(None)):
    owner_id = current_user_id(request)
    if not owner_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    with get_db() as db:
        rows = db.execute(
            "SELECT b.id, b.kind, b.status, b.created_at, b.undone_at, "
            "(SELECT COUNT(*) FROM import_batch_rows r WHERE r.batch_id = b.id) AS records "
            "FROM import_batches b WHERE b.user_id = ? ORDER BY b.id DESC LIMIT 20", (owner_id,)).fetchall()
    return jsonify({"status": "success", "batches": [dict(r) for r in rows]}), 200


@router.api_route("/api/import-batches/{batch_id}/undo", methods=['GET', 'POST'])
def undo_batch(batch_id: int, request: Request, payload: Any = Body(None)):
    """GET shows what undo will do. POST does it, once."""
    owner_id = current_user_id(request)
    if not owner_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    with get_db() as db:
        batch = batches.batch_for(db, owner_id, batch_id)
        if batch is None:
            return jsonify({"status": "error", "message": "That import was not found."}), 404
        if request.method == "GET":
            plan = batches.undo_plan(db, owner_id, batch_id)
            return jsonify({"status": "success", "batch": {"id": batch_id, "kind": batch["kind"], "status": batch["status"]},
                            "remove": plan["remove"], "keep": plan["keep"]}), 200
        if batch["status"] != "committed":
            return jsonify({"status": "success", "message": "This import was already undone.", "removed": None}), 200
        plan = batches.undo(db, owner_id, batch_id)
        record_user_activity(db, owner_id, "import_undone", "Undid an import")
        db.commit()
    if plan is None:
        return jsonify({"status": "success", "message": "This import was already undone.", "removed": None}), 200
    return jsonify({"status": "success", "message": "Import undone.", "removed": plan["remove"], "kept": plan["keep"]}), 200
