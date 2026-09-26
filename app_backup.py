<<<<<<< HEAD
import hmac
import html
=======
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
import logging
import math
import os
import random
import re
<<<<<<< HEAD
import secrets
=======
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
import smtplib
import sqlite3
import time
import uuid
<<<<<<< HEAD
from datetime import datetime, timedelta, timezone
=======
from datetime import datetime, timedelta
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import (Flask, Response, jsonify, make_response, redirect,
                   render_template, request, send_from_directory, session,
                   flash)
<<<<<<< HEAD
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
=======
from werkzeug.security import check_password_hash, generate_password_hash
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

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
app = Flask(__name__)
<<<<<<< HEAD

_secret_key = os.environ.get("SECRET_KEY")
_is_hosted = bool(os.environ.get("DATABASE_URL") or os.environ.get("RENDER"))
if not _secret_key:
    if _is_hosted:
        raise RuntimeError("SECRET_KEY environment variable is required in production.")
    _secret_key = secrets.token_hex(32)
    logging.warning("SECRET_KEY is not set; using an ephemeral key. Sessions reset on restart.")
app.secret_key = _secret_key
app.permanent_session_lifetime = timedelta(days=30)

# Bump this when the offline shell or service worker changes. The value is
# injected into /sw.js so browsers create a fresh cache during deployment.
APP_VERSION = os.environ.get("APP_VERSION", "20260925.1")

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
=======
app.secret_key = os.environ.get("SECRET_KEY", "solobiz_production_secret_key_12345_super_safe")
app.permanent_session_lifetime = timedelta(days=30)


# Bump this when the offline shell or service worker changes. The value is
# injected into /sw.js so browsers create a fresh cache during deployment.
APP_VERSION = os.environ.get("APP_VERSION", "20260924.7")

# Session / Cookie hardening
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("DATABASE_URL") is not None  # True on Render (HTTPS)
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)


# ==========================================
# HYBRID CLOUD DATABASE (POSTGRESQL + SQLITE)
# ==========================================
class CursorWrapper:
    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class DBWrapper:
    def __init__(self, conn, is_postgres=False):
        self.conn = conn
        self.is_postgres = is_postgres

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            if hasattr(self.conn, "rollback"):
                try:
                    self.conn.rollback()
                except Exception:
                    pass
        else:
            if hasattr(self.conn, "commit"):
                try:
                    self.conn.commit()
                except Exception:
                    pass
        if hasattr(self.conn, "close"):
            try:
                self.conn.close()
            except Exception:
                pass

    def execute(self, sql, params=()):
        if self.is_postgres:
            pg_sql = sql.replace("?", "%s")
            if "CREATE TABLE" in pg_sql.upper():
                pg_sql = pg_sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                pg_sql = pg_sql.replace("REAL", "NUMERIC")

            cur = self.conn.cursor()
            is_insert = "INSERT INTO" in pg_sql.upper()
            if is_insert and "RETURNING" not in pg_sql.upper():
                pg_sql += " RETURNING id"

            cur.execute(pg_sql, params)

            last_id = None
            if is_insert:
                try:
                    row = cur.fetchone()
                    if row:
                        if isinstance(row, dict) and "id" in row:
                            last_id = row["id"]
                        elif hasattr(row, "__getitem__"):
                            last_id = row[0]
                except Exception:
                    last_id = None
            return CursorWrapper(cur, lastrowid=last_id)
        else:
            cur = self.conn.cursor()
            cur.execute(sql, params)
            return cur

    def commit(self):
        if hasattr(self.conn, "commit"):
            self.conn.commit()


def get_db():
    database_url = os.environ.get("DATABASE_URL")
    if database_url and HAS_PSYCOPG2:
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
        return DBWrapper(conn, is_postgres=True)
    else:
        conn = sqlite3.connect("solobiz.db")
        conn.row_factory = sqlite3.Row
        return DBWrapper(conn, is_postgres=False)


<<<<<<< HEAD
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
    if not csrf_token_valid():
        if request.path.startswith("/api/") or request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "message": "Invalid request token. Refresh the page and try again."}), 400
        flash("Your session expired. Please try again.", "danger")
        return redirect(request.path if request.path in ("/login", "/register") else "/login")
    return None


=======
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
def get_current_user_id():
    """Retrieve string-based user_id from active Flask session cookie."""
    if "user_id" in session and session["user_id"]:
        return str(session["user_id"])
    return None

<<<<<<< HEAD

def get_user_profile(user_id):
    try:
        with get_db() as db:
            row = db.execute(
                "SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as exc:
        logging.error("Profile lookup failed: %s", exc, exc_info=True)
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
    folder = os.path.join(app.root_path, "static", "uploads", "logos")
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

=======
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)

def init_db():
    database_url = os.environ.get("DATABASE_URL")
    if database_url and HAS_PSYCOPG2:
        # PostgreSQL Cloud Migration & Table Initialization
        tables = [
            """CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                amount NUMERIC NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                date TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS business_profiles (
                id SERIAL PRIMARY KEY,
                user_id TEXT UNIQUE NOT NULL,
                company_name TEXT,
                business_phone TEXT,
                business_address TEXT,
                instagram_handle TEXT,
                whatsapp_number TEXT,
                store_policy TEXT,
                brand_color TEXT DEFAULT '#4F46E5',
                logo_url TEXT,
                store_slug TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS income (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                total_value NUMERIC NOT NULL DEFAULT 0,
                amount_paid NUMERIC NOT NULL DEFAULT 0,
                customer_name TEXT,
                payment_mode TEXT DEFAULT 'Cash',
                date TEXT,
                receipt_id TEXT
            )""",
            """CREATE TABLE IF NOT EXISTS inventory_presets (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                item_name TEXT NOT NULL,
                price NUMERIC NOT NULL,
                stock INTEGER DEFAULT 0
            )"""
        ]
        for tbl_sql in tables:
            try:
                with get_db() as db:
                    db.execute(tbl_sql)
                    db.commit()
            except Exception as e:
                print(f"Table init note: {e}", flush=True)

        migrations = [
            "ALTER TABLE users ALTER COLUMN id DROP DEFAULT",
            "ALTER TABLE users ALTER COLUMN id TYPE TEXT USING id::TEXT",
            "ALTER TABLE expenses ALTER COLUMN user_id DROP DEFAULT",
            "ALTER TABLE expenses ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT",
            "ALTER TABLE income ALTER COLUMN user_id DROP DEFAULT",
            "ALTER TABLE income ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT",
            "ALTER TABLE business_profiles ALTER COLUMN user_id DROP DEFAULT",
            "ALTER TABLE business_profiles ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS receipt_id TEXT",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS total_value NUMERIC DEFAULT 0",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS amount_paid NUMERIC DEFAULT 0",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS payment_mode TEXT DEFAULT 'Cash'",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS instagram_handle TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS whatsapp_number TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS store_policy TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS brand_color TEXT DEFAULT '#4F46E5'",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS logo_url TEXT",
<<<<<<< HEAD
                "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS store_slug TEXT",
            """CREATE TABLE IF NOT EXISTS otp_codes (
                email TEXT NOT NULL,
                purpose TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                payload TEXT,
                attempts INTEGER DEFAULT 0,
                expires TEXT NOT NULL,
                last_sent TEXT NOT NULL,
                PRIMARY KEY (email, purpose)
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_business_profiles_store_slug ON business_profiles (store_slug)"
=======
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS store_slug TEXT"
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
        ]
        for alter_cmd in migrations:
            try:
                with get_db() as db:
                    db.execute(alter_cmd)
                    db.commit()
            except Exception as e:
                print(f"Migration note for '{alter_cmd}': {e}", flush=True)

        # Fail-safe: verify and convert user_id column types to TEXT
        for target_table, target_col in [("users", "id"), ("expenses", "user_id"), ("income", "user_id"), ("business_profiles", "user_id")]:
            try:
                with get_db() as db:
                    res = db.execute(f"""
                        SELECT data_type
                        FROM information_schema.columns
                        WHERE table_name = '{target_table}' AND column_name = '{target_col}'
                    """).fetchone()
                    if res:
                        col_type = str(res["data_type"] if isinstance(res, dict) and "data_type" in res else (res[0] if hasattr(res, "__getitem__") else "")).lower()
                        if "int" in col_type:
                            print(f"{target_table}.{target_col} is '{col_type}'. Converting to TEXT...", flush=True)
                            db.execute(f"ALTER TABLE {target_table} ALTER COLUMN {target_col} DROP DEFAULT")
                            db.execute(f"ALTER TABLE {target_table} ALTER COLUMN {target_col} TYPE TEXT USING {target_col}::TEXT")
                            db.commit()
                            print(f"{target_table}.{target_col} converted to TEXT successfully!", flush=True)
            except Exception as col_ex:
                print(f"Fail-safe conversion note for {target_table}.{target_col}: {col_ex}", flush=True)
    else:
        with get_db() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    date TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS business_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE,
                    company_name TEXT,
                    business_phone TEXT,
                    business_address TEXT,
                    instagram_handle TEXT,
                    whatsapp_number TEXT,
                    store_policy TEXT,
                    brand_color TEXT DEFAULT '#4F46E5',
                    logo_url TEXT,
                    store_slug TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS income (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    description TEXT NOT NULL,
                    total_value REAL NOT NULL,
                    amount_paid REAL NOT NULL,
                    customer_name TEXT,
                    payment_mode TEXT DEFAULT 'Cash',
                    date TEXT,
                    receipt_id TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS inventory_presets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    stock INTEGER DEFAULT 0
                )
            """)
            for col_name, col_type in [
                ("instagram_handle", "TEXT"),
                ("whatsapp_number", "TEXT"),
                ("store_policy", "TEXT"),
                ("brand_color", "TEXT DEFAULT '#4F46E5'"),
                ("logo_url", "TEXT"),
                ("store_slug", "TEXT"),
<<<<<<< HEAD
=======
                ("receipt_id", "TEXT"),
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
            ]:
                try:
                    db.execute(f"ALTER TABLE business_profiles ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
            try:
                db.execute("ALTER TABLE income ADD COLUMN receipt_id TEXT")
            except Exception:
                pass
<<<<<<< HEAD
            db.execute("""
                CREATE TABLE IF NOT EXISTS otp_codes (
                    email TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    payload TEXT,
                    attempts INTEGER DEFAULT 0,
                    expires TEXT NOT NULL,
                    last_sent TEXT NOT NULL,
                    PRIMARY KEY (email, purpose)
                )
            """)
            try:
                db.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_business_profiles_store_slug "
                    "ON business_profiles (store_slug)"
                )
            except Exception:
                pass
