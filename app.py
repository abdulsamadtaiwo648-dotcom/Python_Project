from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
import math
import os
import traceback
import jwt

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_for_solobiz")
CLERK_PUBLISHABLE_KEY = os.environ.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY") or os.environ.get("CLERK_PUBLISHABLE_KEY") or "pk_test_aW5ub2NlbnQtb2NlbG90LTk4MzUuY2xlcmsuYWNjb3VudHMuZGV2JA"

def get_current_user_id():
    """
    Extract string-based user_id (e.g. 'user_2...') from Clerk JWT token in Authorization header,
    or fallback to session['user_id'] if available.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            if "sub" in payload and payload["sub"]:
                return str(payload["sub"])
        except Exception:
            pass
    if "user_id" in session and session["user_id"]:
        return str(session["user_id"])
    return None

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

def init_db():
    with get_db() as db:
        if getattr(db, "is_postgres", False):
            # PostgreSQL Table Creation (Cloud Database)
            db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    amount NUMERIC NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    date TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS business_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT UNIQUE NOT NULL,
                    company_name TEXT,
                    business_phone TEXT,
                    business_address TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS income (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    amount NUMERIC NOT NULL,
                    item_sold TEXT,
                    customer_name TEXT,
                    date TEXT,
                    receipt_id TEXT
                )
            """)
            for alter_cmd in [
                "ALTER TABLE expenses ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT",
                "ALTER TABLE income ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT",
                "ALTER TABLE business_profiles ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT",
                "ALTER TABLE income ADD COLUMN IF NOT EXISTS receipt_id TEXT"
            ]:
                try:
                    db.execute(alter_cmd)
                except Exception:
                    pass
        else:
            # SQLite Table Creation (Local Development)
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
                    business_address TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS income (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    amount REAL NOT NULL,
                    item_sold TEXT,
                    customer_name TEXT,
                    date TEXT,
                    receipt_id TEXT
                )
            """)
            try:
                db.execute("ALTER TABLE income ADD COLUMN receipt_id TEXT")
            except Exception:
                pass
        db.commit()

init_db()

# ==========================================
# AUTHENTICATION ROUTES (CLERK INTEGRATION)
# ==========================================
@app.route("/register", methods=["GET", "POST"])
def register():
    return render_template("register.html", clerk_publishable_key=CLERK_PUBLISHABLE_KEY)

@app.route("/login", methods=["GET", "POST"])
def login():
    return render_template("login.html", clerk_publishable_key=CLERK_PUBLISHABLE_KEY)

@app.route("/logout")
def logout():
    session.pop("user_id", None) 
    return redirect("/login")

# ==========================================
# DASHBOARD & CRUD ROUTES
# ==========================================
@app.route("/")
def index():
    user_id = get_current_user_id()

    if not user_id:
        return render_template(
            "index.html",
            expenses=[],
            total=0.00,
            total_sales=0.00,
            total_expenses=0.00,
            net_profit=0.00,
            username="User",
            clerk_publishable_key=CLERK_PUBLISHABLE_KEY
        )

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        expenses = db.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,)).fetchall()
        sales_query = db.execute("SELECT SUM(amount) AS total FROM income WHERE user_id = ?", (user_id,)).fetchone()
        expenses_query = db.execute("SELECT SUM(amount) AS total FROM expenses WHERE user_id = ?", (user_id,)).fetchone()

    total_sales = float(sales_query["total"]) if sales_query and sales_query["total"] is not None else 0.00
    total_expenses = float(expenses_query["total"]) if expenses_query and expenses_query["total"] is not None else 0.00
    net_profit = float(total_sales) - float(total_expenses)
    
    username = user["email"].split("@")[0].capitalize() if user and hasattr(user, "__getitem__") and "email" in user else "User"

    return render_template(
        "index.html",
        expenses=expenses,
        total=total_expenses,
        total_sales=total_sales,
        total_expenses=total_expenses,
        net_profit=net_profit,
        username=username,
        clerk_publishable_key=CLERK_PUBLISHABLE_KEY
    )

@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    with get_db() as db:
        cursor = db.execute(
            "SELECT id, amount, category, description, date FROM expenses WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
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

@app.route("/calculate", methods=["POST"])
def calculate():
    if "user_id" not in session:
        return redirect("/login")
        
    user_id = session["user_id"]
    
    # Get what the user wants to calculate
    calc_term = request.form["calc_term"].strip()
    calc_term_lower = calc_term.lower()
    calc_type = request.form["calc_type"]
    
    items = []
    
    with get_db() as db:
        # Match their choice exactly like your terminal if/elif statements
        if calc_type == "amount":
            try:
                val = float(calc_term_lower)
                items = db.execute("SELECT amount FROM expenses WHERE user_id = ? AND amount = ?", (user_id, val)).fetchall()
            except ValueError:
                items = []
        elif calc_type == "category":
            items = db.execute("SELECT amount FROM expenses WHERE user_id = ? AND LOWER(category) LIKE ?", (user_id, f"%{calc_term_lower}%")).fetchall()
        elif calc_type == "description":
            items = db.execute("SELECT amount FROM expenses WHERE user_id = ? AND LOWER(description) LIKE ?", (user_id, f"%{calc_term_lower}%")).fetchall()
            
        # We also need to load the main dashboard data so the page doesn't break
        user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        expenses = db.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,)).fetchall()
        
    # Do the math!
    calc_result = sum(float(row["amount"] or 0) for row in items)
    
    total = sum(float(item["amount"] or 0) for item in expenses)
    username = user["email"].split("@")[0].capitalize()
    
    return render_template("index.html", expenses=expenses, total=total, username=username, calc_result=calc_result, calc_term=calc_term)

@app.route("/add", methods=["POST"])
def add_expense():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # Parse JSON payload from request
    data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
    if not isinstance(data, dict):
        return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

    amount_val = data.get("amount")
    category_val = data.get("category")
    description_val = data.get("description")

    if amount_val is None or category_val is None or description_val is None:
        return jsonify({"status": "error", "message": "Missing required fields: amount, category, and description are required"}), 400

    try:
        amount = float(amount_val)
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
            amount = float(data.get("amount", 0))
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
            "expense": {
                "id": expense_id,
                "amount": amount,
                "category": category,
                "description": description,
                "date": expense_date
            }
        }), 200

@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")
    
    with get_db() as db:
        db.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
        db.commit()
        
    return redirect("/")

@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
def edit_expense(expense_id):
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")
    
    if request.method == "GET":
        with get_db() as db:
            item = db.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)).fetchone()
        if item:
            return render_template("edit.html", item=item)
        return redirect("/")
        
    if request.method == "POST":
        amount = float(request.form["amount"])
        category = request.form["category"].strip()
        description = request.form["description"].strip()
        expenses_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        
        with get_db() as db:
            db.execute("UPDATE expenses SET amount = ?, category = ?, description = ?, date = ? WHERE id = ? AND user_id = ?", 
                       (amount, category, expenses_date, description, expense_id, user_id))
            db.commit()
        return redirect("/")

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
        all_expenses = db.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchall()
        
        if search_type == "amount":
            try:
                amount_val = float(search_term)
                search_results = db.execute(
                    "SELECT * FROM expenses WHERE user_id = ? AND amount = ?",
                    (user_id, amount_val)
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
    
    return render_template(
        "index.html",
        expenses=all_expenses,
        total=global_total,
        search_results=search_results,
        search_total=search_total,
        searching=True,
        search_term=display_term
    )

# ==========================================
# BUSINESS PROFILE API ROUTES
# ==========================================
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
                    "company_name": "",
                    "business_phone": "",
                    "business_address": ""
                }
            }), 200

        return jsonify({
            "status": "success",
            "profile": {
                "id": profile["id"],
                "user_id": profile["user_id"],
                "company_name": profile["company_name"] or "",
                "business_phone": profile["business_phone"] or "",
                "business_address": profile["business_address"] or ""
            }
        }), 200

    elif request.method == "POST":
        data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400

        company_name = str(data.get("company_name", "")).strip()
        business_phone = str(data.get("business_phone", "")).strip()
        business_address = str(data.get("business_address", "")).strip()

        if not company_name:
            return jsonify({"status": "error", "message": "Company name is required"}), 400

        with get_db() as db:
            existing = db.execute("SELECT id FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()
            if existing:
                db.execute(
                    """UPDATE business_profiles 
                       SET company_name = ?, business_phone = ?, business_address = ?
                       WHERE user_id = ?""",
                    (company_name, business_phone, business_address, user_id)
                )
                profile_id = existing["id"]
            else:
                cursor = db.execute(
                    """INSERT INTO business_profiles (user_id, company_name, business_phone, business_address)
                       VALUES (?, ?, ?, ?)""",
                    (user_id, company_name, business_phone, business_address)
                )
                profile_id = cursor.lastrowid
            db.commit()

        return jsonify({
            "status": "success",
            "message": "Business profile saved successfully",
            "profile": {
                "id": profile_id,
                "user_id": user_id,
                "company_name": company_name,
                "business_phone": business_phone,
                "business_address": business_address
            }
        }), 200


# ==========================================
# INCOME (SALES) API ROUTES
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
                row_dict = dict(row)
                income_list.append({
                    "id": row_dict["id"],
                    "user_id": row_dict["user_id"],
                    "amount": float(row_dict["amount"]),
                    "item_sold": row_dict.get("item_sold", ""),
                    "customer_name": row_dict.get("customer_name") or "Walk-in Customer",
                    "date": row_dict.get("date"),
                    "receipt_id": row_dict.get("receipt_id") or f"REC-{row_dict['id']}"
                })
        return jsonify({"status": "success", "income": income_list}), 200

    elif request.method == "POST":
        data = request.get_json(silent=True) or request.get_json(force=True, silent=True)
        if not isinstance(data, dict):
            data = request.form.to_dict()

        import time
        income_date = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        receipt_id = data.get("receipt_id") or f"REC-{int(time.time())}"
        customer_name = str(data.get("customer_name", "Walk-in Customer")).strip() or "Walk-in Customer"

        items = data.get("items")
        if not items or not isinstance(items, list):
            # Fallback if submitted as single item
            amount_val = data.get("amount")
            item_sold = str(data.get("item_sold", "")).strip()
            if amount_val is not None and item_sold:
                items = [{"item_sold": item_sold, "amount": amount_val}]
            else:
                items = []

        if not items:
            return jsonify({"status": "error", "message": "Missing required fields: item_sold and amount are required"}), 400

        saved_items = []

        with get_db() as db:
            for idx, product in enumerate(items):
                item_name = str(product.get("item_sold", "")).strip()
                try:
                    amt = float(product.get("amount", 0))
                    if not math.isfinite(amt) or amt <= 0 or not item_name:
                        continue
                except (TypeError, ValueError):
                    continue

                item_receipt_id = receipt_id if len(items) > 1 else (receipt_id + (f"-{idx+1}" if idx > 0 else ""))
                cursor = db.execute(
                    "INSERT INTO income (user_id, amount, item_sold, customer_name, date, receipt_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, amt, item_name, customer_name, income_date, receipt_id)
                )
                income_id = cursor.lastrowid
                saved_items.append({
                    "id": income_id,
                    "user_id": user_id,
                    "amount": amt,
                    "item_sold": item_name,
                    "customer_name": customer_name,
                    "date": income_date,
                    "receipt_id": receipt_id
                })
            db.commit()

        if not saved_items:
            return jsonify({"status": "error", "message": "No valid items were provided"}), 400

        return jsonify({
            "status": "success",
            "message": "Income logged successfully",
            "receipt_id": receipt_id,
            "income": saved_items[0] if len(saved_items) == 1 else saved_items,
            "items": saved_items
        }), 201

@app.route("/user-count")
def user_count():
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        if isinstance(row, dict) or hasattr(row, "keys"):
            total = row["total"]
        elif row:
            total = row[0]
        else:
            total = 0
    return f"<h1>Total Registered Users: {total}</h1>"

@app.errorhandler(Exception)
def handle_exception(e):
    # Prints the exact traceback line directly to screen for real-time debugging
    return f"<h2>We caught the bug! Here is the error:</h2><pre>{traceback.format_exc()}</pre>", 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)