"""The dashboard's month: business dates, no future months, and falling back to the latest month
with data when the current month is empty."""

from datetime import datetime, timedelta, timezone

from api.routers.dashboard import month_label, shift_month

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return client, {"X-CSRFToken": token}


def utc_today():
    return datetime.now(timezone.utc).date()


def this_month():
    return utc_today().strftime("%Y-%m")


def last_month():
    return shift_month(this_month(), -1)


def add_expense(client, headers, day, amount=500):
    body = {"amount": amount, "category": "Others", "description": "Test", "entry_date": day}
    response = client.post("/add", json=body, headers=headers)
    assert response.status_code in (200, 201), response.text


def last_month_day():
    return (utc_today().replace(day=1) - timedelta(days=1)).isoformat()


def dashboard(client, month=None):
    url = "/api/dashboard" if month is None else f"/api/dashboard?month={month}"
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_chosen_month_shows_only_its_own_business_dates():
    client, headers = signed_user()
    add_expense(client, headers, last_month_day(), amount=700)
    data = dashboard(client, last_month())
    assert data["selected_month"] == last_month()
    assert data["month_expenses"] == 700


def test_a_record_saved_today_for_last_month_is_not_in_this_month():
    client, headers = signed_user()
    add_expense(client, headers, last_month_day(), amount=700)
    add_expense(client, headers, utc_today().isoformat(), amount=100)
    assert dashboard(client, this_month())["month_expenses"] == 100
    assert dashboard(client, last_month())["month_expenses"] == 700


def test_a_future_month_cannot_be_chosen():
    client, _ = signed_user()
    next_month = shift_month(this_month(), 1)
    response = client.get(f"/api/dashboard?month={next_month}")
    assert response.status_code == 400
    assert "after this one" in response.json()["message"]


def test_a_badly_formed_month_is_refused():
    client, _ = signed_user()
    for bad in ["2026-13", "2026-00", "November", "2026-1", "2026-11-01", "<script>"]:
        assert client.get(f"/api/dashboard?month={bad}").status_code == 400, bad


def test_an_empty_current_month_falls_back_to_the_latest_month_with_data():
    client, headers = signed_user()
    add_expense(client, headers, last_month_day(), amount=900)
    data = dashboard(client)
    assert data["selected_month"] == last_month()
    assert data["month_expenses"] == 900
    assert data["notice"]["current_month"] == this_month()
    assert data["notice"]["shown_month"] == last_month()
    assert data["notice"]["message"] == (
        f"No records in {month_label(this_month())} yet. Showing {month_label(last_month())}."
    )


def test_a_month_with_data_is_shown_without_a_notice():
    client, headers = signed_user()
    add_expense(client, headers, utc_today().isoformat())
    data = dashboard(client)
    assert data["selected_month"] == this_month()
    assert data["notice"] is None


def test_money_in_alone_counts_as_data_for_the_current_month():
    client, headers = signed_user()
    body = {"amount": 5000, "kind": "Owner's capital", "description": "In", "entry_date": utc_today().isoformat()}
    assert client.post("/api/money-in", json=body, headers=headers).status_code == 201
    data = dashboard(client)
    assert data["selected_month"] == this_month()
    assert data["notice"] is None


def test_a_brand_new_business_shows_the_current_month_with_no_notice():
    client, _ = signed_user()
    data = dashboard(client)
    assert data["selected_month"] == this_month()
    assert data["notice"] is None
    assert data["months_with_data"] == []


def test_months_with_data_lists_past_months_newest_first_and_never_the_future():
    client, headers = signed_user()
    two_back = shift_month(this_month(), -2)
    add_expense(client, headers, two_back + "-10")
    add_expense(client, headers, last_month_day())
    data = dashboard(client)
    assert data["months_with_data"] == [last_month(), two_back]
    assert all(m <= this_month() for m in data["months_with_data"])


def test_the_default_never_moves_to_a_future_month():
    client, headers = signed_user()
    add_expense(client, headers, last_month_day())
    data = dashboard(client)
    assert data["selected_month"] <= this_month()


def test_month_helpers():
    assert shift_month("2026-01", -1) == "2025-12"
    assert shift_month("2026-12", 1) == "2027-01"
    assert month_label("2026-11") == "November 2026"
