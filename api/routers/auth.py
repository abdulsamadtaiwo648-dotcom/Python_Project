"""Authentication: register with e-mail PIN, sign in/out, password reset."""

import json
import logging
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from werkzeug.security import check_password_hash, generate_password_hash

from server.database import get_db

from .. import core
from ..deps import current_user_id

router = APIRouter(prefix="/api")


def fail(message, status=400):
    return JSONResponse({"status": "error", "message": message}, status_code=status)


def ok(**extra):
    return {"status": "ok", **extra}


def complete_login(request: Request, user_id):
    import secrets

    csrf = request.session.get("csrf_token") or secrets.token_urlsafe(32)
    request.session.clear()
    request.session["csrf_token"] = csrf
    request.session["user_id"] = str(user_id)


def record_user_login(db, user_id):
    try:
        core.record_user_activity(db, user_id, "sign_in", "Signed in")
    except Exception:
        logging.exception("Could not record sign-in activity for user %s", user_id)
        db.conn.rollback()


def find_user(email):
    with get_db() as db:
        return db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()


def log_for(email, event, summary):
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
        if user:
            core.record_user_activity(db, user["id"], event, summary)
            db.commit()
    return user


class Email(BaseModel):
    email: str = ""


class RegisterRequest(BaseModel):
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    password: str = ""
    confirm_password: str = ""
    privacy_accepted: bool = False


class VerifyRequest(BaseModel):
    email: str = ""
    code: str = ""


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""


class ResetRequest(BaseModel):
    email: str = ""
    code: str = ""
    password: str = ""


def norm(value):
    return (value or "").strip().lower()


@router.get("/session")
def session_info(request: Request):
    user_id = current_user_id(request)
    user = None
    if user_id:
        with get_db() as db:
            row = db.execute("SELECT id, email, first_name, last_name FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            user = {"id": row["id"], "email": row["email"], "first_name": row["first_name"], "last_name": row["last_name"]}
    return {"status": "ok", "csrf_token": request.session.get("csrf_token", ""), "user": user}


@router.post("/register/request")
def register_request(body: RegisterRequest):
    email = norm(body.email)
    first, last = body.first_name.strip(), body.last_name.strip()
    if not email or not first or not last or not body.password or not body.confirm_password:
        return fail("Complete all required fields.")
    if not body.privacy_accepted:
        return fail("Please review and accept the Privacy Policy to create an account.")
    if body.password != body.confirm_password:
        return fail("Passwords do not match.")
    if not core.is_valid_password(body.password):
        return fail("Password must be at least 8 characters long and contain both letters and numbers.")
    if find_user(email):
        return fail("Email already registered. Please log in.")
    payload = json.dumps({"password": generate_password_hash(body.password), "first_name": first, "last_name": last})
    sent, message, status, _ = core.send_and_store_otp(email, "register", payload, "Email Verification")
    if not sent:
        return fail(message, status)
    return ok(message=message, code=None)


@router.post("/register/verify")
def register_verify(body: VerifyRequest):
    email, code = norm(body.email), body.code.strip()
    if not email or not code:
        return fail("Email and verification PIN are required.")
    if find_user(email):
        return fail("Email already registered. Please log in.")
    record, error = core.verify_otp(email, "register", code, consume=False)
    if error:
        return fail(error)
    user_id = f"user_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    registration = json.loads(record.get("payload") or "{}")
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                (user_id, email, registration.get("password"), registration.get("first_name"), registration.get("last_name")),
            )
            core.record_user_activity(db, user_id, "account_created", "Created a SoloBiz account")
            db.commit()
    except Exception as exc:
        logging.error("register_verify error: %s", exc, exc_info=True)
        if core.is_unique_violation(exc):
            return fail("Email already registered. Please log in.")
        return fail("Failed to verify account. Please try again.", 500)
    core.verify_otp(email, "register", code, consume=True)
    return ok(message="Account created. Please sign in.", redirect="/login")


