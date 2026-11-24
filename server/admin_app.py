"""Standalone Flask application for the SoloBiz internal admin portal.

Access model
------------
* Every route declares the roles allowed to use it, and the check runs here on the
  server. Hiding a link in the page is not a control.
* Roles are read from the database on every request, so a role change or a
  deactivation takes effect immediately.
* Detailed merchant records (sales, expenses, activity) need a role that allows
  them AND an open support grant for that one business. The grant needs a ticket
  reference and a reason, and lasts 20 minutes. A reason alone never grants access.
* Every detailed view, every grant, and every change to account access is written
  to the admin audit log with the admin, the business, the reason and the ticket.
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
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

ROLE_LABELS = {
    "owner": "Owner",
    "support": "Support",
    "viewer": "Viewer",
}
ROLES = tuple(ROLE_LABELS)

# Activity that counts as a business using SoloBiz. A sign-in does not.
ACTIVITY_EVENTS = (
    "sale_created", "sale_deleted", "sale_payment_updated",
    "expense_created", "expense_updated", "expense_deleted",
    "inventory_item_created", "inventory_item_updated", "inventory_item_deleted",
)
ACTIVITY_EVENTS_SQL = ",".join(f"'{event}'" for event in ACTIVITY_EVENTS)  # constants only

GRANT_MINUTES = 20
TICKET_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-/.#]{2,39}")
DIRECTORY_PAGE_SIZE = 25
RECORDS_PAGE_SIZE = 50
TABS = ("overview", "sales", "expenses", "activity")

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


def parse_day(value):
    """A YYYY-MM-DD date from user input, or '' when it is not a date."""
    try:
        return date.fromisoformat((value or "").strip()[:10]).isoformat()
    except ValueError:
        return ""


def page_number():
    try:
        return max(1, int(request.args.get("page", "1")))
    except ValueError:
        return 1


def pager(total, page, per_page):
    pages = max(1, -(-total // per_page))
    page = min(page, pages)
    return {
        "page": page,
        "pages": pages,
        "total": total,
        "offset": (page - 1) * per_page,
        "limit": per_page,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


# --- Login throttling -------------------------------------------------------

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


# --- Audit ------------------------------------------------------------------

def log_admin_action(db, admin_id, action, target_type, target_id=None, reason=None, ticket_ref=None):
    cutoff = (utcnow() - timedelta(days=AUDIT_RETENTION_DAYS)).date().isoformat()
    db.execute("DELETE FROM admin_audit_logs WHERE created_at < ?", (cutoff,))
    db.execute(
        "INSERT INTO admin_audit_logs (admin_id, action, target_type, target_id, reason, ticket_ref) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            admin_id, action[:120], target_type,
            str(target_id) if target_id is not None else None,
            (reason or "")[:300] or None,
            (ticket_ref or "")[:40] or None,
        ),
    )


# --- Support grants (per business, time limited) ----------------------------

def active_grant(user_id):
    grants = session.get("admin_grants") or {}
    grant = grants.get(str(user_id))
    if not grant:
        return None
    expires = parse_utc(grant.get("expires_at"))
    if not expires or expires <= utcnow():
        return None
    return grant


def store_grant(user_id, ticket, reason):
    now = utcnow()
    grants = {
        key: value for key, value in (session.get("admin_grants") or {}).items()
        if (parse_utc(value.get("expires_at")) or now) > now
    }
    grants[str(user_id)] = {
        "ticket": ticket,
        "reason": reason,
        "expires_at": (now + timedelta(minutes=GRANT_MINUTES)).isoformat(),
    }
    session["admin_grants"] = grants


def drop_grant(user_id):
    grants = dict(session.get("admin_grants") or {})
    grants.pop(str(user_id), None)
    session["admin_grants"] = grants


# --- Request hooks ----------------------------------------------------------

@admin_app.template_filter("short_time")
def short_time(value):
    """Show a stored UTC timestamp as YYYY-MM-DD HH:MM, whatever format it was saved in."""
    text = str(value or "").replace("T", " ")
    return text[:16] if text else "—"


@admin_app.context_processor
def inject_context():
    token = session.get("admin_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["admin_csrf_token"] = token
    def page_link(number):
        args = dict(request.view_args or {})
        args.update(request.args.to_dict())
        args["page"] = number
        return url_for(request.endpoint, **args)

    return {
        "csrf_token": token,
        "admin_role": ROLE_LABELS.get(session.get("admin_role", ""), ""),
        "page_link": page_link,
    }


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
def purge_expired_admin_audit_logs():
    global _last_audit_cleanup
    now = utcnow()
    if _last_audit_cleanup and now - _last_audit_cleanup < timedelta(hours=24):
        return None
    cutoff = (now - timedelta(days=AUDIT_RETENTION_DAYS)).date().isoformat()
    try:
        with get_db() as db:
            db.execute("DELETE FROM admin_audit_logs WHERE created_at < ?", (cutoff,))
            db.execute("DELETE FROM user_activity_logs WHERE created_at < ?", (cutoff,))
            db.commit()
        _last_audit_cleanup = now
    except Exception:
        logging.exception("Could not purge expired admin or user activity records")
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


# --- Authorisation ----------------------------------------------------------

def require_super_admin(view):
    """Loads the signed-in admin fresh from the database and checks the session is current."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin_id = session.get("super_admin_id")
        if not admin_id:
            return redirect(url_for("login"))
        try:
            with get_db() as db:
                admin = db.execute(
                    "SELECT id, email, role, session_version FROM super_admins "
                    "WHERE id = ? AND is_active = 1",
                    (admin_id,),
                ).fetchone()
        except Exception:
            logging.exception("Could not validate the admin session")
            admin = None
        if not admin or admin["session_version"] != session.get("admin_session_version"):
            session.clear()
            return redirect(url_for("login"))
        session["admin_role"] = admin["role"]
        return view(admin, *args, **kwargs)

    return wrapped


