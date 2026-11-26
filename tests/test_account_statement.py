"""The account view: a week (Monday to Sunday) or a month for one account, with opening, receipts,
payments and closing. Balances carry across empty weeks and month boundaries, and the starting
balance is counted once. Dashboard cash figures follow the same rules."""

from datetime import date

from api import ledger
from server.database import get_db

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return user_id, client, {"X-CSRFToken": token}


def account_id(client, headers, name):
    accounts = client.get("/api/accounts", headers=headers).json()["accounts"]
    return next(a["id"] for a in accounts if a["name"] == name)


def statement(client, headers, acct, period, day):
    response = client.get(f"/api/accounts/{acct}/statement?period={period}&date={day}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def receipt(client, headers, acct, amount, day, description="Float"):
    body = {"amount": amount, "kind": "Owner contribution", "description": description, "entry_date": day, "account_id": acct}
    assert client.post("/api/money-in", json=body, headers=headers).status_code == 201


def expense(client, headers, acct, amount, day, description="Item"):
    body = {"amount": amount, "category": "Others", "description": description, "entry_date": day, "account_id": acct}
    assert client.post("/add", json=body, headers=headers).status_code == 201


# --- periods -----------------------------------------------------------------------------------

def test_a_week_runs_from_monday_to_sunday_whichever_day_is_asked_for():
    for day in (date(2026, 1, 12), date(2026, 1, 14), date(2026, 1, 18)):
        start, end = ledger.week_bounds(day)
        assert (start, end) == (date(2026, 1, 12), date(2026, 1, 18))
    assert ledger.week_bounds(date(2026, 1, 12))[0].weekday() == 0


def test_a_month_runs_from_its_first_day_to_its_last_including_leap_february():
    assert ledger.month_bounds(date(2024, 2, 9)) == (date(2024, 2, 1), date(2024, 2, 29))
    assert ledger.month_bounds(date(2026, 2, 1)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert ledger.month_bounds(date(2026, 12, 5)) == (date(2026, 12, 1), date(2026, 12, 31))


# --- the week of 12 to 17 January 2026 (made-up descriptions) -----------------------------------

def test_the_week_closes_at_2420_and_the_next_week_opens_at_2420():
    _, client, headers = signed_user()
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": "2026-01-12"}, headers=headers).json()["account"]["id"]
    bank = client.post("/api/accounts", json={"name": "Bank"}, headers=headers).json()["account"]["id"]
    receipt(client, headers, petty, 120000, "2026-01-12", "Float from owner")
    receipt(client, headers, petty, 135000, "2026-01-14", "Float top-up")
    receipt(client, headers, petty, 100000, "2026-01-16", "Float top-up")
    expense(client, headers, petty, 150000, "2026-01-12", "Market run")
    expense(client, headers, petty, 80580, "2026-01-13", "Small supplies")
    expense(client, headers, petty, 122000, "2026-01-15", "Transport")
    expense(client, headers, bank, 256680, "2026-01-13", "Direct pay supplier")

    week = statement(client, headers, petty, "week", "2026-01-14")
    assert week["period"]["start"] == "2026-01-12" and week["period"]["end"] == "2026-01-18"
    assert week["opening"]["balance"] == "0.00"
    assert week["receipts"]["total"] == "355000.00"
    assert week["payments"]["total"] == "352580.00"
    assert week["closing"]["balance"] == "2420.00"
    assert week["closing"]["overspent"] is None

    following = statement(client, headers, petty, "week", "2026-01-19")
    assert following["opening"]["balance"] == "2420.00"
    assert following["receipts"]["total"] == "0.00"
    assert following["closing"]["balance"] == "2420.00"


def test_direct_pay_is_not_in_petty_cash_and_names_nothing_on_it():
    _, client, headers = signed_user()
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": "2026-01-12"}, headers=headers).json()["account"]["id"]
    bank = client.post("/api/accounts", json={"name": "Bank"}, headers=headers).json()["account"]["id"]
    expense(client, headers, bank, 256680, "2026-01-13", "Direct pay supplier")
    week = statement(client, headers, petty, "week", "2026-01-14")
    assert week["payments"]["items"] == [] and week["closing"]["balance"] == "0.00"


# --- carrying balances -------------------------------------------------------------------------

def test_balances_carry_across_empty_weeks_without_becoming_new_money_in():
    _, client, headers = signed_user()
    cash = account_id(client, headers, "Cash")
    receipt(client, headers, cash, 5000, "2026-01-05")
    later = statement(client, headers, cash, "week", "2026-02-02")
    assert later["opening"]["balance"] == "5000.00"
    assert later["receipts"]["items"] == [] and later["closing"]["balance"] == "5000.00"


def test_a_month_opens_with_the_previous_months_closing_balance():
    _, client, headers = signed_user()
    cash = account_id(client, headers, "Cash")
    receipt(client, headers, cash, 9000, "2026-01-30")
    expense(client, headers, cash, 2000, "2026-01-31")
    january = statement(client, headers, cash, "month", "2026-01-15")
    february = statement(client, headers, cash, "month", "2026-02-10")
    assert january["closing"]["balance"] == "7000.00"
    assert february["opening"]["balance"] == "7000.00"


# --- the starting balance ----------------------------------------------------------------------

def test_a_starting_balance_is_counted_once_from_its_date():
    _, client, headers = signed_user()
    bank = client.post("/api/accounts", json={"name": "Bank", "opening_balance": "1000", "opening_date": "2026-01-01"}, headers=headers).json()["account"]["id"]
    jan = statement(client, headers, bank, "month", "2026-01-10")
    feb = statement(client, headers, bank, "month", "2026-02-10")
    assert jan["opening"]["balance"] == "1000.00" and jan["opening"]["starting_balance_in_period"] == "1000.00"
    assert feb["opening"]["balance"] == "1000.00" and feb["opening"]["starting_balance_in_period"] == "0.00"


def test_a_period_before_the_starting_balance_date_shows_nothing_from_it():
    _, client, headers = signed_user()
    bank = client.post("/api/accounts", json={"name": "Bank", "opening_balance": "1000", "opening_date": "2026-03-01"}, headers=headers).json()["account"]["id"]
    assert statement(client, headers, bank, "month", "2026-02-10")["closing"]["balance"] == "0.00"
    assert statement(client, headers, bank, "month", "2026-03-10")["opening"]["balance"] == "1000.00"


# --- negative balances -------------------------------------------------------------------------

def test_a_negative_closing_balance_is_kept_and_reported_as_overspent():
    _, client, headers = signed_user()
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": "2026-01-12"}, headers=headers).json()["account"]["id"]
    receipt(client, headers, petty, 10000, "2026-01-12")
    expense(client, headers, petty, 15000, "2026-01-13")
    week = statement(client, headers, petty, "week", "2026-01-14")
    assert week["closing"]["balance"] == "-5000.00"
    assert week["closing"]["overspent"] == "5000.00"


# --- drill-down --------------------------------------------------------------------------------

def test_each_line_names_its_source_and_a_transfer_names_the_other_account():
    _, client, headers = signed_user()
    cash = account_id(client, headers, "Cash")
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": "2026-01-12"}, headers=headers).json()["account"]["id"]
    body = {"amount": 3000, "kind": "Transfer", "description": "Top up", "entry_date": "2026-01-13", "account_id": petty, "from_account_id": cash}
    assert client.post("/api/money-in", json=body, headers=headers).status_code == 201
    expense(client, headers, petty, 500, "2026-01-14", "Taxi")
    week = statement(client, headers, petty, "week", "2026-01-14")
    transfer_in = week["receipts"]["items"][0]
    assert transfer_in["source"] == "transfer_in" and transfer_in["counterpart"] == "Cash" and transfer_in["amount"] == "3000.00"
    expense_line = week["payments"]["items"][0]
    assert expense_line["source"] == "expense" and expense_line["label"] == "Others · Taxi"
    assert week["closing"]["balance"] == "2500.00"


def test_closing_agrees_with_the_ledger_balance_at_the_end_of_the_period():
    user_id, client, headers = signed_user()
    cash = account_id(client, headers, "Cash")
    receipt(client, headers, cash, 4000, "2026-01-20")
    expense(client, headers, cash, 1500, "2026-01-22")
    month = statement(client, headers, cash, "month", "2026-01-31")
    with get_db() as db:
        row = db.execute("SELECT * FROM accounts WHERE id = ?", (cash,)).fetchone()
        assert ledger.balance_on(db, user_id, row, "2026-01-31") == 250000
    assert month["closing"]["balance"] == "2500.00"


# --- access ------------------------------------------------------------------------------------

def test_a_statement_for_another_businesss_account_is_not_found_and_bad_input_is_refused():
    _, client_a, headers_a = signed_user()
    _, client_b, headers_b = signed_user()
    cash_a = account_id(client_a, headers_a, "Cash")
    assert client_b.get(f"/api/accounts/{cash_a}/statement?period=week&date=2026-01-14", headers=headers_b).status_code == 404
    cash_b = account_id(client_b, headers_b, "Cash")
    assert client_b.get(f"/api/accounts/{cash_b}/statement?period=year&date=2026-01-14", headers=headers_b).status_code == 400
    assert client_b.get(f"/api/accounts/{cash_b}/statement?period=week&date=14-01-2026", headers=headers_b).status_code == 400


def test_the_petty_cash_week_is_shown_on_the_accounts_page_route_too():
    _, client, headers = signed_user()
    assert client.get("/accounts", headers=headers).status_code == 200


# --- dashboard -------------------------------------------------------------------------------------

def dashboard(client, headers, month):
    response = client.get(f"/api/dashboard?month={month}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_net_cash_movement_is_payments_received_plus_money_in_less_expenses_for_the_month():
    _, client, headers = signed_user()
    cash = account_id(client, headers, "Cash")
    body = {"description": "Rice", "total_value": 2000, "amount_paid": 500, "customer_name": "Ada",
            "payment_mode": "Cash", "entry_date": "2026-01-05"}
    assert client.post("/api/income", json=body, headers=headers).status_code in (200, 201)
    receipt(client, headers, cash, 1000, "2026-01-06")
    expense(client, headers, cash, 300, "2026-01-07")
    cash_figures = dashboard(client, headers, "2026-01")["cash"]
    assert cash_figures["payments_received"] == 500.0
    assert cash_figures["net_cash_movement"] == 500 + 1000 - 300
    assert cash_figures["cash_balance"] == cash_figures["net_cash_movement"]


def test_a_later_partial_payment_counts_in_the_month_it_was_made():
    _, client, headers = signed_user()
    body = {"description": "Rice", "total_value": 2000, "amount_paid": 500, "customer_name": "Ada",
            "payment_mode": "Cash", "entry_date": "2026-01-05"}
    income_id = client.post("/api/income", json=body, headers=headers)
    assert income_id.status_code in (200, 201)
    with get_db() as db:
        sale_id = db.execute("SELECT MAX(id) AS id FROM income").fetchone()["id"]
    assert client.post(f"/update_payment/{sale_id}", json={"payment_amount": "700", "payment_date": "2026-02-03"}, headers=headers).status_code == 200
    assert dashboard(client, headers, "2026-01")["cash"]["payments_received"] == 500.0
    assert dashboard(client, headers, "2026-02")["cash"]["payments_received"] == 700.0
    assert "2026-02" in dashboard(client, headers, "2026-02")["months_with_data"]


def test_transfers_leave_the_net_cash_movement_and_profit_unchanged():
    _, client, headers = signed_user()
    cash = account_id(client, headers, "Cash")
    petty = client.post("/api/accounts", json={"name": "Petty Cash"}, headers=headers).json()["account"]["id"]
    body = {"amount": 3000, "kind": "Transfer", "description": "Top up", "entry_date": "2026-01-13", "account_id": petty, "from_account_id": cash}
    assert client.post("/api/money-in", json=body, headers=headers).status_code == 201
    figures = dashboard(client, headers, "2026-01")
    assert figures["cash"]["money_in"] == 0 and figures["cash"]["net_cash_movement"] == 0
    assert figures["net_profit"] == 0 and figures["month_net"] == 0


def test_each_active_account_other_than_the_default_has_a_balance_as_of_the_month_end():
    _, client, headers = signed_user()
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": "2026-01-01"}, headers=headers).json()["account"]["id"]
    old = client.post("/api/accounts", json={"name": "Old till"}, headers=headers).json()["account"]["id"]
    client.put(f"/api/accounts/{old}", json={"archived": True}, headers=headers)
    receipt(client, headers, petty, 2000, "2026-01-20")
    receipt(client, headers, petty, 5000, "2026-02-02")
    jan = dashboard(client, headers, "2026-01")["account_balances"]
    assert [(b["name"], b["balance_text"], b["as_of"]) for b in jan] == [("Petty Cash", "2000.00", "2026-01-31")]
    feb = dashboard(client, headers, "2026-02")["account_balances"]
    assert feb[0]["balance_text"] == "7000.00"
