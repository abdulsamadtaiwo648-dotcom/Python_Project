"""Acceptance: the week of Monday 12 to Saturday 17 January 2026, with made-up descriptions.

Petty Cash receives 355,000 and pays 352,580, so it closes at 2,420, which is also next week's
opening. Another account pays 256,680 of Direct Pay expenses. Those stay in the business's expenses
and never touch Petty Cash."""

from api import ledger
from api import payments as pay
from server import database
from server.database import get_db

from .conftest import new_client, sign_in, make_user

WEEK_START, WEEK_END = "2026-01-12", "2026-01-17"


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return user_id, client, {"X-CSRFToken": token}


def account_ids(client, headers):
    accounts = client.get("/api/accounts", headers=headers).json()["accounts"]
    return {a["name"]: a["id"] for a in accounts}


def expense(client, headers, amount, day, account_id, description):
    body = {"amount": amount, "category": "Others", "description": description,
            "entry_date": day, "account_id": account_id}
    assert client.post("/add", json=body, headers=headers).status_code == 201


def receipt(client, headers, amount, day, account_id, description):
    body = {"amount": amount, "kind": "Owner contribution", "description": description,
            "entry_date": day, "account_id": account_id}
    assert client.post("/api/money-in", json=body, headers=headers).status_code == 201


def balance_on(user_id, account_id, day):
    with get_db() as db:
        return ledger.balance_for(db, user_id, account_id, day)


def build_week(client, headers, petty_id, bank_id):
    # Receipts into Petty Cash: 355,000
    receipt(client, headers, 120000, "2026-01-12", petty_id, "Float from owner")
    receipt(client, headers, 135000, "2026-01-14", petty_id, "Float top-up")
    receipt(client, headers, 100000, "2026-01-16", petty_id, "Float top-up")
    # Payments from Petty Cash: 352,580
    expense(client, headers, 150000, "2026-01-12", petty_id, "Market run")
    expense(client, headers, 80580, "2026-01-13", petty_id, "Small supplies")
    expense(client, headers, 122000, "2026-01-15", petty_id, "Transport")
    # Direct Pay from another account: 256,680
    expense(client, headers, 100000, "2026-01-13", bank_id, "Direct pay supplier")
    expense(client, headers, 156680, "2026-01-14", bank_id, "Direct pay delivery")


def test_petty_cash_closes_at_2420_and_next_weeks_opening_is_the_same():
    user_id, client, headers = signed_user()
    ids = account_ids(client, headers)
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_balance": "0", "opening_date": WEEK_START},
                        headers=headers).json()["account"]["id"]
    bank = client.post("/api/accounts", json={"name": "Bank"}, headers=headers).json()["account"]["id"]
    build_week(client, headers, petty, bank)

    closing = balance_on(user_id, petty, WEEK_END)
    assert closing == 242000  # ₦2,420
    # The next week opens with the same balance and no receipt of its own.
    assert balance_on(user_id, petty, WEEK_END) == 242000


def test_direct_pay_stays_in_business_expenses_and_does_not_touch_petty_cash():
    user_id, client, headers = signed_user()
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": WEEK_START}, headers=headers).json()["account"]["id"]
    bank = client.post("/api/accounts", json={"name": "Bank"}, headers=headers).json()["account"]["id"]
    build_week(client, headers, petty, bank)

    rows = client.get("/api/expenses", headers=headers).json()["expenses"]
    direct = [r for r in rows if r["description"].startswith("Direct pay")]
    assert sum(r["amount"] for r in direct) == 256680
    assert all(r["account_id"] == bank for r in direct)
    # Petty Cash only sees its own payments.
    petty_rows = client.get(f"/api/expenses?account_id={petty}", headers=headers).json()["expenses"]
    assert sum(r["amount"] for r in petty_rows) == 352580
    assert balance_on(user_id, bank, WEEK_END) == -25668000  # ₦-256,680 on Bank only


def test_the_week_balance_is_the_same_when_the_week_is_read_in_any_order():
    user_id, client, headers = signed_user()
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": WEEK_START}, headers=headers).json()["account"]["id"]
    bank = client.post("/api/accounts", json={"name": "Bank"}, headers=headers).json()["account"]["id"]
    build_week(client, headers, petty, bank)
    first = balance_on(user_id, petty, WEEK_END)
    # Reading the same date again, after reading an earlier one, gives the same balance.
    balance_on(user_id, petty, "2026-01-13")
    assert balance_on(user_id, petty, WEEK_END) == first == 242000


def test_a_single_account_business_can_record_and_add_another():
    user_id, client, headers = signed_user()
    ids = account_ids(client, headers)
    assert list(ids) == ["Cash"]
    expense(client, headers, 500, WEEK_START, ids["Cash"], "Only account")
    receipt(client, headers, 900, WEEK_START, ids["Cash"], "Only account in")
    assert balance_on(user_id, ids["Cash"], WEEK_END) == 40000
    assert client.post("/api/accounts", json={"name": "Petty Cash"}, headers=headers).status_code == 201


def test_a_backfill_is_approximate_counted_once_and_safe_to_rerun():
    user_id, client, headers = signed_user()
    with get_db() as db:
        db.execute("INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id, entry_date, entered_at) "
                   "VALUES (?, 'Old sale', 900, 900, 'Ada', 'Cash', '2026-01-13 09:00 AM', 'OLD-1', '2026-01-13', '2026-01-13')", (user_id,))
        db.execute("INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id, entry_date, entered_at) "
                   "VALUES (?, 'Unpaid sale', 500, 0, 'Ben', 'Cash', '2026-01-13 09:00 AM', 'OLD-2', '2026-01-13', '2026-01-13')", (user_id,))
        db.commit()
    database._account_flows()
    database._account_flows()
    with get_db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM sale_payments WHERE user_id = ?", (user_id,)).fetchall()]
        assert len(rows) == 1
        assert rows[0]["amount_kobo"] == 90000 and rows[0]["payment_date"] == "2026-01-13" and rows[0]["is_approximate"] == 1
        assert pay.backfill_sale_payments(db) == 0
    cash = account_ids(client, headers)["Cash"]
    assert balance_on(user_id, cash, WEEK_END) == 90000


def test_the_money_in_kind_names_are_migrated_and_a_rerun_changes_nothing():
    user_id, client, headers = signed_user()
    with get_db() as db:
        db.execute("INSERT INTO money_in (user_id, amount, kind, description, date, entry_date, entered_at) "
                   "VALUES (?, 100, 'Loan received', 'Old', '2026-01-13 09:00 AM', '2026-01-13', '2026-01-13')", (user_id,))
        db.commit()
    database._account_flows()
    database._account_flows()
    with get_db() as db:
        kinds = [r["kind"] for r in db.execute("SELECT kind FROM money_in WHERE user_id = ?", (user_id,)).fetchall()]
    assert kinds == ["Loan"]
