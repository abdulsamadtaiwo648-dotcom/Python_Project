"""Delete all test transactions. Only the owner of a business marked as a test business can use it,
and only after typing DELETE. Account setup, business settings, products and categories are kept.
Stock is restored for sold products, the same as deleting those sales."""

from typing import Any

from fastapi import Body, Request

from server.database import get_db

from ..compat import JsonRouter, jsonify
from ..deps import actor_for

router = JsonRouter()

TRANSACTION_TABLES = ("sale_payments", "income", "expenses", "money_in", "import_batches")


def _owner_test_business(request: Request):
    """(owner_id, None) when this request is the test business's owner, else (None, (response, status))."""
    who = actor_for(request)
    if not who:
        return None, (jsonify({"status": "error", "message": "Unauthorized"}), 401)
    if who["is_staff"]:
        return None, (jsonify({"status": "error", "message": "Only the business owner can do this."}), 403)
    with get_db() as db:
        row = db.execute("SELECT is_test_account FROM users WHERE id = ?", (who["owner_id"],)).fetchone()
    if not row or not row["is_test_account"]:
        return None, (jsonify({"status": "error", "message": "This reset is only for test businesses."}), 403)
    return who["owner_id"], None


def _plan(db, owner_id):
    count = lambda sql: int(db.execute(sql, (owner_id,)).fetchone()["n"] or 0)  # noqa: E731
    stock = [
        {"product_id": r["id"], "item_name": r["item_name"], "quantity": int(r["units"] or 0)}
        for r in db.execute(
            "SELECT p.id, p.item_name, SUM(COALESCE(i.quantity, 1)) AS units FROM income i "
            "JOIN inventory_presets p ON p.id = i.inventory_item_id AND p.user_id = i.user_id AND p.track_stock = 1 "
            "WHERE i.user_id = ? AND i.inventory_item_id IS NOT NULL GROUP BY p.id, p.item_name",
            (owner_id,)).fetchall()
    ]
    return {
        "sales": count("SELECT COUNT(*) AS n FROM income WHERE user_id = ?"),
        "sale_payments": count("SELECT COUNT(*) AS n FROM sale_payments WHERE user_id = ?"),
        "expenses": count("SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?"),
        "money_in": count("SELECT COUNT(*) AS n FROM money_in WHERE user_id = ?"),
        "import_batches": count("SELECT COUNT(*) AS n FROM import_batches WHERE user_id = ?"),
        "stock_restored": stock,
        "kept": {
            "accounts": count("SELECT COUNT(*) AS n FROM accounts WHERE user_id = ?"),
            "products": count("SELECT COUNT(*) AS n FROM inventory_presets WHERE user_id = ?"),
            "expense_categories": count("SELECT COUNT(*) AS n FROM expense_categories WHERE user_id = ?"),
        },
    }


@router.api_route("/api/test-reset", methods=['GET'])
def preview_reset(request: Request, payload: Any = Body(None)):
    owner_id, refusal = _owner_test_business(request)
    if refusal:
        return refusal
    with get_db() as db:
        return jsonify({"status": "success", "clears": _plan(db, owner_id), "confirm_word": "DELETE"}), 200


@router.api_route("/api/test-reset", methods=['POST'])
def run_reset(request: Request, payload: Any = Body(None)):
    owner_id, refusal = _owner_test_business(request)
    if refusal:
        return refusal
    if not isinstance(payload, dict) or payload.get("confirm") != "DELETE":
        return jsonify({"status": "error", "message": "Type DELETE to confirm."}), 400
    with get_db() as db:
        plan = _plan(db, owner_id)
        for item in plan["stock_restored"]:
            db.execute("UPDATE inventory_presets SET stock = COALESCE(stock, 0) + ? WHERE id = ? AND user_id = ?",
                       (item["quantity"], item["product_id"], owner_id))
        # Batch rows go first: they point at the batches, not at the business.
        db.execute("DELETE FROM import_batch_rows WHERE batch_id IN (SELECT id FROM import_batches WHERE user_id = ?)", (owner_id,))
        for table in TRANSACTION_TABLES:
            if table != "import_batch_rows":
                db.execute(f"DELETE FROM {table} WHERE user_id = ?", (owner_id,))
        db.commit()
    return jsonify({"status": "success", "message": "Test transactions deleted.", "cleared": plan}), 200