def require_roles(*roles):
    """Allows the view only for the listed roles. Checked on every request."""
    def decorator(view):
        @require_super_admin
        def checked(admin, *args, **kwargs):
            if admin["role"] not in roles:
                return render_template("forbidden.html", admin_email=admin["email"]), 403
            return view(admin, *args, **kwargs)

        return wraps(view)(checked)

    return decorator


ANY_ROLE = ("owner", "support", "viewer")
SUPPORT_ROLES = ("owner", "support")


# --- Routes -----------------------------------------------------------------

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
                    "SELECT id, email, password_hash, role, session_version FROM super_admins "
                    "WHERE LOWER(email) = LOWER(?) AND is_active = 1",
                    (email,),
                ).fetchone()
            if admin and check_password_hash(admin["password_hash"], password):
                clear_admin_login_failures(email)
                with get_db() as db:
                    log_admin_action(db, admin["id"], "signed in", "admin", admin["id"])
                    db.commit()
                session.clear()
                session["super_admin_id"] = admin["id"]
                session["admin_session_version"] = admin["session_version"]
                session["admin_role"] = admin["role"]
                session.permanent = True
                return redirect(url_for("dashboard"))
            record_admin_login_failure(email)
        except Exception:
            logging.exception("Super-admin login failed")
        flash("The email or password is incorrect.", "error")
    return render_template("login.html")