=======
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
            db.commit()

    # Repair legacy duplicate storefront slugs so one public URL cannot expose
    # another user's business profile.
    try:
        with get_db() as db:
            rows = db.execute(
                "SELECT id, user_id, store_slug FROM business_profiles "
                "WHERE store_slug IS NOT NULL ORDER BY id ASC"
            ).fetchall()
            seen_slugs = set()
            for row in rows:
                item = dict(row)
                slug = str(item.get("store_slug") or "").strip()
                slug_key = slug.lower()
                if not slug or slug_key not in seen_slugs:
                    if slug:
                        seen_slugs.add(slug_key)
                    continue

                base_slug = slug
                owner_suffix = re.sub(r"[^a-z0-9]", "", str(item.get("user_id", "")).lower())[-8:] or "vendor"
                candidate = f"{base_slug}-{owner_suffix}"
                counter = 2
                while candidate.lower() in seen_slugs:
                    candidate = f"{base_slug}-{owner_suffix}-{counter}"
                    counter += 1
                db.execute(
                    "UPDATE business_profiles SET store_slug = ? WHERE id = ?",
                    (candidate, item["id"])
                )
                seen_slugs.add(candidate.lower())
            db.commit()
    except Exception as repair_error:
        print(f"Storefront slug repair note: {repair_error}", flush=True)


init_db()


# ==========================================
# OTP & EMAIL SERVICES (RESEND API + SMTP)
# ==========================================
<<<<<<< HEAD
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
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
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
=======
# In-memory stores for pending OTP codes (keyed by email)
RESET_CODES = {}
REGISTRATION_CODES = {}


