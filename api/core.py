"""Framework-neutral services shared by the API routers: validation, one-time
PINs, sign-in lockout, e-mail delivery and activity logging."""

import hashlib
import hmac
import html
import logging
import os
import re
import secrets
import smtplib
import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from werkzeug.security import check_password_hash, generate_password_hash

from server.database import get_db

from .settings import settings

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

MAX_LOGO_BYTES = 2 * 1024 * 1024
PASSWORD_PATTERN = re.compile(r"^(?=.*[a-zA-Z])(?=.*\d).{8,}$")
BRAND_COLOR_PATTERN = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
OTP_TTL_MINUTES = 15
OTP_RESEND_SECONDS = 30
OTP_MAX_ATTEMPTS = 5

def utcnow():
    return datetime.now(timezone.utc)


def is_valid_password(password):
    return bool(PASSWORD_PATTERN.match(password or ""))


def is_unique_violation(exc):
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    message = str(exc).lower()
    return "unique" in message or "duplicate" in message or "already exists" in message


def sanitize_brand_color(value):
    color = str(value or "").strip()
    if BRAND_COLOR_PATTERN.match(color):
        return color.upper() if len(color) == 7 else color
    return "#1d4ed8"


LOGO_URL_MAX_LENGTH = 500
_LOGO_UNSAFE_CHARS = re.compile(r"[\s\"'<>\\`\x00-\x1f\x7f]")


def sanitize_logo_url(value):
    """Return the logo URL if it is safe to place in an href or src, otherwise an empty string.
    Accepts our own /media/<token> and /static/uploads/logos/ paths, or an https URL with a real host."""
    url = str(value or "").strip()
    if not url or len(url) > LOGO_URL_MAX_LENGTH or _LOGO_UNSAFE_CHARS.search(url):
        return ""
    if url.startswith("/media/"):
        return url if re.fullmatch(r"/media/[A-Za-z0-9_-]{16,40}", url) else ""
    if url.startswith("/static/uploads/logos/"):
        return url if re.fullmatch(r"/static/uploads/logos/[A-Za-z0-9_-]+\.(png|jpe?g|webp)", url) else ""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return ""
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443):
        return ""
    if re.fullmatch(r"[0-9.]+", host):
        return ""  # IP addresses are not logo hosts
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", host) or any(label.startswith("-") or label.endswith("-") for label in host.split(".")):
        return ""
    return url


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


LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_LOCKOUT = timedelta(minutes=15)


def _login_fingerprint(email):
    normalized = (email or "").strip().lower().encode("utf-8")
    return hmac.new(settings.secret_key.encode("utf-8"), normalized, hashlib.sha256).hexdigest()


def login_locked_until(email):
    """Return when the sign-in lockout for this email ends, or None."""
    with get_db() as db:
        row = db.execute(
            "SELECT blocked_until FROM user_login_attempts WHERE fingerprint = ?",
            (_login_fingerprint(email),),
        ).fetchone()
    if not row or not row["blocked_until"]:
        return None
    until = parse_otp_datetime(row["blocked_until"])
    return until if until > utcnow() else None


def record_login_failure(email):
    fingerprint = _login_fingerprint(email)
    now = utcnow()
    with get_db() as db:
        row = db.execute(
            "SELECT attempts, window_started FROM user_login_attempts WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        started = parse_otp_datetime(row["window_started"]) if row else None
        if not row or now - started >= LOGIN_WINDOW:
            attempts, started = 1, now
        else:
            attempts = int(row["attempts"]) + 1
        blocked_until = (now + LOGIN_LOCKOUT).isoformat() if attempts >= LOGIN_MAX_ATTEMPTS else None
        if row:
            db.execute(
                "UPDATE user_login_attempts SET attempts = ?, window_started = ?, blocked_until = ? "
                "WHERE fingerprint = ?",
                (attempts, started.isoformat(), blocked_until, fingerprint),
            )
        else:
            db.execute(
                "INSERT INTO user_login_attempts (fingerprint, attempts, window_started, blocked_until) "
                "VALUES (?, ?, ?, ?)",
                (fingerprint, attempts, started.isoformat(), blocked_until),
            )
        db.commit()


def clear_login_failures(email):
    with get_db() as db:
        db.execute(
            "DELETE FROM user_login_attempts WHERE fingerprint = ?",
            (_login_fingerprint(email),),
        )
        db.commit()


def otp_delivery_message(email, is_live, code):
    if is_live:
        return f"We sent a 6-digit PIN to {email}. Check your inbox or spam folder."
    if os.environ.get("ALLOW_DEV_OTP") == "1":
        return f"Dev mode — verification PIN: {code}"
    return "Email delivery is not configured. Set RESEND_API_KEY or SMTP credentials, or ALLOW_DEV_OTP=1 for local testing."




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
    <div style="font-size:22px;font-weight:800;color:#1d4ed8;margin-bottom:8px;letter-spacing:-0.4px;">SoloBiz</div>
    <div style="font-size:18px;font-weight:700;color:#0f172a;margin-bottom:12px;">{safe_type}</div>
    <p style="font-size:14px;color:#64748b;line-height:1.6;margin-bottom:24px;">
      Use the 6-digit verification PIN below to continue. This code expires in 15 minutes.
    </p>
    <div style="background:#f8fafc;border:1px solid #bfdbfe;border-radius:12px;padding:18px;font-size:32px;font-weight:800;letter-spacing:8px;color:#1e40af;margin:20px 0;font-family:ui-monospace,monospace;">{safe_code}</div>
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


GENERIC_RESET_MESSAGE = "If an account exists for that email, we sent a verification PIN."
