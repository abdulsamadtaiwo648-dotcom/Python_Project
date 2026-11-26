"""The cash card: sales collected, money in, expenses, profit and cash balance for the month shown.
Money in is cash, so it changes the balance but never the profit."""

from datetime import datetime, timedelta, timezone

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return client, {"X-CSRFToken": token}


def today():
    return datetime.now(timezone.utc).date()


def this_month():
    return today().strftime("%Y-%m")


def cash_for(client, month):
    response = client.get(f"/api/dashboard?month={month}")
    assert response.status_code == 200, response.text
    return response.json()["cash"]


def sale(client, headers, day, paid):
    body = {"description": "Rice", "total_value": paid, "amount_paid": paid, "customer_name": "Ada",
            "payment_mode": "Cash", "entry_date": day}
    assert client.post("/api/income", json=body, headers=headers).status_code in (200, 201)


def expense(client, headers, day, amount):
    body = {"amount": amount, "category": "Others", "description": "Test", "entry_date": day}
    assert client.post("/add", json=body, headers=headers).status_code in (200, 201)


def money_in(client, headers, day, amount):
    body = {"amount": amount, "kind": "Owner contribution", "description": "In", "entry_date": day}
    assert client.post("/api/money-in", json=body, headers=headers).status_code == 201


def test_the_cash_card_adds_up_sales_money_in_and_expenses():
    client, headers = signed_user()
    day = today().isoformat()
    sale(client, headers, day, 10000)
    money_in(client, headers, day, 4000)
    expense(client, headers, day, 3000)
    cash = cash_for(client, this_month())
    assert cash["sales_collected"] == 10000
    assert cash["money_in"] == 4000
    assert cash["expenses"] == 3000
    assert cash["profit"] == 7000
    assert cash["cash_balance"] == 11000


def test_money_in_changes_the_balance_but_not_the_profit():
    client, headers = signed_user()
    money_in(client, headers, today().isoformat(), 50000)
    cash = cash_for(client, this_month())
    assert cash["profit"] == 0
    assert cash["cash_balance"] == 50000


def test_spending_more_than_is_collected_leaves_a_negative_balance():
    client, headers = signed_user()
    expense(client, headers, today().isoformat(), 900)
    cash = cash_for(client, this_month())
    assert cash["profit"] == -900
    assert cash["cash_balance"] == -900


def test_the_cash_card_follows_the_month_chosen():
    client, headers = signed_user()
    last_day = (today().replace(day=1) - timedelta(days=1)).isoformat()
    money_in(client, headers, last_day, 2000)
    sale(client, headers, today().isoformat(), 500)
    assert cash_for(client, this_month())["money_in"] == 0
    last = cash_for(client, last_day[:7])
    assert last["money_in"] == 2000
    assert last["sales_collected"] == 0
    assert last["cash_balance"] == 2000
