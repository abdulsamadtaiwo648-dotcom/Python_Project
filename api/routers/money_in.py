"""Money in that is not a sale: list, add, edit and delete."""

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request

from server.database import get_db

from .. import core
from .. import money_in as mi
from .. import record_rules as rules
from ..compat import JsonRouter, jsonify
from ..deps import current_user_id
from ..subscriptions import history_cutoff

record_user_activity = core.record_user_activity
router = JsonRouter()


def _parse(data, request, user_id):
    """(fields, None) when the body is valid, or (None, error response)."""
    try:
        amount = float(str(data.get("amount", "")).replace(",", ""))
    except (TypeError, ValueError):
        return None, (jsonify({"status": "error", "message": "Amount must be a valid number"}), 400)
    if not math.isfinite(amount) or amount <= 0:
        return None, (jsonify({"status": "error", "message": "Amount must be a positive number"}), 400)
    kind = str(data.get("kind", "")).strip()
    if kind not in mi.KINDS:
        return None, (jsonify({"status": "error", "message": "Choose what kind of money this is."}), 400)
    description = str(data.get("description") or "").strip()
    if rules.too_long(description, rules.MAX_DESCRIPTION):
        core.log_refused_input(user_id, request.url.path, "money in description too long")
        return None, (jsonify({"status": "error", "message": "The note must be 200 characters or fewer."}), 400)
    entry_day, entry_err = rules.check_entry_date(data.get("entry_date"))
    if entry_err:
        core.log_refused_input(user_id, request.url.path, "money in date " + entry_err)
        return None, (jsonify({"status": "error", "message": f"Choose a valid date: {entry_err}."}), 400)
    return {"amount": amount, "kind": kind, "description": description, "entry_day": entry_day}, None


@router.api_route("/api/money-in", methods=['GET'])
def list_money_in(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    with get_db() as db:
        cutoff = history_cutoff(user_id)
        sql = "SELECT id, amount, kind, description, date, entry_date FROM money_in WHERE user_id = ?"
        params = (user_id,)
        if cutoff:
            sql += " AND entry_date >= ?"
            params = (user_id, cutoff)
        rows = db.execute(sql + " ORDER BY entry_date DESC, id DESC", params).fetchall()
    items = [{"id": r["id"], "amount": float(r["amount"]), "kind": r["kind"], "description": r["description"],
              "date": r["date"], "entry_date": r["entry_date"]} for r in rows]
    return jsonify({"status": "success", "money_in": items, "kinds": mi.KINDS}), 200


@router.api_route("/api/money-in", methods=['POST'])
def add_money_in(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = payload if isinstance(payload, dict) else {}
    fields, error = _parse(data, request, user_id)
    if error:
        return error
    stamp = rules.display_stamp(fields["entry_day"])
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO money_in (user_id, amount, kind, description, date, entry_date, entered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, fields["amount"], fields["kind"], fields["description"], stamp, fields["entry_day"],
             datetime.now(timezone.utc).isoformat()),
        )
        record_user_activity(db, user_id, "money_in_added", "Recorded money in")
        db.commit()
        new_id = cursor.lastrowid
    return jsonify({"status": "success", "message": "Money in recorded",
                    "item": {"id": new_id, **fields, "date": stamp}}), 201


@router.api_route("/api/money-in/{item_id}", methods=['PUT', 'DELETE'])
def change_money_in(item_id: int, request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    with get_db() as db:
        if request.method == "DELETE":
            deleted = db.execute("DELETE FROM money_in WHERE id = ? AND user_id = ?", (item_id, user_id))
            if deleted.rowcount:
                record_user_activity(db, user_id, "money_in_deleted", "Deleted money in")
            db.commit()
            if not deleted.rowcount:
                return jsonify({"status": "error", "message": "That entry was not found."}), 404
            return jsonify({"status": "success", "message": "Deleted"}), 200

        data = payload if isinstance(payload, dict) else {}
        fields, error = _parse(data, request, user_id)
        if error:
            return error
        updated = db.execute(
            "UPDATE money_in SET amount = ?, kind = ?, description = ?, date = ?, entry_date = ? WHERE id = ? AND user_id = ?",
            (fields["amount"], fields["kind"], fields["description"], rules.display_stamp(fields["entry_day"]),
             fields["entry_day"], item_id, user_id),
        )
        if updated.rowcount:
            record_user_activity(db, user_id, "money_in_updated", "Changed money in")
        db.commit()
        if not updated.rowcount:
            return jsonify({"status": "error", "message": "That entry was not found."}), 404
    return jsonify({"status": "success", "message": "Saved"}), 200
