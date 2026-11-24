"""Sales and expense rules: payment modes, length limits, batch size, dates, and replays.

The app is called directly through ASGI with a signed session cookie (the same cookie format
the main test suite uses), so these run without the FastAPI test client."""

import asyncio
import base64
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
os.environ.setdefault("SQLITE_DATABASE_PATH", os.path.join(tempfile.mkdtemp(prefix="solobiz-sales-rules-"), "rules.db"))
os.environ.setdefault("SECRET_KEY", "sales-rules-test-secret-key-long-enough-0123456789")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("RENDER", None)

import pytest  # noqa: E402
from itsdangerous import TimestampSigner  # noqa: E402

from api import record_rules  # noqa: E402
from api.main import app  # noqa: E402
from api.settings import settings  # noqa: E402
from server.database import get_db  # noqa: E402

CSRF = "sales-rules-csrf-token"


def cookie_for(user_id):
    payload = base64.b64encode(json.dumps({"user_id": user_id, "csrf_token": CSRF}).encode())
    return TimestampSigner(settings.secret_key).sign(payload).decode()


async def _call(method, path, body=None, user_id=None, extra_headers=()):
    raw = json.dumps(body).encode() if body is not None else b""
    headers = [(b"host", b"testserver.local"), (b"content-type", b"application/json"),
               (b"content-length", str(len(raw)).encode())]
    if user_id:
        headers += [(b"cookie", f"session={cookie_for(user_id)}".encode()), (b"x-csrftoken", CSRF.encode())]
    headers += [(k.encode(), v.encode()) for k, v in extra_headers]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
             "headers": headers, "client": ("127.0.0.1", 1), "server": ("testserver.local", 80)}
    sent, delivered = [], [False]

    async def receive():
        if not delivered[0]:
            delivered[0] = True
            return {"type": "http.request", "body": raw, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    text = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, (json.loads(text) if text else None)


def call(*args, **kwargs):
    return asyncio.run(_call(*args, **kwargs))


@pytest.fixture
def owner():
    user_id = "rules-" + uuid.uuid4().hex[:10]
    with get_db() as db:
        db.execute("INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                   (user_id, f"{user_id}@example.test", "x", "Rules", "Tester"))
        db.commit()
    return user_id


def income_rows(user_id):
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM income WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()]


def expense_rows(user_id):
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM expenses WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()]


def checkout_body(checkout_id, **overrides):
    body = {
        "checkout_id": checkout_id,
        "items": [{"item_name": "Rice bag", "quantity": 1, "unit_price": 1000, "checkout_line_id": "line-1"}],
        "amount_paid": 1000,
        "payment_mode": "Cash",
        "customer_name": "Ada",
        "receipt_id": "REC-" + checkout_id,
    }
    body.update(overrides)
    return body


def sale_body(**overrides):
    body = {"description": "Rice bag", "total_value": 1000, "amount_paid": 1000, "payment_mode": "Cash",
            "customer_name": "Ada", "receipt_id": "R-" + uuid.uuid4().hex[:8]}
    body.update(overrides)
    return body


# --- Payment modes -----------------------------------------------------------------

def test_checkout_accepts_an_allowed_mode_in_any_case_and_stores_the_canonical_name(owner):
    status, _ = call("POST", "/api/checkout", checkout_body("chk-mode-1", payment_mode="pos"), owner, [("x-client-op", "op-" + owner)])
    assert status in (200, 201)
    assert income_rows(owner)[0]["payment_mode"] == "POS"


def test_checkout_refuses_an_unknown_payment_mode_and_saves_nothing(owner):
    status, body = call("POST", "/api/checkout", checkout_body("chk-mode-2", payment_mode="Bitcoin"), owner)
    assert status == 400
    assert "payment method" in body["message"]
    assert income_rows(owner) == []


def test_single_sale_refuses_an_unknown_payment_mode(owner):
    status, _ = call("POST", "/api/income", sale_body(payment_mode="Crypto"), owner)
    assert status == 400
    assert income_rows(owner) == []


