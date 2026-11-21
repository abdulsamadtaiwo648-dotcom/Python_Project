"""Database connections, compatibility wrapper, and schema initialization."""

import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone

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

# Tables known to have no generated `id` column (their key is something else).
# Anything else is looked up in the database once and remembered.
_TABLES_WITHOUT_ID = {"otp_codes", "subscriptions", "client_ops", "provider_plans", "user_login_attempts", "staff_members"}
_TABLE_HAS_ID = {}


class DBWrapper:
    def __init__(self, conn, is_postgres=False):
        self.conn = conn
        self.is_postgres = is_postgres

    def _table_has_id(self, table):
        """Can an INSERT into this table ask PostgreSQL for RETURNING id?"""
        if not table or table in _TABLES_WITHOUT_ID:
            return False
        if table not in _TABLE_HAS_ID:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s AND column_name = 'id'",
                (table,),
            )
            _TABLE_HAS_ID[table] = cur.fetchone() is not None
        return _TABLE_HAS_ID[table]

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
            # Some tables (OTP codes, subscriptions, ...) have no generated id.
            # Asking PostgreSQL for RETURNING id on them makes the insert fail.
            should_return_id = (
                is_insert
                and "RETURNING" not in pg_sql.upper()
                and self._table_has_id(insert_table)
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
        database_url = database_url.strip()
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        elif database_url.startswith("postgresql+psycopg://"):
            database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        elif database_url.startswith("postgresql+psycopg2://"):
            database_url = database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
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

def init_admin_db():
    """Create the separate super-admin accounts and admin audit storage."""
    with get_db() as db:
        if db.is_postgres:
            db.execute("""
                CREATE TABLE IF NOT EXISTS super_admins (
                    id SERIAL PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    session_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT
                )
            """)
        else:
            db.execute("""
                CREATE TABLE IF NOT EXISTS super_admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    session_version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS admin_login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE NOT NULL,
                attempts INTEGER NOT NULL,
                window_started TEXT NOT NULL,
                blocked_until TEXT
            )
        """ if not db.is_postgres else """
            CREATE TABLE IF NOT EXISTS admin_login_attempts (
                id SERIAL PRIMARY KEY,
                fingerprint TEXT UNIQUE NOT NULL,
                attempts INTEGER NOT NULL,
                window_started TEXT NOT NULL,
                blocked_until TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not db.is_postgres else """
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT,
                reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """ if not db.is_postgres else """
            CREATE TABLE IF NOT EXISTS user_activity_logs (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT
            )
        """)
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_activity_user_time "
            "ON user_activity_logs (user_id, created_at)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_created_at "
            "ON admin_audit_logs (created_at)"
        )
        if db.is_postgres:
            db.execute(
                "ALTER TABLE super_admins ADD COLUMN IF NOT EXISTS "
                "is_active INTEGER NOT NULL DEFAULT 1"
            )
            db.execute(
                "ALTER TABLE super_admins ADD COLUMN IF NOT EXISTS "
                "session_version INTEGER NOT NULL DEFAULT 1"
            )
            db.execute(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "account_status TEXT NOT NULL DEFAULT 'active'"
            )
        else:
            admin_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(super_admins)").fetchall()
            }
            if "is_active" not in admin_columns:
                db.execute(
                    "ALTER TABLE super_admins ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
                )
            if "session_version" not in admin_columns:
                db.execute(
                    "ALTER TABLE super_admins ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1"
                )
            users_table = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'"
            ).fetchone()
            if users_table:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(users)").fetchall()}
                if "account_status" not in columns:
                    db.execute(
                        "ALTER TABLE users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'"
                    )
        db.commit()

def init_push_subscriptions_table():
    """Browser push subscriptions: one row per device that turned on alerts.
    Created before the account-deletion triggers that clean it up."""
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                endpoint TEXT UNIQUE NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions (user_id)")
        db.commit()


def init_client_ops_table():
    """Operations queued on a device while offline and replayed later. The id
    the device sends is remembered so a replay that already landed (but whose
    answer was lost) is not applied twice."""
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS client_ops (
                user_id TEXT NOT NULL,
                op_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, op_id)
            )
        """)
        # Replays only happen within days; keep a generous 60 days of ids.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        db.execute("DELETE FROM client_ops WHERE created_at < ?", (cutoff,))
        db.commit()


def init_billing_tables():
    """Subscriptions (one row per account), payment attempts/records, and the
    Flutterwave payment-plan ids created for each plan and price."""
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id TEXT PRIMARY KEY,
                plan TEXT NOT NULL,
                trial_ends_at TEXT,
                period_end TEXT,
                cancel_at_period_end INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                plan TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                tx_ref TEXT UNIQUE NOT NULL,
                provider_tx_id TEXT UNIQUE,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id)")
        db.execute("""
            CREATE TABLE IF NOT EXISTS provider_plans (
                plan TEXT NOT NULL,
                amount REAL NOT NULL,
                provider_plan_id TEXT NOT NULL,
                PRIMARY KEY (plan, amount)
            )
        """)
        db.commit()