@admin_app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@admin_app.get("/dashboard")
@require_roles(*ANY_ROLE)
def dashboard(admin):
    cutoff = (utcnow() - timedelta(days=6)).date().isoformat()  # 7 calendar days, including today
    with get_db() as db:
        def count(sql, params=()):
            return db.execute(sql, params).fetchone()["n"]

        metrics = {
            "accounts": count("SELECT COUNT(*) AS n FROM users WHERE is_test_account = 0"),
            "test_accounts": count("SELECT COUNT(*) AS n FROM users WHERE is_test_account = 1"),
            "profiles": count(
                "SELECT COUNT(*) AS n FROM business_profiles bp JOIN users u ON u.id = bp.user_id "
                "WHERE u.is_test_account = 0 AND COALESCE(bp.company_name, '') <> ''"
            ),
            "active_7d": count(
                "SELECT COUNT(DISTINCT a.user_id) AS n FROM user_activity_logs a "
                "JOIN users u ON u.id = a.user_id "
                f"WHERE u.is_test_account = 0 AND a.event_type IN ({ACTIVITY_EVENTS_SQL}) "
                "AND substr(a.created_at, 1, 10) >= ?",
                (cutoff,),
            ),
            "signed_in_7d": count(
                "SELECT COUNT(DISTINCT a.user_id) AS n FROM user_activity_logs a "
                "JOIN users u ON u.id = a.user_id "
                "WHERE u.is_test_account = 0 AND a.event_type = 'sign_in' "
                "AND substr(a.created_at, 1, 10) >= ?",
                (cutoff,),
            ),
            "paused": count(
                "SELECT COUNT(*) AS n FROM users WHERE is_test_account = 0 AND account_status = 'paused'"
            ),
        }
    return render_template("dashboard.html", admin_email=admin["email"], metrics=metrics, cutoff=cutoff)


@admin_app.get("/users")
@require_roles(*ANY_ROLE)
def users(admin):
    query = request.args.get("q", "").strip()[:120]
    pattern = f"%{query}%"
    where = (
        "(? = '' OR LOWER(u.email) LIKE LOWER(?) "
        "OR LOWER(COALESCE(u.first_name, '') || ' ' || COALESCE(u.last_name, '')) LIKE LOWER(?) "
        "OR LOWER(COALESCE(bp.company_name, '')) LIKE LOWER(?))"
    )
    params = (query, pattern, pattern, pattern)
    with get_db() as db:
        total = db.execute(
            "SELECT COUNT(*) AS n FROM users u LEFT JOIN business_profiles bp ON bp.user_id = u.id "
            f"WHERE {where}",
            params,
        ).fetchone()["n"]
        page = pager(total, page_number(), DIRECTORY_PAGE_SIZE)
        rows = db.execute(
            "SELECT u.id, u.email, u.account_status, u.is_test_account, bp.company_name, "
            "(SELECT MAX(a.created_at) FROM user_activity_logs a "
            " WHERE a.user_id = u.id AND a.event_type = 'sign_in') AS last_sign_in, "
            "(SELECT MAX(a.created_at) FROM user_activity_logs a "
            " WHERE a.user_id = u.id AND a.event_type IN (" + ACTIVITY_EVENTS_SQL + ")) AS last_activity "
            "FROM users u LEFT JOIN business_profiles bp ON bp.user_id = u.id "
            f"WHERE {where} ORDER BY u.id DESC LIMIT ? OFFSET ?",
            params + (page["limit"], page["offset"]),
        ).fetchall()
    return render_template("users.html", admin_email=admin["email"], users=rows, query=query, page=page)


def business_or_404(db, user_id):
    return db.execute(
        "SELECT u.id, u.email, u.first_name, u.last_name, u.account_status, u.is_test_account, "
        "bp.company_name, bp.business_phone, bp.business_address, bp.store_slug "
        "FROM users u LEFT JOIN business_profiles bp ON bp.user_id = u.id WHERE u.id = ?",
        (user_id,),
    ).fetchone()