def test_single_sale_accepts_card_and_other(owner):
    assert call("POST", "/api/income", sale_body(payment_mode="Card"), owner)[0] == 201
    assert call("POST", "/api/income", sale_body(payment_mode="Other"), owner)[0] == 201
    assert [r["payment_mode"] for r in income_rows(owner)] == ["Card", "Other"]


# --- Length limits -----------------------------------------------------------------

def test_description_over_200_characters_is_refused(owner):
    status, _ = call("POST", "/api/income", sale_body(description="x" * 201), owner)
    assert status == 400
    assert call("POST", "/api/income", sale_body(description="x" * 200), owner)[0] == 201


def test_customer_name_over_120_characters_is_refused(owner):
    assert call("POST", "/api/income", sale_body(customer_name="n" * 121), owner)[0] == 400
    assert call("POST", "/api/checkout", checkout_body("chk-len-1", customer_name="n" * 121), owner)[0] == 400


def test_receipt_id_over_64_characters_is_refused(owner):
    assert call("POST", "/api/income", sale_body(receipt_id="r" * 65), owner)[0] == 400
    assert call("POST", "/api/checkout", checkout_body("chk-len-2", receipt_id="r" * 65), owner)[0] == 400


def test_expense_category_and_description_limits(owner):
    base = {"amount": 500, "category": "Transport", "description": "Okada"}
    assert call("POST", "/add", {**base, "category": "c" * 81}, owner)[0] == 400
    assert call("POST", "/add", {**base, "description": "d" * 201}, owner)[0] == 400
    assert call("POST", "/add", base, owner)[0] in (200, 201)
    assert len(expense_rows(owner)) == 1


# --- Bulk sync -----------------------------------------------------------------

def test_sync_refuses_more_than_100_sales_in_one_request(owner):
    status, body = call("POST", "/api/sync-sales", {"sales": [sale_body() for _ in range(101)]}, owner)
    assert status == 400
    assert "100" in body["message"]
    assert income_rows(owner) == []


def test_sync_accepts_exactly_100_sales(owner):
    status, body = call("POST", "/api/sync-sales", {"sales": [sale_body() for _ in range(100)]}, owner)
    assert status == 200
    assert body["count"] == 100


def test_sync_skips_only_the_bad_record(owner):
    sales = [sale_body(), sale_body(payment_mode="Crypto"), sale_body(description="x" * 201), sale_body()]
    status, body = call("POST", "/api/sync-sales", {"sales": sales}, owner)
    assert status == 200
    assert body["count"] == 2
    assert len(income_rows(owner)) == 2


# --- Dates ----------------------------------------------------------------------

def stamp(when):
    return when.strftime("%Y-%m-%d %I:%M %p")


def test_a_recent_client_date_is_kept():
    when = datetime.now(timezone.utc) - timedelta(days=3)
    assert record_rules.sale_date_label(stamp(when)) == stamp(when)


def test_a_future_date_is_replaced_with_server_time():
    now = datetime.now(timezone.utc)
    label = record_rules.sale_date_label(stamp(now + timedelta(hours=2)), now)
    assert label == stamp(now)


def test_a_small_clock_skew_is_allowed():
    now = datetime.now(timezone.utc)
    near = now + timedelta(minutes=3)
    assert record_rules.sale_date_label(stamp(near), now) == stamp(near)


def test_a_date_older_than_two_years_is_replaced_with_server_time():
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=800)
    assert record_rules.sale_date_label(stamp(old), now) == stamp(now)


@pytest.mark.parametrize("value", ["", None, "yesterday", "2026-13-40 99:99 XX", "<script>"])
def test_an_unreadable_date_is_replaced_with_server_time(value):
    now = datetime.now(timezone.utc)
    assert record_rules.sale_date_label(value, now) == stamp(now)


def test_the_date_stored_for_a_synced_sale_follows_the_rule(owner):
    future = datetime.now(timezone.utc) + timedelta(days=10)
    call("POST", "/api/sync-sales", {"sales": [sale_body(date=stamp(future))]}, owner)
    stored = income_rows(owner)[0]["date"]
    assert stored != stamp(future)
    assert datetime.strptime(stored, record_rules.SALE_DATE_FORMAT).replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc) + timedelta(minutes=5)


