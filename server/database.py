"""Database connections, compatibility wrapper, and schema initialization."""

import logging
import os
import re
import sqlite3
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

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
            insert_match = re.match(r"\s*INSERT\s+INTO\s+([\w.\"]+)", pg_sql, re.IGNORECASE)
            insert_table = insert_match.group(1).split(".")[-1].strip('"').lower() if insert_match else ""
            # OTP rows are keyed by (email, purpose) and have no generated id.
            # Asking PostgreSQL for RETURNING id makes the OTP insert fail before email delivery.
            should_return_id = (
                is_insert
                and "RETURNING" not in pg_sql.upper()
                and insert_table != "otp_codes"
            )
            if should_return_id:
                pg_sql += " RETURNING id"

            cur.execute(pg_sql, params)

            last_id = None
            if is_insert and "RETURNING" in pg_sql.upper():
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
        database_path = os.environ.get(
            "SQLITE_DATABASE_PATH",
            os.path.join(os.path.dirname(__file__), "solobiz.db"),
        )
        conn = sqlite3.connect(database_path)
        conn.row_factory = sqlite3.Row
        return DBWrapper(conn, is_postgres=False)

def init_db():
    database_url = os.environ.get("DATABASE_URL")
    if database_url and HAS_PSYCOPG2:
        # PostgreSQL Cloud Migration & Table Initialization
        tables = [
            """CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password TEXT,
                first_name TEXT,
                last_name TEXT
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
                store_slug TEXT,
                profile_updated_at TEXT,
                profile_change_reason TEXT,
                profile_change_note TEXT
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
                receipt_id TEXT,
                checkout_id TEXT,
                checkout_line_id TEXT,
                inventory_item_id INTEGER,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price NUMERIC NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS inventory_presets (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                item_name TEXT NOT NULL,
                price NUMERIC NOT NULL,
                stock INTEGER DEFAULT 0,
                track_stock INTEGER NOT NULL DEFAULT 0
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
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT",
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
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS checkout_id TEXT",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS checkout_line_id TEXT",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS inventory_item_id INTEGER",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS unit_price NUMERIC NOT NULL DEFAULT 0",
            "ALTER TABLE inventory_presets ADD COLUMN IF NOT EXISTS track_stock INTEGER NOT NULL DEFAULT 0",
            "UPDATE inventory_presets SET track_stock = 1 WHERE stock > 0 AND track_stock = 0",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS instagram_handle TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS whatsapp_number TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS store_policy TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS brand_color TEXT DEFAULT '#4F46E5'",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS logo_url TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS store_slug TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS profile_updated_at TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS profile_change_reason TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS profile_change_note TEXT",
            "UPDATE business_profiles SET profile_updated_at = CURRENT_TIMESTAMP::TEXT WHERE profile_updated_at IS NULL",
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
        ]
        for alter_cmd in migrations:
            try:
                with get_db() as db:
                    db.execute(alter_cmd)
                    db.commit()
            except Exception as e:
                print(f"Migration note for '{alter_cmd}': {e}", flush=True)

        # Direct SQL deletion of a user must also remove every account-owned
        # row and any registration/reset code tied to that email.
        try:
            with get_db() as db:
                db.execute("""
                    CREATE OR REPLACE FUNCTION solobiz_cleanup_deleted_user() RETURNS TRIGGER AS $$
                    BEGIN
                        DELETE FROM expenses WHERE user_id = OLD.id;
                        DELETE FROM income WHERE user_id = OLD.id;
                        DELETE FROM business_profiles WHERE user_id = OLD.id;
                        DELETE FROM inventory_presets WHERE user_id = OLD.id;
                        DELETE FROM otp_codes WHERE LOWER(email) = LOWER(OLD.email);
                        RETURN OLD;
                    END;
                    $$ LANGUAGE plpgsql
                """)
                db.execute("DROP TRIGGER IF EXISTS solobiz_user_delete_cleanup ON users")
                db.execute("""
                    CREATE TRIGGER solobiz_user_delete_cleanup
                    AFTER DELETE ON users
                    FOR EACH ROW EXECUTE FUNCTION solobiz_cleanup_deleted_user()
                """)
                for table in ("expenses", "income", "business_profiles", "inventory_presets"):
                    db.execute(
                        f"DELETE FROM {table} WHERE NOT EXISTS "
                        f"(SELECT 1 FROM users WHERE users.id = {table}.user_id)"
                    )
                db.commit()
        except Exception as cleanup_error:
            logging.error("Could not install account deletion cleanup: %s", cleanup_error, exc_info=True)

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
                    password TEXT,
                    first_name TEXT,
                    last_name TEXT
                )
            """)
            user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            if "first_name" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
            if "last_name" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
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
                    store_slug TEXT,
                    profile_updated_at TEXT,
                    profile_change_reason TEXT,
                    profile_change_note TEXT
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
                    receipt_id TEXT,
                    checkout_id TEXT,
                    checkout_line_id TEXT,
                    inventory_item_id INTEGER,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    unit_price REAL NOT NULL DEFAULT 0
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS inventory_presets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    stock INTEGER DEFAULT 0,
                    track_stock INTEGER NOT NULL DEFAULT 0
                )
            """)
            for col_name, col_type in [
                ("instagram_handle", "TEXT"),
                ("whatsapp_number", "TEXT"),
                ("store_policy", "TEXT"),
                ("brand_color", "TEXT DEFAULT '#4F46E5'"),
                ("logo_url", "TEXT"),
                ("store_slug", "TEXT"),
                ("profile_updated_at", "TEXT"),
                ("profile_change_reason", "TEXT"),
                ("profile_change_note", "TEXT"),
            ]:
                try:
                    db.execute(f"ALTER TABLE business_profiles ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass
            db.execute(
                "UPDATE business_profiles SET profile_updated_at = ? WHERE profile_updated_at IS NULL",
                (datetime.now(timezone.utc).isoformat(),)
            )
            try:
                db.execute("ALTER TABLE income ADD COLUMN receipt_id TEXT")
            except Exception:
                pass
            for table, column, column_type in [
                ("income", "checkout_id", "TEXT"),
                ("income", "checkout_line_id", "TEXT"),
                ("income", "inventory_item_id", "INTEGER"),
                ("income", "quantity", "INTEGER NOT NULL DEFAULT 1"),
                ("income", "unit_price", "REAL NOT NULL DEFAULT 0"),
                ("inventory_presets", "track_stock", "INTEGER NOT NULL DEFAULT 0"),
            ]:
                try:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                except Exception:
                    pass
            db.execute("UPDATE inventory_presets SET track_stock = 1 WHERE stock > 0 AND track_stock = 0")
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
            db.execute("""
                CREATE TRIGGER IF NOT EXISTS solobiz_user_delete_cleanup
                AFTER DELETE ON users
                BEGIN
                    DELETE FROM expenses WHERE user_id = OLD.id;
                    DELETE FROM income WHERE user_id = OLD.id;
                    DELETE FROM business_profiles WHERE user_id = OLD.id;
                    DELETE FROM inventory_presets WHERE user_id = OLD.id;
                    DELETE FROM otp_codes WHERE LOWER(email) = LOWER(OLD.email);
                END
            """)
            for table in ("expenses", "income", "business_profiles", "inventory_presets"):
                db.execute(
                    f"DELETE FROM {table} WHERE NOT EXISTS "
                    f"(SELECT 1 FROM users WHERE users.id = {table}.user_id)"
                )
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