@router.post("/register/resend")
def register_resend(body: Email):
    email = norm(body.email)
    if not email:
        return fail("Email address is required.")
    with get_db() as db:
        existing = db.execute(
            "SELECT payload FROM otp_codes WHERE email = ? AND purpose = ?", (email, "register")
        ).fetchone()
    if not existing:
        return fail("No pending registration found for this email.")
    sent, message, status, _ = core.send_and_store_otp(email, "register", existing["payload"], "Email Verification")
    if not sent:
        return fail(message, status)
    return ok(message=message, code=None)


@router.post("/login")
def login(body: LoginRequest, request: Request):
    email, password = norm(body.email), body.password
    if not email or not password:
        return fail("Please enter both email and password.")
    if core.login_locked_until(email):
        return fail("Too many sign-in attempts. Please wait 15 minutes or reset your password.", 429)
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
        # Older accounts were saved with surrounding spaces removed.
        password_ok = bool(user and user["password"]) and (
            check_password_hash(user["password"], password)
            or (password != password.strip() and check_password_hash(user["password"], password.strip()))
        )
        if not password_ok:
            if user:
                core.record_user_activity(db, user["id"], "sign_in_failed", "Unsuccessful sign-in attempt")
                db.commit()
            core.record_login_failure(email)
            return fail("Invalid email or password. Please try again.", 401)
        if user["account_status"] != "active":
            core.record_user_activity(db, user["id"], "sign_in_blocked", "Sign-in attempt blocked because the account is paused")
            db.commit()
            return fail("This account is currently unavailable. Please contact support.", 403)
        record_user_login(db, user["id"])
        complete_login(request, user["id"])
    core.clear_login_failures(email)
    return ok(redirect="/dashboard")


@router.post("/logout")
def logout(request: Request):
    try:
        from .push import remove_session_push_subscription

        remove_session_push_subscription(request)
    except Exception:
        logging.exception("Could not remove this device's push subscription on sign-out")
    request.session.clear()
    return ok(redirect="/login")


@router.post("/forgot-password/request")
def forgot_request(body: Email):
    email = norm(body.email)
    if not email:
        return fail("Please enter a valid email address.")
    if log_for(email, "password_change_requested", "Requested a password reset"):
        sent, message, status, _ = core.send_and_store_otp(email, "reset", None, "Password Reset")
        if not sent:
            return fail(message, status)
    return ok(message=core.GENERIC_RESET_MESSAGE, code=None)


@router.post("/forgot-password/resend")
def forgot_resend(body: Email):
    email = norm(body.email)
    if not email:
        return fail("Please enter a valid email address.")
    if log_for(email, "password_reset_code_resent", "Requested another password reset code"):
        sent, message, status, _ = core.send_and_store_otp(email, "reset", None, "Password Reset")
        if not sent:
            return fail(message, status)
    return ok(message=core.GENERIC_RESET_MESSAGE, code=None)


@router.post("/forgot-password/reset")
def forgot_reset(body: ResetRequest, request: Request):
    email, code, new_password = norm(body.email), body.code.strip(), body.password
    if not email or not code or not new_password:
        if email:
            log_for(email, "password_change_failed", "Password change submission was incomplete")
        return fail("Email, verification PIN, and new password are required.")
    if not core.is_valid_password(new_password):
        log_for(email, "password_change_failed", "Password change attempt did not meet security requirements")
        return fail("New password must be at least 8 characters and include a letter and a number.")
    if not find_user(email):
        # Same answer as a missing code: no account enumeration.
        return fail("No pending verification found. Please request a new PIN.")
    _, error = core.verify_otp(email, "reset", code, consume=True)
    if error:
        log_for(email, "password_change_failed", "Password reset verification failed")
        return fail(error)
    with get_db() as db:
        db.execute("UPDATE users SET password = ? WHERE LOWER(email) = LOWER(?)", (generate_password_hash(new_password), email))
        db.commit()
        user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
        if user:
            core.record_user_activity(db, user["id"], "password_changed", "Password was changed through account recovery")
            record_user_login(db, user["id"])
            complete_login(request, user["id"])
    core.clear_login_failures(email)
    return ok(message="Password updated successfully!", redirect="/dashboard")
