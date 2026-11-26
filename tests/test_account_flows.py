"""Accounts in use: expenses paid from an account, Money In received into one, transfers between two,
and sale payments as dated ledger rows. Each record is counted once, on the account it affects."""

from datetime import datetime, timedelta, timezone

from api import ledger
from api import payments as pay
from server.database import get_db

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return user_id, client, {"X-CSRFToken": token}


def today():
    return datetime.now(timezone.utc).date()


def days_ago(n):
    return (today() - timedelta(days=n)).isoformat()


def accounts_by_name(client, headers):
    data = client.get("/api/accounts", headers=headers).json()
    return {a["name"]: a for a in data["accounts"]}


def add_account(client, headers, name, **extra):
    response = client.post("/api/accounts", json={"name": name, **extra}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["account"]["id"]


def balance(user_id, account_id, day=None):
    with get_db() as db:
        return ledger.balance_for(db, user_id, account_id, (day or today()).isoformat())


def cash_id(client, headers):
    return accounts_by_name(client, headers)["Cash"]["id"]


def expense(client, headers, amount, account_id=None, day=None, description="Fuel"):
    body = {"amount": amount, "category": "Others", "description": description, "entry_date": day or today().isoformat()}
    if account_id is not None:
        body["account_id"] = account_id
    return client.post("/add", json=body, headers=headers)


def money_in(client, headers, amount, kind="Owner contribution", account_id=None, day=None):
    body = {"amount": amount, "kind": kind, "description": "In", "entry_date": day or today().isoformat()}
    if account_id is not None:
        body["account_id"] = account_id
    return client.post("/api/money-in", json=body, headers=headers)


def transfer(client, headers, amount, to_id, from_id, day=None):
    body = {"amount": amount, "kind": "Transfer", "description": "Top up", "entry_date": day or today().isoformat(),
            "account_id": to_id, "from_account_id": from_id}
    return client.post("/api/money-in", json=body, headers=headers)


def sale(client, headers, total, paid, day=None):
    """Record a sale and return {'id': the sale's row id}. `day` is a YYYY-MM-DD string."""
    body = {"description": "Rice", "total_value": total, "amount_paid": paid, "customer_name": "Ada",
            "payment_mode": "Cash", "entry_date": day or today().isoformat()}
    response = client.post("/api/income", json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    with get_db() as db:
        user_id = db.execute("SELECT user_id FROM income ORDER BY id DESC LIMIT 1").fetchone()["user_id"]
        row = db.execute("SELECT MAX(id) AS id FROM income WHERE user_id = ?", (user_id,)).fetchone()
    return {"id": row["id"]}


def payment_rows(user_id, income_id=None):
    with get_db() as db:
        if income_id is None:
            return [dict(r) for r in db.execute("SELECT * FROM sale_payments WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()]
        return [dict(r) for r in db.execute("SELECT * FROM sale_payments WHERE user_id = ? AND income_id = ? ORDER BY id", (user_id, income_id)).fetchall()]


def income_row(user_id, income_id):
    with get_db() as db:
        return dict(db.execute("SELECT * FROM income WHERE id = ? AND user_id = ?", (income_id, user_id)).fetchone())


# --- expenses paid from an account ------------------------------------------------------------

def test_an_expense_defaults_to_the_default_account():
    user_id, client, headers = signed_user()
    assert expense(client, headers, 1000).status_code == 201
    assert balance(user_id, cash_id(client, headers)) == -100000


def test_an_expense_is_paid_from_the_account_chosen_and_only_that_account_changes():
    user_id, client, headers = signed_user()
    petty = add_account(client, headers, "Petty Cash")
    assert expense(client, headers, 400, account_id=petty).status_code == 201
    assert balance(user_id, petty) == -40000
    assert balance(user_id, cash_id(client, headers)) == 0


def test_an_expense_cannot_be_paid_from_another_businesses_account_or_an_archived_one():
    _, client_a, headers_a = signed_user()
    user_b, client_b, headers_b = signed_user()
    foreign = add_account(client_a, headers_a, "A only")
    assert expense(client_b, headers_b, 100, account_id=foreign).status_code == 400
    petty = add_account(client_b, headers_b, "Petty Cash")
    client_b.put(f"/api/accounts/{petty}", json={"archived": True}, headers=headers_b)
    assert expense(client_b, headers_b, 100, account_id=petty).status_code == 400


def test_an_expense_can_be_moved_to_another_account_and_is_not_counted_twice():
    user_id, client, headers = signed_user()
    petty = add_account(client, headers, "Petty Cash")
    assert expense(client, headers, 1000).status_code == 201
    expense_id = client.get("/api/expenses", headers=headers).json()["expenses"][0]["server_id"]
    body = {"amount": 1000, "category": "Others", "description": "Fuel", "account_id": petty}
    assert client.put(f"/api/expenses/{expense_id}", json=body, headers=headers).status_code == 200
    assert balance(user_id, cash_id(client, headers)) == 0
    assert balance(user_id, petty) == -100000


def test_deleting_an_expense_removes_its_payment_from_the_account_once():
    user_id, client, headers = signed_user()
    petty = add_account(client, headers, "Petty Cash")
    expense(client, headers, 250, account_id=petty)
    expense_id = client.get("/api/expenses", headers=headers).json()["expenses"][0]["server_id"]
    assert client.delete(f"/api/expenses/{expense_id}", headers=headers).status_code == 200
    assert balance(user_id, petty) == 0


def test_expenses_can_be_filtered_by_account():
    _, client, headers = signed_user()
    petty = add_account(client, headers, "Petty Cash")
    expense(client, headers, 100, account_id=petty, description="Petty item")
    expense(client, headers, 200, description="Cash item")
    rows = client.get(f"/api/expenses?account_id={petty}", headers=headers).json()["expenses"]
    assert [r["description"] for r in rows] == ["Petty item"]


# --- money in and transfers -------------------------------------------------------------------

def test_money_in_is_received_into_the_default_account_unless_another_is_chosen():
    user_id, client, headers = signed_user()
    petty = add_account(client, headers, "Petty Cash")
    assert money_in(client, headers, 5000).status_code == 201
    assert money_in(client, headers, 2000, account_id=petty).status_code == 201
    assert balance(user_id, cash_id(client, headers)) == 500000
    assert balance(user_id, petty) == 200000


def test_a_transfer_is_one_record_that_moves_money_between_two_accounts():
    user_id, client, headers = signed_user()
    cash = cash_id(client, headers)
    petty = add_account(client, headers, "Petty Cash")
    money_in(client, headers, 10000)
    assert transfer(client, headers, 3000, to_id=petty, from_id=cash).status_code == 201
    assert balance(user_id, cash) == 700000
    assert balance(user_id, petty) == 300000
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM money_in WHERE user_id = ? AND kind = 'Transfer'", (user_id,)).fetchone()["n"] == 1


def test_a_transfer_is_left_out_of_business_money_in_sales_expenses_and_profit():
    _, client, headers = signed_user()
    cash = cash_id(client, headers)
    petty = add_account(client, headers, "Petty Cash")
    transfer(client, headers, 3000, to_id=petty, from_id=cash)
    assert client.get("/api/money-in", headers=headers).json()["money_in"] == []
    data = client.get(f"/api/dashboard?month={today().strftime('%Y-%m')}", headers=headers).json()
    assert data["cash"]["money_in"] == 0
    assert data["month_income"] == 0 and data["month_expenses"] == 0 and data["net_profit"] == 0


def test_a_transfer_needs_two_different_active_accounts_in_the_same_business():
    _, client, headers = signed_user()
    cash = cash_id(client, headers)
    petty = add_account(client, headers, "Petty Cash")
    assert transfer(client, headers, 100, to_id=cash, from_id=cash).status_code == 400
    assert transfer(client, headers, 100, to_id=petty, from_id=999999).status_code == 400
    client.put(f"/api/accounts/{petty}", json={"archived": True}, headers=headers)
    assert transfer(client, headers, 100, to_id=petty, from_id=cash).status_code == 400


def test_a_transfer_to_another_businesss_account_is_refused():
    _, client_a, headers_a = signed_user()
    _, client_b, headers_b = signed_user()
    foreign = cash_id(client_a, headers_a)
    own = cash_id(client_b, headers_b)
    assert transfer(client_b, headers_b, 100, to_id=foreign, from_id=own).status_code == 400


def test_a_transfer_from_an_archived_account_is_refused_even_when_it_was_active_before():
    _, client, headers = signed_user()
    cash = cash_id(client, headers)
    petty = add_account(client, headers, "Petty Cash")
    client.put(f"/api/accounts/{petty}", json={"archived": True}, headers=headers)
    assert transfer(client, headers, 100, to_id=cash, from_id=petty).status_code == 400


# --- sale payments ----------------------------------------------------------------------------

def test_a_sale_paid_in_full_is_one_dated_payment_on_the_default_account():
    user_id, client, headers = signed_user()
    result = sale(client, headers, 2000, 2000, day=days_ago(2))
    rows = payment_rows(user_id, result["id"])
    assert len(rows) == 1 and rows[0]["amount_kobo"] == 200000
    assert rows[0]["payment_date"] == days_ago(2) and rows[0]["is_approximate"] == 0
    assert balance(user_id, cash_id(client, headers)) == 200000


def test_an_unpaid_sale_does_not_increase_cash():
    user_id, client, headers = signed_user()
    sale(client, headers, 2000, 0)
    assert payment_rows(user_id) == []
    assert balance(user_id, cash_id(client, headers)) == 0


def test_later_partial_payments_are_dated_rows_and_the_sale_total_follows_them():
    user_id, client, headers = signed_user()
    result = sale(client, headers, 2000, 500, day=days_ago(5))
    income_id = result["id"]
    response = client.post(f"/update_payment/{income_id}", json={"payment_amount": "300", "payment_date": days_ago(3)}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["applied_amount"] == 300.0
    assert income_row(user_id, income_id)["amount_paid"] == 800.0
    rows = payment_rows(user_id, income_id)
    assert [(r["amount_kobo"], r["payment_date"]) for r in rows] == [(50000, days_ago(5)), (30000, days_ago(3))]
    assert balance(user_id, cash_id(client, headers), today() - timedelta(days=4)) == 50000
    assert balance(user_id, cash_id(client, headers)) == 80000


def test_a_payment_is_capped_at_what_is_owed_and_only_the_applied_amount_is_recorded():
    user_id, client, headers = signed_user()
    income_id = sale(client, headers, 1000, 800)["id"]
    response = client.post(f"/update_payment/{income_id}", json={"payment_amount": "5000"}, headers=headers)
    assert response.json()["applied_amount"] == 200.0
    assert income_row(user_id, income_id)["amount_paid"] == 1000.0
    assert sum(r["amount_kobo"] for r in payment_rows(user_id, income_id)) == 100000


def test_a_payment_on_a_sale_already_paid_records_nothing_and_says_so():
    user_id, client, headers = signed_user()
    income_id = sale(client, headers, 1000, 1000)["id"]
    response = client.post(f"/update_payment/{income_id}", json={"payment_amount": "100"}, headers=headers)
    assert response.status_code == 200 and response.json()["applied_amount"] == 0
    assert len(payment_rows(user_id, income_id)) == 1


def test_a_payment_with_an_invalid_date_is_refused():
    user_id, client, headers = signed_user()
    income_id = sale(client, headers, 1000, 0)["id"]
    response = client.post(f"/update_payment/{income_id}", json={"payment_amount": "100", "payment_date": "tomorrow-ish"}, headers=headers)
    assert response.status_code == 400
    assert payment_rows(user_id, income_id) == []


def test_a_checkout_records_each_sale_line_once():
    user_id, client, headers = signed_user()
    body = {"checkout_id": "chk-flow-1", "customer_name": "Ada", "payment_mode": "Cash", "amount_paid": 1500,
            "items": [{"item_name": "Soap", "quantity": 1, "unit_price": 1000, "checkout_line_id": "line-1"},
                      {"item_name": "Sugar", "quantity": 1, "unit_price": 1000, "checkout_line_id": "line-2"}]}
    response = client.post("/api/checkout", json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    rows = payment_rows(user_id)
    assert sum(r["amount_kobo"] for r in rows) == 150000
    assert balance(user_id, cash_id(client, headers)) == 150000


def test_a_sale_synced_from_offline_records_its_payment_once():
    user_id, client, headers = signed_user()
    body = {"sales": [{"description": "Bread", "total_value": 800, "amount_paid": 800, "customer_name": "Ada",
                       "payment_mode": "Cash", "receipt_id": "SYNC-1", "date": days_ago(1)}]}
    assert client.post("/api/sync-sales", json=body, headers=headers).status_code == 200
    assert sum(r["amount_kobo"] for r in payment_rows(user_id)) == 80000


def test_deleting_a_sale_removes_its_payments_from_the_account():
    user_id, client, headers = signed_user()
    income_id = sale(client, headers, 1000, 1000)["id"]
    assert client.delete(f"/api/income/{income_id}", headers=headers).status_code == 200
    assert payment_rows(user_id, income_id) == []
    assert balance(user_id, cash_id(client, headers)) == 0


def test_a_spreadsheet_sale_records_its_payment():
    user_id, client, headers = signed_user()
    rows = [{"date": days_ago(4), "description": "Rice", "amount": "900", "customer": "Ada", "payment_mode": "Cash"}]
    assert client.post("/api/import/sales", json={"rows": rows}, headers=headers).json()["imported"] == 1
    assert sum(r["amount_kobo"] for r in payment_rows(user_id)) == 90000


# --- the ledger agrees with the records -----------------------------------------------------

def test_the_ledger_lists_every_movement_on_an_account_with_its_source():
    user_id, client, headers = signed_user()
    cash = cash_id(client, headers)
    petty = add_account(client, headers, "Petty Cash")
    money_in(client, headers, 5000)
    transfer(client, headers, 1000, to_id=petty, from_id=cash)
    expense(client, headers, 300, account_id=petty)
    sale(client, headers, 700, 700)
    with get_db() as db:
        kinds = sorted((e["source"], e["direction"], e["kobo"]) for e in ledger.entries(db, user_id, petty))
    assert kinds == [("expense", "out", 30000), ("transfer_in", "in", 100000)]
    with get_db() as db:
        cash_kinds = sorted((e["source"], e["direction"]) for e in ledger.entries(db, user_id, cash))
    assert cash_kinds == [("money_in", "in"), ("sale_payment", "in"), ("transfer_out", "out")]


def test_an_opening_balance_counts_once_from_its_date():
    user_id, client, headers = signed_user()
    petty = add_account(client, headers, "Petty Cash", opening_balance="150.00", opening_date=days_ago(10))
    assert balance(user_id, petty, today() - timedelta(days=11)) == 0
    assert balance(user_id, petty, today() - timedelta(days=10)) == 15000
    assert balance(user_id, petty) == 15000
