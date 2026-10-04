import hmac
import html
import calendar
import json
import logging
import math
import os
import re
import secrets
import smtplib
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import (Flask, Response, jsonify, make_response, redirect,
                   render_template, request, send_from_directory, session,
                   flash)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    import resend
    HAS_RESEND = True
except ImportError:
    HAS_RESEND = False

try:
    import requests as http_requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ==========================================
# FLASK APP CONFIG
# ==========================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_ROOT = os.path.join(PROJECT_ROOT, "client")
app = Flask(
    __name__,
    template_folder=os.path.join(CLIENT_ROOT, "templates"),
    static_folder=os.path.join(CLIENT_ROOT, "static"),
)

_secret_key = os.environ.get("SECRET_KEY")
_is_hosted = bool(os.environ.get("DATABASE_URL") or os.environ.get("RENDER"))
if not _secret_key:
    _secret_key = "solobiz_production_secret_key_987456123_ultra_safe"
    logging.warning("SECRET_KEY environment variable is not set; using fallback production key.")
app.secret_key = _secret_key
app.permanent_session_lifetime = timedelta(days=30)

from .database import get_db, init_db

# Bump this when the offline shell or service worker changes. The value is
# injected into /sw.js so browsers create a fresh cache during deployment.
APP_VERSION = os.environ.get("APP_VERSION", "20261001.1")

# Session / Cookie hardening
_secure_cookie = os.environ.get("SESSION_COOKIE_SECURE")
if _secure_cookie is None:
    app.config["SESSION_COOKIE_SECURE"] = _is_hosted
else:
    app.config["SESSION_COOKIE_SECURE"] = _secure_cookie.strip().lower() in ("1", "true", "yes")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

PASSWORD_PATTERN = re.compile(r"^(?=.*[a-zA-Z])(?=.*\d).{8,}$")
BRAND_COLOR_PATTERN = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
OTP_TTL_MINUTES = 15
OTP_RESEND_SECONDS = 30
OTP_MAX_ATTEMPTS = 5
ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


# ==========================================
# HYBRID CLOUD DATABASE (POSTGRESQL + SQLITE)
# ==========================================






def utcnow():
    return datetime.now(timezone.utc)


def is_valid_password(password):
    return bool(PASSWORD_PATTERN.match(password or ""))


def is_unique_violation(exc):
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message or "already exists" in message


def ensure_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_token_valid():
    expected = session.get("csrf_token") or ""
    sent = (
        request.headers.get("X-CSRFToken")
        or request.form.get("csrf_token")
        or ""
    )
    if request.is_json:
        try:
            payload = request.get_json(silent=True) or {}
            if isinstance(payload, dict) and payload.get("csrf_token"):
                sent = payload.get("csrf_token")
        except Exception:
            pass
    return bool(expected) and hmac.compare_digest(str(sent), str(expected))


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": ensure_csrf_token()}


@app.before_request
def enforce_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        ensure_csrf_token()
        return None
    # Exempt public auth entrypoints from hard CSRF failure so users are never locked out
    exempt_paths = ("/login", "/register")
    if request.path in exempt_paths or request.path.startswith("/api/register/") or request.path.startswith("/api/forgot-password/"):
        return None
    if not csrf_token_valid():
        if request.path.startswith("/api/") or request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "message": "Invalid request token. Refresh the page and try again."}), 400
        flash("Your session expired. Please try again.", "danger")
        return redirect(request.path if request.path in ("/login", "/register") else "/login")
    return None


def get_current_user_id():
    """Retrieve string-based user_id from active Flask session cookie."""
    if "user_id" in session and session["user_id"]:
        user_id = str(session["user_id"])
        # A signed session cookie can outlive its database row. Resolve the
        # account before treating the cookie as authenticated.
        try:
            with get_db() as db:
                exists = db.execute(
                    "SELECT account_status FROM users WHERE id = ?", (user_id,)
                ).fetchone()
            if exists:
                if exists["account_status"] == "active":
                    return user_id
        except Exception as auth_error:
            logging.error("Could not validate the active user session: %s", auth_error)
            return None
        session.clear()
    return None


def sanitize_brand_color(value):
    color = str(value or "").strip()
    if BRAND_COLOR_PATTERN.match(color):
        return color.upper() if len(color) == 7 else color
    return "#4F46E5"


def sanitize_logo_url(value):
    url = str(value or "").strip()
    if not url:
        return ""
    if url.startswith("/static/uploads/logos/") and ".." not in url:
        return url
    if url.startswith("https://") and " " not in url:
        return url
    return ""


def save_uploaded_logo(file_storage, user_id):
    filename = secure_filename(file_storage.filename or "")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        return None, "Logo must be a PNG, JPG, WEBP, or GIF image."
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > app.config["MAX_CONTENT_LENGTH"]:
        return None, "Logo must be smaller than 2MB."
    folder = os.path.join(CLIENT_ROOT, "static", "uploads", "logos")
    os.makedirs(folder, exist_ok=True)
    stored_name = f"logo_{secure_filename(user_id)}_{int(time.time())}{ext}"
    file_storage.save(os.path.join(folder, stored_name))
    return f"/static/uploads/logos/{stored_name}", None


