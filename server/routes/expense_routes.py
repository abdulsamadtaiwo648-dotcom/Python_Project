"""Expense Routes HTTP routes."""

from datetime import datetime, timezone
from flask import flash, jsonify, redirect, render_template, request
import math
from ..app import (
    app,
    get_current_user_id,
    get_db,
    record_user_activity,
)


@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    with get_db() as db:
        rows = db.execute(
            "SELECT id, amount, category, description, date FROM expenses WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ).fetchall()
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


@app.route("/add", methods=["POST"])
def add_expense():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
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


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE", "PUT"])
def api_expense_detail(expense_id):
    user_id = get_current_user_id()
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
        data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
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


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        ).fetchone()
        if not existing:
            return redirect("/dashboard")
        db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
        record_user_activity(db, user_id, "expense_deleted", "Deleted an expense")
        db.commit()
    return redirect("/dashboard")


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")

    with get_db() as db:
        item = db.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)).fetchone()

    if request.method == "GET":
        if item:
            return render_template("edit.html", item=item, index=expense_id)
        return redirect("/")

    if request.method == "POST":
        try:
            amount = float(str(request.form.get("amount", "0")).replace(',', ''))
        except (TypeError, ValueError):
            flash("Expense amount must be a valid number.")
            return render_template("edit.html", item=item, index=expense_id)

        if not math.isfinite(amount) or amount <= 0:
            flash("Expense amount must be greater than zero.")
            return render_template("edit.html", item=item, index=expense_id)

        category = str(request.form.get("category", "")).strip()
        description = str(request.form.get("description", "")).strip()
        if not category or not description:
            flash("Category and description are required.")
            return render_template("edit.html", item=item, index=expense_id)

        expenses_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %I:%M %p")
        with get_db() as db:
            updated = db.execute(
                "UPDATE expenses SET amount = ?, category = ?, description = ?, date = ? WHERE id = ? AND user_id = ?",
                (amount, category, description, expenses_date, expense_id, user_id)
            )
            if updated.rowcount:
                record_user_activity(db, user_id, "expense_updated", "Updated an expense")
            db.commit()
        return redirect("/dashboard")

    return redirect("/dashboard")