def sales_records(db, user_id, start, end, page):
    where = ["i.user_id = ?"]
    params = [user_id]
    if start:
        where.append("substr(i.date, 1, 10) >= ?")
        params.append(start)
    if end:
        where.append("substr(i.date, 1, 10) <= ?")
        params.append(end)
    clause = " AND ".join(where)
    summary = db.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(i.total_value), 0) AS total, "
        "COALESCE(SUM(i.amount_paid), 0) AS received, "
        "COALESCE(SUM(CASE WHEN i.total_value > i.amount_paid THEN i.total_value - i.amount_paid ELSE 0 END), 0) AS outstanding "
        f"FROM income i WHERE {clause}",
        params,
    ).fetchone()
    pg = pager(summary["n"], page, RECORDS_PAGE_SIZE)
    rows = db.execute(
        "SELECT i.id, i.description, i.customer_name, i.total_value, i.amount_paid, "
        "i.payment_mode, i.date, i.receipt_id "
        f"FROM income i WHERE {clause} ORDER BY i.id DESC LIMIT ? OFFSET ?",
        params + [pg["limit"], pg["offset"]],
    ).fetchall()
    return {"summary": summary, "rows": rows, "page": pg}


def expense_records(db, user_id, start, end, page):
    where = ["e.user_id = ?"]
    params = [user_id]
    if start:
        where.append("substr(e.date, 1, 10) >= ?")
        params.append(start)
    if end:
        where.append("substr(e.date, 1, 10) <= ?")
        params.append(end)
    clause = " AND ".join(where)
    summary = db.execute(
        f"SELECT COUNT(*) AS n, COALESCE(SUM(e.amount), 0) AS total FROM expenses e WHERE {clause}",
        params,
    ).fetchone()
    pg = pager(summary["n"], page, RECORDS_PAGE_SIZE)
    rows = db.execute(
        "SELECT e.id, e.category, e.description, e.amount, e.date "
        f"FROM expenses e WHERE {clause} ORDER BY e.id DESC LIMIT ? OFFSET ?",
        params + [pg["limit"], pg["offset"]],
    ).fetchall()
    return {"summary": summary, "rows": rows, "page": pg}


def activity_records(db, user_id, start, end, page):
    where = ["a.user_id = ?"]
    params = [user_id]
    if start:
        where.append("substr(a.created_at, 1, 10) >= ?")
        params.append(start)
    if end:
        where.append("substr(a.created_at, 1, 10) <= ?")
        params.append(end)
    clause = " AND ".join(where)
    total = db.execute(f"SELECT COUNT(*) AS n FROM user_activity_logs a WHERE {clause}", params).fetchone()["n"]
    pg = pager(total, page, RECORDS_PAGE_SIZE)
    rows = db.execute(
        "SELECT a.event_type, a.summary, a.created_at FROM user_activity_logs a "
        f"WHERE {clause} ORDER BY a.id DESC LIMIT ? OFFSET ?",
        params + [pg["limit"], pg["offset"]],
    ).fetchall()
    return {"summary": {"n": total}, "rows": rows, "page": pg}


RECORD_TABS = {
    "sales": ("viewed sales records", sales_records),
    "expenses": ("viewed expense records", expense_records),
    "activity": ("viewed business activity", activity_records),
}