def parse_otp_datetime(value):
    if not value:
        return utcnow()
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return utcnow()


def upsert_otp(email, purpose, payload=None):
    code = f"{secrets.randbelow(1000000):06d}"
    now = utcnow()
    with get_db() as db:
        existing = db.execute(
            "SELECT last_sent FROM otp_codes WHERE email = ? AND purpose = ?",
            (email, purpose)
        ).fetchone()
        if existing:
            elapsed = (now - parse_otp_datetime(existing["last_sent"])).total_seconds()
            if elapsed < OTP_RESEND_SECONDS:
                remaining = int(OTP_RESEND_SECONDS - elapsed)
                return None, remaining
        db.execute(
            "DELETE FROM otp_codes WHERE email = ? AND purpose = ?",
            (email, purpose)
        )
        db.execute(
            """INSERT INTO otp_codes (email, purpose, code_hash, payload, attempts, expires, last_sent)
               VALUES (?, ?, ?, ?, 0, ?, ?)""",
            (
                email,
                purpose,
                generate_password_hash(code),
                payload,
                (now + timedelta(minutes=OTP_TTL_MINUTES)).isoformat(),
                now.isoformat(),
            )
        )
        db.commit()
    return code, 0


def verify_otp(email, purpose, code, consume=True):
    with get_db() as db:
        record = db.execute(
            "SELECT * FROM otp_codes WHERE email = ? AND purpose = ?",
            (email, purpose)
        ).fetchone()
        if not record:
            return None, "No pending verification found. Please request a new PIN."
        item = dict(record)
        if utcnow() > parse_otp_datetime(item.get("expires")):
            db.execute("DELETE FROM otp_codes WHERE email = ? AND purpose = ?", (email, purpose))
            db.commit()
            return None, "Verification PIN expired. Please request a new one."
        attempts = int(item.get("attempts") or 0)
        if attempts >= OTP_MAX_ATTEMPTS:
            db.execute("DELETE FROM otp_codes WHERE email = ? AND purpose = ?", (email, purpose))
            db.commit()
            return None, "Too many incorrect attempts. Please request a new PIN."
        if not check_password_hash(item.get("code_hash") or "", str(code or "").strip()):
            db.execute(
                "UPDATE otp_codes SET attempts = ? WHERE email = ? AND purpose = ?",
                (attempts + 1, email, purpose)
            )
            db.commit()
            return None, "Incorrect verification PIN. Please try again."
        if consume:
            db.execute("DELETE FROM otp_codes WHERE email = ? AND purpose = ?", (email, purpose))
            db.commit()
        return item, None


def otp_delivery_message(email, is_live, code):
    if is_live:
        return f"We sent a 6-digit PIN to {email}. Check your inbox or spam folder."
    if os.environ.get("ALLOW_DEV_OTP") == "1":
        return f"Dev mode — verification PIN: {code}"
    return "Email delivery is not configured. Set RESEND_API_KEY or SMTP credentials, or ALLOW_DEV_OTP=1 for local testing."




init_db()


# ==========================================
# OTP & EMAIL SERVICES (RESEND API + SMTP)
# ==========================================
def _build_otp_html(subject_type: str, otp_code: str) -> str:
    """Build the HTML body for OTP emails."""
    safe_code = html.escape(otp_code)
    safe_type = html.escape(subject_type)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background-color:#f8fafc;margin:0;padding:40px 20px;color:#0f172a;">
  <div style="max-width:480px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;padding:32px;text-align:center;">
    <div style="font-size:22px;font-weight:800;color:#4F46E5;margin-bottom:8px;letter-spacing:-0.4px;">SoloBiz</div>
    <div style="font-size:18px;font-weight:700;color:#0f172a;margin-bottom:12px;">{safe_type}</div>
    <p style="font-size:14px;color:#64748b;line-height:1.6;margin-bottom:24px;">
      Use the 6-digit verification PIN below to continue. This code expires in 15 minutes.
    </p>
    <div style="background:#f8fafc;border:1px solid #c7d2fe;border-radius:12px;padding:18px;font-size:32px;font-weight:800;letter-spacing:8px;color:#4338ca;margin:20px 0;font-family:ui-monospace,monospace;">{safe_code}</div>
    <p style="font-size:13px;color:#94a3b8;margin-top:20px;">If you didn't request this code, you can ignore this email.</p>
  </div>
