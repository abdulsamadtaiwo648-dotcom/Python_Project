"""Dashboard month totals use the business date, not the time an entry was saved. Money in is
never counted as income or profit."""

from datetime import datetime, timedelta, timezone

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return client, {"X-CSRFToken": token}


def first_of_this_month():
    return datetime.now(timezone.utc).date().replace(day=1)


def last_of_last_month():
    return first_of_this_month() - timedelta(days=1)


def dashboard(client):
    """This month's figures, asked for explicitly (the default may show an earlier month)."""
    current = datetime.now(timezone.utc).strftime("%Y-%m")
    response = client.get(f"/api/dashboard?month={current}")
    assert response.status_code == 200, response.text
    return response.json()


def test_an_expense_saved_today_for_last_month_is_not_in_this_months_total():
    client, headers = signed_user()
    body = {"amount": 900, "category": "Others", "description": "Late receipt", "entry_date": last_of_last_month().isoformat()}
    assert client.post("/add", json=body, headers=headers).status_code in (200, 201)
    data = dashboard(client)
    assert data["month_expenses"] == 0
    assert data["total_expenses"] == 900  # all-time totals still count it


def test_an_expense_dated_this_month_counts_this_month_even_if_saved_later():
    client, headers = signed_user()
    body = {"amount": 450, "category": "Others", "description": "Earlier this month",
            "entry_date": first_of_this_month().isoformat()}
    assert client.post("/add", json=body, headers=headers).status_code in (200, 201)
    assert dashboard(client)["month_expenses"] == 450


def test_todays_expense_counts_as_todays_spending():
    client, headers = signed_user()
    today = datetime.now(timezone.utc).date().isoformat()
    client.post("/add", json={"amount": 300, "category": "Others", "description": "Today", "entry_date": today}, headers=headers)
    assert dashboard(client)["today_expenses"] == 300


def test_a_sale_dated_last_month_is_not_in_this_months_income():
    client, headers = signed_user()
    body = {"description": "Old sale", "total_value": 5000, "amount_paid": 5000, "customer_name": "Ada",
            "payment_mode": "Cash", "entry_date": last_of_last_month().isoformat()}
    assert client.post("/api/income", json=body, headers=headers).status_code in (200, 201)
    data = dashboard(client)
    assert data["month_income"] == 0
    assert data["total_sales"] == 5000


def test_money_in_is_not_income_or_profit():
    client, headers = signed_user()
    body = {"amount": 40000, "kind": "Owner contribution", "description": "Put in", "entry_date": first_of_this_month().isoformat()}
    assert client.post("/api/money-in", json=body, headers=headers).status_code == 201
    data = dashboard(client)
    assert data["month_income"] == 0
    assert data["total_sales"] == 0
    assert data["net_profit"] == 0
    assert data["month_net"] == 0


def test_a_month_with_more_spent_than_earned_is_a_loss():
    client, headers = signed_user()
    today = datetime.now(timezone.utc).date().isoformat()
    client.post("/api/income", json={"description": "Small sale", "total_value": 1000, "amount_paid": 1000,
                                     "customer_name": "Ada", "payment_mode": "Cash", "entry_date": today}, headers=headers)
    client.post("/add", json={"amount": 2500, "category": "Others", "description": "Restock", "entry_date": today}, headers=headers)
    data = dashboard(client)
    assert data["month_net"] == -1500
    assert data["month_net"] < 0