def _build_otp_html(subject_type: str, otp_code: str) -> str:
    """Build the HTML body for OTP emails."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background-color:#0f172a;margin:0;padding:40px 20px;color:#f8fafc;">
  <div style="max-width:480px;margin:0 auto;background:#1e293b;border:1px solid #334155;border-radius:16px;padding:32px;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,0.3);">
    <div style="font-size:24px;font-weight:800;color:#6366f1;margin-bottom:8px;letter-spacing:-0.5px;">SoloBiz</div>
    <div style="font-size:20px;font-weight:700;color:#ffffff;margin-bottom:12px;">{subject_type}</div>
    <p style="font-size:14px;color:#94a3b8;line-height:1.6;margin-bottom:24px;">
      Use the 6-digit verification PIN below to verify your email address. This code expires in 15 minutes.
    </p>
    <div style="background:#0f172a;border:2px dashed #6366f1;border-radius:12px;padding:18px;font-size:32px;font-weight:900;letter-spacing:8px;color:#818cf8;margin:20px 0;font-family:monospace;">{otp_code}</div>
    <p style="font-size:13px;color:#64748b;margin-top:20px;">If you didn't request this code, please ignore this email.</p>
    <div style="font-size:12px;color:#475569;margin-top:24px;border-top:1px solid #334155;padding-top:16px;">&copy; SoloBiz &mdash; Smart Finance for Independent Vendors</div>
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
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = (os.environ.get("SMTP_USER")
                 or os.environ.get("SMTP_USERNAME")
                 or os.environ.get("GMAIL_USER"))
    smtp_pass = (os.environ.get("SMTP_PASSWORD")
                 or os.environ.get("GMAIL_APP_PASSWORD"))
    from_email = (os.environ.get("RESEND_FROM_EMAIL")
                  or "SoloBiz <noreply@solobiz.dev>")

    subject = f"Your SoloBiz {subject_type} Code: {otp_code}"
    html_content = _build_otp_html(subject_type, otp_code)

    # Always log to server console (visible in Render logs)
    print(f"\n==========================================", flush=True)
    print(f"🔑 [{subject_type.upper()}] PIN for {to_email}: {otp_code}", flush=True)
    print(f"==========================================\n", flush=True)

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

    # 3. Dev/test fallback — PIN is printed in server logs
    print(f"ℹ️  No live email configured — dev mode. PIN shown above.", flush=True)
    return True, f"Dev PIN: {otp_code}", False
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        otp_code = request.form.get("otp_code", "").strip()

<<<<<<< HEAD
=======
        # ── Step 2: Verify OTP and create account ──
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
        if otp_code:
            if not email:
                flash("Email is required for OTP verification.", "danger")
                return render_template("register.html")
<<<<<<< HEAD
            record, error = verify_otp(email, "register", otp_code, consume=False)
            if error:
                flash(error, "danger")
                return render_template("register.html", step="otp", pending_email=email)
            new_user_id = f"user_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            try:
                with get_db() as db:
                    db.execute(
                        "INSERT INTO users (id, email, password) VALUES (?, ?, ?)",
                        (new_user_id, email, record.get("payload"))
                    )
                    db.commit()
                verify_otp(email, "register", otp_code, consume=True)
                complete_login(new_user_id)
                flash("Email verified! Welcome to SoloBiz!", "success")
                return redirect("/dashboard")
            except Exception as e:
                logging.error(f"Account creation failed after OTP verify: {e}", exc_info=True)
                if is_unique_violation(e):
                    flash("Email already registered. Please log in.", "danger")
                    return render_template("register.html")
                flash("Account creation failed. Please try again.", "danger")
                return render_template("register.html", step="otp", pending_email=email)

        if not email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html")
        if not is_valid_password(password):
            flash("Password must be at least 8 characters and include a letter and a number.", "danger")
            return render_template("register.html")

        try:
            with get_db() as db:
                existing = db.execute(
                    "SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)
                ).fetchone()
                if existing:
                    flash("Email already registered. Please log in.", "danger")
                    return render_template("register.html", error="Email already registered. Please log in.")
        except Exception as e:
            logging.error(f"User check error during registration: {e}", exc_info=True)
            flash("Could not start registration. Please try again.", "danger")
            return render_template("register.html")

        ok, message, status, is_live = send_and_store_otp(
            email, "register", generate_password_hash(password), "Email Verification"
        )
        flash(message, "success" if ok else "danger")
        if not ok:
            return render_template("register.html"), status if status != 429 else 200
        return render_template("register.html", step="otp", pending_email=email)

    return render_template("register.html")


@app.route("/api/register/request", methods=["POST"])
def register_api_request():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()

        if not email or not password:
            return jsonify({"status": "error", "message": "Email and password are required."}), 400
        if not is_valid_password(password):
            return jsonify({"status": "error", "message": "Password must be at least 8 characters long and contain both letters and numbers."}), 400

        with get_db() as db:
            if db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone():
                return jsonify({"status": "error", "message": "Email already registered. Please log in."}), 400

        ok, message, status, _ = send_and_store_otp(
            email, "register", generate_password_hash(password), "Email Verification"
        )
        if not ok:
            return jsonify({"status": "error", "message": message}), status
        return jsonify({"status": "ok", "message": message, "code": None})
    except Exception as e:
        logging.error(f"register_api_request error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to send verification PIN. Please try again."}), 500


@app.route("/api/register/verify", methods=["POST"])
def register_api_verify():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        code = (data.get("code") or "").strip()

        if not email or not code:
            return jsonify({"status": "error", "message": "Email and verification PIN are required."}), 400

        record, error = verify_otp(email, "register", code, consume=False)
        if error:
            return jsonify({"status": "error", "message": error}), 400

        new_user_id = f"user_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        with get_db() as db:
            db.execute(
                "INSERT INTO users (id, email, password) VALUES (?, ?, ?)",
                (new_user_id, email, record.get("payload"))
            )
            db.commit()
        verify_otp(email, "register", code, consume=True)
        complete_login(new_user_id)
        return jsonify({"status": "ok", "message": "Account created successfully!", "redirect": "/dashboard"})
    except Exception as e:
        logging.error(f"register_api_verify error: {e}", exc_info=True)
        if is_unique_violation(e):
            return jsonify({"status": "error", "message": "Email already registered. Please log in."}), 400
        return jsonify({"status": "error", "message": "Failed to verify account. Please try again."}), 500


@app.route("/api/register/resend", methods=["POST"])
def register_api_resend():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({"status": "error", "message": "Email address is required."}), 400

        with get_db() as db:
            existing = db.execute(
                "SELECT payload FROM otp_codes WHERE email = ? AND purpose = ?",
                (email, "register")
            ).fetchone()
        if not existing:
            return jsonify({"status": "error", "message": "No pending registration found for this email."}), 400

        ok, message, status, _ = send_and_store_otp(
            email, "register", existing["payload"], "Email Verification"
        )
        if not ok:
            return jsonify({"status": "error", "message": message}), status
        return jsonify({"status": "ok", "message": message, "code": None})
    except Exception as e:
        logging.error(f"register_api_resend error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to resend PIN. Please try again."}), 500


=======

            record = REGISTRATION_CODES.get(email)
            if not record:
                flash("No pending registration found. Please start over.", "danger")
                return render_template("register.html")

            if record["code"] != otp_code:
                flash("Incorrect verification PIN. Please try again.", "danger")
                return render_template("register.html", step="otp", pending_email=email)

            if datetime.now() > record["expires"]:
                REGISTRATION_CODES.pop(email, None)
                flash("Verification PIN expired. Please request a new one.", "danger")
                return render_template("register.html")

            new_user_id = f"user_{int(time.time())}_{uuid.uuid4().hex[:6]}"
            try:
                with get_db() as db:
                    db.execute(
                        "INSERT INTO users (id, email, password) VALUES (?, ?, ?)",
                        (new_user_id, email, record["password_hash"])
                    )
                    db.commit()
                REGISTRATION_CODES.pop(email, None)
                session.permanent = True
                session["user_id"] = new_user_id
                flash("Email verified! Welcome to SoloBiz!", "success")
                return redirect("/dashboard")
            except sqlite3.IntegrityError:
                flash("Email already registered. Please log in.", "danger")
                return render_template("register.html")
            except Exception as e:
                logging.error(f"Account creation failed after OTP verify: {e}", exc_info=True)
                flash("Account creation failed. Please try again.", "danger")
                return render_template("register.html", step="otp", pending_email=email)

        # ── Step 1: Validate and send OTP ──
        if not email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("register.html")

        try:
            with get_db() as db:
                existing = db.execute(
                    "SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)
                ).fetchone()
                if existing:
                    flash("Email already registered. Please log in.", "danger")
                    return render_template("register.html", error="Email already registered. Please log in.")
        except Exception as e:
            logging.error(f"User check error during registration: {e}", exc_info=True)

        code = str(random.randint(100000, 999999))
        REGISTRATION_CODES[email] = {
            "code": code,
            "password_hash": generate_password_hash(password),
            "expires": datetime.now() + timedelta(minutes=15),
            "last_sent": datetime.now()
        }

        _, _, is_live = send_otp_email(email, code, subject_type="Email Verification")
        if is_live:
            flash(f"We sent a 6-digit PIN to {email}. Please check your inbox or spam folder.", "success")
        else:
            flash(f"Dev mode — verification PIN: {code}", "success")
        return render_template("register.html", step="otp", pending_email=email, dev_code=code if not is_live else None)

    return render_template("register.html")


@app.route("/api/register/request", methods=["POST"])
def register_api_request():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()

        if not email or not password:
            return jsonify({"status": "error", "message": "Email and password are required."}), 400
        if not re.match(r'^(?=.*[a-zA-Z])(?=.*\d).{8,}$', password):
            return jsonify({"status": "error", "message": "Password must be at least 8 characters long and contain both letters and numbers."}), 400

        with get_db() as db:
            if db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone():
                return jsonify({"status": "error", "message": "Email already registered. Please log in."}), 400

        # Rate-limit resend requests (30 seconds)
        existing = REGISTRATION_CODES.get(email)
        if existing and "last_sent" in existing:
            elapsed = (datetime.now() - existing["last_sent"]).total_seconds()
            if elapsed < 30:
                remaining = int(30 - elapsed)
                return jsonify({"status": "error", "message": f"Please wait {remaining}s before requesting a new PIN."}), 429

        code = str(random.randint(100000, 999999))
        REGISTRATION_CODES[email] = {
            "code": code,
            "password_hash": generate_password_hash(password),
            "expires": datetime.now() + timedelta(minutes=15),
            "last_sent": datetime.now()
        }

        _, _, is_live = send_otp_email(email, code, subject_type="Email Verification")

        if is_live:
            return jsonify({
                "status": "ok",
                "message": f"Verification PIN sent to {email}! Please check your inbox or spam folder.",
                "code": None
            })
        else:
            return jsonify({
                "status": "ok",
                "message": f"Dev mode — verification PIN: {code}",
                "code": code
            })

    except Exception as e:
        logging.error(f"register_api_request error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to send verification PIN. Please try again."}), 500


@app.route("/api/register/verify", methods=["POST"])
def register_api_verify():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        code = (data.get("code") or "").strip()

        if not email or not code:
            return jsonify({"status": "error", "message": "Email and verification PIN are required."}), 400

        record = REGISTRATION_CODES.get(email)
        if not record:
            return jsonify({"status": "error", "message": "No pending registration found for this email."}), 400
        if record["code"] != code:
            return jsonify({"status": "error", "message": "Incorrect verification PIN. Please try again."}), 400
        if datetime.now() > record["expires"]:
            REGISTRATION_CODES.pop(email, None)
            return jsonify({"status": "error", "message": "Verification PIN expired. Please request a new one."}), 400

        new_user_id = f"user_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        with get_db() as db:
            db.execute(
                "INSERT INTO users (id, email, password) VALUES (?, ?, ?)",
                (new_user_id, email, record["password_hash"])
            )
            db.commit()

        REGISTRATION_CODES.pop(email, None)
        session.permanent = True
        session["user_id"] = new_user_id
        flash("Email verified! Welcome to SoloBiz!", "success")
        return jsonify({"status": "ok", "message": "Account created successfully!", "redirect": "/dashboard"})

    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "Email already registered. Please log in."}), 400
    except Exception as e:
        logging.error(f"register_api_verify error: {e}", exc_info=True)
        err = str(e).lower()
        if "unique" in err or "duplicate" in err or "already exists" in err:
            return jsonify({"status": "error", "message": "Email already registered. Please log in."}), 400
        return jsonify({"status": "error", "message": "Failed to verify account. Please try again."}), 500


@app.route("/api/register/resend", methods=["POST"])
def register_api_resend():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()

        if not email:
            return jsonify({"status": "error", "message": "Email address is required."}), 400

        record = REGISTRATION_CODES.get(email)
        if not record:
            return jsonify({"status": "error", "message": "No pending registration found for this email."}), 400

        if "last_sent" in record:
            elapsed = (datetime.now() - record["last_sent"]).total_seconds()
            if elapsed < 30:
                remaining = int(30 - elapsed)
                return jsonify({"status": "error", "message": f"Please wait {remaining}s before requesting a new PIN."}), 429

        code = str(random.randint(100000, 999999))
        record["code"] = code
        record["expires"] = datetime.now() + timedelta(minutes=15)
        record["last_sent"] = datetime.now()

        _, _, is_live = send_otp_email(email, code, subject_type="Email Verification")

        if is_live:
            return jsonify({"status": "ok", "message": "New verification PIN sent to your email!", "code": None})
        else:
            return jsonify({"status": "ok", "message": f"Dev mode — new PIN: {code}", "code": code})

    except Exception as e:
        logging.error(f"register_api_resend error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to resend PIN. Please try again."}), 500


>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
@app.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user_id():
        return redirect("/dashboard")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            response = make_response(render_template("login.html"))
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
<<<<<<< HEAD
=======
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
            return response

        try:
            with get_db() as db:
                user = db.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
                if not user or not user["password"] or not check_password_hash(user["password"], password):
                    flash("Invalid email or password. Please try again.", "danger")
                    return render_template("login.html")
<<<<<<< HEAD
                complete_login(user["id"])
=======
                session.permanent = True
                session["user_id"] = str(user["id"])
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
                return redirect("/dashboard")
        except Exception as e:
            logging.error(f"Login error for '{email}': {e}", exc_info=True)
            flash("An unexpected error occurred. Please try again.", "danger")
            return render_template("login.html")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    resp = make_response(redirect("/login"))
    resp.delete_cookie(app.config.get("SESSION_COOKIE_NAME", "session"))
    return resp


# ==========================================
# FORGOT PASSWORD ROUTES
# ==========================================
<<<<<<< HEAD
GENERIC_RESET_MESSAGE = "If an account exists for that email, we sent a verification PIN."


=======
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
@app.route("/api/forgot-password/request", methods=["POST"])
def forgot_password_request():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({"status": "error", "message": "Please enter a valid email address."}), 400

        with get_db() as db:
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
<<<<<<< HEAD
        if user:
            ok, message, status, _ = send_and_store_otp(email, "reset", None, "Password Reset")
            if not ok:
                return jsonify({"status": "error", "message": message}), status
        return jsonify({"status": "ok", "message": GENERIC_RESET_MESSAGE, "code": None})
=======
            if not user:
                return jsonify({"status": "error", "message": "No account found with this email. Please register first."}), 404

        code = str(random.randint(100000, 999999))
        RESET_CODES[email] = {"code": code, "expires": datetime.now() + timedelta(minutes=15), "last_sent": datetime.now()}

        _, _, is_live = send_otp_email(email, code, subject_type="Password Reset")

        if is_live:
            return jsonify({"status": "ok", "message": "Verification PIN sent to your email!", "code": None})
        else:
            return jsonify({"status": "ok", "message": f"Dev mode — PIN: {code}", "code": code})

>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
    except Exception as e:
        logging.error(f"forgot_password_request error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to generate PIN. Please try again."}), 500


@app.route("/api/forgot-password/resend", methods=["POST"])
def forgot_password_resend():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({"status": "error", "message": "Please enter a valid email address."}), 400
<<<<<<< HEAD
        with get_db() as db:
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
        if user:
            ok, message, status, _ = send_and_store_otp(email, "reset", None, "Password Reset")
            if not ok:
                return jsonify({"status": "error", "message": message}), status
        return jsonify({"status": "ok", "message": GENERIC_RESET_MESSAGE, "code": None})
=======

        with get_db() as db:
            if not db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone():
                return jsonify({"status": "error", "message": "No account found with this email."}), 404

        existing = RESET_CODES.get(email)
        if existing and "last_sent" in existing:
            elapsed = (datetime.now() - existing["last_sent"]).total_seconds()
            if elapsed < 30:
                remaining = int(30 - elapsed)
                return jsonify({"status": "error", "message": f"Please wait {remaining}s before requesting a new PIN."}), 429

        code = str(random.randint(100000, 999999))
        RESET_CODES[email] = {"code": code, "expires": datetime.now() + timedelta(minutes=15), "last_sent": datetime.now()}

        _, _, is_live = send_otp_email(email, code, subject_type="Password Reset")

        if is_live:
            return jsonify({"status": "ok", "message": "New verification PIN sent to your email!", "code": None})
        else:
            return jsonify({"status": "ok", "message": f"Dev mode — new PIN: {code}", "code": code})

>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
    except Exception as e:
        logging.error(f"forgot_password_resend error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to resend PIN. Please try again."}), 500


@app.route("/api/forgot-password/reset", methods=["POST"])
def forgot_password_reset():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        code = (data.get("code") or "").strip()
        new_password = (data.get("password") or "").strip()

        if not email or not code or not new_password:
            return jsonify({"status": "error", "message": "Email, verification PIN, and new password are required."}), 400
<<<<<<< HEAD
        if not is_valid_password(new_password):
            return jsonify({"status": "error", "message": "New password must be at least 8 characters and include a letter and a number."}), 400

        record, error = verify_otp(email, "reset", code, consume=True)
        if error:
            return jsonify({"status": "error", "message": error}), 400
=======
        if len(new_password) < 6:
            return jsonify({"status": "error", "message": "New password must be at least 6 characters long."}), 400

        record = RESET_CODES.get(email)
        if not record or record["code"] != code or datetime.now() > record["expires"]:
            return jsonify({"status": "error", "message": "Invalid or expired verification PIN. Please request a new one."}), 400
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)

        hashed = generate_password_hash(new_password)
        with get_db() as db:
            db.execute("UPDATE users SET password = ? WHERE LOWER(email) = LOWER(?)", (hashed, email))
            db.commit()
<<<<<<< HEAD
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
            if user:
                complete_login(user["id"])

        return jsonify({"status": "ok", "message": "Password updated successfully!", "redirect": "/dashboard"})
    except Exception as e:
        logging.error(f"forgot_password_reset error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to update password. Please try again."}), 500
=======

        RESET_CODES.pop(email, None)

        with get_db() as db:
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
            if user:
                session.clear()
                session.permanent = True
                session["user_id"] = str(user["id"])

        return jsonify({"status": "ok", "message": "Password updated successfully!", "redirect": "/dashboard"})

    except Exception as e:
        logging.error(f"forgot_password_reset error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Failed to update password. Please try again."}), 500


>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
# ==========================================
# STATIC & SEO ROUTES
# ==========================================
@app.route("/")
def root():
    if get_current_user_id():
        return redirect("/dashboard")
    return render_template("landing.html")

@app.route('/sw.js')
def service_worker():
    sw_script = render_template('sw.js', version=APP_VERSION)
    response = make_response(sw_script)
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app.route("/sitemap.xml")
def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://solobiz.dev/</loc><lastmod>2026-09-20</lastmod><priority>1.0</priority></url>
  <url><loc>https://solobiz.dev/login</loc><priority>0.8</priority></url>
  <url><loc>https://solobiz.dev/register</loc><priority>0.8</priority></url>
</urlset>"""
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml; charset=utf-8"
    return response