</body>
</html>"""



def send_otp_email(to_email: str, otp_code: str, subject_type: str = "Email Verification"):
    """
    Send a 6-digit OTP via Resend API (primary) or SMTP (fallback).
    Returns (success: bool, message: str, is_live_delivered: bool).

    Environment variables:
      RESEND_API_KEY        — Resend API key (primary)
      RESEND_FROM_EMAIL     — Verified sender address, e.g. "SoloBiz <noreply@yourdomain.com>"
      SMTP_SERVER           — SMTP host (default: smtp.gmail.com)
      SMTP_PORT             — SMTP port (default: 587)
      SMTP_USER / GMAIL_USER        — SMTP login username
      SMTP_PASSWORD / GMAIL_APP_PASSWORD — SMTP login password
    """
    api_key = os.environ.get("RESEND_API_KEY")
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_user = (os.environ.get("SMTP_USER")
                 or os.environ.get("SMTP_USERNAME")
                 or os.environ.get("GMAIL_USER"))
    smtp_pass = (os.environ.get("SMTP_PASSWORD")
                 or os.environ.get("GMAIL_APP_PASSWORD"))
    from_email = (os.environ.get("RESEND_FROM_EMAIL")
                  or "SoloBiz <noreply@solobiz.dev>")

    subject = f"Your SoloBiz {subject_type} code"
    html_content = _build_otp_html(subject_type, otp_code)
    if os.environ.get("ALLOW_DEV_OTP") == "1":
        print(f"[DEV OTP] {subject_type} for {to_email}: {otp_code}", flush=True)

    # 1. Try Resend API
    if api_key:
        try:
            if HAS_RESEND:
                resend.api_key = api_key
                resend.Emails.send({
                    "from": from_email,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content
                })
            elif HAS_REQUESTS:
                resp = http_requests.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": from_email,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_content
                    },
                    timeout=10
                )
                resp.raise_for_status()
            print(f"✅ OTP email sent via Resend to {to_email}", flush=True)
            return True, "Verification code sent to your email!", True
        except Exception as e:
            logging.error(f"Resend API failed for {to_email}: {e}", exc_info=True)
            print(f"❌ Resend failed: {e}", flush=True)

    # 2. Try SMTP (Gmail or other)
    if smtp_user and smtp_pass:
        try:
            smtp_port = int(os.environ.get("SMTP_PORT") or "587")
            if not 1 <= smtp_port <= 65535:
                raise ValueError("SMTP_PORT must be between 1 and 65535.")
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = to_email
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_email, [to_email], msg.as_string())
            print(f"✅ OTP email sent via SMTP to {to_email}", flush=True)
            return True, "Verification code sent to your email!", True
        except Exception as e:
            logging.error(f"SMTP failed for {to_email}: {e}", exc_info=True)
            print(f"❌ SMTP failed: {e}", flush=True)

    if os.environ.get("ALLOW_DEV_OTP") == "1":
        return True, f"Dev mode — verification PIN: {otp_code}", False
    return False, "Email delivery is not configured.", False


def complete_login(user_id):
    csrf = session.get("csrf_token") or secrets.token_urlsafe(32)
    session.clear()
    session.permanent = True
    session["csrf_token"] = csrf
    session["user_id"] = str(user_id)


def record_user_login(db, user_id):
    try:
        record_user_activity(db, user_id, "sign_in", "Signed in")
    except Exception:
        logging.exception("Could not record sign-in activity for user %s", user_id)
        db.conn.rollback()


def record_user_activity(db, user_id, event_type, summary):
    db.execute(
        "INSERT INTO user_activity_logs (user_id, event_type, summary) VALUES (?, ?, ?)",
        (str(user_id), str(event_type)[:60], str(summary)[:240]),
    )


def send_and_store_otp(email, purpose, payload=None, subject_type="Email Verification"):
    code, wait_seconds = upsert_otp(email, purpose, payload=payload)
    if wait_seconds:
        return False, f"Please wait {wait_seconds}s before requesting a new PIN.", 429, False
    ok, message, is_live = send_otp_email(email, code, subject_type=subject_type)
    if not ok and os.environ.get("ALLOW_DEV_OTP") != "1":
        with get_db() as db:
            db.execute("DELETE FROM otp_codes WHERE email = ? AND purpose = ?", (email, purpose))
            db.commit()
        return False, message, 503, False
    return True, otp_delivery_message(email, is_live, code), 200, is_live
# ==========================================
# FORGOT PASSWORD ROUTES
# ==========================================
GENERIC_RESET_MESSAGE = "If an account exists for that email, we sent a verification PIN."
# ==========================================
# ERROR HANDLERS
# ==========================================
@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/") or request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({"status": "error", "message": "The requested resource was not found."}), 404
    return render_template("404.html"), 404


@app.errorhandler(500)
@app.errorhandler(Exception)
def handle_exception(e):
    logging.error("Unhandled Server Exception: %s", e, exc_info=True)
    if request.path.startswith("/api/") or request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({"status": "error", "message": "An internal server error occurred. Please try again later."}), 500
    return render_template("500.html"), 500



# Import route modules after shared services and error handlers are ready.
from . import routes  # noqa: F401  (imports route modules to register handlers)
