"""Money in that is not a sale: list, add, edit and delete. Transfers are recorded here too, but are
kept out of the business's money-in list and totals."""

import math
from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request

from server.database import get_db

from .. import accounts as acc
from .. import core
from .. import money_in as mi
from .. import record_rules as rules
from ..compat import JsonRouter, jsonify
from ..deps import current_user_id
from ..subscriptions import history_cutoff

record_user_activity = core.record_user_activity
router = JsonRouter()


def _parse(db, data, request, user_id, current=None):
    """(fields, None) when the body is valid, or (None, error response). `current` is the row being
    edited, if any."""
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

    current_id = current["account_id"] if current else None
    if kind == mi.TRANSFER:
        to_row = acc.account_for_business(db, user_id, data.get("account_id"))
        from_row = acc.account_for_business(db, user_id, data.get("from_account_id"))
        if to_row is None or from_row is None:
            return None, (jsonify({"status": "error", "message": "Choose the account the money came from and the account it goes to."}), 400)
        if to_row["id"] == from_row["id"]:
            return None, (jsonify({"status": "error", "message": "A transfer needs two different accounts."}), 400)
        if to_row["archived"] or from_row["archived"]:
            return None, (jsonify({"status": "error", "message": "Transfers need active accounts. Restore the archived account first."}), 400)
        account_id, from_account_id = to_row["id"], from_row["id"]
    else:
        account_id, error = acc.resolve_for_entry(db, user_id, data.get("account_id"), current_id)
        if error:
            return None, (jsonify({"status": "error", "message": error}), 400)
        from_account_id = None
    return {"amount": amount, "kind": kind, "description": description, "entry_day": entry_day,
            "account_id": account_id, "from_account_id": from_account_id}, None


@router.api_route("/api/money-in", methods=['GET'])
def list_money_in(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    with get_db() as db:
        cutoff = history_cutoff(user_id)
        sql = ("SELECT id, amount, kind, description, date, entry_date, account_id FROM money_in "
               "WHERE user_id = ? AND kind != ?")
        params = (user_id, mi.TRANSFER)
        if cutoff:
            sql += " AND entry_date >= ?"
            params = (user_id, mi.TRANSFER, cutoff)
        rows = db.execute(sql + " ORDER BY entry_date DESC, id DESC", params).fetchall()
    items = [{"id": r["id"], "amount": float(r["amount"]), "kind": r["kind"], "description": r["description"],
              "date": r["date"], "entry_date": r["entry_date"], "account_id": r["account_id"]} for r in rows]
    return jsonify({"status": "success", "money_in": items, "kinds": mi.INCOME_KINDS, "transfer": mi.TRANSFER}), 200


@router.api_route("/api/money-in", methods=['POST'])
def add_money_in(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = payload if isinstance(payload, dict) else {}
    with get_db() as db:
        acc.ensure_default(db, user_id)
        fields, error = _parse(db, data, request, user_id)
        if error:
            return error
        stamp = rules.display_stamp(fields["entry_day"])
        cursor = db.execute(
            "INSERT INTO money_in (user_id, amount, kind, description, date, entry_date, entered_at, account_id, from_account_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, fields["amount"], fields["kind"], fields["description"], stamp, fields["entry_day"],
             datetime.now(timezone.utc).isoformat(), fields["account_id"], fields["from_account_id"]),
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

        current = db.execute("SELECT id, account_id, kind FROM money_in WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone()
        if not current:
            return jsonify({"status": "error", "message": "That entry was not found."}), 404
        data = payload if isinstance(payload, dict) else {}
        fields, error = _parse(db, data, request, user_id, current=current)
        if error:
            return error
        updated = db.execute(
            "UPDATE money_in SET amount = ?, kind = ?, description = ?, date = ?, entry_date = ?, account_id = ?, from_account_id = ? "
            "WHERE id = ? AND user_id = ?",
            (fields["amount"], fields["kind"], fields["description"], rules.display_stamp(fields["entry_day"]),
             fields["entry_day"], fields["account_id"], fields["from_account_id"], item_id, user_id),
        )
        if updated.rowcount:
            record_user_activity(db, user_id, "money_in_updated", "Changed money in")
        db.commit()
    return jsonify({"status": "success", "message": "Saved"}), 200
