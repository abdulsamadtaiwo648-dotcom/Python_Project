"""Checks for the internal admin portal, run against a temporary SQLite database.

Run from the repository root:
    python -m pytest admin_tests -q

These tests use Flask's test client, so they do not need the FastAPI test client.
"""

import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

_DB_DIR = tempfile.mkdtemp(prefix="solobiz-admin-tests-")
os.environ["SQLITE_DATABASE_PATH"] = os.path.join(_DB_DIR, "admin-test.db")
os.environ["ADMIN_SECRET_KEY"] = "test-admin-secret-key-that-is-long-enough-0123456789"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("RENDER", None)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from werkzeug.security import generate_password_hash  # noqa: E402

from server import admin_app as portal  # noqa: E402
from server.database import get_db, init_db  # noqa: E402

PASSWORD = "correct horse 2026"
NOW = datetime.now(timezone.utc)
RECENT = NOW.isoformat()
OLD = (NOW - timedelta(days=30)).isoformat()
TODAY_LABEL = NOW.strftime("%Y-%m-%d %I:%M %p")
OLD_LABEL = (NOW - timedelta(days=30)).strftime("%Y-%m-%d %I:%M %p")


def seed():
    """Sample data: businesses in each adoption state, plus admins in each role."""
    init_db()
    with get_db() as db:
        for table in ("income", "expenses", "user_activity_logs", "business_profiles",
                      "admin_audit_logs", "super_admins", "users"):
            db.execute(f"DELETE FROM {table}")

        def user(uid, email, status="active", test=0):
            db.execute(
                "INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                (uid, email, "x", "Ada", "Sample"),
            )
            db.execute("UPDATE users SET account_status = ?, is_test_account = ? WHERE id = ?",
                       (status, test, uid))

        def profile(uid, name):
            db.execute(
                "INSERT INTO business_profiles (user_id, company_name, business_phone, business_address) "
                "VALUES (?, ?, ?, ?)",
                (uid, name, "0800 000 0000", "1 Sample Road"),
            )

        def event(uid, kind, summary, when=RECENT):
            db.execute(
                "INSERT INTO user_activity_logs (user_id, event_type, summary, created_at) VALUES (?, ?, ?, ?)",
                (uid, kind, summary, when),
            )

        # A: active business with a profile, a sale, an expense and three events (counted once).
        user("biz-a", "owner-a@example.test")
        profile("biz-a", "Sample Stores")
        event("biz-a", "sale_created", "Recorded a sale")
        event("biz-a", "sale_created", "Recorded a sale")
        event("biz-a", "expense_created", "Recorded an expense")
        event("biz-a", "sign_in", "Signed in")
        db.execute(
            "INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id) "
            "VALUES ('biz-a', 'Rice bag', 1000, 400, 'Chidi', 'Cash', ?, 'REC-A-1')", (TODAY_LABEL,),
        )
        db.execute(
            "INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id) "
            "VALUES ('biz-a', 'Old sale', 500, 500, 'Ngozi', 'Transfer', ?, 'REC-A-0')", (OLD_LABEL,),
        )
        db.execute(
            "INSERT INTO expenses (user_id, amount, category, description, date) VALUES ('biz-a', 250, 'Transport', 'Okada', ?)",
            (TODAY_LABEL,),
        )
        # B: paused business with activity only 30 days ago (not active).
        user("biz-b", "owner-b@example.test", status="paused")
        profile("biz-b", "Quiet Shop")
        event("biz-b", "sale_created", "Recorded a sale", when=OLD)
        # C: signs in only, has no profile yet.
        user("biz-c", "owner-c@example.test")
        event("biz-c", "sign_in", "Signed in")
        # T: marked as a test account, very active. Must never be counted.
        user("biz-t", "demo@example.test", test=1)
        profile("biz-t", "Demo Business")
        event("biz-t", "sale_created", "Recorded a sale")
        # D: an unmarked account whose name looks like a test. It must still be counted.
        user("biz-d", "tester@example.test")
        profile("biz-d", "Test Traders")
        event("biz-d", "inventory_item_created", "Added an inventory item")

        for number in range(60):
            db.execute(
                "INSERT INTO expenses (user_id, amount, category, description, date) VALUES ('biz-a', ?, 'Bulk', ?, ?)",
                (10 + number, f"Bulk item {number}", TODAY_LABEL),
            )

        db.execute(
            "INSERT INTO super_admins (email, password_hash, role, is_active) VALUES (?, ?, 'owner', 1)",
            ("owner@admin.test", generate_password_hash(PASSWORD)),
        )
        db.execute(
            "INSERT INTO super_admins (email, password_hash, role, is_active) VALUES (?, ?, 'support', 1)",
            ("support@admin.test", generate_password_hash(PASSWORD)),
        )
        db.execute(
            "INSERT INTO super_admins (email, password_hash, role, is_active) VALUES (?, ?, 'viewer', 1)",
            ("viewer@admin.test", generate_password_hash(PASSWORD)),
        )
        db.execute("DELETE FROM admin_login_attempts")
        db.commit()


