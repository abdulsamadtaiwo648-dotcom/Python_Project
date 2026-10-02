"""Expense Routes HTTP routes."""

from datetime import datetime
from flask import flash, jsonify, redirect, render_template, request
import math
from ..app import (
    app,
    get_current_user_id,
    get_db,
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

    expense_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, description, expense_date)
        )
        expense_id = cursor.lastrowid
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
            db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
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

        expense_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        with get_db() as db:
            db.execute(
                "UPDATE expenses SET amount = ?, category = ?, description = ?, date = ? WHERE id = ? AND user_id = ?",
                (amount, category, description, expense_date, expense_id, user_id)
            )
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

        expenses_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        with get_db() as db:
            db.execute(
                "UPDATE expenses SET amount = ?, category = ?, description = ?, date = ? WHERE id = ? AND user_id = ?",
                (amount, category, description, expenses_date, expense_id, user_id)
            )
            db.commit()
        return redirect("/dashboard")

    return redirect("/dashboard")


@app.route("/calculate", methods=["POST"])
def calculate():
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")

    calc_term = request.form.get("calc_term", "").strip()
    calc_term_lower = calc_term.lower()
    calc_type = request.form.get("calc_type", "")
    items = []

    with get_db() as db:
        if calc_type == "amount":
            try:
                val = float(calc_term_lower)
                items = db.execute("SELECT amount FROM expenses WHERE user_id = ? AND amount = ?", (user_id, val)).fetchall()
            except ValueError:
                items = []
        elif calc_type == "category":
            items = db.execute(
                "SELECT amount FROM expenses WHERE user_id = ? AND LOWER(category) LIKE ?",
                (user_id, f"%{calc_term_lower}%")
            ).fetchall()
        elif calc_type == "description":
            items = db.execute(
                "SELECT amount FROM expenses WHERE user_id = ? AND LOWER(description) LIKE ?",
                (user_id, f"%{calc_term_lower}%")
            ).fetchall()

        user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        expenses = db.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,)).fetchall()

    calc_result = sum(float(row["amount"] or 0) for row in items)
    total_expenses = sum(float(item["amount"] or 0) for item in expenses)
    username = user["email"].split("@")[0].capitalize() if user and user["email"] else "Entrepreneur"

    total_sales = 0.0
    try:
        with get_db() as db:
            row = db.execute(
                "SELECT SUM(COALESCE(amount_paid, 0)) AS total FROM income WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if row and row["total"] is not None:
                total_sales = float(row["total"])
    except Exception:
        pass

    return render_template(
        "index.html",
        expenses=expenses,
        total=total_expenses,
        total_sales=total_sales,
        total_expenses=total_expenses,
        net_profit=total_sales - total_expenses,
        username=username,
        calc_result=calc_result,
        calc_term=calc_term
    )


@app.route("/search", methods=["POST"])
def search():
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")

    raw_search = request.form.get("search_term", "").strip()
    search_term = raw_search.lower()
    search_type = request.form.get("search_type", "")
    search_results = []
    display_term = raw_search

    with get_db() as db:
        all_expenses = db.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,)).fetchall()

        if search_type == "amount":
            try:
                amount_val = float(search_term)
                search_results = db.execute(
                    "SELECT * FROM expenses WHERE user_id = ? AND amount = ?", (user_id, amount_val)
                ).fetchall()
                if search_results:
                    display_term = f"â‚¦{amount_val:,.2f}"
            except ValueError:
                search_results = []
        elif search_type == "category":
            search_results = db.execute(
                "SELECT * FROM expenses WHERE user_id = ? AND LOWER(category) LIKE ?",
                (user_id, f"%{search_term}%")
            ).fetchall()
            if search_results:
                display_term = search_results[0]["category"].capitalize()

    global_total = sum(float(item["amount"] or 0) for item in all_expenses)
    search_total = sum(float(item["amount"] or 0) for item in search_results)

    username = "Entrepreneur"
    total_sales = 0.0
    try:
        with get_db() as db:
            user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
            if user and user["email"]:
                username = user["email"].split("@")[0].capitalize()
            row = db.execute(
                "SELECT SUM(COALESCE(amount_paid, 0)) AS total FROM income WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if row and row["total"] is not None:
                total_sales = float(row["total"])
    except Exception:
        pass

    return render_template(
        "index.html",
        expenses=all_expenses,
        total=global_total,
        total_sales=total_sales,
        total_expenses=global_total,
        net_profit=total_sales - global_total,
        username=username,
        search_results=search_results,
        search_total=search_total,
        searching=True,
        search_term=display_term
    )