@app.route("/robots.txt")
def robots():
    txt = """User-agent: *
Allow: /
Allow: /login
Allow: /register
Disallow: /dashboard
Disallow: /api/

Sitemap: https://solobiz.dev/sitemap.xml"""
    response = make_response(txt)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    return response


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.root_path, "static"), "favicon.png", mimetype="image/png")


# ==========================================
# DASHBOARD ROUTE
# ==========================================
@app.route("/dashboard")
def dashboard():
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")

    expenses = []
    total_sales = 0.0
    total_expenses = 0.0
    username = "Entrepreneur"

    try:
        with get_db() as db:
            try:
                user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
                if user and user["email"]:
                    username = user["email"].split("@")[0].capitalize()
            except Exception as e:
                print(f"Dashboard user query note: {e}", flush=True)

            try:
                expenses = db.execute(
                    "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC", (user_id,)
                ).fetchall() or []
            except Exception as e:
                print(f"Dashboard expenses list note: {e}", flush=True)

            try:
                row = db.execute(
                    "SELECT SUM(COALESCE(amount_paid, 0)) AS total FROM income WHERE user_id = ?",
                    (user_id,)
                ).fetchone()
                if row and row["total"] is not None:
                    total_sales = float(row["total"])
            except Exception as e:
                print(f"Dashboard sales sum note: {e}", flush=True)

            try:
                row = db.execute("SELECT SUM(amount) AS total FROM expenses WHERE user_id = ?", (user_id,)).fetchone()
                if row and row["total"] is not None:
                    total_expenses = float(row["total"])
            except Exception as e:
                print(f"Dashboard expenses sum note: {e}", flush=True)

    except Exception as e:
        logging.error(f"Dashboard data fetch error for user '{user_id}': {e}", exc_info=True)

    net_profit = total_sales - total_expenses

    profile = None
    try:
        with get_db() as db:
            prof_row = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()
            if prof_row:
                profile = dict(prof_row)
    except Exception as e:
        print(f"Dashboard profile query note: {e}", flush=True)

    return render_template(
        "index.html",
        expenses=expenses,
        total=total_expenses,
        total_sales=total_sales,
        total_expenses=total_expenses,
        net_profit=net_profit,
        username=username,
        profile=profile
    )


