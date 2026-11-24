"""Platform report and business metrics: no identifying fields, small-group suppression,
admin-only access, and an audit entry for every view."""

import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
os.environ.setdefault("SQLITE_DATABASE_PATH", os.path.join(tempfile.mkdtemp(prefix="solobiz-report-"), "report.db"))
os.environ.setdefault("ADMIN_SECRET_KEY", "platform-report-test-admin-secret-key-0123456789")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("RENDER", None)

import pytest  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

from server import admin_app as portal  # noqa: E402
from server.database import get_db, init_db  # noqa: E402

PASSWORD = "report-password-2026"
init_db()  # the app's tables must exist before the admin reads them
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
NAMES = ["Chidi Okafor", "Stores Ng", "Ada Nwosu", "Kemi Bello", "Musa Dan", "Tunde Ola"]


def day_stamp(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %I:%M %p")


def clear_tables():
    with get_db() as db:
        for table in ("income", "expenses", "user_activity_logs", "business_profiles", "inventory_presets",
                      "admin_audit_logs", "super_admins", "users", "user_login_attempts", "admin_login_attempts"):
            db.execute(f"DELETE FROM {table}")
        db.commit()


def add_business(db, uid, company, test=0):
    db.execute("INSERT INTO users (id, email, password, first_name, last_name, is_test_account) VALUES (?, ?, ?, ?, ?, ?)",
               (uid, f"{uid}@owner.example", "x", "Owner", uid, test))
    db.execute("INSERT INTO business_profiles (user_id, company_name) VALUES (?, ?)", (uid, company))


def add_sale(db, uid, days_ago, customer):
    db.execute(
        "INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id) "
        "VALUES (?, ?, 1000, 400, ?, 'Cash', ?, ?)",
        (uid, f"Rice bag {uid}", customer, day_stamp(days_ago), f"REC-{uid}-{days_ago}"),
    )


def add_event(db, uid, event, days_ago=0):
    db.execute("INSERT INTO user_activity_logs (user_id, event_type, summary, created_at) VALUES (?, ?, 'x', ?)",
               (uid, event, (NOW - timedelta(days=days_ago)).isoformat()))


def seed_six():
    """Six businesses: five active (sales on three days), one with a single day, plus a test account."""
    clear_tables()
    with get_db() as db:
        for index in range(6):
            uid = f"biz{index + 1}"
            add_business(db, uid, f"{NAMES[index]} Trading")
            add_event(db, uid, "account_created", days_ago=2)
            add_event(db, uid, "sign_in", days_ago=0)
        for index in range(5):
            uid = f"biz{index + 1}"
            for days_ago in (0, 1, 2):
                add_sale(db, uid, days_ago, f"Customer {index}-{days_ago}")
        add_sale(db, "biz6", 0, "Customer solo")
        add_business(db, "test1", "Demo Shop Ltd", test=1)
        for days_ago in (0, 1, 2):
            add_sale(db, "test1", days_ago, "Test customer")
        db.execute("INSERT INTO expenses (user_id, amount, category, description, date) VALUES ('biz1', 300, 'Fuel', 'Generator fuel', ?)",
                   (day_stamp(0),))
        db.execute("INSERT INTO expenses (user_id, amount, category, description, date) VALUES ('biz2', 200, 'Transport', 'Okada fare', ?)",
                   (day_stamp(0),))
        db.execute("INSERT INTO inventory_presets (user_id, item_name, price, stock, track_stock) VALUES ('biz1', 'Sneakers', 500, 5, 1)")
        db.commit()


def seed_three():
    clear_tables()
    with get_db() as db:
        for index in range(3):
            uid = f"small{index + 1}"
            add_business(db, uid, f"{NAMES[index]} Small")
            for days_ago in (0, 1, 2):
                add_sale(db, uid, days_ago, f"Small customer {index}")
        db.commit()


def make_admin(email, role):
    with get_db() as db:
        db.execute("INSERT INTO super_admins (email, password_hash, role, is_active) VALUES (?, ?, ?, 1)",
                   (email, generate_password_hash(PASSWORD), role))
        db.commit()


@pytest.fixture
def client():
    portal.admin_app.config["TESTING"] = True
    seed_six()
    make_admin("report-owner@admin.test", "owner")
    make_admin("report-viewer@admin.test", "viewer")
    with get_db() as db:
        db.execute("DELETE FROM admin_login_attempts")
        db.commit()
    return portal.admin_app.test_client()


def sign_in(client, email):
    client.get("/login")
    client.get("/dashboard")
    with client.session_transaction() as sess:
        token = sess["admin_csrf_token"]
    response = client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})
    assert response.status_code == 302


REPORT_QUERY = "purpose=board"


def figure(html, label):
    """The value shown next to a figure label in the report table."""
    match = re.search(re.escape(label) + r"</td>\s*<td[^>]*>(.*?)</td>", html, re.S)
    assert match, label
    return re.sub(r"<[^>]+>|\s+", " ", match.group(1)).strip()


# --- Figures ----------------------------------------------------------------------

