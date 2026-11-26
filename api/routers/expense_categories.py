"""Expense categories: list, add, rename and archive. Archiving never deletes an expense."""

from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request

from server.database import get_db

from .. import core
from .. import expense_categories as cats
from .. import record_rules as rules
from ..compat import JsonRouter, jsonify
from ..deps import current_user_id

record_user_activity = core.record_user_activity
router = JsonRouter()


def _view(row):
    return {"id": row["id"], "name": row["name"], "archived": bool(row["archived"])}


def _name_problem(name):
    if not name:
        return "Enter a category name."
    if rules.too_long(name, rules.MAX_CATEGORY):
        return "A category name must be 80 characters or fewer."
    return None


@router.api_route("/api/expense-categories", methods=['GET'])
def list_categories(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    with get_db() as db:
        cats.ensure(db, user_id)
        rows = db.execute(
            "SELECT id, name, archived FROM expense_categories WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
    return jsonify({"status": "success", "categories": [_view(r) for r in rows]}), 200


@router.api_route("/api/expense-categories", methods=['POST'])
def add_category(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = payload if isinstance(payload, dict) else {}
    name = str(data.get("name", "")).strip()
    problem = _name_problem(name)
    if problem:
        if rules.too_long(name, rules.MAX_CATEGORY):
            core.log_refused_input(user_id, request.url.path, "category name too long")
        return jsonify({"status": "error", "message": problem}), 400
    with get_db() as db:
        cats.ensure(db, user_id)
        clash = cats.find_by_name(db, user_id, name)
        if clash:
            hint = " Restore it from the list instead." if clash["archived"] else ""
            return jsonify({"status": "error", "message": f"You already have a category called {clash['name']}.{hint}"}), 400
        cursor = db.execute(
            "INSERT INTO expense_categories (user_id, name, archived, created_at) VALUES (?, ?, 0, ?)",
            (user_id, name, datetime.now(timezone.utc).isoformat()),
        )
        record_user_activity(db, user_id, "expense_category_added", "Added an expense category")
        db.commit()
        new_id = cursor.lastrowid
    return jsonify({"status": "success", "message": "Category added",
                    "category": {"id": new_id, "name": name, "archived": False}}), 201


@router.api_route("/api/expense-categories/{category_id}", methods=['PUT'])
def update_category(category_id: int, request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = payload if isinstance(payload, dict) else {}
    with get_db() as db:
        cats.ensure(db, user_id)
        row = db.execute(
            "SELECT id, name, archived FROM expense_categories WHERE id = ? AND user_id = ?", (category_id, user_id)
        ).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "That category was not found."}), 404
        old_name, new_name, archived = row["name"], row["name"], bool(row["archived"])

        if "name" in data:
            new_name = str(data.get("name") or "").strip()
            problem = _name_problem(new_name)
            if problem:
                if rules.too_long(new_name, rules.MAX_CATEGORY):
                    core.log_refused_input(user_id, request.url.path, "category name too long")
                return jsonify({"status": "error", "message": problem}), 400
            clash = cats.find_by_name(db, user_id, new_name, exclude_id=category_id)
            if clash:
                return jsonify({"status": "error", "message": f"You already have a category called {clash['name']}."}), 400

        if "archived" in data:
            archived = bool(data.get("archived"))
            if archived:
                others = db.execute(
                    "SELECT COUNT(*) AS n FROM expense_categories WHERE user_id = ? AND archived = 0 AND id != ?",
                    (user_id, category_id),
                ).fetchone()
                if not others or others["n"] == 0:
                    return jsonify({"status": "error", "message": "Keep at least one active category."}), 400

        db.execute(
            "UPDATE expense_categories SET name = ?, archived = ? WHERE id = ? AND user_id = ?",
            (new_name, 1 if archived else 0, category_id, user_id),
        )
        if new_name != old_name:
            # Renaming changes the name on every expense that used it, so the list and the records agree.
            db.execute(
                "UPDATE expenses SET category = ? WHERE user_id = ? AND category = ?",
                (new_name, user_id, old_name),
            )
        record_user_activity(db, user_id, "expense_category_changed", "Changed an expense category")
        db.commit()
    return jsonify({"status": "success", "message": "Category saved",
                    "category": {"id": category_id, "name": new_name, "archived": archived}}), 200
