"""Import past sales and expenses from a spreadsheet exported as CSV.

Each row is checked the same way as when it is typed in. A row that is not allowed, or that
already exists, is skipped and the reason is returned, so one bad row never blocks the rest."""

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request

from server.database import get_db

from .. import core
from .. import expense_categories as cats
from .. import record_rules as rules
from ..compat import JsonRouter, jsonify
from ..deps import current_user_id
from ..payments import record_sale_payment

record_user_activity = core.record_user_activity
router = JsonRouter()

MAX_IMPORT_ROWS = 200


def _text(row, key):
    return str(row.get(key) or "").strip()


@router.api_route("/api/import/expenses", methods=['POST'])
def import_expenses(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    rows = (payload or {}).get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return jsonify({"status": "error", "message": "Send the rows to import."}), 400
    if len(rows) > MAX_IMPORT_ROWS:
        return jsonify({"status": "error", "message": f"Import at most {MAX_IMPORT_ROWS} rows at a time."}), 400

    imported, skipped = 0, []
    with get_db() as db:
        cats.ensure(db, user_id)
        for number, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                skipped.append({"row": number, "reason": "Not a row of values."})
                continue
            try:
                amount = float(_text(row, "amount").replace(",", ""))
            except ValueError:
                skipped.append({"row": number, "reason": "The amount is not a number."})
                continue
            if not math.isfinite(amount) or amount <= 0:
                skipped.append({"row": number, "reason": "The amount must be more than zero."})
                continue
            day, day_err = rules.check_entry_date(_text(row, "date"))
            if day_err:
                skipped.append({"row": number, "reason": f"The date: {day_err}."})
                continue
            description = _text(row, "description")
            if not description or rules.too_long(description, rules.MAX_DESCRIPTION):
                skipped.append({"row": number, "reason": "The description is missing or too long."})
                continue
            category = _text(row, "category") or "Others"
            if rules.too_long(category, rules.MAX_CATEGORY):
                skipped.append({"row": number, "reason": "The category name is too long."})
                continue

            # A category not on the list is added, unless it was archived on purpose.
            stored = cats.choice_for_expense(db, user_id, category)
            if stored is None:
                if cats.find_by_name(db, user_id, category):
                    skipped.append({"row": number, "reason": f"The category {category} is archived. Restore it first."})
                    continue
                db.execute("INSERT INTO expense_categories (user_id, name, archived, created_at) VALUES (?, ?, 0, ?)",
                           (user_id, category, datetime.now(timezone.utc).isoformat()))
                stored = category

            duplicate = db.execute(
                "SELECT 1 FROM expenses WHERE user_id = ? AND entry_date = ? AND amount = ? AND category = ? AND description = ?",
                (user_id, day, amount, stored, description),
            ).fetchone()
            if duplicate:
                skipped.append({"row": number, "reason": "Already recorded."})
                continue

            db.execute(
                "INSERT INTO expenses (user_id, amount, category, description, date, entry_date, entered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, amount, stored, description, rules.display_stamp(day), day, datetime.now(timezone.utc).isoformat()),
            )
            imported += 1
        if imported:
            record_user_activity(db, user_id, "expenses_imported", f"Imported {imported} expenses")
        db.commit()
    return jsonify({"status": "success", "imported": imported, "skipped": skipped}), 200


@router.api_route("/api/import/sales", methods=['POST'])
def import_sales(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    rows = (payload or {}).get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return jsonify({"status": "error", "message": "Send the rows to import."}), 400
    if len(rows) > MAX_IMPORT_ROWS:
        return jsonify({"status": "error", "message": f"Import at most {MAX_IMPORT_ROWS} rows at a time."}), 400

    imported, skipped = 0, []
    with get_db() as db:
        for number, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                skipped.append({"row": number, "reason": "Not a row of values."})
                continue
            try:
                total = float(_text(row, "amount").replace(",", ""))
            except ValueError:
                skipped.append({"row": number, "reason": "The amount is not a number."})
                continue
            if not math.isfinite(total) or total <= 0:
                skipped.append({"row": number, "reason": "The amount must be more than zero."})
                continue
            day, day_err = rules.check_entry_date(_text(row, "date"))
            if day_err:
                skipped.append({"row": number, "reason": f"The date: {day_err}."})
                continue
            description = _text(row, "description")
            if not description or rules.too_long(description, rules.MAX_DESCRIPTION):
                skipped.append({"row": number, "reason": "The item description is missing or too long."})
                continue
            customer = _text(row, "customer") or "Walk-in Customer"
            if rules.too_long(customer, rules.MAX_CUSTOMER_NAME):
                skipped.append({"row": number, "reason": "The customer name is too long."})
                continue
            mode = rules.payment_mode_or_none(_text(row, "payment_mode"))
            if mode is None:
                skipped.append({"row": number, "reason": "The payment mode is not one the app accepts."})
                continue

            duplicate = db.execute(
                "SELECT 1 FROM income WHERE user_id = ? AND entry_date = ? AND total_value = ? AND description = ? AND customer_name = ?",
                (user_id, day, total, description, customer),
            ).fetchone()
            if duplicate:
                skipped.append({"row": number, "reason": "Already recorded."})
                continue

            receipt_id = f"IMP-{day.replace('-', '')}-{number}-{int(datetime.now(timezone.utc).timestamp())}"
            cursor = db.execute(
                """INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode,
                   date, receipt_id, entry_date, entered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, description, total, 0, customer, mode, rules.display_stamp(day), receipt_id, day,
                 datetime.now(timezone.utc).isoformat()),
            )
            record_sale_payment(db, user_id, cursor.lastrowid, total, day)
            imported += 1
        if imported:
            record_user_activity(db, user_id, "sales_imported", f"Imported {imported} sales")
        db.commit()
    return jsonify({"status": "success", "imported": imported, "skipped": skipped}), 200