def test_report_figures_are_correct_and_test_accounts_are_excluded(client):
    sign_in(client, "report-owner@admin.test")
    html = client.get(f"/platform-report?{REPORT_QUERY}").get_data(as_text=True)
    assert figure(html, "Businesses registered") == "6"
    assert figure(html, "Businesses that signed in") == "6"
    assert figure(html, "Active businesses") == "5"
    assert figure(html, "Active businesses as a share of all") == "83.3%"
    assert figure(html, "Sales recorded") == "16"
    assert "₦16,000.00" in figure(html, "Total sales value")
    assert figure(html, "Still owed") == "₦9,600.00"
    assert figure(html, "Businesses using stock tracking") == "fewer than 5"
    assert figure(html, "Businesses recording expenses") == "fewer than 5"


def test_small_groups_are_withheld_everywhere(client):
    seed_three()
    make_admin("report-owner@admin.test", "owner")  # seeding the businesses clears the admin accounts
    sign_in(client, "report-owner@admin.test")
    html = client.get(f"/platform-report?{REPORT_QUERY}").get_data(as_text=True)
    assert figure(html, "Businesses registered") == "fewer than 5"
    assert figure(html, "Active businesses") == "fewer than 5"
    assert figure(html, "Active businesses as a share of all") == "fewer than 5"
    assert figure(html, "Sales recorded") == "fewer than 5"
    assert "fewer than 5" in figure(html, "Still owed")
    assert "₦" not in figure(html, "Total sales value")


def test_weekly_counts_are_listed_and_withheld_when_small(client):
    sign_in(client, "report-owner@admin.test")
    html = client.get(f"/platform-report?{REPORT_QUERY}").get_data(as_text=True)
    assert "Active businesses, week by week" in html
    assert f"<td data-label=\"Week ending\">{TODAY.isoformat()}</td>" in html
    assert "Active businesses\">5</td>" in html


# --- No identifying fields ---------------------------------------------------------

IDENTIFYING = ["Trading", "Chidi", "Okafor", "Stores Ng", "Ada Nwosu", "owner.example", "biz1", "biz6",
               "Customer", "Rice bag", "REC-", "Demo Shop", "Test customer", "Generator fuel", "Okada",
               "Sneakers"]


def test_report_page_contains_no_identifying_fields(client):
    sign_in(client, "report-owner@admin.test")
    html = client.get(f"/platform-report?{REPORT_QUERY}").get_data(as_text=True)
    for text in IDENTIFYING:
        assert text not in html, text
    assert "@" not in re.sub(r"<[^>]*>", "", html.split("<main>")[-1])


def test_csv_contains_no_identifying_fields(client):
    sign_in(client, "report-owner@admin.test")
    response = client.get(f"/platform-report.csv?{REPORT_QUERY}")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    body = response.get_data(as_text=True)
    for text in IDENTIFYING:
        assert text not in body, text
    assert "@" not in body
    assert "Active businesses" in body


def test_printable_view_contains_no_identifying_fields(client):
    sign_in(client, "report-owner@admin.test")
    body = client.get(f"/platform-report/print?{REPORT_QUERY}").get_data(as_text=True)
    body = re.sub(r"<style>.*?</style>", "", body, flags=re.S)  # the CSS has an @media rule
    for text in IDENTIFYING:
        assert text not in body, text
    assert "@" not in body


# --- Access and audit ------------------------------------------------------------

def test_signed_out_visitors_cannot_open_any_report_view(client):
    for path in ("/platform-report", "/platform-report.csv", "/platform-report/print"):
        response = client.get(f"{path}?{REPORT_QUERY}")
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"], path


def test_a_viewer_can_open_the_report_but_only_while_signed_in(client):
    sign_in(client, "report-viewer@admin.test")
    assert client.get(f"/platform-report?{REPORT_QUERY}").status_code == 200


def test_the_report_asks_for_a_reason_before_showing_figures(client):
    sign_in(client, "report-owner@admin.test")
    html = client.get("/platform-report").get_data(as_text=True)
    assert "Choose a reason before the report is shown" in html
    assert "Businesses registered" not in html


def test_each_view_download_and_print_is_logged_with_the_reason(client):
    sign_in(client, "report-owner@admin.test")
    client.get(f"/platform-report?purpose=board")
    client.get(f"/platform-report.csv?purpose=product")
    client.get(f"/platform-report/print?purpose=other&note=Quarterly+review")
    with get_db() as db:
        rows = [dict(r) for r in db.execute(
            "SELECT action, target_type, reason FROM admin_audit_logs WHERE target_type = 'platform_report' ORDER BY id").fetchall()]
    assert [row["action"] for row in rows] == [
        "viewed platform report", "downloaded platform report (CSV)", "printed platform report"]
    assert rows[0]["reason"] == "Board or investor update"
    assert rows[1]["reason"] == "Product review"
    assert rows[2]["reason"] == "Other: Quarterly review"


def test_a_view_without_a_reason_is_not_logged_as_a_view(client):
    sign_in(client, "report-owner@admin.test")
    client.get("/platform-report")
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) AS n FROM admin_audit_logs WHERE target_type = 'platform_report'").fetchone()["n"]
    assert count == 0


# --- Dashboard figures -----------------------------------------------------------

def test_dashboard_shows_three_day_activity_and_signups(client):
    sign_in(client, "report-owner@admin.test")
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Active, sales on 3+ days in 7 days" in html
    assert "New sign-ups, last 7 days" in html
    assert re.search(r"Active, sales on 3\+ days in 7 days</div>\s*<div class=\"metric-value\">5", html)
    assert re.search(r"New sign-ups, last 7 days</div>\s*<div class=\"metric-value\">6<", html)
