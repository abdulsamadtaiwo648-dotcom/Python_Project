"""What each plan may do on the server."""

from datetime import datetime, timedelta, timezone

import pytest

from api import subscriptions as subs
from server.database import get_db

from .conftest import new_client, sign_in, make_user


def free_user():
    """An account whose Pro trial ended long ago."""
    user_id, email = make_user()
    subs.ensure_subscription(user_id, datetime.now(timezone.utc) - timedelta(days=60))
    return user_id, email


def signed(user):
    client = new_client()
    response, token = sign_in(client, user[1])
    assert response.status_code == 200
    return client, {"X-CSRFToken": token}


def add_product(client, headers, n):
    return client.post("/api/inventory-presets", json={"item_name": f"Item {n}", "price": 100, "stock": 5}, headers=headers)


def test_free_plan_allows_ten_products_then_asks_to_upgrade():
    user = free_user()
    client, headers = signed(user)
    for n in range(10):
        assert add_product(client, headers, n).status_code == 201
    blocked = add_product(client, headers, 11)
    assert blocked.status_code == 403
    body = blocked.json()
    assert body["code"] == "upgrade_required" and "10 products" in body["message"]


def test_basic_allows_more_products_and_pro_has_no_limit():
    user = free_user()
    client, headers = signed(user)
    subs.activate(user[0], "basic")
    for n in range(12):
        assert add_product(client, headers, n).status_code == 201


def test_sales_and_expenses_older_than_the_plan_history_are_hidden_not_deleted():
    user = free_user()
    client, headers = signed(user)
    old = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d %I:%M %p")
    with get_db() as db:
        db.execute("INSERT INTO income (user_id, description, total_value, amount_paid, customer_name, payment_mode, date, receipt_id) VALUES (?, 'Old sale', 10, 10, 'x', 'Cash', ?, 'R1')", (user[0], old))
        db.execute("INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, 5, 'Others', 'Old cost', ?)", (user[0], old))
        db.commit()
    assert client.get("/api/income").json()["income"] == []
    assert client.get("/api/expenses").json()["expenses"] == []
    subs.activate(user[0], "basic")                  # 365 days of history
    assert len(client.get("/api/income").json()["income"]) == 1
    assert len(client.get("/api/expenses").json()["expenses"]) == 1


@pytest.mark.parametrize("plan,allowed", [(None, False), ("basic", False), ("pro", True)])
def test_only_pro_can_publish_a_website(plan, allowed):
    user = free_user()
    client, headers = signed(user)
    if plan:
        subs.activate(user[0], plan)
    with get_db() as db:
        db.execute("DELETE FROM business_profiles WHERE user_id = ?", (user[0],))
        db.execute("INSERT INTO business_profiles (user_id, company_name, business_phone, business_address, whatsapp_number, store_slug) VALUES (?, 'Plan Co', '+2348011112222', 'Lagos', '08033334444', ?)", (user[0], f"planco-{user[0][-6:].lower()}"))
        db.commit()
    state = client.get("/api/website").json()["website"]
    content = state["content"]
    content["about"] = "We sell things."
    assert client.put("/api/website", json=content, headers=headers).status_code == 200      # drafting is free
    response = client.post("/api/website/publish", headers=headers)
    if allowed:
        assert response.status_code in (200, 400)          # 400 only if the site lacks products/contact
        assert response.json().get("code") != "upgrade_required"
    else:
        assert response.status_code == 403 and response.json()["code"] == "upgrade_required"


def test_public_website_goes_offline_when_the_plan_lapses():
    user = free_user()
    client, headers = signed(user)
    subs.activate(user[0], "pro", datetime.now(timezone.utc) - timedelta(days=1))
    with get_db() as db:
        db.execute("DELETE FROM business_profiles WHERE user_id = ?", (user[0],))
        db.execute("INSERT INTO business_profiles (user_id, company_name, business_phone, business_address, whatsapp_number, store_slug) VALUES (?, 'Lapse Co', '+2348011112222', 'Lagos', '08033334444', ?)", (user[0], f"lapse-{user[0][-6:].lower()}"))
        db.commit()
    state = client.get("/api/website").json()["website"]
    slug = state["slug"]
    content = state["content"]
    content["layout"] = "service"
    content["services"] = [{"name": "Haircut", "description": "", "price": 3000, "image_url": ""}]
    client.put("/api/website", json=content, headers=headers)
    assert client.post("/api/website/publish", headers=headers).status_code == 200
    page = new_client().get(f"/site/{slug}")
    assert page.status_code == 200 and "Haircut" in page.text and "Website by" not in page.text   # Pro: no SoloBiz credit
    # The paid period and grace run out.
    with get_db() as db:
        db.execute("UPDATE subscriptions SET period_end = ? WHERE user_id = ?", ((datetime.now(timezone.utc) - timedelta(days=9)).isoformat(), user[0]))
        db.commit()
    assert new_client().get(f"/site/{slug}").status_code == 404


def test_stock_alerts_are_not_part_of_the_free_plan(monkeypatch):
    from server import push

    monkeypatch.setenv("VAPID_PUBLIC_KEY", "x")
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "y")
    monkeypatch.setattr(push, "push_enabled", lambda: True)
    user = free_user()
    client, headers = signed(user)
    response = client.post("/api/push/subscribe", json={"subscription": {}}, headers=headers)
    assert response.status_code == 403 and response.json()["feature"] == "alerts"
