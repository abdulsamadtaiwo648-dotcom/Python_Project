"""Business dates: the day a sale or expense belongs to, kept apart from the save time."""

from datetime import datetime, timedelta, timezone

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


def expense_body(entry_date=None, amount=20):
    body = {"amount": amount, "category": "Delivery & Logistics", "description": "Okada to market"}
    if entry_date is not None:
        body["entry_date"] = entry_date
    return body


def expense_rows(user_id):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT entry_date, entered_at, date FROM expenses WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()]


def expense_id_for(user_id):
    with get_db() as db:
        return db.execute("SELECT id FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()["id"]


def income_rows(user_id):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT entry_date, entered_at, date FROM income WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()]


def test_an_expense_can_be_recorded_for_a_past_day():
    user_id, client, headers = signed_user()
    past = (today() - timedelta(days=5)).isoformat()
    response = client.post("/add", json=expense_body(past), headers=headers)
    assert response.status_code in (200, 201), response.text
    row = expense_rows(user_id)[0]
    assert row["entry_date"] == past
    assert row["date"].startswith(past)
    assert row["entered_at"]  # the real save time is kept separately


def test_a_date_left_out_means_today():
    user_id, client, headers = signed_user()
    assert client.post("/add", json=expense_body(), headers=headers).status_code in (200, 201)
    assert expense_rows(user_id)[0]["entry_date"] == today().isoformat()


def test_a_date_beyond_one_day_ahead_is_refused_and_nothing_is_saved():
    user_id, client, headers = signed_user()
    future = (today() + timedelta(days=3)).isoformat()
    response = client.post("/add", json=expense_body(future), headers=headers)
    assert response.status_code == 400
    assert "future" in response.json()["message"]
    assert expense_rows(user_id) == []


def test_a_date_more_than_two_years_back_is_refused():
    user_id, client, headers = signed_user()
    old = (today() - timedelta(days=800)).isoformat()
    response = client.post("/add", json=expense_body(old), headers=headers)
    assert response.status_code == 400
    assert "two years" in response.json()["message"]
    assert expense_rows(user_id) == []


def test_a_malformed_date_is_refused():
    user_id, client, headers = signed_user()
    for bad in ["yesterday", "2026-13-40", "<script>", "25/11/2026"]:
        response = client.post("/add", json=expense_body(bad), headers=headers)
        assert response.status_code == 400, bad
    assert expense_rows(user_id) == []


def test_editing_an_expense_can_change_its_date():
    user_id, client, headers = signed_user()
    client.post("/add", json=expense_body(today().isoformat()), headers=headers)
    expense_id = expense_id_for(user_id)
    new_day = (today() - timedelta(days=12)).isoformat()
    body = expense_body(new_day, amount=35)
    response = client.put(f"/api/expenses/{expense_id}", json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["expense"]["entry_date"] == new_day
    assert expense_rows(user_id)[0]["entry_date"] == new_day


def test_editing_without_a_date_keeps_the_business_date():
    user_id, client, headers = signed_user()
    kept = (today() - timedelta(days=7)).isoformat()
    client.post("/add", json=expense_body(kept), headers=headers)
    expense_id = expense_id_for(user_id)
    response = client.put(f"/api/expenses/{expense_id}", json=expense_body(None, amount=44), headers=headers)
    assert response.status_code == 200, response.text
    assert expense_rows(user_id)[0]["entry_date"] == kept


def test_a_sale_can_be_recorded_for_a_past_day():
    user_id, client, headers = signed_user()
    past = (today() - timedelta(days=3)).isoformat()
    body = {"description": "Rice 5kg", "total_value": 9000, "amount_paid": 9000, "customer_name": "Ada",
            "payment_mode": "Cash", "entry_date": past}
    response = client.post("/api/income", json=body, headers=headers)
    assert response.status_code in (200, 201), response.text
    row = income_rows(user_id)[0]
    assert row["entry_date"] == past
    assert row["entered_at"]


def test_a_sale_with_a_future_date_is_refused():
    user_id, client, headers = signed_user()
    body = {"description": "Rice", "total_value": 100, "amount_paid": 100, "customer_name": "Ada",
            "payment_mode": "Cash", "entry_date": (today() + timedelta(days=4)).isoformat()}
    response = client.post("/api/income", json=body, headers=headers)
    assert response.status_code == 400
    assert income_rows(user_id) == []


def test_an_offline_sale_synced_later_keeps_the_day_it_was_made():
    user_id, client, headers = signed_user()
    made_on = (today() - timedelta(days=2)).isoformat()
    sale = {"description": "Soap", "total_value": 500, "amount_paid": 500, "customer_name": "Walk-in Customer",
            "payment_mode": "Cash", "receipt_id": "OFF-1", "entry_date": made_on}
    response = client.post("/api/sync-sales", json={"sales": [sale]}, headers=headers)
    assert response.status_code == 200, response.text
    row = income_rows(user_id)[0]
    assert row["entry_date"] == made_on
    assert row["date"].startswith(made_on)


def test_an_offline_sale_with_a_bad_date_is_kept_and_dated_today():
    user_id, client, headers = signed_user()
    sale = {"description": "Soap", "total_value": 500, "amount_paid": 500, "customer_name": "Walk-in Customer",
            "payment_mode": "Cash", "receipt_id": "OFF-2", "entry_date": "2099-01-01"}
    client.post("/api/sync-sales", json={"sales": [sale]}, headers=headers)
    rows = income_rows(user_id)
    assert len(rows) == 1  # never dropped
    assert rows[0]["entry_date"] == today().isoformat()
