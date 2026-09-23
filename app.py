import logging
import math
import os
import random
import re
import smtplib
import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import (Flask, Response, jsonify, make_response, redirect,
                   render_template, request, send_from_directory, session,
                   flash)
from werkzeug.security import check_password_hash, generate_password_hash

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
app.secret_key = os.environ.get("SECRET_KEY", "solobiz_production_secret_key_12345_super_safe")
app.permanent_session_lifetime = timedelta(days=30)
APP_VERSION = str(int(time.time()))

# Session / Cookie hardening
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("DATABASE_URL") is not None  # True on Render (HTTPS)


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


def get_current_user_id():
    """Retrieve string-based user_id from active Flask session cookie."""
    if "user_id" in session and session["user_id"]:
        return str(session["user_id"])
    return None


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
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS store_slug TEXT"
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
                ("receipt_id", "TEXT"),
            ]:
                try:
                    db.execute(f"ALTER TABLE business_profiles ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
            try:
                db.execute("ALTER TABLE income ADD COLUMN receipt_id TEXT")
            except Exception:
                pass
            db.commit()


init_db()


# ==========================================
# OTP & EMAIL SERVICES (RESEND API + SMTP)
# ==========================================
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


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        otp_code = request.form.get("otp_code", "").strip()

        # ── Step 2: Verify OTP and create account ──
        if otp_code:
            if not email:
                flash("Email is required for OTP verification.", "danger")
                return render_template("register.html")

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


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Please enter both email and password.", "danger")
            return render_template("login.html")

        try:
            with get_db() as db:
                user = db.execute("SELECT * FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
                if not user or not user["password"] or not check_password_hash(user["password"], password):
                    flash("Invalid email or password. Please try again.", "danger")
                    return render_template("login.html")
                session.permanent = True
                session["user_id"] = str(user["id"])
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
@app.route("/api/forgot-password/request", methods=["POST"])
def forgot_password_request():
    try:
        data = request.get_json(force=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return jsonify({"status": "error", "message": "Please enter a valid email address."}), 400

        with get_db() as db:
            user = db.execute("SELECT id FROM users WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
            if not user:
                return jsonify({"status": "error", "message": "No account found with this email. Please register first."}), 404

        code = str(random.randint(100000, 999999))
        RESET_CODES[email] = {"code": code, "expires": datetime.now() + timedelta(minutes=15), "last_sent": datetime.now()}

        _, _, is_live = send_otp_email(email, code, subject_type="Password Reset")

        if is_live:
            return jsonify({"status": "ok", "message": "Verification PIN sent to your email!", "code": None})
        else:
            return jsonify({"status": "ok", "message": f"Dev mode — PIN: {code}", "code": code})

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
        if len(new_password) < 6:
            return jsonify({"status": "error", "message": "New password must be at least 6 characters long."}), 400

        record = RESET_CODES.get(email)
        if not record or record["code"] != code or datetime.now() > record["expires"]:
            return jsonify({"status": "error", "message": "Invalid or expired verification PIN. Please request a new one."}), 400

        hashed = generate_password_hash(new_password)
        with get_db() as db:
            db.execute("UPDATE users SET password = ? WHERE LOWER(email) = LOWER(?)", (hashed, email))
            db.commit()

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
                row = db.execute("SELECT COALESCE(SUM(amount_paid), 0) AS total FROM income WHERE user_id = ?", (user_id,)).fetchone()
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

    response = make_response(render_template(
        "index.html",
        expenses=expenses,
        total=total_expenses,
        total_sales=total_sales,
        total_expenses=total_expenses,
        net_profit=net_profit,
        username=username,
        profile=profile
    ))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


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
        db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
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

    calc_term = request.form["calc_term"].strip()
    calc_term_lower = calc_term.lower()
    calc_type = request.form["calc_type"]
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
    username = user["email"].split("@")[0].capitalize() if user and user.get("email") else "Entrepreneur"

    total_sales = 0.0
    try:
        with get_db() as db:
            row = db.execute("SELECT SUM(total_value) AS total FROM income WHERE user_id = ?", (user_id,)).fetchone()
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

    raw_search = request.form["search_term"].strip()
    search_term = raw_search.lower()
    search_type = request.form["search_type"]
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
            row = db.execute("SELECT SUM(total_value) AS total FROM income WHERE user_id = ?", (user_id,)).fetchone()
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

        # Clear the OTP from session after successful validation
        session.pop('profile_verification_code', None)

        company_name = str(data.get("company_name", "")).strip()
        business_phone = str(data.get("business_phone", "")).strip()
        business_address = str(data.get("business_address", "")).strip()
        instagram_handle = str(data.get("instagram_handle", "")).strip()
        whatsapp_number = str(data.get("whatsapp_number", "")).strip()
        store_policy = str(data.get("store_policy", "")).strip()
        brand_color = str(data.get("brand_color", "#4F46E5")).strip() or "#4F46E5"

        if not company_name:
            return jsonify({"status": "error", "message": "Company name is required"}), 400

        store_slug = slugify(company_name)

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
        stock = int(data.get("stock", 0))

        if not item_name or price <= 0:
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
            stock = int(data.get("stock", dict(existing).get("stock", 0)))

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
                total_value = float(item.get("total_value", 0))
                amount_paid = float(item.get("amount_paid", 0))
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

        payment_mode = str(data.get("payment_mode", "Cash")).strip()

        if not description or not math.isfinite(total_value) or total_value < 0:
            return jsonify({"status": "error", "message": "Description and a valid total value are required"}), 400
        if not math.isfinite(amount_paid) or amount_paid < 0:
            return jsonify({"status": "error", "message": "Amount paid must be zero or greater"}), 400
        amount_paid = min(amount_paid, total_value)

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

    payment_amount_raw = (data.get('payment_amount') or data.get('amount_paid') or '').strip()
    try:
        payment_amount = float(payment_amount_raw)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Please enter a valid payment amount."}), 400

    if payment_amount <= 0:
        return jsonify({"status": "error", "message": "Payment must be greater than zero."}), 400

    with get_db() as db:
        row = db.execute("SELECT * FROM income WHERE id = ? AND user_id = ?", (receipt_id, user_id)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Receipt not found."}), 404

        item = dict(row)
        total_value = float(item.get("total_value", 0))
        current_paid = float(item.get("amount_paid", 0))
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
            total_value = float(sale.get("total_value", sale.get("amount", 0)))
            amount_paid = float(sale.get("amount_paid", sale.get("amount", 0)))
            payment_mode = str(sale.get("payment_mode", "Cash")).strip()
            customer_name = str(sale.get("customer_name") or "Walk-in Customer").strip() or "Walk-in Customer"
            sale_date = sale.get("date") or datetime.now().strftime("%Y-%m-%d %I:%M %p")
            receipt_id = sale.get("receipt_id") or f"REC-{int(time.time())}"

            try:
                if (not math.isfinite(total_value) or total_value <= 0 or
                    not math.isfinite(amount_paid) or amount_paid < 0 or not description):
                    continue
                amount_paid = min(amount_paid, total_value)
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