@pytest.fixture(autouse=True)
def fresh_data():
    seed()
    yield


@pytest.fixture
def client():
    portal.admin_app.config["TESTING"] = True
    return portal.admin_app.test_client()


def csrf(client):
    """The token is created when a page renders. /login redirects when already signed in,
    so also render a signed-in page (the overview) to make sure a token exists."""
    client.get("/login")
    client.get("/dashboard")
    with client.session_transaction() as sess:
        return sess["admin_csrf_token"]


def sign_in(client, email):
    token = csrf(client)
    response = client.post("/login", data={"email": email, "password": PASSWORD, "csrf_token": token})
    assert response.status_code == 302, response.get_data(as_text=True)[:300]
    return token


def post(client, url, data, token=None):
    token = token or csrf(client)
    return client.post(url, data={**data, "csrf_token": token})


def audit_rows():
    with get_db() as db:
        return [dict(row) for row in db.execute(
            "SELECT a.action, a.target_type, a.target_id, a.reason, a.ticket_ref, s.email "
            "FROM admin_audit_logs a JOIN super_admins s ON s.id = a.admin_id ORDER BY a.id"
        ).fetchall()]


def set_test_marker(uid, value):
    with get_db() as db:
        db.execute("UPDATE users SET is_test_account = ? WHERE id = ?", (value, uid))
        db.commit()


def admin_id(email):
    with get_db() as db:
        return db.execute("SELECT id FROM super_admins WHERE email = ?", (email,)).fetchone()["id"]


# --- Overview adoption metrics ------------------------------------------------

def test_overview_counts_each_active_business_once_and_excludes_test_accounts(client):
    sign_in(client, "owner@admin.test")
    html = client.get("/dashboard").get_data(as_text=True)
    # Registered accounts: A, B, C, D (T is excluded).
    assert re.search(r'Registered accounts</div>\s*<div class="metric-value">4<', html)
    # Business profiles with a name, not test: A, B, D.
    assert re.search(r'Business profiles</div>\s*<div class="metric-value">3<', html)
    # Active in 7 days: A (sales, expense) and D (inventory). B is too old, C only signed in, T is a test account.
    assert re.search(r'Active businesses, last 7 days</div>\s*<div class="metric-value">2<', html)
    # Signed in in 7 days (not active): A and C.
    assert "Signed in, last 7 days</dt><dd>2 businesses" in html
    assert re.search(r'Paused accounts</div>\s*<div class="metric-value">1<', html)


def test_overview_has_no_platform_money_cards(client):
    sign_in(client, "owner@admin.test")
    html = client.get("/dashboard").get_data(as_text=True)
    for label in ("Sales recorded", "Payments collected", "Expenses recorded", "Net cash movement"):
        assert label not in html