def init_staff_table():
    """Staff accounts created by a business owner: which owner they work for,
    their role and the pages they may use. The staff person's login is a normal
    users row whose password the owner set."""
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS staff_members (
                user_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                role TEXT NOT NULL,
                pages TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_staff_owner ON staff_members (owner_id)")
        db.commit()


def init_website_tables():
    """Business websites (one per account) and the images they use.

    Images live in the database because the host's disk is wiped on deploy.
    Created before the account-deletion triggers that clean them up."""
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS business_websites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                draft TEXT NOT NULL,
                published TEXT,
                is_published INTEGER NOT NULL DEFAULT 0,
                published_at TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS website_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                content_type TEXT NOT NULL,
                data %s NOT NULL,
                size INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """ % ("BYTEA" if db.is_postgres else "BLOB")
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_website_media_user ON website_media (user_id)")
        db.commit()


def _baseline_schema():
    """Version 1 of the schema: every table, column, trigger and one-time repair the app
    has ever needed. Each step is written to be safe to run again, but it now runs once."""
    init_push_subscriptions_table()
    init_client_ops_table()
    init_billing_tables()
    init_staff_table()
    init_website_tables()
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
                brand_color TEXT DEFAULT '#1d4ed8',
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
            )""",
            """CREATE TABLE IF NOT EXISTS user_activity_logs (
                id SERIAL PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP::TEXT
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
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status TEXT NOT NULL DEFAULT 'active'",
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
            # Optional bulk pricing: `bulk_price` buys `bulk_quantity` units.
            "ALTER TABLE inventory_presets ADD COLUMN IF NOT EXISTS bulk_quantity INTEGER",
            "ALTER TABLE inventory_presets ADD COLUMN IF NOT EXISTS bulk_price NUMERIC",
            # Stock at or below this level triggers a low-stock alert.
            "ALTER TABLE inventory_presets ADD COLUMN IF NOT EXISTS low_stock_threshold INTEGER NOT NULL DEFAULT 3",
            # Public website: which products show, and an optional photo.
            "ALTER TABLE inventory_presets ADD COLUMN IF NOT EXISTS show_on_website INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE inventory_presets ADD COLUMN IF NOT EXISTS image_url TEXT",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS sale_type TEXT NOT NULL DEFAULT 'unit'",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS bundle_count INTEGER",
            "ALTER TABLE income ADD COLUMN IF NOT EXISTS bundle_size INTEGER",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS instagram_handle TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS whatsapp_number TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS store_policy TEXT",
            "ALTER TABLE business_profiles ADD COLUMN IF NOT EXISTS brand_color TEXT DEFAULT '#1d4ed8'",
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
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_business_profiles_store_slug ON business_profiles (store_slug)",
            "CREATE INDEX IF NOT EXISTS idx_user_activity_user_time ON user_activity_logs (user_id, created_at)",
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
                        DELETE FROM user_activity_logs WHERE user_id = OLD.id;
                        DELETE FROM push_subscriptions WHERE user_id = OLD.id;
                        DELETE FROM business_websites WHERE user_id = OLD.id;
                        DELETE FROM website_media WHERE user_id = OLD.id;
                        DELETE FROM subscriptions WHERE user_id = OLD.id;
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
                for table in ("expenses", "income", "business_profiles", "inventory_presets", "user_activity_logs"):
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
            if "account_status" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'")
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
                    brand_color TEXT DEFAULT '#1d4ed8',
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
            db.execute("""
                CREATE TABLE IF NOT EXISTS user_activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_activity_user_time "
                "ON user_activity_logs (user_id, created_at)"
            )
            for col_name, col_type in [
                ("instagram_handle", "TEXT"),
                ("whatsapp_number", "TEXT"),
                ("store_policy", "TEXT"),
                ("brand_color", "TEXT DEFAULT '#1d4ed8'"),
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
                ("inventory_presets", "bulk_quantity", "INTEGER"),
                ("inventory_presets", "bulk_price", "REAL"),
                ("inventory_presets", "low_stock_threshold", "INTEGER NOT NULL DEFAULT 3"),
                ("inventory_presets", "show_on_website", "INTEGER NOT NULL DEFAULT 1"),
                ("inventory_presets", "image_url", "TEXT"),
                ("income", "sale_type", "TEXT NOT NULL DEFAULT 'unit'"),
                ("income", "bundle_count", "INTEGER"),
                ("income", "bundle_size", "INTEGER"),
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
            db.execute("DROP TRIGGER IF EXISTS solobiz_user_delete_cleanup")
            db.execute("""
                CREATE TRIGGER solobiz_user_delete_cleanup
                AFTER DELETE ON users
                BEGIN
                    DELETE FROM expenses WHERE user_id = OLD.id;
                    DELETE FROM income WHERE user_id = OLD.id;
                    DELETE FROM business_profiles WHERE user_id = OLD.id;
                    DELETE FROM inventory_presets WHERE user_id = OLD.id;
                    DELETE FROM user_activity_logs WHERE user_id = OLD.id;
                    DELETE FROM push_subscriptions WHERE user_id = OLD.id;
                    DELETE FROM business_websites WHERE user_id = OLD.id;
                    DELETE FROM website_media WHERE user_id = OLD.id;
                    DELETE FROM subscriptions WHERE user_id = OLD.id;
                    DELETE FROM otp_codes WHERE LOWER(email) = LOWER(OLD.email);
                END
            """)
            for table in ("expenses", "income", "business_profiles", "inventory_presets", "user_activity_logs"):
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

    # Failed sign-in counters for the user login form. Rows are keyed by a
    # keyed hash of the email so raw addresses are not stored here. The id
    # column exists because the PostgreSQL wrapper appends RETURNING id.
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT UNIQUE NOT NULL,
                attempts INTEGER NOT NULL,
                window_started TEXT NOT NULL,
                blocked_until TEXT
            )
        """)
        db.commit()


def _drop_floor_tables():
    """Migration 0002: the community Floor tables. Runs only once DROP_FLOOR_TABLES is set,
    so an older release that still uses them keeps working (blue-green deploys). Returns
    False, so it is not recorded, until the variable is set."""
    if (os.environ.get("DROP_FLOOR_TABLES") or "").strip().lower() not in ("1", "true", "yes"):
        return False
    # Children before parents so foreign keys never block the drop.
    for table in ("community_vote", "sabi_plug_recommendation", "sabi_plug_request", "street_tip", "market_mood"):
        try:
            with get_db() as db:
                db.execute(f"DROP TABLE IF EXISTS {table}")
                db.commit()
        except Exception as drop_error:
            logging.warning("Could not drop removed Floor table %s: %s", table, drop_error)
    return True


# ---------------------------------------------------------------------------
# Schema migrations. Each step runs once per database and is recorded in
# schema_migrations. A new change to the schema is a new function appended to
# MIGRATIONS below. Never edit a migration that has already shipped.
# ---------------------------------------------------------------------------
MIGRATIONS = [
    ("0001_baseline", _baseline_schema),
    ("0002_drop_floor_tables", _drop_floor_tables),
]

_MIGRATION_LOCK_ID = 730001  # PostgreSQL advisory lock: one server migrates at a time


def _ensure_migrations_table(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    db.commit()


def run_migrations(migrations=None):
    """Apply every migration not yet recorded, in order. Returns the names applied now."""
    migrations = MIGRATIONS if migrations is None else migrations
    applied_now = []
    is_postgres = bool(os.environ.get("DATABASE_URL") and HAS_PSYCOPG2)
    lock_db = get_db()
    try:
        if is_postgres:
            lock_db.execute("SELECT pg_advisory_lock(%s)" % _MIGRATION_LOCK_ID)
        with get_db() as db:
            _ensure_migrations_table(db)
        for name, step in migrations:
            with get_db() as db:
                done = db.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (name,)).fetchone()
            if done:
                continue
            logging.info("Applying schema migration %s", name)
            if step() is False:          # not ready yet (e.g. waiting for a flag): try again next start
                continue
            with get_db() as db:
                db.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (name, datetime.now(timezone.utc).isoformat()),
                )
                db.commit()
            applied_now.append(name)
    finally:
        if is_postgres:
            try:
                lock_db.execute("SELECT pg_advisory_unlock(%s)" % _MIGRATION_LOCK_ID)
            except Exception:
                logging.exception("Could not release the migration lock")
        try:
            lock_db.close()
        except Exception:
            pass
    return applied_now


def init_db():
    """Bring the database up to date. Safe to call on every start: only missing steps run."""
    run_migrations()
