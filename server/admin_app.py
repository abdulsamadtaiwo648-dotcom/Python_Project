"""Standalone Flask application for the SoloBiz super-admin portal."""

import hmac
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlsplit

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from .database import get_db, init_admin_db


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
admin_app = Flask(
    "solobiz_admin",
    template_folder=os.path.join(PROJECT_ROOT, "client", "templates", "admin"),
)

admin_secret = os.environ.get("ADMIN_SECRET_KEY")
if not admin_secret:
    raise RuntimeError("Set ADMIN_SECRET_KEY before starting the SoloBiz admin portal.")
if len(admin_secret) < 32:
    raise RuntimeError("ADMIN_SECRET_KEY must contain at least 32 characters.")
if os.environ.get("RENDER") and not os.environ.get("DATABASE_URL"):
    raise RuntimeError("Set DATABASE_URL on the hosted SoloBiz admin service.")
if os.environ.get("DATABASE_URL"):
    from .database import HAS_PSYCOPG2
    if not HAS_PSYCOPG2:
        raise RuntimeError("Install psycopg2 to connect the admin portal to PostgreSQL.")

admin_app.secret_key = admin_secret
admin_app.config.update(
    SESSION_COOKIE_NAME="solobiz_admin_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get(
        "ADMIN_COOKIE_SECURE", "true" if os.environ.get("RENDER") else "false"
    ).lower() in {"1", "true", "yes"},
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

init_admin_db()

ACCESS_PURPOSES = {
    "support": "Customer support",
    "security": "Security review",
    "operations": "Service operations",
    "legal": "Legal request",
    "other": "Other",
}
SENSITIVE_ENDPOINTS = {
    "dashboard", "users", "user_detail", "update_user_status",
    "sales", "expenses", "activity",
}
ADMIN_LOGIN_WINDOW = timedelta(minutes=15)
ADMIN_LOGIN_LOCKOUT = timedelta(minutes=15)
ADMIN_LOGIN_MAX_ATTEMPTS = 5
AUDIT_RETENTION_DAYS = 365
_last_audit_cleanup = None


def utcnow():
    return datetime.now(timezone.utc)


def parse_utc(value):
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def admin_login_fingerprint(email):
    normalized = (email or "").strip().lower().encode("utf-8")
    return hmac.new(admin_secret.encode("utf-8"), normalized, hashlib.sha256).hexdigest()


def admin_login_locked_until(email):
    fingerprint = admin_login_fingerprint(email)
    now = utcnow()
    with get_db() as db:
        row = db.execute(
            "SELECT blocked_until FROM admin_login_attempts WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        db.execute(
            "DELETE FROM admin_login_attempts WHERE window_started < ?",
            ((now - timedelta(days=1)).isoformat(),),
        )
    return parse_utc(row["blocked_until"]) if row and row["blocked_until"] else None


