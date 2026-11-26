"""Accounts: list, add, rename, set the default, archive and restore. Owners change accounts; staff with
a sales, expenses, dashboard or reports page can read them."""

from datetime import datetime, timezone
from typing import Any

from fastapi import Body, Request

from server.database import get_db

from .. import accounts as acc
from .. import core
from datetime import date as date_cls

from .. import ledger
from ..compat import JsonRouter, jsonify
from ..deps import current_user_id
from ..money import naira_text, parse_naira, today_iso

record_user_activity = core.record_user_activity
router = JsonRouter()


def _error(message, status=400):
    return jsonify({"status": "error", "message": message}), status


def _body(payload):
    return payload if isinstance(payload, dict) else {}


@router.api_route("/api/accounts", methods=['GET'])
def list_accounts(request: Request, payload: Any = Body(None)):
    owner_id = current_user_id(request)
    if not owner_id:
        return _error("Unauthorized", 401)
    with get_db() as db:
        acc.ensure_default(db, owner_id)
        rows = acc.all_accounts(db, owner_id)
        default = acc.default_account(db, owner_id)
    return jsonify({
        "status": "success",
        "accounts": [acc.view(r) for r in rows],
        "default_id": default["id"] if default else None,
    }), 200


@router.api_route("/api/accounts", methods=['POST'])
def add_account(request: Request, payload: Any = Body(None)):
    owner_id = current_user_id(request)
    if not owner_id:
        return _error("Unauthorized", 401)
    data = _body(payload)
    name = str(data.get("name") or "").strip()
    problem = acc.name_problem(name)
    if problem:
        return _error(problem)
    opening_text = data.get("opening_balance")
    kobo = 0
    if opening_text not in (None, ""):
        kobo = parse_naira(opening_text)
        if kobo is None:
            return _error("Enter the opening balance as an amount, for example 5000 or 5,000.50.")
    day, error = acc.opening_date_for(str(data.get("opening_date") or "").strip())
    if error:
        return _error(error)
    with get_db() as db:
        acc.ensure_default(db, owner_id)
        if acc.name_taken(db, owner_id, name):
            return _error(f"You already have an account called {acc.name_taken(db, owner_id, name)['name']}.")
        cursor = db.execute(
            "INSERT INTO accounts (user_id, name, is_default, archived, opening_kobo, opening_date, created_at) "
            "VALUES (?, ?, 0, 0, ?, ?, ?)",
            (owner_id, name, kobo, day, datetime.now(timezone.utc).isoformat()),
        )
        record_user_activity(db, owner_id, "account_added", "Added an account")
        db.commit()
        row = acc.account_for_business(db, owner_id, cursor.lastrowid)
    return jsonify({"status": "success", "message": "Account added", "account": acc.view(row)}), 201


@router.api_route("/api/accounts/{account_id}", methods=['PUT'])
def change_account(account_id: int, request: Request, payload: Any = Body(None)):
    owner_id = current_user_id(request)
    if not owner_id:
        return _error("Unauthorized", 401)
    data = _body(payload)
    with get_db() as db:
        acc.ensure_default(db, owner_id)
        row = acc.account_for_business(db, owner_id, account_id)
        if not row:
            return _error("That account was not found.", 404)

        updates = {}
        if "name" in data:
            name = str(data.get("name") or "").strip()
            problem = acc.name_problem(name)
            if problem:
                return _error(problem)
            clash = acc.name_taken(db, owner_id, name, exclude_id=row["id"])
            if clash:
                return _error(f"You already have an account called {clash['name']}.")
            updates["name"] = name
        if "opening_balance" in data:
            kobo = parse_naira(data.get("opening_balance")) if data.get("opening_balance") not in (None, "") else 0
            if kobo is None:
                return _error("Enter the opening balance as an amount, for example 5000 or 5,000.50.")
            updates["opening_kobo"] = kobo
        if "opening_date" in data:
            day, error = acc.opening_date_for(str(data.get("opening_date") or "").strip())
            if error:
                return _error(error)
            updates["opening_date"] = day
        if "archived" in data:
            archive = bool(data.get("archived"))
            if archive and row["is_default"]:
                return _error("The default account cannot be archived. Make another account the default first.")
            updates["archived"] = 1 if archive else 0
        if data.get("is_default") is True:
            if row["archived"] or updates.get("archived") == 1:
                return _error("Restore the account before making it the default.")
            # The rule is one default per business: clear the old one first, then set this one.
            db.execute("UPDATE accounts SET is_default = 0 WHERE user_id = ? AND is_default = 1", (owner_id,))
            updates["is_default"] = 1
        elif data.get("is_default") is False and row["is_default"]:
            return _error("Choose another account as the default instead.")

        if updates:
            assignments = ", ".join(f"{column} = ?" for column in updates)
            db.execute(
                f"UPDATE accounts SET {assignments} WHERE id = ? AND user_id = ?",
                (*updates.values(), account_id, owner_id),
            )
            record_user_activity(db, owner_id, "account_changed", "Changed an account")
        db.commit()
        row = acc.account_for_business(db, owner_id, account_id)
    return jsonify({"status": "success", "message": "Account saved", "account": acc.view(row)}), 200


def _item(e):
    return {"date": e["day"], "direction": e["direction"], "amount": naira_text(e["kobo"]),
            "label": e["label"], "source": e["source"], "counterpart": e["counterpart"],
            "approximate": e["approximate"], "ref": e["ref"]}


@router.api_route("/api/accounts/{account_id}/statement", methods=['GET'])
def account_statement(account_id: int, request: Request, payload: Any = Body(None)):
    """One account for a week (Monday to Sunday) or a month, containing the date asked for."""
    owner_id = current_user_id(request)
    if not owner_id:
        return _error("Unauthorized", 401)
    kind = request.query_params.get("period", "month")
    if kind not in ("week", "month"):
        return _error("Choose a week or a month.")
    raw = request.query_params.get("date") or today_iso()
    try:
        anchor = date_cls.fromisoformat(raw)
    except ValueError:
        return _error("Choose a date in the form YYYY-MM-DD.")
    with get_db() as db:
        acc.ensure_default(db, owner_id)
        row = acc.account_for_business(db, owner_id, account_id)
        if row is None:
            return _error("That account was not found.", 404)
        st = ledger.statement(db, owner_id, row, kind, anchor)
    closing = st["closing"]
    return jsonify({
        "status": "success",
        "account": acc.view(row),
        "period": {"kind": kind, "start": st["start"], "end": st["end"],
                   "previous_anchor": st["previous_anchor"], "next_anchor": st["next_anchor"]},
        "opening": {
            "balance": naira_text(st["opening"]),
            "starting_balance": naira_text(st["starting_balance"]),
            "starting_balance_in_period": naira_text(st["starting_balance_in_period"]),
            "activity_before": naira_text(st["activity_before"]),
            "starting_balance_date": st["starting_balance_date"],
        },
        "receipts": {"total": naira_text(st["receipts_total"]), "items": [_item(e) for e in st["receipts"]]},
        "payments": {"total": naira_text(st["payments_total"]), "items": [_item(e) for e in st["payments"]]},
        "closing": {"balance": naira_text(closing), "overspent": naira_text(-closing) if closing < 0 else None},
    }), 200