# ==========================================
# EXPENSES API ROUTES
# ==========================================
@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    with get_db() as db:
        rows = db.execute(
            "SELECT id, amount, category, description, date FROM expenses WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        ).fetchall()
        expenses = [
            {
                "server_id": row["id"],
                "amount": float(row["amount"]),
                "category": row["category"],
                "description": row["description"],
                "date": row["date"],
                "synced": True
            }
            for row in rows
        ]
    return jsonify({"expenses": expenses}), 200


@app.route("/add", methods=["POST"])
def add_expense():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    amount_val = data.get("amount")
    category_val = data.get("category")
    description_val = data.get("description")

    if amount_val is None or category_val is None or description_val is None:
        return jsonify({"status": "error", "message": "Missing required fields: amount, category, and description"}), 400

    try:
        amount = float(str(amount_val).replace(',', ''))
        if not math.isfinite(amount) or amount <= 0:
            return jsonify({"status": "error", "message": "Amount must be a positive number"}), 400
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Amount must be a valid number"}), 400

    category = str(category_val).strip()
    description = str(description_val).strip()
    if not category or not description:
        return jsonify({"status": "error", "message": "Category and description cannot be empty"}), 400

    expense_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, description, expense_date)
        )
        expense_id = cursor.lastrowid
        db.commit()

    return jsonify({
        "status": "success",
        "message": "Expense added successfully",
        "expense": {
            "id": expense_id,
            "user_id": user_id,
            "amount": amount,
            "category": category,
            "description": description,
            "date": expense_date
        }
    }), 201


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE", "PUT"])
def api_expense_detail(expense_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "DELETE":
        with get_db() as db:
            db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
            db.commit()
        return jsonify({"status": "success", "message": "Expense deleted successfully", "id": expense_id}), 200

    elif request.method == "PUT":
        data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        try:
            amount = float(str(data.get("amount", "0")).replace(',', ''))
            if not math.isfinite(amount) or amount <= 0:
                return jsonify({"status": "error", "message": "Amount must be a positive number"}), 400
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Invalid amount"}), 400

        category = str(data.get("category", "")).strip()
        description = str(data.get("description", "")).strip()
        if not category or not description:
            return jsonify({"status": "error", "message": "Category and description cannot be empty"}), 400

        expense_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        with get_db() as db:
            db.execute(
                "UPDATE expenses SET amount = ?, category = ?, description = ?, date = ? WHERE id = ? AND user_id = ?",
                (amount, category, description, expense_date, expense_id, user_id)
            )
            db.commit()

        return jsonify({
            "status": "success",
            "message": "Expense updated successfully",
            "expense": {"id": expense_id, "amount": amount, "category": category, "description": description, "date": expense_date}
        }), 200


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")
    with get_db() as db:
<<<<<<< HEAD
        existing = db.execute(
            "SELECT id FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
        ).fetchone()
        if not existing:
            return redirect("/dashboard")
        db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
=======
        cursor = db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
        if cursor.rowcount == 0:
            return redirect("/dashboard")
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
        db.commit()
    return redirect("/dashboard")


@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")

    with get_db() as db:
        item = db.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)).fetchone()

    if request.method == "GET":
        if item:
            return render_template("edit.html", item=item, index=expense_id)
        return redirect("/")

    if request.method == "POST":
        try:
            amount = float(str(request.form.get("amount", "0")).replace(',', ''))
        except (TypeError, ValueError):
            flash("Expense amount must be a valid number.")
            return render_template("edit.html", item=item, index=expense_id)

        if not math.isfinite(amount) or amount <= 0:
            flash("Expense amount must be greater than zero.")
            return render_template("edit.html", item=item, index=expense_id)

        category = str(request.form.get("category", "")).strip()
        description = str(request.form.get("description", "")).strip()
        if not category or not description:
            flash("Category and description are required.")
            return render_template("edit.html", item=item, index=expense_id)

        expenses_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        with get_db() as db:
            db.execute(
                "UPDATE expenses SET amount = ?, category = ?, description = ?, date = ? WHERE id = ? AND user_id = ?",
                (amount, category, description, expenses_date, expense_id, user_id)
            )
            db.commit()
        return redirect("/dashboard")

    return redirect("/dashboard")