def record_admin_login_failure(email):
    fingerprint = admin_login_fingerprint(email)
    now = utcnow()
    now_text = now.isoformat()
    with get_db() as db:
        row = db.execute(
            "SELECT attempts, window_started FROM admin_login_attempts WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        started = parse_utc(row["window_started"]) if row else None
        if not row or not started or now - started >= ADMIN_LOGIN_WINDOW:
            attempts = 1
            started = now
        else:
            attempts = int(row["attempts"]) + 1
        blocked_until = (now + ADMIN_LOGIN_LOCKOUT).isoformat() if attempts >= ADMIN_LOGIN_MAX_ATTEMPTS else None
        if row:
            db.execute(
                "UPDATE admin_login_attempts SET attempts = ?, window_started = ?, blocked_until = ? "
                "WHERE fingerprint = ?",
                (attempts, started.isoformat(), blocked_until, fingerprint),
            )
        else:
            db.execute(
                "INSERT INTO admin_login_attempts "
                "(fingerprint, attempts, window_started, blocked_until) VALUES (?, ?, ?, ?)",
                (fingerprint, attempts, now_text, blocked_until),
            )


def clear_admin_login_failures(email):
    with get_db() as db:
        db.execute(
            "DELETE FROM admin_login_attempts WHERE fingerprint = ?",
            (admin_login_fingerprint(email),),
        )


def access_purpose_text():
    access = session.get("admin_data_access") or {}
    purpose = access.get("purpose", "")
    if purpose == "other":
        return f"Other: {access.get('note', '')}"[:140]
    return ACCESS_PURPOSES.get(purpose, "Not provided")


def log_sensitive_view(db, admin, action, target_type, target_id=None, count=None):
    details = f"Purpose: {access_purpose_text()}"
    if count is not None:
        details += f"; records shown: {count}"
    log_admin_action(db, admin["id"], action, target_type, target_id, details)


def log_admin_action(db, admin_id, action, target_type, target_id=None, reason=None):
    cutoff = (utcnow() - timedelta(days=365)).date().isoformat()
    db.execute("DELETE FROM admin_audit_logs WHERE created_at < ?", (cutoff,))
    db.execute(
        "INSERT INTO admin_audit_logs (admin_id, action, target_type, target_id, reason) "
        "VALUES (?, ?, ?, ?, ?)",
        (admin_id, action, target_type, str(target_id) if target_id is not None else None, reason),
    )


@admin_app.context_processor
def inject_csrf_token():
    token = session.get("admin_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["admin_csrf_token"] = token
    access = session.get("admin_data_access") or {}
    purpose = access.get("purpose", "")
    purpose_label = ACCESS_PURPOSES.get(purpose, "Not selected")
    if purpose == "other" and access.get("note"):
        purpose_label = f"Other: {access['note']}"
    return {"csrf_token": token, "data_access_purpose": purpose_label}


@admin_app.before_request
def protect_post_requests():
    if request.method != "POST":
        return None
    expected = session.get("admin_csrf_token") or ""
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRFToken") or ""
    if not expected or not hmac.compare_digest(expected, supplied):
        return "Invalid request token. Refresh the page and try again.", 400
    return None


@admin_app.before_request
def require_data_access_purpose():
    if request.endpoint not in SENSITIVE_ENDPOINTS or not session.get("super_admin_id"):
        return None
    access = session.get("admin_data_access") or {}
    expires = parse_utc(access.get("expires_at"))
    if access.get("purpose") in ACCESS_PURPOSES and expires and expires > utcnow():
        return None
    session.pop("admin_data_access", None)
    target = request.full_path.rstrip("?")
    return redirect(url_for("access_purpose", next=target))


@admin_app.before_request
def purge_expired_admin_audit_logs():
    global _last_audit_cleanup
    now = utcnow()
    if _last_audit_cleanup and now - _last_audit_cleanup < timedelta(hours=24):
        return None
    cutoff = (now - timedelta(days=AUDIT_RETENTION_DAYS)).date().isoformat()
    try:
        with get_db() as db:
            db.execute("DELETE FROM admin_audit_logs WHERE created_at < ?", (cutoff,))
            db.commit()
        _last_audit_cleanup = now
    except Exception:
        logging.exception("Could not purge expired admin audit records")
    return None


@admin_app.after_request
def protect_admin_responses(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


def require_super_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin_id = session.get("super_admin_id")
        if not admin_id:
            return redirect(url_for("login"))
        try:
            with get_db() as db:
                admin = db.execute(
                    "SELECT id, email, session_version FROM super_admins "
                    "WHERE id = ? AND is_active = 1",
                    (admin_id,),
                ).fetchone()
        except Exception:
            logging.exception("Could not validate the admin session")
            admin = None
        if not admin or admin["session_version"] != session.get("admin_session_version"):
            session.clear()
            return redirect(url_for("login"))
        return view(admin, *args, **kwargs)

    return wrapped


@admin_app.get("/")
def home():
    if session.get("super_admin_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


def safe_admin_return_path(value):
    parsed = urlsplit(value or "")
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//") or "\\" in parsed.path:
        return url_for("dashboard")
    return value


@admin_app.route("/access-purpose", methods=["GET", "POST"])
@require_super_admin
def access_purpose(admin):
    next_path = safe_admin_return_path(request.values.get("next", ""))
    if request.method == "POST":
        purpose = request.form.get("purpose", "").strip()
        note = request.form.get("note", "").strip()
        if purpose not in ACCESS_PURPOSES or (purpose == "other" and not 5 <= len(note) <= 120):
            flash("Choose a purpose and add a short note when selecting Other.", "error")
        else:
            session["admin_data_access"] = {
                "purpose": purpose,
                "note": note[:120] if purpose == "other" else "",
                "expires_at": (utcnow() + timedelta(minutes=20)).isoformat(),
            }
            return redirect(next_path)
    return render_template(
        "access_purpose.html", admin_email=admin["email"], next_path=next_path,
    )


@admin_app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("super_admin_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        try:
            locked_until = admin_login_locked_until(email)
            if locked_until and locked_until > utcnow():
                flash("Too many sign-in attempts. Try again in 15 minutes.", "error")
                return render_template("login.html"), 429
            with get_db() as db:
                admin = db.execute(
                    "SELECT id, email, password_hash, session_version FROM super_admins "
                    "WHERE LOWER(email) = LOWER(?) AND is_active = 1",
                    (email,),
                ).fetchone()
            if admin and check_password_hash(admin["password_hash"], password):
                clear_admin_login_failures(email)
                with get_db() as db:
                    log_admin_action(db, admin["id"], "signed in", "admin", admin["id"])
                session.clear()
                session["super_admin_id"] = admin["id"]
                session["admin_session_version"] = admin["session_version"]
                session.permanent = True
                return redirect(url_for("dashboard"))
            record_admin_login_failure(email)
        except Exception:
            logging.exception("Super-admin login failed")
        flash("The email or password is incorrect.", "error")
    return render_template("login.html")


@admin_app.get("/dashboard")
@require_super_admin
def dashboard(admin):
    current_month = datetime.now().strftime("%Y-%m")
    with get_db() as db:
        metrics = {
            "users": db.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"],
            "businesses": db.execute("SELECT COUNT(*) AS total FROM business_profiles").fetchone()["total"],
            "sales": db.execute("SELECT COALESCE(SUM(total_value), 0) AS total FROM income").fetchone()["total"],
            "collected": db.execute("SELECT COALESCE(SUM(amount_paid), 0) AS total FROM income").fetchone()["total"],
            "outstanding": db.execute(
                "SELECT COALESCE(SUM(CASE WHEN total_value > amount_paid "
                "THEN total_value - amount_paid ELSE 0 END), 0) AS total FROM income"
            ).fetchone()["total"],
            "expenses": db.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM expenses").fetchone()["total"],
            "month_sales": db.execute(
                "SELECT COALESCE(SUM(amount_paid), 0) AS total FROM income WHERE date LIKE ?",
                (f"{current_month}%",),
            ).fetchone()["total"],
            "month_expenses": db.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM expenses WHERE date LIKE ?",
                (f"{current_month}%",),
            ).fetchone()["total"],
            "paused": db.execute(
                "SELECT COUNT(*) AS total FROM users WHERE account_status = 'paused'"
            ).fetchone()["total"],
            "recent_activity": db.execute(
                "SELECT action, target_type, target_id, reason, created_at "
                "FROM admin_audit_logs ORDER BY id DESC LIMIT 6"
            ).fetchall(),
        }
        log_sensitive_view(db, admin, "viewed platform overview", "analytics")
        db.commit()
    return render_template("dashboard.html", admin_email=admin["email"], metrics=metrics)


@admin_app.get("/users")
@require_super_admin
def users(admin):
    query = request.args.get("q", "").strip()[:120]
    pattern = f"%{query}%"
    with get_db() as db:
        rows = db.execute(
            "SELECT u.id, u.email, u.first_name, u.last_name, u.account_status, bp.company_name "
            "FROM users u LEFT JOIN business_profiles bp ON bp.user_id = u.id "
            "WHERE (? = '' OR LOWER(u.email) LIKE LOWER(?) "
            "OR LOWER(COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(bp.company_name, '')) LIKE LOWER(?)) "
            "ORDER BY u.id DESC LIMIT 200",
            (query, pattern, pattern, pattern),
        ).fetchall()
        log_sensitive_view(db, admin, "viewed business directory", "business_directory", count=len(rows))
        db.commit()
    return render_template("users.html", admin_email=admin["email"], users=rows, query=query)


@admin_app.get("/users/<user_id>")
@require_super_admin
def user_detail(admin, user_id):
    with get_db() as db:
        user = db.execute(
            "SELECT u.id, u.email, u.first_name, u.last_name, u.account_status, "
            "bp.company_name, bp.business_phone, bp.business_address, bp.store_slug "
            "FROM users u LEFT JOIN business_profiles bp ON bp.user_id = u.id WHERE u.id = ?",
            (user_id,),
        ).fetchone()
        if not user:
            return render_template("not_found.html"), 404
        sales = db.execute(
            "SELECT id, description, total_value, amount_paid, date "
            "FROM income WHERE user_id = ? ORDER BY id DESC LIMIT 100", (user_id,)
        ).fetchall()
        expenses = db.execute(
            "SELECT id, category, description, amount, date "
            "FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 100", (user_id,)
        ).fetchall()
        log_sensitive_view(
            db, admin, "viewed business account and transactions", "user", user_id,
            count=len(sales) + len(expenses),
        )
        audit = db.execute(
            "SELECT action, reason, created_at FROM admin_audit_logs "
            "WHERE target_type = 'user' AND target_id = ? ORDER BY id DESC LIMIT 20", (user_id,)
        ).fetchall()
    return render_template(
        "user_detail.html", admin_email=admin["email"], user=user,
        sales=sales, expenses=expenses, audit=audit,
    )


@admin_app.post("/users/<user_id>/status")
@require_super_admin
def update_user_status(admin, user_id):
    new_status = request.form.get("status", "").strip()
    reason = request.form.get("reason", "").strip()[:200]
    if new_status not in {"active", "paused"} or len(reason) < 3:
        flash("Choose a valid account status and provide a short reason.", "error")
        return redirect(url_for("user_detail", user_id=user_id))
    with get_db() as db:
        user = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return render_template("not_found.html"), 404
        db.execute("UPDATE users SET account_status = ? WHERE id = ?", (new_status, user_id))
        log_admin_action(
            db, admin["id"], "account " + new_status, "user", user_id,
            f"{reason} (access purpose: {access_purpose_text()})",
        )
        db.commit()
    flash("Account access updated.", "success")
    return redirect(url_for("user_detail", user_id=user_id))


def transaction_rows(table, filters, limit=200):
    query = filters.get("q", "").strip()[:100]
    category = filters.get("category", "").strip()[:80]
    minimum = filters.get("min_amount", "").strip()[:30]
    maximum = filters.get("max_amount", "").strip()[:30]
    pattern = f"%{query}%"
    where = [
        "(? = '' OR LOWER(source.label) LIKE LOWER(?) OR LOWER(source.email) LIKE LOWER(?) "
        "OR LOWER(COALESCE(source.company_name, '')) LIKE LOWER(?))"
    ]
    params = [query, pattern, pattern, pattern]
    try:
        if minimum:
            min_value = Decimal(minimum)
            if not min_value.is_finite() or min_value < 0:
                raise InvalidOperation
            where.append("source.amount >= ?")
            params.append(str(min_value))
    except InvalidOperation:
        minimum = ""
    try:
        if maximum:
            max_value = Decimal(maximum)
            if not max_value.is_finite() or max_value < 0:
                raise InvalidOperation
            where.append("source.amount <= ?")
            params.append(str(max_value))
    except InvalidOperation:
        maximum = ""
    if minimum and maximum and Decimal(minimum) > Decimal(maximum):
        minimum, maximum = "", ""
        where = [part for part in where if part not in {"source.amount >= ?", "source.amount <= ?"}]
        params = params[:4]
    if table == "sales":
        from_sql = (
            "FROM income i JOIN users u ON u.id = i.user_id "
            "LEFT JOIN business_profiles bp ON bp.user_id = u.id"
        )
        select_sql = (
            "SELECT i.id, i.description AS label, i.total_value AS amount, "
            "i.amount_paid AS paid, i.date, i.payment_mode AS detail, u.email, bp.company_name "
        )
        if category == "paid":
            where.append("i.amount_paid >= i.total_value")
        elif category == "unpaid":
            where.append("i.amount_paid <= 0")
        elif category == "partial":
            where.append("i.amount_paid > 0 AND i.amount_paid < i.total_value")
        else:
            category = ""
        where_sql = " AND ".join(where).replace("source.label", "i.description").replace("source.email", "u.email").replace("source.company_name", "bp.company_name").replace("source.amount", "i.total_value")
    else:
        from_sql = (
            "FROM expenses e JOIN users u ON u.id = e.user_id "
            "LEFT JOIN business_profiles bp ON bp.user_id = u.id"
        )
        select_sql = (
            "SELECT e.id, COALESCE(e.description, e.category) AS label, e.amount, "
            "NULL AS paid, e.date, e.category AS detail, u.email, bp.company_name "
        )
        if category:
            where.append("LOWER(e.category) = LOWER(?)")
            params.append(category)
        where_sql = " AND ".join(where).replace("source.label", "e.description").replace("source.email", "u.email").replace("source.company_name", "bp.company_name").replace("source.amount", "e.amount")
    params.append(limit)
    with get_db() as db:
        rows = db.execute(
            f"{select_sql}{from_sql} WHERE {where_sql} ORDER BY 1 DESC LIMIT ?", params
        ).fetchall()
    return rows, query, category, minimum, maximum


@admin_app.get("/sales")
@require_super_admin
def sales(admin):
    rows, query, status_filter, minimum, maximum = transaction_rows("sales", request.args)
    with get_db() as db:
        log_sensitive_view(db, admin, "viewed sales records", "sales", count=len(rows))
        db.commit()
    return render_template(
        "transactions.html", admin_email=admin["email"], heading="Sales",
        rows=rows, query=query, detail_filter=status_filter, is_sales=True,
        min_amount=minimum, max_amount=maximum,
    )


@admin_app.get("/expenses")
@require_super_admin
def expenses(admin):
    rows, query, category_filter, minimum, maximum = transaction_rows("expenses", request.args)
    with get_db() as db:
        log_sensitive_view(db, admin, "viewed expense records", "expenses", count=len(rows))
        db.commit()
    return render_template(
        "transactions.html", admin_email=admin["email"], heading="Expenses",
        rows=rows, query=query, detail_filter=category_filter, is_sales=False,
        min_amount=minimum, max_amount=maximum,
    )


@admin_app.get("/activity")
@require_super_admin
def activity(admin):
    with get_db() as db:
        log_sensitive_view(db, admin, "viewed admin audit history", "admin_audit_logs")
        db.commit()
        rows = db.execute(
            "SELECT a.action, a.target_type, a.target_id, a.reason, a.created_at, s.email "
            "FROM admin_audit_logs a JOIN super_admins s ON s.id = a.admin_id "
            "ORDER BY a.id DESC LIMIT 200"
        ).fetchall()
    return render_template("activity.html", admin_email=admin["email"], events=rows)


@admin_app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@admin_app.errorhandler(404)
def admin_not_found(_error):
    return render_template("not_found.html"), 404