@admin_app.get("/users/<user_id>")
@require_roles(*ANY_ROLE)
def user_detail(admin, user_id):
    tab = request.args.get("tab", "overview")
    if tab not in TABS:
        tab = "overview"
    start = parse_day(request.args.get("from"))
    end = parse_day(request.args.get("to"))
    page = page_number()
    with get_db() as db:
        business = business_or_404(db, user_id)
        if not business:
            return render_template("not_found.html"), 404
        context = {
            "admin_email": admin["email"], "business": business, "tab": tab,
            "date_from": start, "date_to": end, "grant": None, "locked": None, "records": None,
        }
        if tab == "overview":
            context["last_sign_in"] = db.execute(
                "SELECT MAX(created_at) AS t FROM user_activity_logs WHERE user_id = ? AND event_type = 'sign_in'",
                (user_id,),
            ).fetchone()["t"]
            context["last_activity"] = db.execute(
                "SELECT MAX(created_at) AS t FROM user_activity_logs WHERE user_id = ? "
                f"AND event_type IN ({ACTIVITY_EVENTS_SQL})",
                (user_id,),
            ).fetchone()["t"]
            context["audit"] = db.execute(
                "SELECT a.action, a.reason, a.ticket_ref, a.created_at, s.email "
                "FROM admin_audit_logs a JOIN super_admins s ON s.id = a.admin_id "
                "WHERE a.target_type IN ('user', 'business') AND a.target_id = ? "
                "ORDER BY a.id DESC LIMIT 20",
                (user_id,),
            ).fetchall()
        else:
            grant = active_grant(user_id)
            context["grant"] = grant
            if admin["role"] not in SUPPORT_ROLES:
                context["locked"] = "role"
            elif not grant:
                context["locked"] = "grant"
            else:
                action, loader = RECORD_TABS[tab]
                records = loader(db, user_id, start, end, page)
                context["records"] = records
                log_admin_action(
                    db, admin["id"],
                    f"{action}: {records['summary']['n']} matching, page {records['page']['page']}",
                    "business", user_id, grant["reason"], grant["ticket"],
                )
                db.commit()
    return render_template("user_detail.html", **context)


@admin_app.post("/users/<user_id>/access")
@require_roles(*SUPPORT_ROLES)
def open_support_access(admin, user_id):
    ticket = request.form.get("ticket", "").strip()
    reason = request.form.get("reason", "").strip()
    tab = request.form.get("tab", "sales")
    if tab not in RECORD_TABS:
        tab = "sales"
    if not TICKET_PATTERN.fullmatch(ticket):
        flash("Enter a support ticket reference, such as SUP-1042.", "error")
        return redirect(url_for("user_detail", user_id=user_id, tab=tab))
    if not 5 <= len(reason) <= 160:
        flash("Describe the reason in 5 to 160 characters.", "error")
        return redirect(url_for("user_detail", user_id=user_id, tab=tab))
    with get_db() as db:
        if not business_or_404(db, user_id):
            return render_template("not_found.html"), 404
        log_admin_action(db, admin["id"], "opened support access", "business", user_id, reason, ticket)
        db.commit()
    store_grant(user_id, ticket, reason)
    flash(f"Support access opened for {GRANT_MINUTES} minutes. It is recorded in the audit log.", "success")
    return redirect(url_for("user_detail", user_id=user_id, tab=tab))


@admin_app.post("/users/<user_id>/access/close")
@require_roles(*SUPPORT_ROLES)
def close_support_access(admin, user_id):
    grant = active_grant(user_id)
    drop_grant(user_id)
    if grant:
        with get_db() as db:
            log_admin_action(
                db, admin["id"], "closed support access", "business", user_id,
                grant["reason"], grant["ticket"],
            )
            db.commit()
    return redirect(url_for("user_detail", user_id=user_id, tab="overview"))


@admin_app.post("/users/<user_id>/status")
@require_roles(*SUPPORT_ROLES)
def update_user_status(admin, user_id):
    new_status = request.form.get("status", "").strip()
    reason = request.form.get("reason", "").strip()[:200]
    if new_status not in {"active", "paused"} or len(reason) < 3:
        flash("Choose a valid account status and provide a short reason.", "error")
        return redirect(url_for("user_detail", user_id=user_id))
    with get_db() as db:
        if not business_or_404(db, user_id):
            return render_template("not_found.html"), 404
        db.execute("UPDATE users SET account_status = ? WHERE id = ?", (new_status, user_id))
        log_admin_action(
            db, admin["id"], "account " + new_status, "business", user_id, reason,
        )
        db.commit()
    flash("Account access updated and recorded.", "success")
    return redirect(url_for("user_detail", user_id=user_id))