# --- Replays --------------------------------------------------------------------

def test_replaying_the_same_checkout_does_not_record_it_twice(owner):
    body = checkout_body("chk-replay-1")
    first = call("POST", "/api/checkout", body, owner, [("x-client-op", "op-replay-" + owner)])
    second = call("POST", "/api/checkout", body, owner, [("x-client-op", "op-replay-" + owner)])
    assert first[0] in (200, 201)
    assert second[0] in (200, 201)
    assert len(income_rows(owner)) == 1


def test_replaying_an_expense_with_the_same_operation_id_is_not_applied_twice(owner):
    headers = [("x-client-op", "op-expense-" + owner)]
    payload = {"amount": 900, "category": "Fuel", "description": "Generator"}
    call("POST", "/add", payload, owner, headers)
    status, body = call("POST", "/add", payload, owner, headers)
    assert status in (200, 201)
    assert body.get("duplicate") is True
    assert len(expense_rows(owner)) == 1


# --- Operation claims (replay safety) ----------------------------------------------

from api import core as api_core  # noqa: E402


def claim_row(user_id, op_id, status, created_at):
    with get_db() as db:
        db.execute("DELETE FROM client_ops WHERE user_id = ? AND op_id = ?", (user_id, op_id))
        db.execute("INSERT INTO client_ops (user_id, op_id, created_at, status) VALUES (?, ?, ?, ?)",
                   (user_id, op_id, created_at.isoformat(), status))
        db.commit()


def test_claims_are_atomic_for_direct_calls(owner):
    op = "op-atomic-" + owner
    assert api_core.claim_client_op(owner, op) == "new"
    assert api_core.claim_client_op(owner, op) == "busy"
    api_core.finish_client_op(owner, op)
    assert api_core.claim_client_op(owner, op) == "done"


def test_a_replay_while_the_first_copy_is_in_progress_is_refused_with_503_and_writes_nothing(owner):
    op = "op-busy-" + owner
    assert api_core.claim_client_op(owner, op) == "new"  # the first copy is still running
    status, body = call("POST", "/add", {"amount": 700, "category": "Fuel", "description": "Gen"}, owner, [("x-client-op", op)])
    assert status == 503
    assert "retried" in body["message"]
    assert expense_rows(owner) == []


def test_a_claim_left_pending_for_too_long_is_taken_over(owner):
    op = "op-stale-" + owner
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    claim_row(owner, op, "pending", old)
    status, _ = call("POST", "/add", {"amount": 700, "category": "Fuel", "description": "Gen"}, owner, [("x-client-op", op)])
    assert status in (200, 201)
    assert len(expense_rows(owner)) == 1
    replay_status, replay = call("POST", "/add", {"amount": 700, "category": "Fuel", "description": "Gen"}, owner, [("x-client-op", op)])
    assert replay.get("duplicate") is True
    assert len(expense_rows(owner)) == 1


def test_a_failed_change_releases_its_claim_so_a_corrected_retry_is_applied(owner):
    op = "op-retry-" + owner
    bad = {"amount": 700, "category": "c" * 81, "description": "Gen"}
    status, _ = call("POST", "/add", bad, owner, [("x-client-op", op)])
    assert status == 400
    assert expense_rows(owner) == []
    good = {"amount": 700, "category": "Fuel", "description": "Gen"}
    status, _ = call("POST", "/add", good, owner, [("x-client-op", op)])
    assert status in (200, 201)
    assert len(expense_rows(owner)) == 1


def test_a_claim_belongs_to_one_business_only(owner):
    other = "rules-other-" + uuid.uuid4().hex[:8]
    with get_db() as db:
        db.execute("INSERT INTO users (id, email, password, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                   (other, f"{other}@example.test", "x", "Other", "Tester"))
        db.commit()
    op = "op-shared-" + owner
    assert api_core.claim_client_op(owner, op) == "new"
    assert api_core.claim_client_op(other, op) == "new"