def test_marking_a_business_as_test_changes_the_adoption_figures(client):
    sign_in(client, "support@admin.test")
    response = post(client, "/users/biz-d/test-account", {"marked": "1", "reason": "Internal demo account"})
    assert response.status_code == 302
    html = client.get("/dashboard").get_data(as_text=True)
    assert re.search(r'Active businesses, last 7 days</div>\s*<div class="metric-value">1<', html)
    assert audit_rows()[-1]["action"] == "marked as test account"


# --- Access control ------------------------------------------------------------

def test_merchant_or_signed_out_visitor_cannot_reach_admin_pages(client):
    for path in ("/dashboard", "/users", "/users/biz-a", "/activity", "/admins", "/system-status"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"], path


def test_signed_out_post_is_refused(client):
    response = client.post("/users/biz-a/status", data={"status": "paused", "reason": "test", "csrf_token": "x"})
    assert response.status_code in (302, 400)
    assert audit_rows() == []
    with get_db() as db:
        assert db.execute("SELECT account_status FROM users WHERE id = 'biz-a'").fetchone()["account_status"] == "active"


def test_viewer_cannot_change_account_access_on_the_server(client):
    sign_in(client, "viewer@admin.test")
    response = post(client, "/users/biz-a/status", {"status": "paused", "reason": "Trying from viewer"})
    assert response.status_code == 403
    with get_db() as db:
        assert db.execute("SELECT account_status FROM users WHERE id = 'biz-a'").fetchone()["account_status"] == "active"
    assert not any(row["action"] != "signed in" for row in audit_rows())


def test_viewer_cannot_open_detailed_records_even_with_a_grant(client):
    sign_in(client, "viewer@admin.test")
    with client.session_transaction() as sess:
        sess["admin_grants"] = {"biz-a": {"ticket": "SUP-1", "reason": "Trying with a grant",
                                          "expires_at": (NOW + timedelta(minutes=10)).isoformat()}}
    html = client.get("/users/biz-a?tab=sales").get_data(as_text=True)
    assert "Your role cannot view detailed records" in html
    assert "Rice bag" not in html
    assert not any(row["action"].startswith("viewed sales") for row in audit_rows())


def test_support_role_is_refused_owner_pages(client):
    sign_in(client, "support@admin.test")
    assert client.get("/admins").status_code == 403
    response = post(client, f"/admins/{admin_id('viewer@admin.test')}/role", {"role": "owner", "reason": "Promote"})
    assert response.status_code == 403


def test_forbidden_page_says_what_happened(client):
    sign_in(client, "viewer@admin.test")
    html = client.get("/admins").get_data(as_text=True)
    assert "Your role cannot open this page" in html


# --- Support grant and reason gate -----------------------------------------------

def test_detailed_sales_need_a_ticket_and_reason_before_they_show(client):
    sign_in(client, "support@admin.test")
    html = client.get("/users/biz-a?tab=sales").get_data(as_text=True)
    assert "Open support access" in html
    assert "Rice bag" not in html
    assert not any(row["action"].startswith("viewed sales") for row in audit_rows())


def test_a_reason_without_a_valid_ticket_does_not_open_access(client):
    sign_in(client, "support@admin.test")
    response = post(client, "/users/biz-a/access", {"ticket": "", "reason": "Customer asked", "tab": "sales"})
    assert response.status_code == 302
    html = client.get("/users/biz-a?tab=sales").get_data(as_text=True)
    assert "Open support access" in html
    assert "Rice bag" not in html


def test_granted_access_shows_records_and_is_audited_with_business_ticket_and_reason(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-1042", "reason": "Customer reports a missing sale", "tab": "sales"})
    html = client.get("/users/biz-a?tab=sales").get_data(as_text=True)
    assert "Rice bag" in html
    views = [row for row in audit_rows() if row["action"].startswith("viewed sales")]
    assert views, audit_rows()
    last = views[-1]
    assert last["target_type"] == "business"
    assert last["target_id"] == "biz-a"
    assert last["ticket_ref"] == "SUP-1042"
    assert last["reason"] == "Customer reports a missing sale"
    assert last["email"] == "support@admin.test"


def test_expired_grant_closes_the_records_again(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-7", "reason": "Short check", "tab": "sales"})
    with client.session_transaction() as sess:
        grants = dict(sess["admin_grants"])
        grants["biz-a"] = {**grants["biz-a"], "expires_at": (NOW - timedelta(minutes=1)).isoformat()}
        sess["admin_grants"] = grants
    html = client.get("/users/biz-a?tab=sales").get_data(as_text=True)
    assert "Open support access" in html
    assert "Rice bag" not in html


def test_a_grant_for_one_business_does_not_open_another(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-9", "reason": "Checking business A", "tab": "sales"})
    html = client.get("/users/biz-d?tab=expenses").get_data(as_text=True)
    assert "Open support access" in html


def test_closing_access_is_audited(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-11", "reason": "Quick look", "tab": "sales"})
    post(client, "/users/biz-a/access/close", {})
    assert audit_rows()[-1]["action"] == "closed support access"
    assert audit_rows()[-1]["ticket_ref"] == "SUP-11"


# --- Sales, expenses and money labels ----------------------------------------------

def test_sale_shows_marked_as_received_and_outstanding_balance(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-2", "reason": "Balance check", "tab": "sales"})
    html = client.get("/users/biz-a?tab=sales").get_data(as_text=True)
    assert "Marked as received" in html
    assert "Outstanding balance" in html
    assert "Part paid" in html
    assert "₦600.00" in html  # 1000 total, 400 received


def test_sales_date_filter_limits_the_rows(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-3", "reason": "Date filter", "tab": "sales"})
    today = NOW.date().isoformat()
    html = client.get(f"/users/biz-a?tab=sales&from={today}&to={today}").get_data(as_text=True)
    assert "Rice bag" in html
    assert "Old sale" not in html


def test_expenses_tab_total_matches_the_rows(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-4", "reason": "Expense check", "tab": "expenses"})
    html = client.get("/users/biz-a?tab=expenses").get_data(as_text=True)
    # 250 (Okada) + sum of 10..69 (60 bulk items) = 250 + 2370 = 2620
    assert "₦2,620.00" in html


def test_expense_records_are_paginated(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-5", "reason": "Pagination", "tab": "expenses"})
    first = client.get("/users/biz-a?tab=expenses").get_data(as_text=True)
    second = client.get("/users/biz-a?tab=expenses&page=2").get_data(as_text=True)
    assert "page 1 of 2" in first
    assert "Bulk item 59" in first
    assert "Bulk item 10" in first  # newest first: page 1 holds the 50 newest rows
    assert "Bulk item 9" in second
    assert "Okada" in second  # the oldest entry is on the last page
    assert "Bulk item 10" not in second


# --- Account access and admin management -----------------------------------------

def test_pausing_an_account_needs_a_reason_and_is_audited(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-c/status", {"status": "paused", "reason": "Requested by owner"})
    with get_db() as db:
        assert db.execute("SELECT account_status FROM users WHERE id = 'biz-c'").fetchone()["account_status"] == "paused"
    assert audit_rows()[-1]["action"] == "account paused"
    assert audit_rows()[-1]["reason"] == "Requested by owner"


def test_directory_shows_access_status_and_not_email_addresses(client):
    sign_in(client, "viewer@admin.test")
    html = client.get("/users").get_data(as_text=True)
    assert "Access enabled" in html
    assert "Paused" in html
    assert "owner-a@example.test" not in html
    detail = client.get("/users/biz-a").get_data(as_text=True)
    assert "owner-a@example.test" in detail


def test_directory_search_matches_email_without_showing_it(client):
    sign_in(client, "viewer@admin.test")
    html = client.get("/users?q=owner-c@example.test").get_data(as_text=True)
    assert "Unnamed business" in html
    # The address appears once, in the search box the admin typed it into, and nowhere in the results.
    assert html.count("owner-c@example.test") == 1
    assert 'value="owner-c@example.test"' in html


def test_owner_can_see_admins_and_must_give_a_reason_to_change_a_role(client):
    sign_in(client, "owner@admin.test")
    assert client.get("/admins").status_code == 200
    post(client, f"/admins/{admin_id('viewer@admin.test')}/role", {"role": "support", "reason": "ab"})
    with get_db() as db:
        assert db.execute("SELECT role FROM super_admins WHERE email = 'viewer@admin.test'").fetchone()["role"] == "viewer"


def test_role_change_takes_effect_for_an_existing_session(client):
    other = portal.admin_app.test_client()
    sign_in(other, "support@admin.test")
    assert other.get("/users").status_code == 200

    sign_in(client, "owner@admin.test")
    post(client, f"/admins/{admin_id('support@admin.test')}/role", {"role": "viewer", "reason": "Scope reduced"})

    response = other.get("/users")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_owner_cannot_demote_or_disable_themselves_or_the_last_owner(client):
    sign_in(client, "owner@admin.test")
    post(client, f"/admins/{admin_id('owner@admin.test')}/role", {"role": "viewer", "reason": "Self change"})
    post(client, f"/admins/{admin_id('owner@admin.test')}/status", {"active": "0", "reason": "Self disable"})
    with get_db() as db:
        row = db.execute("SELECT role, is_active FROM super_admins WHERE email = 'owner@admin.test'").fetchone()
        assert row["role"] == "owner" and row["is_active"] == 1
    assert not any("admin" in row["action"] and row["target_type"] == "admin" for row in audit_rows())


def test_admin_role_and_access_changes_are_audited(client):
    sign_in(client, "owner@admin.test")
    post(client, f"/admins/{admin_id('support@admin.test')}/status", {"active": "0", "reason": "Left the team"})
    last = audit_rows()[-1]
    assert last["action"] == "admin access disabled"
    assert last["target_type"] == "admin"
    assert last["reason"] == "Left the team"


# --- Admin activity page -------------------------------------------------------

def test_admin_activity_filters_by_business_and_action(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-a/access", {"ticket": "SUP-20", "reason": "Filter test", "tab": "sales"})
    client.get("/users/biz-a?tab=sales")
    post(client, "/users/biz-c/status", {"status": "paused", "reason": "Unrelated pause"})

    by_business = client.get("/activity?business=biz-a").get_data(as_text=True)
    assert "SUP-20" in by_business
    assert "Unrelated pause" not in by_business

    by_action = client.get("/activity?action=viewed+sales").get_data(as_text=True)
    assert "viewed sales records" in by_action
    assert "Unrelated pause" not in by_action


def test_admin_activity_filters_by_admin(client):
    sign_in(client, "support@admin.test")
    post(client, "/users/biz-c/status", {"status": "paused", "reason": "Support pause"})
    post(client, "/logout", {})
    sign_in(client, "owner@admin.test")
    post(client, "/users/biz-d/status", {"status": "paused", "reason": "Owner pause"})
    html = client.get(f"/activity?admin={admin_id('owner@admin.test')}").get_data(as_text=True)
    assert "Owner pause" in html
    assert "Support pause" not in html


def test_viewer_cannot_read_admin_activity(client):
    sign_in(client, "viewer@admin.test")
    assert client.get("/activity").status_code == 403


# --- System status ------------------------------------------------------------

def clear_telemetry():
    with get_db() as db:
        db.execute("DELETE FROM request_minutes")
        db.execute("DELETE FROM request_errors")
        db.commit()


def add_telemetry(route, status_class, n, ms_bucket, when):
    with get_db() as db:
        db.execute(
            "INSERT INTO request_minutes (minute, route, status_class, n, total_ms, " + ms_bucket + ") "
            "VALUES (?, ?, ?, ?, 0, ?) "
            "ON CONFLICT (minute, route, status_class) DO UPDATE SET "
            "n = request_minutes.n + excluded.n, " + ms_bucket + " = request_minutes." + ms_bucket + " + excluded." + ms_bucket,
            (when.strftime("%Y-%m-%dT%H:%M"), route, status_class, n, n),
        )
        db.commit()


def add_error(request_id, route, status, when):
    with get_db() as db:
        db.execute(
            "INSERT INTO request_errors (request_id, created_at, route, status, duration_ms) VALUES (?, ?, ?, ?, 730)",
            (request_id, when.isoformat(), route, status),
        )
        db.commit()


def test_system_status_with_no_requests_shows_zero_not_invented_values(client):
    clear_telemetry()
    sign_in(client, "viewer@admin.test")
    html = client.get("/system-status").get_data(as_text=True)
    assert re.search(r'Requests</div>\s*<div class="metric-value">0<', html)
    assert "No server errors in this period." in html
    assert "Slowest 5% of requests" in html


def test_system_status_counts_requests_errors_and_slowest_bucket(client):
    clear_telemetry()
    now = NOW
    add_telemetry("/api/sales", "2xx", 90, "ms_lt_250", now)
    add_telemetry("/api/sales", "2xx", 8, "ms_lt_1000", now)
    add_telemetry("/api/income/{sale_id}", "5xx", 2, "ms_lt_5000", now)
    add_error("req-abc123", "/api/income/{sale_id}", 500, now)
    sign_in(client, "viewer@admin.test")
    html = client.get("/system-status?window=24h").get_data(as_text=True)
    assert re.search(r'Requests</div>\s*<div class="metric-value">100<', html)
    assert re.search(r'Server errors</div>\s*<div class="metric-value">2 <span class="muted"[^>]*>2.0%', html)
    # 95% of 100 requests is 95. The first 90 are under 250 ms, and 98 are under 1 second, so that is the slowest-5% bound.
    assert "under 1 second" in html
    assert "req-abc123" in html
    assert "/api/income/{sale_id}" in html


def test_system_status_window_excludes_older_requests(client):
    clear_telemetry()
    add_telemetry("/old", "2xx", 50, "ms_lt_250", NOW - timedelta(days=3))
    add_telemetry("/new", "2xx", 4, "ms_lt_250", NOW)
    sign_in(client, "viewer@admin.test")
    assert re.search(r'Requests</div>\s*<div class="metric-value">4<',
                     client.get("/system-status?window=24h").get_data(as_text=True))
    assert re.search(r'Requests</div>\s*<div class="metric-value">54<',
                     client.get("/system-status?window=7d").get_data(as_text=True))


def test_system_status_says_not_available_when_logging_is_missing(client):
    from server.database import _request_telemetry_tables

    with get_db() as db:
        db.execute("DROP TABLE request_minutes")
        db.execute("DROP TABLE request_errors")
        db.commit()
    try:
        sign_in(client, "viewer@admin.test")
        html = client.get("/system-status").get_data(as_text=True)
        assert "Request logging is not available yet." in html
        assert "Not available until request logging is set up." in html
    finally:
        _request_telemetry_tables()


def test_system_status_shows_unreachable_when_the_database_fails(client, monkeypatch):
    sign_in(client, "viewer@admin.test")
    real_get_db = portal.get_db

    class FailingPing:
        """Fails only the health check's own query, so the session check still works."""

        def __init__(self, db):
            self._db = db

        def execute(self, sql, params=()):
            if sql.strip() == "SELECT 1":
                raise RuntimeError("database down")
            return self._db.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._db, name)

    class Wrapper:
        def __enter__(self):
            self._cm = real_get_db()
            return FailingPing(self._cm.__enter__())

        def __exit__(self, *exc):
            return self._cm.__exit__(*exc)

    monkeypatch.setattr(portal, "get_db", lambda: Wrapper())
    html = client.get("/system-status").get_data(as_text=True)
    assert "Unreachable" in html


# --- User activity -------------------------------------------------------------

def test_viewer_cannot_open_user_activity(client):
    sign_in(client, "viewer@admin.test")
    assert client.get("/user-activity").status_code == 403


def test_user_activity_lists_events_with_friendly_labels_and_no_emails(client):
    sign_in(client, "support@admin.test")
    html = client.get("/user-activity").get_data(as_text=True)
    assert "Sale recorded" in html
    assert "Signed in" in html
    assert "Sample Stores" in html
    assert "Unnamed business" in html  # biz-c has no profile
    assert "owner-a@example.test" not in html
    assert "owner-c@example.test" not in html


def test_user_activity_group_filter_limits_the_events(client):
    sign_in(client, "support@admin.test")
    html = client.get("/user-activity?group=expenses").get_data(as_text=True)
    assert "Expense recorded" in html
    assert "Sale recorded" not in html
    assert "Signed in" not in html


def test_user_activity_business_filter_matches_the_name(client):
    sign_in(client, "support@admin.test")
    html = client.get("/user-activity?business=Quiet").get_data(as_text=True)
    assert "Quiet Shop" in html
    assert "Sample Stores" not in html


def test_user_activity_views_are_audited(client):
    sign_in(client, "support@admin.test")
    client.get("/user-activity?group=sales")
    last = audit_rows()[-1]
    assert last["action"].startswith("viewed user activity")
    assert "group sales" in last["action"]
    assert last["email"] == "support@admin.test"


def test_user_activity_empty_filter_says_so(client):
    sign_in(client, "support@admin.test")
    html = client.get("/user-activity?business=no-such-business-xyz").get_data(as_text=True)
    assert "No activity matches these filters." in html


def test_system_status_is_named_correctly_in_navigation(client):
    sign_in(client, "viewer@admin.test")
    html = client.get("/dashboard").get_data(as_text=True)
    assert ">System status<" in html
    assert "API health" not in html
    assert "User activity" not in html  # viewers do not see it


def test_timestamps_are_shown_without_microseconds_or_offsets(client):
    sign_in(client, "support@admin.test")
    html = client.get("/user-activity").get_data(as_text=True)
    assert "+00:00" not in html
    assert "551977" not in html
    assert NOW.strftime("%Y-%m-%d %H:%M") in html


# --- Refused input flags -------------------------------------------------------

def add_refusals(uid, count, when=None):
    when = (when or NOW).isoformat()
    with get_db() as db:
        for _ in range(count):
            db.execute(
                "INSERT INTO user_activity_logs (user_id, event_type, summary, created_at) VALUES (?, 'input_rejected', "
                "'Refused input on /api/income: script or markup in description', ?)",
                (uid, when),
            )
        db.commit()


def test_a_business_with_twenty_or_more_refused_inputs_is_flagged(client):
    add_refusals("biz-a", 21)
    add_refusals("biz-d", 19)
    sign_in(client, "viewer@admin.test")
    dash = client.get("/dashboard").get_data(as_text=True)
    assert "Flagged for review" in dash
    assert "21 refused" in dash
    assert "19 refused" not in dash
    detail = client.get("/users/biz-a").get_data(as_text=True)
    assert "Refused input, 7 days" in detail
    assert "Flagged for review" in detail


def test_refusals_older_than_seven_days_do_not_count(client):
    add_refusals("biz-a", 25, when=NOW - timedelta(days=10))
    sign_in(client, "viewer@admin.test")
    dash = client.get("/dashboard").get_data(as_text=True)
    assert "No business has reached the threshold this week." in dash


def test_refusal_records_show_on_the_user_activity_page_without_values(client):
    add_refusals("biz-a", 1)
    sign_in(client, "support@admin.test")
    html = client.get("/user-activity?group=security").get_data(as_text=True)
    assert "Input refused" in html
    assert "script or markup in description" in html
    assert "<img" not in html