@app.route("/calculate", methods=["POST"])
def calculate():
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")

    calc_term = request.form.get("calc_term", "").strip()
    calc_term_lower = calc_term.lower()
    calc_type = request.form.get("calc_type", "")
    items = []

    with get_db() as db:
        if calc_type == "amount":
            try:
                val = float(calc_term_lower)
                items = db.execute("SELECT amount FROM expenses WHERE user_id = ? AND amount = ?", (user_id, val)).fetchall()
            except ValueError:
                items = []
        elif calc_type == "category":
            items = db.execute(
                "SELECT amount FROM expenses WHERE user_id = ? AND LOWER(category) LIKE ?",
                (user_id, f"%{calc_term_lower}%")
            ).fetchall()
        elif calc_type == "description":
            items = db.execute(
                "SELECT amount FROM expenses WHERE user_id = ? AND LOWER(description) LIKE ?",
                (user_id, f"%{calc_term_lower}%")
            ).fetchall()

        user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        expenses = db.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,)).fetchall()

    calc_result = sum(float(row["amount"] or 0) for row in items)
    total_expenses = sum(float(item["amount"] or 0) for item in expenses)
    username = user["email"].split("@")[0].capitalize() if user and user["email"] else "Entrepreneur"

    total_sales = 0.0
    try:
        with get_db() as db:
            row = db.execute(
                "SELECT SUM(COALESCE(amount_paid, 0)) AS total FROM income WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if row and row["total"] is not None:
                total_sales = float(row["total"])
    except Exception:
        pass

    return render_template(
        "index.html",
        expenses=expenses,
        total=total_expenses,
        total_sales=total_sales,
        total_expenses=total_expenses,
        net_profit=total_sales - total_expenses,
        username=username,
        calc_result=calc_result,
        calc_term=calc_term
    )


@app.route("/search", methods=["POST"])
def search():
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")

    raw_search = request.form.get("search_term", "").strip()
    search_term = raw_search.lower()
    search_type = request.form.get("search_type", "")
    search_results = []
    display_term = raw_search

    with get_db() as db:
        all_expenses = db.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,)).fetchall()

        if search_type == "amount":
            try:
                amount_val = float(search_term)
                search_results = db.execute(
                    "SELECT * FROM expenses WHERE user_id = ? AND amount = ?", (user_id, amount_val)
                ).fetchall()
                if search_results:
                    display_term = f"₦{amount_val:,.2f}"
            except ValueError:
                search_results = []
        elif search_type == "category":
            search_results = db.execute(
                "SELECT * FROM expenses WHERE user_id = ? AND LOWER(category) LIKE ?",
                (user_id, f"%{search_term}%")
            ).fetchall()
            if search_results:
                display_term = search_results[0]["category"].capitalize()

    global_total = sum(float(item["amount"] or 0) for item in all_expenses)
    search_total = sum(float(item["amount"] or 0) for item in search_results)

    username = "Entrepreneur"
    total_sales = 0.0
    try:
        with get_db() as db:
            user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
            if user and user["email"]:
                username = user["email"].split("@")[0].capitalize()
            row = db.execute(
                "SELECT SUM(COALESCE(amount_paid, 0)) AS total FROM income WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if row and row["total"] is not None:
                total_sales = float(row["total"])
    except Exception:
        pass

    return render_template(
        "index.html",
        expenses=all_expenses,
        total=global_total,
        total_sales=total_sales,
        total_expenses=global_total,
        net_profit=total_sales - global_total,
        username=username,
        search_results=search_results,
        search_total=search_total,
        searching=True,
        search_term=display_term
    )


# ==========================================
# HELPER: URL SLUG GENERATOR
# ==========================================
def slugify(text):
    if not text:
        return "store"
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-') or "store"


def get_unique_store_slug(company_name, user_id, current_slug=None):
    """Return a public storefront slug that cannot point at another user."""
    base_slug = slugify(company_name)
    if current_slug:
        with get_db() as db:
            current_owner = db.execute(
                "SELECT user_id FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
                (current_slug,)
            ).fetchone()
        if current_owner and str(current_owner["user_id"]) == str(user_id):
            return current_slug

    with get_db() as db:
        existing = db.execute(
            "SELECT user_id FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
            (base_slug,)
        ).fetchone()

    if not existing or str(existing["user_id"]) == str(user_id):
        return base_slug

    owner_suffix = re.sub(r"[^a-z0-9]", "", str(user_id).lower())[-8:] or "vendor"
    candidate = f"{base_slug}-{owner_suffix}"
    with get_db() as db:
        collision = db.execute(
            "SELECT user_id FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
            (candidate,)
        ).fetchone()
    if not collision or str(collision["user_id"]) == str(user_id):
        return candidate

    return f"{candidate}-{uuid.uuid4().hex[:6]}"
<<<<<<< HEAD


# ==========================================
# PUBLIC DIGITAL STOREFRONT
# ==========================================
@app.route("/api/avatar/<store_slug>")
def dynamic_business_avatar(store_slug):
    company_name = store_slug
    color_hex = "4F46E5"
    with get_db() as db:
        profile = db.execute(
            "SELECT company_name, brand_color FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
            (store_slug,)
        ).fetchone()
        if profile:
            if profile["company_name"]:
                company_name = profile["company_name"]
            if profile["brand_color"]:
                color_hex = profile["brand_color"].replace("#", "")

    if len(color_hex) not in [3, 6]:
        color_hex = "4F46E5"

    initials = (company_name[:2] if len(company_name) >= 2 else (company_name[:1] or "B")).upper()
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="120" fill="#{color_hex}"/>
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-weight="900" font-size="210">{initials}</text>
</svg>'''
    return Response(svg, mimetype="image/svg+xml")


@app.route("/store/<store_slug>")
def public_storefront(store_slug):
    with get_db() as db:
        profile = db.execute(
            "SELECT * FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)", (store_slug,)
        ).fetchone()

    if not profile:
        return render_template("landing.html"), 404

    profile_dict = dict(profile)
    user_id = profile_dict["user_id"]
    base_url = request.host_url.rstrip("/")

    if profile_dict.get("logo_url"):
        logo_path = profile_dict["logo_url"]
        if logo_path.startswith("http://") or logo_path.startswith("https://"):
            logo_absolute_url = logo_path
        else:
            logo_absolute_url = base_url + (logo_path if logo_path.startswith("/") else "/" + logo_path)
    else:
        logo_absolute_url = f"{base_url}/api/avatar/{store_slug}"

    sales_count = 0
    try:
        with get_db() as db:
            res = db.execute("SELECT COUNT(*) as count FROM income WHERE user_id = ?", (user_id,)).fetchone()
            if res:
                sales_count = res["count"] if hasattr(res, "__getitem__") else 0
    except Exception:
        pass

    return render_template(
        "storefront.html",
        profile=profile_dict,
        sales_count=sales_count,
        logo_absolute_url=logo_absolute_url
    )


# ==========================================
# BUSINESS PROFILE API
# ==========================================
@app.route("/api/business_profile/request-otp", methods=["POST"])
def request_profile_otp():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
=======
>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)


# ==========================================
# PUBLIC DIGITAL STOREFRONT
# ==========================================
@app.route("/api/avatar/<store_slug>")
def dynamic_business_avatar(store_slug):
    company_name = store_slug
    color_hex = "4F46E5"
    with get_db() as db:
<<<<<<< HEAD
        user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()

    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    email = user["email"]
    ok, message, status, _ = send_and_store_otp(email, "profile", None, "Profile Update Verification")
    if not ok:
        return jsonify({"status": "error", "message": message}), status
    return jsonify({"status": "success", "message": message})


@app.route("/api/business_profile", methods=["GET", "POST"])
def api_business_profile():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "GET":
        with get_db() as db:
            profile = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()

        if not profile:
            return jsonify({
                "status": "success",
                "profile": {
                    "company_name": "", "business_phone": "", "business_address": "",
                    "instagram_handle": "", "whatsapp_number": "", "store_policy": "",
                    "brand_color": "#4F46E5", "logo_url": "", "store_slug": ""
                }
            }), 200

        profile_dict = dict(profile)
        return jsonify({
            "status": "success",
            "profile": {
                "id": profile_dict.get("id"),
                "user_id": profile_dict.get("user_id"),
                "company_name": profile_dict.get("company_name") or "",
                "business_phone": profile_dict.get("business_phone") or "",
                "business_address": profile_dict.get("business_address") or "",
                "instagram_handle": profile_dict.get("instagram_handle") or "",
                "whatsapp_number": profile_dict.get("whatsapp_number") or "",
                "store_policy": profile_dict.get("store_policy") or "",
                "brand_color": profile_dict.get("brand_color") or "#4F46E5",
                "logo_url": profile_dict.get("logo_url") or "",
                "store_slug": profile_dict.get("store_slug") or ""
            }
        }), 200

    elif request.method == "POST":
        data = request.form if request.form else (request.get_json(silent=True) or {})

        # OTP Validation — verify against the hashed code stored in otp_codes table
        provided_otp = str(data.get("otp", "")).strip()
        with get_db() as db:
            user_row = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user_row:
            return jsonify({"status": "error", "message": "User not found"}), 404

        _record, otp_error = verify_otp(user_row["email"], "profile", provided_otp, consume=True)
        if otp_error:
            return jsonify({"status": "error", "message": otp_error}), 400

        company_name = str(data.get("company_name", "")).strip()
        business_phone = str(data.get("business_phone", "")).strip()
        business_address = str(data.get("business_address", "")).strip()
        instagram_handle = str(data.get("instagram_handle", "")).strip()
        whatsapp_number = str(data.get("whatsapp_number", "")).strip()
        store_policy = str(data.get("store_policy", "")).strip()
        brand_color = sanitize_brand_color(data.get("brand_color", "#4F46E5"))

        if not company_name:
            return jsonify({"status": "error", "message": "Company name is required"}), 400

        logo_url = None
        if "logo" in request.files:
            file = request.files["logo"]
            if file and file.filename:
                saved_url, logo_err = save_uploaded_logo(file, user_id)
                if logo_err:
                    return jsonify({"status": "error", "message": logo_err}), 400
                logo_url = saved_url
        elif data.get("logo_url"):
            logo_url = sanitize_logo_url(data.get("logo_url"))

        with get_db() as db:
            existing = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()
            existing_dict = dict(existing) if existing else {}
            current_logo = logo_url if logo_url is not None else (existing_dict.get("logo_url") or "")
            current_slug = (
                existing_dict.get("store_slug") or ""
                if existing_dict and slugify(existing_dict.get("company_name", "")) == slugify(company_name)
                else ""
            )
            store_slug = get_unique_store_slug(company_name, user_id, current_slug=current_slug)

=======
        profile = db.execute(
            "SELECT company_name, brand_color FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
            (store_slug,)
        ).fetchone()
        if profile:
            if profile["company_name"]:
                company_name = profile["company_name"]
            if profile["brand_color"]:
                color_hex = profile["brand_color"].replace("#", "")

    if len(color_hex) not in [3, 6]:
        color_hex = "4F46E5"

    initials = (company_name[:2] if len(company_name) >= 2 else (company_name[:1] or "B")).upper()
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="120" fill="#{color_hex}"/>
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-weight="900" font-size="210">{initials}</text>
</svg>'''
    return Response(svg, mimetype="image/svg+xml")


@app.route("/store/<store_slug>")
def public_storefront(store_slug):
    with get_db() as db:
        profile = db.execute(
            "SELECT * FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)", (store_slug,)
        ).fetchone()

    if not profile:
        return render_template("landing.html"), 404

    profile_dict = dict(profile)
    user_id = profile_dict["user_id"]
    base_url = request.host_url.rstrip("/")

    if profile_dict.get("logo_url"):
        logo_path = profile_dict["logo_url"]
        if logo_path.startswith("http://") or logo_path.startswith("https://"):
            logo_absolute_url = logo_path
        else:
            logo_absolute_url = base_url + (logo_path if logo_path.startswith("/") else "/" + logo_path)
    else:
        logo_absolute_url = f"{base_url}/api/avatar/{store_slug}"

    sales_count = 0
    try:
        with get_db() as db:
            res = db.execute("SELECT COUNT(*) as count FROM income WHERE user_id = ?", (user_id,)).fetchone()
            if res:
                sales_count = res["count"] if hasattr(res, "__getitem__") else 0
    except Exception:
        pass

    return render_template(
        "storefront.html",
        profile=profile_dict,
        sales_count=sales_count,
        logo_absolute_url=logo_absolute_url
    )


# ==========================================
# BUSINESS PROFILE API
# ==========================================
@app.route("/api/business_profile/request-otp", methods=["POST"])
def request_profile_otp():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    with get_db() as db:
        user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
        
    email = user["email"]
    otp_code = str(random.randint(100000, 999999))
    session['profile_verification_code'] = otp_code
    
    send_otp_email(email, otp_code, subject_type="Profile Update Verification")
    print(f"[DEBUG] Profile OTP Generated for {email}: {otp_code}")
    
    return jsonify({"status": "success", "message": "Verification code sent"})


@app.route("/api/business_profile", methods=["GET", "POST"])
def api_business_profile():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "GET":
        with get_db() as db:
            profile = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()

        if not profile:
            return jsonify({
                "status": "success",
                "profile": {
                    "company_name": "", "business_phone": "", "business_address": "",
                    "instagram_handle": "", "whatsapp_number": "", "store_policy": "",
                    "brand_color": "#4F46E5", "logo_url": "", "store_slug": ""
                }
            }), 200

        profile_dict = dict(profile)
        return jsonify({
            "status": "success",
            "profile": {
                "id": profile_dict.get("id"),
                "user_id": profile_dict.get("user_id"),
                "company_name": profile_dict.get("company_name") or "",
                "business_phone": profile_dict.get("business_phone") or "",
                "business_address": profile_dict.get("business_address") or "",
                "instagram_handle": profile_dict.get("instagram_handle") or "",
                "whatsapp_number": profile_dict.get("whatsapp_number") or "",
                "store_policy": profile_dict.get("store_policy") or "",
                "brand_color": profile_dict.get("brand_color") or "#4F46E5",
                "logo_url": profile_dict.get("logo_url") or "",
                "store_slug": profile_dict.get("store_slug") or ""
            }
        }), 200

    elif request.method == "POST":
        data = request.form if request.form else (request.get_json(silent=True) or {})

        # OTP Validation
        provided_otp = str(data.get("otp", "")).strip()
        expected_otp = session.get('profile_verification_code')

        if not expected_otp or provided_otp != str(expected_otp):
            return jsonify({"status": "error", "message": "Invalid or expired verification code."}), 400

        company_name = str(data.get("company_name", "")).strip()
        business_phone = str(data.get("business_phone", "")).strip()
        business_address = str(data.get("business_address", "")).strip()
        instagram_handle = str(data.get("instagram_handle", "")).strip()
        whatsapp_number = str(data.get("whatsapp_number", "")).strip()
        store_policy = str(data.get("store_policy", "")).strip()
        brand_color = str(data.get("brand_color", "#4F46E5")).strip() or "#4F46E5"

        if not company_name:
            return jsonify({"status": "error", "message": "Company name is required"}), 400

        # Consume the one-time code only after all required input is valid.
        session.pop('profile_verification_code', None)

        logo_url = None
        if "logo" in request.files:
            file = request.files["logo"]
            if file and file.filename:
                os.makedirs(os.path.join(app.root_path, "static", "uploads", "logos"), exist_ok=True)
                filename = f"logo_{user_id}_{int(datetime.now().timestamp())}.png"
                file_path = os.path.join(app.root_path, "static", "uploads", "logos", filename)
                file.save(file_path)
                logo_url = f"/static/uploads/logos/{filename}"
        elif data.get("logo_url"):
            logo_url = str(data.get("logo_url")).strip()

        with get_db() as db:
            existing = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()
            existing_dict = dict(existing) if existing else {}
            current_logo = logo_url if logo_url is not None else (existing_dict.get("logo_url") or "")
            current_slug = (
                existing_dict.get("store_slug") or ""
                if existing_dict and slugify(existing_dict.get("company_name", "")) == slugify(company_name)
                else ""
            )
            store_slug = get_unique_store_slug(company_name, user_id, current_slug=current_slug)

>>>>>>> parent of c31c267 (feat: update PWA caching and enhance UI/SEO)
            if existing:
                db.execute(
                    """UPDATE business_profiles
                       SET company_name=?, business_phone=?, business_address=?,
                           instagram_handle=?, whatsapp_number=?, store_policy=?,
                           brand_color=?, logo_url=?, store_slug=?
                       WHERE user_id=?""",
                    (company_name, business_phone, business_address,
                     instagram_handle, whatsapp_number, store_policy,
                     brand_color, current_logo, store_slug, user_id)
                )
                profile_id = existing_dict["id"]
            else:
                cursor = db.execute(
                    """INSERT INTO business_profiles
                       (user_id, company_name, business_phone, business_address, instagram_handle,
                        whatsapp_number, store_policy, brand_color, logo_url, store_slug)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, company_name, business_phone, business_address,
                     instagram_handle, whatsapp_number, store_policy,
                     brand_color, current_logo, store_slug)
                )
                profile_id = cursor.lastrowid
            db.commit()

        return jsonify({
            "status": "success",
            "message": "Business profile saved successfully!",
            "profile": {
                "id": profile_id, "user_id": user_id, "company_name": company_name,
                "business_phone": business_phone, "business_address": business_address,
                "instagram_handle": instagram_handle, "whatsapp_number": whatsapp_number,
                "store_policy": store_policy, "brand_color": brand_color,
                "logo_url": current_logo, "store_slug": store_slug
            }
        }), 200


# ==========================================
# INVENTORY PRESETS API
# ==========================================
@app.route("/api/inventory-presets", methods=["GET", "POST"])
def api_inventory_presets():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "GET":
        with get_db() as db:
            rows = db.execute("SELECT * FROM inventory_presets WHERE user_id = ? ORDER BY id ASC", (user_id,)).fetchall()
            presets = [{"id": dict(r)["id"], "item_name": dict(r)["item_name"], "price": float(dict(r)["price"]), "stock": int(dict(r)["stock"])} for r in rows]
        return jsonify({"status": "success", "presets": presets}), 200

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        item_name = str(data.get("item_name", "")).strip()
        try:
            price = float(str(data.get("price", "0")).replace(",", ""))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Invalid price"}), 400
        try:
            stock = int(data.get("stock", 0))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Stock must be a whole number."}), 400

        if not item_name or not math.isfinite(price) or price <= 0 or stock < 0:
            return jsonify({"status": "error", "message": "Item name and a positive price are required."}), 400

        with get_db() as db:
            count = db.execute("SELECT COUNT(*) as cnt FROM inventory_presets WHERE user_id = ?", (user_id,)).fetchone()
            if int(dict(count)["cnt"]) >= 10:
                return jsonify({"status": "error", "message": "Maximum 10 presets allowed."}), 400

            cursor = db.execute(
                "INSERT INTO inventory_presets (user_id, item_name, price, stock) VALUES (?, ?, ?, ?)",
                (user_id, item_name, price, stock)
            )
            db.commit()
        return jsonify({"status": "success", "preset": {"id": cursor.lastrowid, "item_name": item_name, "price": price, "stock": stock}}), 201


@app.route("/api/inventory-presets/<int:preset_id>", methods=["PUT", "DELETE"])
def api_inventory_preset_detail(preset_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    with get_db() as db:
        existing = db.execute("SELECT * FROM inventory_presets WHERE id = ? AND user_id = ?", (preset_id, user_id)).fetchone()
        if not existing:
            return jsonify({"status": "error", "message": "Preset not found"}), 404

        if request.method == "DELETE":
            db.execute("DELETE FROM inventory_presets WHERE id = ? AND user_id = ?", (preset_id, user_id))
            db.commit()
            return jsonify({"status": "success", "message": "Preset deleted"}), 200

        elif request.method == "PUT":
            data = request.get_json(silent=True) or {}
            item_name = str(data.get("item_name", dict(existing).get("item_name", ""))).strip()
            try:
                price = float(str(data.get("price", dict(existing).get("price", 0))).replace(",", ""))
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "Invalid price"}), 400
            try:
                stock = int(data.get("stock", dict(existing).get("stock", 0)))
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "Stock must be a whole number."}), 400

            if not item_name or not math.isfinite(price) or price <= 0 or stock < 0:
                return jsonify({"status": "error", "message": "Item name and a positive price are required."}), 400

            db.execute(
                "UPDATE inventory_presets SET item_name = ?, price = ?, stock = ? WHERE id = ? AND user_id = ?",
                (item_name, price, stock, preset_id, user_id)
            )
            db.commit()
            return jsonify({"status": "success", "preset": {"id": preset_id, "item_name": item_name, "price": price, "stock": stock}}), 200


@app.route("/api/inventory-presets/<int:preset_id>/decrement", methods=["POST"])
def api_preset_decrement_stock(preset_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    with get_db() as db:
        row = db.execute("SELECT * FROM inventory_presets WHERE id = ? AND user_id = ?", (preset_id, user_id)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Preset not found"}), 404

        current_stock = int(dict(row)["stock"])
        if current_stock > 0:
            new_stock = current_stock - 1
            db.execute("UPDATE inventory_presets SET stock = ? WHERE id = ? AND user_id = ?", (new_stock, preset_id, user_id))
            db.commit()
            return jsonify({"status": "success", "stock": new_stock}), 200
        else:
            return jsonify({"status": "warning", "message": "Out of stock", "stock": 0}), 200


# ==========================================
# INCOME (SALES) API
# ==========================================
@app.route("/api/income", methods=["GET", "POST"])
@app.route("/add_income", methods=["GET", "POST"])
def api_income():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "GET":
        with get_db() as db:
            rows = db.execute("SELECT * FROM income WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
            income_list = []
            for row in rows:
                item = dict(row)
                total_value = float(item.get("total_value") if item.get("total_value") is not None else item.get("amount", 0))
                amount_paid = float(item.get("amount_paid") if item.get("amount_paid") is not None else item.get("amount", 0))
                balance_owed = max(total_value - amount_paid, 0)
                income_list.append({
                    "id": item["id"],
                    "user_id": item["user_id"],
                    "description": item.get("description", ""),
                    "total_value": total_value,
                    "amount_paid": amount_paid,
                    "balance_owed": balance_owed,
                    "customer_name": item.get("customer_name") or "Walk-in Customer",
                    "payment_mode": item.get("payment_mode") or "Cash",
                    "date": item.get("date"),
                    "receipt_id": item.get("receipt_id") or f"REC-{item['id']}"
                })
        return jsonify({"status": "success", "income": income_list}), 200

    elif request.method == "POST":
        data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            data = request.form.to_dict()

        income_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        receipt_id = data.get("receipt_id") or f"REC-{int(time.time())}"
        customer_name = str(data.get("customer_name", "Walk-in Customer")).strip() or "Walk-in Customer"

        description = str(data.get("description", "")).strip()
        try:
            total_value = float(str(data.get("total_value", "0")).replace(',', ''))
            amount_paid = float(str(data.get("amount_paid", "0")).replace(',', ''))
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "Invalid amount format"}), 400

        payment_mode = str(data.get("payment_mode", "Cash")).strip() or "Cash"

        if (
            not description
            or not math.isfinite(total_value)
            or not math.isfinite(amount_paid)
            or total_value <= 0
            or amount_paid < 0
            or amount_paid > total_value
        ):
            return jsonify({"status": "error", "message": "Description and a valid total value are required"}), 400

        with get_db() as db:
            cursor = db.execute(
                "INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, description, total_value, amount_paid, customer_name, payment_mode, income_date, receipt_id)
            )
            saved_item = {
                "id": cursor.lastrowid, 
                "user_id": user_id, 
                "description": description,
                "total_value": total_value, 
                "amount_paid": amount_paid, 
                "customer_name": customer_name,
                "payment_mode": payment_mode,
                "date": income_date, 
                "receipt_id": receipt_id
            }
            db.commit()

        return jsonify({
            "status": "success",
            "message": "Income logged successfully",
            "receipt_id": receipt_id,
            "income": saved_item
        }), 201


@app.route('/update_payment/<int:receipt_id>', methods=['POST'])
def update_payment(receipt_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.form.to_dict() if request.form else {}
    if not data and request.is_json:
        data = request.get_json(silent=True) or {}

    payment_amount_raw = str(data.get('payment_amount') or data.get('amount_paid') or '').strip()
    try:
        payment_amount = float(payment_amount_raw)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Please enter a valid payment amount."}), 400

    if not math.isfinite(payment_amount) or payment_amount <= 0:
        return jsonify({"status": "error", "message": "Payment must be greater than zero."}), 400

    with get_db() as db:
        row = db.execute("SELECT * FROM income WHERE id = ? AND user_id = ?", (receipt_id, user_id)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Receipt not found."}), 404

        item = dict(row)
        total_value = float(item.get("total_value") if item.get("total_value") is not None else item.get("amount", 0))
        current_paid = float(item.get("amount_paid") if item.get("amount_paid") is not None else item.get("amount", 0))
        updated_paid = min(total_value, current_paid + payment_amount)
        db.execute(
            "UPDATE income SET amount_paid = ? WHERE id = ? AND user_id = ?",
            (updated_paid, receipt_id, user_id)
        )
        db.commit()

    return jsonify({
        "status": "success",
        "message": "Payment added successfully.",
        "updated_amount_paid": updated_paid,
        "balance_owed": max(total_value - updated_paid, 0)
    }), 200


# ==========================================
# BATCH OFFLINE SALES SYNC ROUTE
# ==========================================
@app.route("/api/sync-sales", methods=["POST"])
def sync_sales():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.get_json(silent=True) or request.get_json(force=True, silent=True) or {}
    sales_array = data.get("sales", [])

    if not sales_array or not isinstance(sales_array, list):
        return jsonify({"status": "success", "success": True, "message": "No sales to sync", "count": 0}), 200

    saved_items = []
    with get_db() as db:
        for sale in sales_array:
            if not isinstance(sale, dict):
                continue
            
            description = str(sale.get("description") or sale.get("item_sold") or sale.get("item") or "").strip()
            try:
                total_value = float(str(sale.get("total_value", sale.get("amount", 0))).replace(",", ""))
                amount_paid = float(str(sale.get("amount_paid", sale.get("amount", 0))).replace(",", ""))
            except (TypeError, ValueError):
                continue
            payment_mode = str(sale.get("payment_mode", "Cash")).strip()
            customer_name = str(sale.get("customer_name") or "Walk-in Customer").strip() or "Walk-in Customer"
            sale_date = sale.get("date") or datetime.now().strftime("%Y-%m-%d %I:%M %p")
            receipt_id = sale.get("receipt_id") or f"REC-{int(time.time())}"

            try:
                if (
                    not math.isfinite(total_value)
                    or not math.isfinite(amount_paid)
                    or total_value <= 0
                    or amount_paid < 0
                    or amount_paid > total_value
                    or not description
                ):
                    continue
            except (TypeError, ValueError):
                continue

            cursor = db.execute(
                """INSERT INTO income (
                    user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, description, total_value, amount_paid, customer_name, payment_mode, sale_date, receipt_id)
            )
            saved_items.append({
                "id": cursor.lastrowid, "user_id": user_id, 
                "description": description, "total_value": total_value, "amount_paid": amount_paid,
                "customer_name": customer_name, "payment_mode": payment_mode,
                "date": sale_date, "receipt_id": receipt_id
            })
        db.commit()

    return jsonify({
        "status": "success",
        "success": True,
        "message": f"Successfully synced {len(saved_items)} sales",
        "count": len(saved_items),
        "items": saved_items
    }), 200




# ==========================================
# UTILITY ROUTES
# ==========================================
@app.route("/user-count")
def user_count():
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        total = row["total"] if (isinstance(row, dict) or hasattr(row, "keys")) else (row[0] if row else 0)
    return f"<h1>Total Registered Users: {total}</h1>"


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


# ==========================================
# ENTRY POINT
# ==========================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)