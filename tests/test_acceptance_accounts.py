"""Acceptance for accounts, through the HTTP API only (the way the app uses it).

The January figures are made up: Petty Cash receives 355,000 and pays 352,580 in the week of Monday
12 to Saturday 17 January 2026, closing at 2,420 (which is next week's opening). Direct Pay of 256,680
is paid from another account and must not affect Petty Cash."""

from datetime import date, timedelta

from server.database import get_db

from .conftest import new_client, sign_in, make_user

WEEK = "2026-01-14"          # any day of Monday 12 – Sunday 18 January
NEXT_WEEK = "2026-01-21"
FEB = "2026-02-10"


def signed_user(test=False):
    user_id, email = make_user()
    if test:
        with get_db() as db:
            db.execute("UPDATE users SET is_test_account = 1 WHERE id = ?", (user_id,))
            db.commit()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return user_id, client, {"X-CSRFToken": token}


def ids(client, headers):
    return {a["name"]: a["id"] for a in client.get("/api/accounts", headers=headers).json()["accounts"]}


def statement(client, headers, account, period, day):
    response = client.get(f"/api/accounts/{account}/statement?period={period}&date={day}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def dashboard(client, headers, month):
    response = client.get(f"/api/dashboard?month={month}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def build_january(client, headers):
    """Petty Cash and Bank, with the week of 12–17 January. Returns the account ids."""
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": "2026-01-12"}, headers=headers).json()["account"]["id"]
    bank = client.post("/api/accounts", json={"name": "Bank"}, headers=headers).json()["account"]["id"]
    for amount, day, text in ((120000, "2026-01-12", "Float from owner"), (135000, "2026-01-14", "Float top-up"),
                              (100000, "2026-01-16", "Float top-up")):
        body = {"amount": amount, "kind": "Owner contribution", "description": text, "entry_date": day, "account_id": petty}
        assert client.post("/api/money-in", json=body, headers=headers).status_code == 201
    for amount, day, text, account in ((150000, "2026-01-12", "Market run", petty), (80580, "2026-01-13", "Small supplies", petty),
                                       (122000, "2026-01-15", "Transport", petty), (100000, "2026-01-13", "Direct pay supplier", bank),
                                       (156680, "2026-01-14", "Direct pay delivery", bank)):
        body = {"amount": amount, "category": "Others", "description": text, "entry_date": day, "account_id": account}
        assert client.post("/add", json=body, headers=headers).status_code == 201
    return petty, bank


# --- the reconciliation --------------------------------------------------------------------------

def test_petty_cash_starts_at_zero():
    _, client, headers = signed_user()
    petty, _ = build_january(client, headers)
    before = statement(client, headers, petty, "week", "2026-01-05")
    assert before["opening"]["balance"] == "0.00" and before["closing"]["balance"] == "0.00"


def test_the_week_has_355000_received_and_352580_paid():
    _, client, headers = signed_user()
    petty, _ = build_january(client, headers)
    week = statement(client, headers, petty, "week", WEEK)
    assert week["period"]["start"] == "2026-01-12" and week["period"]["end"] == "2026-01-18"
    assert week["receipts"]["total"] == "355000.00"
    assert week["payments"]["total"] == "352580.00"


def test_closing_is_2420_and_next_weeks_opening_is_the_same_with_no_new_receipt():
    _, client, headers = signed_user()
    petty, _ = build_january(client, headers)
    assert statement(client, headers, petty, "week", WEEK)["closing"]["balance"] == "2420.00"
    following = statement(client, headers, petty, "week", NEXT_WEEK)
    assert following["opening"]["balance"] == "2420.00"
    assert following["receipts"]["items"] == []


def test_direct_pay_stays_in_business_expenses_and_does_not_touch_petty_cash():
    _, client, headers = signed_user()
    petty, bank = build_january(client, headers)
    expenses = client.get("/api/expenses", headers=headers).json()["expenses"]
    direct = [e for e in expenses if e["description"].startswith("Direct pay")]
    assert sum(e["amount"] for e in direct) == 256680
    assert statement(client, headers, petty, "week", WEEK)["payments"]["total"] == "352580.00"
    assert statement(client, headers, bank, "week", WEEK)["payments"]["total"] == "256680.00"


# --- transfers -----------------------------------------------------------------------------------

def test_a_transfer_moves_both_balances_and_leaves_business_totals_unchanged():
    _, client, headers = signed_user()
    cash = ids(client, headers)["Cash"]
    petty = client.post("/api/accounts", json={"name": "Petty Cash"}, headers=headers).json()["account"]["id"]
    before = dashboard(client, headers, "2026-01")
    before_money_in = client.get("/api/money-in", headers=headers).json()["money_in"]
    body = {"amount": 5000, "kind": "Transfer", "description": "Top up", "entry_date": "2026-01-13",
            "account_id": petty, "from_account_id": cash}
    assert client.post("/api/money-in", json=body, headers=headers).status_code == 201
    after = dashboard(client, headers, "2026-01")
    assert client.get("/api/money-in", headers=headers).json()["money_in"] == before_money_in
    assert after["month_income"] == before["month_income"]
    assert after["month_expenses"] == before["month_expenses"]
    assert after["net_profit"] == before["net_profit"] and after["month_net"] == before["month_net"]
    assert after["cash"]["money_in"] == before["cash"]["money_in"]
    assert statement(client, headers, petty, "week", WEEK)["receipts"]["total"] == "5000.00"
    assert statement(client, headers, cash, "week", WEEK)["payments"]["total"] == "5000.00"


# --- carrying balances ----------------------------------------------------------------------------

def test_balances_carry_across_empty_weeks_and_into_the_next_month():
    _, client, headers = signed_user()
    petty, _ = build_january(client, headers)
    feb = statement(client, headers, petty, "month", FEB)
    assert feb["opening"]["balance"] == "2420.00"
    assert feb["receipts"]["items"] == [] and feb["payments"]["items"] == []
    assert statement(client, headers, petty, "week", "2026-02-23")["opening"]["balance"] == "2420.00"


# --- negative balances ----------------------------------------------------------------------------

def test_a_negative_balance_is_kept_and_reported_as_overspent():
    _, client, headers = signed_user()
    petty = client.post("/api/accounts", json={"name": "Petty Cash", "opening_date": "2026-01-12"}, headers=headers).json()["account"]["id"]
    client.post("/add", json={"amount": 300, "category": "Others", "description": "Over", "entry_date": "2026-01-13", "account_id": petty}, headers=headers)
    week = statement(client, headers, petty, "week", WEEK)
    assert week["closing"]["balance"] == "-300.00" and week["closing"]["overspent"] == "300.00"


# --- sales -----------------------------------------------------------------------------------------

def test_sale_collections_and_partial_payments_count_once_and_unpaid_amounts_do_not():
    _, client, headers = signed_user()
    cash = ids(client, headers)["Cash"]
    paid = client.post("/api/income", json={"description": "Rice", "total_value": 2000, "amount_paid": 500,
                                            "customer_name": "Ada", "payment_mode": "Cash", "entry_date": "2026-01-13"}, headers=headers)
    assert paid.status_code in (200, 201)
    client.post("/api/income", json={"description": "Unpaid", "total_value": 1000, "amount_paid": 0,
                                     "customer_name": "Ben", "payment_mode": "Cash", "entry_date": "2026-01-13"}, headers=headers)
    with get_db() as db:
        rice = db.execute("SELECT MAX(id) AS id FROM income WHERE description = 'Rice'").fetchone()["id"]
    client.post(f"/update_payment/{rice}", json={"payment_amount": "700", "payment_date": "2026-01-15"}, headers=headers)
    week = statement(client, headers, cash, "week", WEEK)
    assert week["receipts"]["total"] == "1200.00"
    assert [i["amount"] for i in week["receipts"]["items"]] == ["500.00", "700.00"]


# --- expenses, filters and drill-downs -------------------------------------------------------------

def test_moving_an_expense_and_filtering_agree_with_the_account_statements():
    _, client, headers = signed_user()
    petty, bank = build_january(client, headers)
    expense_id = next(e["server_id"] for e in client.get("/api/expenses", headers=headers).json()["expenses"]
                      if e["description"] == "Transport")
    body = {"amount": 122000, "category": "Others", "description": "Transport", "account_id": bank}
    assert client.put(f"/api/expenses/{expense_id}", json=body, headers=headers).status_code == 200
    petty_rows = client.get(f"/api/expenses?account_id={petty}", headers=headers).json()["expenses"]
    assert sum(e["amount"] for e in petty_rows) == 230580
    week = statement(client, headers, petty, "week", WEEK)
    assert week["payments"]["total"] == "230580.00"
    assert week["closing"]["balance"] == "124420.00"  # 355,000 received - 230,580 still paid


# --- CSV import --------------------------------------------------------------------------------------

def test_csv_preview_flags_unknown_accounts_and_repeats_and_undo_touches_only_its_batch():
    user_id, client, headers = signed_user()
    build_january(client, headers)
    keep = client.post("/api/import/commit", json={
        "kind": "expenses", "batch_key": "other", "rows": [{"date": "2026-01-13", "amount": "10", "category": "Others", "description": "Kept"}]},
        headers=headers).json()
    rows = [
        {"date": "2026-01-13", "amount": "10", "category": "Others", "description": "Kept"},
        {"date": "2026-01-13", "amount": "20", "category": "Others", "description": "Direct Pay", "paid_from": "Direct Pay"},
    ]
    checked = client.post("/api/import/preview", json={"kind": "expenses", "rows": rows}, headers=headers).json()
    assert checked["rows"][0]["status"] == "duplicate"
    assert checked["rows"][1]["status"] == "error" and "is not on your list" in checked["rows"][1]["reasons"][0]
    result = client.post("/api/import/commit", json={"kind": "expenses", "batch_key": "mine",
                                                     "rows": [{"date": "2026-01-20", "amount": "30", "category": "Others", "description": "Mine"}]},
                         headers=headers).json()
    client.post(f"/api/import-batches/{result['batch_id']}/undo", headers=headers)
    descriptions = [e["description"] for e in client.get("/api/expenses", headers=headers).json()["expenses"]]
    assert "Mine" not in descriptions and "Kept" in descriptions
    assert keep["batch_id"] is not None


# --- single account and other businesses -------------------------------------------------------------

def test_a_single_account_business_records_receipts_and_expenses_and_can_add_another():
    user_id, client, headers = signed_user()
    assert list(ids(client, headers)) == ["Cash"]
    cash = ids(client, headers)["Cash"]
    assert client.post("/add", json={"amount": 500, "category": "Others", "description": "Only", "entry_date": "2026-01-13"}, headers=headers).status_code == 201
    assert client.post("/api/money-in", json={"amount": 900, "kind": "Owner contribution", "description": "In", "entry_date": "2026-01-13"}, headers=headers).status_code == 201
    assert statement(client, headers, cash, "week", WEEK)["closing"]["balance"] == "400.00"
    assert client.post("/api/accounts", json={"name": "Petty Cash"}, headers=headers).status_code == 201


def test_another_business_cannot_read_or_use_these_accounts():
    _, client_a, headers_a = signed_user()
    petty, _ = build_january(client_a, headers_a)
    _, client_b, headers_b = signed_user()
    assert client_b.get(f"/api/accounts/{petty}/statement?period=week&date={WEEK}", headers=headers_b).status_code == 404
    assert client_b.post("/add", json={"amount": 1, "category": "Others", "description": "x", "account_id": petty}, headers=headers_b).status_code == 400


def test_the_test_reset_is_refused_for_a_live_business():
    _, client, headers = signed_user(test=False)
    assert client.post("/api/test-reset", json={"confirm": "DELETE"}, headers=headers).status_code == 403


# --- dashboard, reports and routing ------------------------------------------------------------------

def test_the_month_picker_changes_the_dashboard_and_the_money_in_page_opens_directly():
    _, client, headers = signed_user()
    build_january(client, headers)
    january = dashboard(client, headers, "2026-01")
    february = dashboard(client, headers, "2026-02")
    assert january["selected_month"] == "2026-01" and february["selected_month"] == "2026-02"
    assert january["month_expenses"] != february["month_expenses"]
    assert client.get("/money-in", headers=headers).status_code == 200
    assert client.get("/accounts", headers=headers).status_code == 200
