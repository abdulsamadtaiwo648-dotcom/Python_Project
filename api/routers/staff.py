"""Team: the owner creates staff accounts, sets their password and their pages."""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from werkzeug.security import generate_password_hash

from server.database import get_db

from .. import core
from .. import permissions as perm
from ..deps import require_user

router = APIRouter(prefix="/api/staff")


def _fail(message, status=400, **extra):
    return JSONResponse({"status": "error", "message": message, **extra}, status_code=status)


class StaffIn(BaseModel):
    name: str = ""
    email: str = ""
    password: str = ""
    role: str = "sales"
    pages: list[str] = []


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    pages: Optional[list[str]] = None
    password: Optional[str] = None


def _pages_for(role, pages):
    if role == "custom":
        chosen = [p for p in pages if p in perm.PAGES]
        return chosen
    if role in perm.ROLES:
        return list(perm.ROLES[role]["pages"])
    return None


def _view(db, row):
    user = db.execute("SELECT email, first_name, last_name FROM users WHERE id = ?", (row["user_id"],)).fetchone()
    pages = perm.staff_pages(row)
    role = perm.ROLES.get(row["role"], {}).get("label", "Custom")
    name = " ".join(x for x in [user["first_name"], user["last_name"]] if x) if user else ""
    return {"id": row["user_id"], "name": name, "email": user["email"] if user else "", "role": row["role"],
            "role_label": role, "pages": pages, "created_at": row["created_at"]}


@router.get("")
def list_staff(request: Request, owner_id: str = Depends(require_user)):
    with get_db() as db:
        rows = db.execute("SELECT * FROM staff_members WHERE owner_id = ? ORDER BY created_at", (owner_id,)).fetchall()
        staff = [_view(db, dict(r)) for r in rows]
    used, limit = perm.seat_usage(owner_id)
    return {
        "status": "success",
        "staff": staff,
        "seats": {"used": used, "limit": limit},
        "roles": [{"key": k, "label": v["label"], "pages": v["pages"], "blurb": v["blurb"]} for k, v in perm.ROLES.items()],
        "pages": [{"key": k, "label": v} for k, v in perm.PAGES.items()],
    }


@router.post("")
def add_staff(body: StaffIn, owner_id: str = Depends(require_user)):
    email = body.email.strip().lower()
    name = body.name.strip()
    if not name or not email or "@" not in email:
        return _fail("Enter the staff member's name and a valid email address.")
    if not core.is_valid_password(body.password):
        return _fail("The password must be at least 8 characters and include a letter and a number.")
    pages = _pages_for(body.role, body.pages)
    if pages is None:
        return _fail("Choose a role.")
    if not pages:
        return _fail("Tick at least one page for this role.")
    used, limit = perm.seat_usage(owner_id)
    if used >= limit:
        return _fail(
            f"Your plan allows {limit} staff account{'s' if limit != 1 else ''}. "
            + ("Upgrade to add more staff." if limit < 10 else "Remove someone to add another."),
            403, code="upgrade_required", feature="staff",
        )
    first, _, last = name.partition(" ")
    user_id = f"staff_{uuid.uuid4().hex[:16]}"
    try:
        with get_db() as db:
            if db.execute("SELECT 1 FROM users WHERE LOWER(email) = ?", (email,)).fetchone():
                return _fail("That email already has a SoloBiz account. Use a different email for this staff member.")
            db.execute(
                "INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                (user_id, email, generate_password_hash(body.password), first, last),
            )
            db.execute(
                "INSERT INTO staff_members (user_id, owner_id, role, pages, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, owner_id, body.role, _json(pages), perm.now_iso()),
            )
            perm.record(db, owner_id, "staff_added", f"Added staff member {name} as {perm.ROLES[body.role]['label']}")
            db.commit()
    except Exception:
        logging.exception("Could not create staff account")
        return _fail("Could not create the account. Please try again.", 500)
    return {"status": "success", "message": f"{name} can now sign in with the email and password you set.", "id": user_id}


@router.put("/{staff_id}")
def update_staff(staff_id: str, body: StaffUpdate, owner_id: str = Depends(require_user)):
    with get_db() as db:
        row = db.execute("SELECT * FROM staff_members WHERE user_id = ? AND owner_id = ?", (staff_id, owner_id)).fetchone()
        if not row:
            return _fail("That staff member was not found.", 404)
        row = dict(row)
        role = body.role or row["role"]
        if body.role is not None or body.pages is not None:
            pages = _pages_for(role, body.pages if body.pages is not None else perm.staff_pages(row))
            if pages is None:
                return _fail("Choose a role.")
            if not pages:
                return _fail("Tick at least one page for this role.")
            db.execute("UPDATE staff_members SET role = ?, pages = ? WHERE user_id = ?", (role, _json(pages), staff_id))
        if body.name is not None:
            name = body.name.strip()
            if not name:
                return _fail("Enter a name.")
            first, _, last = name.partition(" ")
            db.execute("UPDATE users SET first_name = ?, last_name = ? WHERE id = ?", (first, last, staff_id))
        if body.password:
            if not core.is_valid_password(body.password):
                return _fail("The password must be at least 8 characters and include a letter and a number.")
            db.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(body.password), staff_id))
        perm.record(db, owner_id, "staff_updated", "Changed a staff member's access or details")
        db.commit()
        updated = dict(db.execute("SELECT * FROM staff_members WHERE user_id = ?", (staff_id,)).fetchone())
        view = _view(db, updated)
    return {"status": "success", "message": "Saved.", "staff": view}


@router.delete("/{staff_id}")
def remove_staff(staff_id: str, owner_id: str = Depends(require_user)):
    with get_db() as db:
        row = db.execute("SELECT 1 FROM staff_members WHERE user_id = ? AND owner_id = ?", (staff_id, owner_id)).fetchone()
        if not row:
            return _fail("That staff member was not found.", 404)
        db.execute("DELETE FROM staff_members WHERE user_id = ? AND owner_id = ?", (staff_id, owner_id))
        db.execute("DELETE FROM users WHERE id = ?", (staff_id,))
        perm.record(db, owner_id, "staff_removed", "Removed a staff member")
        db.commit()
    return {"status": "success", "message": "Access removed. They can no longer sign in."}


def _json(value):
    return json.dumps(value)