@admin_app.post("/users/<user_id>/test-account")
@require_roles(*SUPPORT_ROLES)
def update_test_marker(admin, user_id):
    marked = request.form.get("marked", "") == "1"
    reason = request.form.get("reason", "").strip()[:200]
    if len(reason) < 3:
        flash("Give a short reason for changing the test-account marker.", "error")
        return redirect(url_for("user_detail", user_id=user_id))
    with get_db() as db:
        if not business_or_404(db, user_id):
            return render_template("not_found.html"), 404
        db.execute("UPDATE users SET is_test_account = ? WHERE id = ?", (1 if marked else 0, user_id))
        log_admin_action(
            db, admin["id"],
            "marked as test account" if marked else "removed test-account marker",
            "business", user_id, reason,
        )
        db.commit()
    flash("Test-account marker updated. Adoption figures now reflect this.", "success")
    return redirect(url_for("user_detail", user_id=user_id))


@admin_app.get("/activity")
@require_roles(*SUPPORT_ROLES)
def activity(admin):
    admin_filter = request.args.get("admin", "").strip()
    business_filter = request.args.get("business", "").strip()[:64]
    action_filter = request.args.get("action", "").strip()[:80]
    start = parse_day(request.args.get("from"))
    end = parse_day(request.args.get("to"))
    where = ["1 = 1"]
    params = []
    if admin_filter.isdigit():
        where.append("a.admin_id = ?")
        params.append(int(admin_filter))
    if business_filter:
        where.append("a.target_type IN ('user', 'business') AND a.target_id = ?")
        params.append(business_filter)
    if action_filter:
        where.append("LOWER(a.action) LIKE LOWER(?)")
        params.append(f"%{action_filter}%")
    if start:
        where.append("substr(a.created_at, 1, 10) >= ?")
        params.append(start)
    if end:
        where.append("substr(a.created_at, 1, 10) <= ?")
        params.append(end)
    clause = " AND ".join(where)
    with get_db() as db:
        total = db.execute(
            f"SELECT COUNT(*) AS n FROM admin_audit_logs a WHERE {clause}", params
        ).fetchone()["n"]
        page = pager(total, page_number(), RECORDS_PAGE_SIZE)
        rows = db.execute(
            "SELECT a.action, a.target_type, a.target_id, a.reason, a.ticket_ref, a.created_at, s.email "
            "FROM admin_audit_logs a JOIN super_admins s ON s.id = a.admin_id "
            f"WHERE {clause} ORDER BY a.id DESC LIMIT ? OFFSET ?",
            params + [page["limit"], page["offset"]],
        ).fetchall()
        admins = db.execute("SELECT id, email FROM super_admins ORDER BY email").fetchall()
    return render_template(
        "activity.html", admin_email=admin["email"], events=rows, page=page, admins=admins,
        filters={
            "admin": admin_filter, "business": business_filter, "action": action_filter,
            "date_from": start, "date_to": end,
        },
    )


@admin_app.get("/system-status")
@require_roles(*ANY_ROLE)
def system_status(admin):
    database_ok = True
    try:
        with get_db() as db:
            db.execute("SELECT 1").fetchone()
    except Exception:
        logging.exception("System status check could not reach the database")
        database_ok = False
    # The SoloBiz app does not record request telemetry yet, so request volume,
    # error rate, latency and recent failures are reported as not available.
    return render_template("system_status.html", admin_email=admin["email"], database_ok=database_ok)


