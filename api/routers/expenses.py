"""Expenses: list, add, edit and delete."""

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request

from server.database import get_db

from .. import core
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
        sql = "SELECT id, amount, category, description, date FROM expenses WHERE user_id = ?"
        params = (user_id,)
        if cutoff:
            sql += " AND date >= ?"
            params = (user_id, cutoff)
        rows = db.execute(sql + " ORDER BY id DESC", params).fetchall()
        expenses = [
            {
                "server_id": row["id"],
                "amount": float(row["amount"]),
                "category": row["category"],
                "description": row["description"],
                "date": row["date"],
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

    expense_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %I:%M %p")
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, description, expense_date)
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
            "date": expense_date
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

        expense_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %I:%M %p")
        with get_db() as db:
            updated = db.execute(
                "UPDATE expenses SET amount = ?, category = ?, description = ?, date = ? WHERE id = ? AND user_id = ?",
                (amount, category, description, expense_date, expense_id, user_id)
            )
            if updated.rowcount:
                record_user_activity(db, user_id, "expense_updated", "Updated an expense")
            db.commit()

        return jsonify({
            "status": "success",
            "message": "Expense updated successfully",
            "expense": {"id": expense_id, "amount": amount, "category": category, "description": description, "date": expense_date}
        }), 200


