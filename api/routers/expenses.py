"""Expenses: list, add, edit and delete."""

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request

from server.database import get_db

from .. import accounts as acc
from .. import core
from .. import expense_categories as cats
from .. import record_rules as rules
from ..compat import JsonRouter, jsonify
from ..deps import current_user_id
from ..subscriptions import history_cutoff

record_user_activity = core.record_user_activity
router = JsonRouter()



@router.api_route("/api/expenses", methods=['GET'])
def get_expenses(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    with get_db() as db:
        cutoff = history_cutoff(user_id)
        sql = "SELECT id, amount, category, description, date, entry_date, account_id FROM expenses WHERE user_id = ?"
        params = [user_id]
        if cutoff:
            sql += " AND entry_date >= ?"
            params.append(cutoff)
        account_filter = request.query_params.get("account_id")
        if account_filter:
            try:
                sql += " AND account_id = ?"
                params.append(int(account_filter))
            except ValueError:
                return jsonify({"expenses": []}), 200
        rows = db.execute(sql + " ORDER BY id DESC", tuple(params)).fetchall()
        expenses = [
            {
                "server_id": row["id"],
                "amount": float(row["amount"]),
                "category": row["category"],
                "description": row["description"],
                "date": row["date"],
                "entry_date": row["entry_date"],
                "account_id": row["account_id"],
                "synced": True
            }
            for row in rows
        ]
    return jsonify({"expenses": expenses}), 200


@router.api_route("/add", methods=['POST'])
def add_expense(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = payload
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    amount_val = data.get("amount")
    category_val = data.get("category")
    description_val = data.get("description")

    if amount_val is None or category_val is None or description_val is None:
        return jsonify({"status": "error", "message": "Missing required fields: amount, category, and description"}), 400

    try:
        amount = float(str(amount_val).replace(',', ''))
        if not math.isfinite(amount) or amount <= 0:
            return jsonify({"status": "error", "message": "Amount must be a positive number"}), 400
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Amount must be a valid number"}), 400

    category = str(category_val).strip()
    description = str(description_val).strip()
    if not category or not description:
        return jsonify({"status": "error", "message": "Category and description cannot be empty"}), 400
    if rules.too_long(category, rules.MAX_CATEGORY) or rules.too_long(description, rules.MAX_DESCRIPTION):
        core.log_refused_input(user_id, request.url.path, "category or description too long")
        return jsonify({"status": "error", "message": "Category must be 80 characters or fewer and description 200 or fewer."}), 400

    with get_db() as db:
        cats.ensure(db, user_id)
        stored_category = cats.choice_for_expense(db, user_id, category)
    if stored_category is None:
        return jsonify({"status": "error", "message": "Choose a category from your list."}), 400
    category = stored_category

    with get_db() as db:
        acc.ensure_default(db, user_id)
        account_id, account_error = acc.resolve_for_entry(db, user_id, data.get("account_id"))
    if account_error:
        return jsonify({"status": "error", "message": account_error}), 400

    entry_day, entry_err = rules.check_entry_date(data.get("entry_date"))
    if entry_err:
        core.log_refused_input(user_id, request.url.path, "expense date " + entry_err)
        return jsonify({"status": "error", "message": f"Choose a valid date: {entry_err}."}), 400
    expense_date = rules.display_stamp(entry_day)
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date, entry_date, entered_at, account_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, amount, category, description, expense_date, entry_day, datetime.now(timezone.utc).isoformat(), account_id)
        )
        expense_id = cursor.lastrowid
        record_user_activity(db, user_id, "expense_created", "Recorded an expense")
        db.commit()

    return jsonify({
        "status": "success",
        "message": "Expense added successfully",
        "expense": {
            "id": expense_id,
            "user_id": user_id,
            "amount": amount,
            "category": category,
            "description": description,
            "date": expense_date,
            "entry_date": entry_day
        }
    }), 201


@router.api_route("/api/expenses/{expense_id}", methods=['DELETE', 'PUT'])
def api_expense_detail(expense_id: int, request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "DELETE":
        with get_db() as db:
            deleted = db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
            if deleted.rowcount:
                record_user_activity(db, user_id, "expense_deleted", "Deleted an expense")
            db.commit()
        return jsonify({"status": "success", "message": "Expense deleted successfully", "id": expense_id}), 200

    elif request.method == "PUT":
        data = payload
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        try:
            amount = float(str(data.get("amount", "0")).replace(',', ''))
            if not math.isfinite(amount) or amount <= 0:
                return jsonify({"status": "error", "message": "Amount must be a positive number"}), 400
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Invalid amount"}), 400

        category = str(data.get("category", "")).strip()
        description = str(data.get("description", "")).strip()
        if not category or not description:
            return jsonify({"status": "error", "message": "Category and description cannot be empty"}), 400
        if rules.too_long(category, rules.MAX_CATEGORY) or rules.too_long(description, rules.MAX_DESCRIPTION):
            core.log_refused_input(user_id, request.url.path, "category or description too long")
            return jsonify({"status": "error", "message": "Category must be 80 characters or fewer and description 200 or fewer."}), 400

        # Editing keeps the business date unless a new one is sent.
        with get_db() as db:
            cats.ensure(db, user_id)
            current = db.execute("SELECT category, account_id FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)).fetchone()
            stored_category = cats.choice_for_expense(db, user_id, category, current["category"] if current else None)
            if stored_category is None:
                return jsonify({"status": "error", "message": "Choose a category from your list."}), 400
            category = stored_category
            account_id, account_error = acc.resolve_for_entry(
                db, user_id, data.get("account_id"), current["account_id"] if current else None)
            if account_error:
                return jsonify({"status": "error", "message": account_error}), 400
            if "entry_date" in data:
                entry_day, entry_err = rules.check_entry_date(data.get("entry_date"))
                if entry_err:
                    core.log_refused_input(user_id, request.url.path, "expense date " + entry_err)
                    return jsonify({"status": "error", "message": f"Choose a valid date: {entry_err}."}), 400
                updated = db.execute(
                    "UPDATE expenses SET amount = ?, category = ?, description = ?, date = ?, entry_date = ?, account_id = ? WHERE id = ? AND user_id = ?",
                    (amount, category, description, rules.display_stamp(entry_day), entry_day, account_id, expense_id, user_id)
                )
            else:
                updated = db.execute(
                    "UPDATE expenses SET amount = ?, category = ?, description = ?, account_id = ? WHERE id = ? AND user_id = ?",
                    (amount, category, description, account_id, expense_id, user_id)
                )
            if updated.rowcount:
                record_user_activity(db, user_id, "expense_updated", "Updated an expense")
            saved = db.execute("SELECT date, entry_date FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)).fetchone()
            db.commit()

        return jsonify({
            "status": "success",
            "message": "Expense updated successfully",
            "expense": {"id": expense_id, "amount": amount, "category": category, "description": description,
                        "date": saved["date"] if saved else None, "entry_date": saved["entry_date"] if saved else None}
        }), 200