# Friendly labels for activity events written by the SoloBiz app.
EVENT_LABELS = {
    "sign_in": "Signed in",
    "sign_in_failed": "Failed sign-in",
    "sign_in_blocked": "Sign-in blocked (paused)",
    "account_created": "Account created",
    "password_changed": "Password changed",
    "profile_change_code_requested": "Profile change requested",
    "profile_change_rejected": "Profile change rejected",
    "profile_change_verification_failed": "Profile verification failed",
    "business_profile_created": "Business profile created",
    "business_profile_updated": "Business profile updated",
    "sale_created": "Sale recorded",
    "sale_deleted": "Sale deleted",
    "sale_payment_updated": "Payment recorded",
    "expense_created": "Expense recorded",
    "expense_updated": "Expense updated",
    "expense_deleted": "Expense deleted",
    "inventory_item_created": "Inventory item added",
    "inventory_item_updated": "Inventory item updated",
    "inventory_item_deleted": "Inventory item removed",
    "website_published": "Website published",
    "website_unpublished": "Website taken offline",
    "push_enabled": "Stock alerts turned on",
    "push_disabled": "Stock alerts turned off",
    "staff_added": "Staff member added",
    "staff_updated": "Staff member updated",
    "staff_removed": "Staff member removed",
}

# Filter groups for the User activity page. Values are constants, never user input.
EVENT_GROUPS = {
    "sales": ("Sales", ["sale_created", "sale_deleted", "sale_payment_updated"]),
    "expenses": ("Expenses", ["expense_created", "expense_updated", "expense_deleted"]),
    "inventory": ("Inventory", ["inventory_item_created", "inventory_item_updated", "inventory_item_deleted"]),
    "sign_ins": ("Sign-ins and security", ["sign_in", "sign_in_failed", "sign_in_blocked", "password_changed"]),
    "profile": ("Profile and account", ["account_created", "business_profile_created", "business_profile_updated",
                                        "profile_change_code_requested", "profile_change_rejected",
                                        "profile_change_verification_failed"]),
    "website": ("Website", ["website_published", "website_unpublished"]),
    "team": ("Team and alerts", ["staff_added", "staff_updated", "staff_removed",
                                 "push_enabled", "push_disabled"]),
}


def event_label(event_type):
    return EVENT_LABELS.get(event_type, (event_type or "").replace("_", " ").capitalize())


@admin_app.get("/user-activity")
@require_roles(*SUPPORT_ROLES)
def user_activity(admin):
    business_filter = request.args.get("business", "").strip()[:100]
    group_filter = request.args.get("group", "").strip()
    start = parse_day(request.args.get("from"))
    end = parse_day(request.args.get("to"))
    where = ["1 = 1"]
    params = []
    if business_filter:
        where.append("(LOWER(COALESCE(bp.company_name, '')) LIKE LOWER(?) OR a.user_id = ?)")
        params.extend([f"%{business_filter}%", business_filter])
    if group_filter in EVENT_GROUPS:
        types = EVENT_GROUPS[group_filter][1]
        where.append("a.event_type IN (" + ",".join("?" for _ in types) + ")")
        params.extend(types)
    else:
        group_filter = ""
    if start:
        where.append("substr(a.created_at, 1, 10) >= ?")
        params.append(start)
    if end:
        where.append("substr(a.created_at, 1, 10) <= ?")
        params.append(end)
    clause = " AND ".join(where)
    from_sql = "FROM user_activity_logs a JOIN users u ON u.id = a.user_id LEFT JOIN business_profiles bp ON bp.user_id = a.user_id"
    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) AS n {from_sql} WHERE {clause}", params).fetchone()["n"]
        page = pager(total, page_number(), RECORDS_PAGE_SIZE)
        rows = db.execute(
            "SELECT a.user_id, a.event_type, a.summary, a.created_at, bp.company_name, u.is_test_account "
            f"{from_sql} WHERE {clause} ORDER BY a.id DESC LIMIT ? OFFSET ?",
            params + [page["limit"], page["offset"]],
        ).fetchall()
        log_admin_action(
            db, admin["id"],
            f"viewed user activity: {total} matching, page {page['page']}"
            + (f", group {group_filter}" if group_filter else ""),
            "activity", None, None,
        )
        db.commit()
    events = [
        {
            "user_id": row["user_id"],
            "company_name": row["company_name"],
            "is_test_account": row["is_test_account"],
            "created_at": row["created_at"],
            "label": event_label(row["event_type"]),
            "summary": row["summary"],
        }
        for row in rows
    ]
    return render_template(
        "user_activity.html", admin_email=admin["email"], events=events, page=page,
        groups=EVENT_GROUPS,
        filters={"business": business_filter, "group": group_filter, "date_from": start, "date_to": end},
    )


