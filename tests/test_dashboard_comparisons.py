"""Comparison notes under the dashboard figures: zero-aware wording, percentages only when both
months have a value, and a net loss shown as a loss when no income came in."""

import calendar
from datetime import datetime, timedelta, timezone

from api.routers.dashboard import compare_note, margin_note, shift_month

from .conftest import new_client, sign_in, make_user

NOV, OCT = "2026-11", "2026-10"


def note(current, previous, noun="income", selected=NOV, prev=OCT, cur=NOV):
    return compare_note(current, previous, noun, selected, prev, cur)


def test_a_zero_this_month_with_something_last_month_says_nothing_recorded_yet():
    assert note(0, 5000) == "Nothing recorded yet this month (₦5,000 last month)"


def test_a_zero_past_month_names_the_month_it_is_about():
    assert note(0, 5000, selected=OCT, prev="2026-09") == "Nothing recorded in October 2026 (₦5,000 in September)"


def test_nothing_in_either_month_says_nothing_recorded_yet():
    assert note(0, 0) == "Nothing recorded yet this month"
    assert note(0, 0, selected=OCT, prev="2026-09") == "Nothing recorded in October 2026"


def test_a_rise_shows_an_up_arrow_and_the_previous_month_name():
    assert note(11200, 10000) == "▲ 12% vs October"


def test_a_fall_shows_a_down_arrow():
    assert note(9200, 10000) == "▼ 8% vs October"


def test_no_change_is_said_plainly():
    assert note(10000, 10000) == "No change vs October"


def test_no_percentage_when_last_month_had_nothing():
    assert note(8000, 0) == "No income in October to compare"
    assert note(8000, 0, noun="expenses") == "No expenses in October to compare"


def test_percentages_use_the_name_of_the_month_before_the_shown_one():
    assert note(12000, 10000, selected="2026-01", prev="2025-12", cur="2026-01") == "▲ 20% vs December"


def test_a_loss_with_no_income_is_a_net_loss_not_a_zero_margin():
    assert margin_note(0, 800, -800) == "No income recorded"


def test_a_loss_with_some_income_says_spending_is_above_income():
    assert margin_note(500, 800, -300) == "Spending is above income"


def test_no_income_and_no_spending_is_not_a_loss():
    assert margin_note(0, 0, 0) == "No income yet"


def test_a_profit_shows_its_margin():
    assert margin_note(1000, 400, 600) == "60% margin"


# --- through the endpoint ---------------------------------------------------------------------

def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return client, {"X-CSRFToken": token}


def month_of(d):
    return d.strftime("%Y-%m")


def utc_today():
    return datetime.now(timezone.utc).date()


def last_month_name():
    return calendar.month_name[int(shift_month(month_of(utc_today()), -1)[5:7])]


def sale(client, headers, day, amount):
    body = {"description": "Rice", "total_value": amount, "amount_paid": amount, "customer_name": "Ada",
            "payment_mode": "Cash", "entry_date": day}
    assert client.post("/api/income", json=body, headers=headers).status_code in (200, 201)


def expense(client, headers, day, amount):
    body = {"amount": amount, "category": "Others", "description": "Test", "entry_date": day}
    assert client.post("/add", json=body, headers=headers).status_code in (200, 201)


def dashboard(client, month):
    response = client.get(f"/api/dashboard?month={month}")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_endpoint_says_nothing_recorded_when_this_month_is_empty_but_last_month_was_not():
    client, headers = signed_user()
    last_day = (utc_today().replace(day=1) - timedelta(days=1)).isoformat()
    sale(client, headers, last_day, 5000)
    data = dashboard(client, month_of(utc_today()))
    assert data["income_note"] == "Nothing recorded yet this month (₦5,000 last month)"


def test_the_endpoint_shows_a_percentage_only_when_both_months_have_sales():
    client, headers = signed_user()
    last_day = (utc_today().replace(day=1) - timedelta(days=1)).isoformat()
    sale(client, headers, last_day, 10000)
    sale(client, headers, utc_today().isoformat(), 11200)
    data = dashboard(client, month_of(utc_today()))
    assert data["income_note"] == f"▲ 12% vs {last_month_name()}"


def test_the_endpoint_says_no_income_to_compare_when_last_month_had_none():
    client, headers = signed_user()
    sale(client, headers, utc_today().isoformat(), 8000)
    data = dashboard(client, month_of(utc_today()))
    assert data["income_note"] == f"No income in {last_month_name()} to compare"


def test_expenses_with_no_income_show_a_net_loss():
    client, headers = signed_user()
    expense(client, headers, utc_today().isoformat(), 800)
    data = dashboard(client, month_of(utc_today()))
    assert data["month_income"] == 0
    assert data["month_net"] == -800
    assert data["net_note"] == "No income recorded"