@admin_app.get("/admins")
@require_roles("owner")
def admins(admin):
    with get_db() as db:
        rows = db.execute(
            "SELECT s.id, s.email, s.role, s.is_active, s.created_at, "
            "(SELECT MAX(a.created_at) FROM admin_audit_logs a "
            " WHERE a.admin_id = s.id AND a.action = 'signed in') AS last_sign_in "
            "FROM super_admins s ORDER BY s.id"
        ).fetchall()
    return render_template("admins.html", admin_email=admin["email"], admins=rows, current_id=admin["id"],
                           roles=ROLE_LABELS)


def active_owner_count(db):
    return db.execute(
        "SELECT COUNT(*) AS n FROM super_admins WHERE role = 'owner' AND is_active = 1"
    ).fetchone()["n"]


@admin_app.post("/admins/<int:admin_id>/role")
@require_roles("owner")
def change_admin_role(admin, admin_id):
    new_role = request.form.get("role", "").strip()
    reason = request.form.get("reason", "").strip()[:200]
    if new_role not in ROLES or len(reason) < 3:
        flash("Choose a role and give a short reason.", "error")
        return redirect(url_for("admins"))
    with get_db() as db:
        target = db.execute("SELECT id, email, role, is_active FROM super_admins WHERE id = ?", (admin_id,)).fetchone()
        if not target:
            abort(404)
        if target["id"] == admin["id"]:
            flash("You cannot change your own role.", "error")
            return redirect(url_for("admins"))
        if target["role"] == "owner" and new_role != "owner" and target["is_active"] and active_owner_count(db) <= 1:
            flash("At least one active owner must remain.", "error")
            return redirect(url_for("admins"))
        db.execute(
            "UPDATE super_admins SET role = ?, session_version = session_version + 1 WHERE id = ?",
            (new_role, admin_id),
        )
        log_admin_action(db, admin["id"], f"changed admin role to {new_role}", "admin", admin_id, reason)
        db.commit()
    flash("Admin role updated. That admin must sign in again.", "success")
    return redirect(url_for("admins"))


@admin_app.post("/admins/<int:admin_id>/status")
@require_roles("owner")
def change_admin_status(admin, admin_id):
    active = request.form.get("active", "") == "1"
    reason = request.form.get("reason", "").strip()[:200]
    if len(reason) < 3:
        flash("Give a short reason for changing admin access.", "error")
        return redirect(url_for("admins"))
    with get_db() as db:
        target = db.execute("SELECT id, role, is_active FROM super_admins WHERE id = ?", (admin_id,)).fetchone()
        if not target:
            abort(404)
        if target["id"] == admin["id"]:
            flash("You cannot change your own access.", "error")
            return redirect(url_for("admins"))
        if not active and target["role"] == "owner" and target["is_active"] and active_owner_count(db) <= 1:
            flash("At least one active owner must remain.", "error")
            return redirect(url_for("admins"))
        db.execute(
            "UPDATE super_admins SET is_active = ?, session_version = session_version + 1 WHERE id = ?",
            (1 if active else 0, admin_id),
        )
        log_admin_action(
            db, admin["id"], "admin access " + ("enabled" if active else "disabled"),
            "admin", admin_id, reason,
        )
        db.commit()
    flash("Admin access updated and recorded.", "success")
    return redirect(url_for("admins"))


@admin_app.errorhandler(404)
def admin_not_found(_error):
    return render_template("not_found.html"), 404


@admin_app.errorhandler(500)
def admin_server_error(_error):
    logging.exception("Admin portal error")
    return render_template("error.html"), 500
