"""Per-product low-stock alert levels."""

import pytest


@pytest.fixture
def headers(signed_in):
    return {"X-CSRFToken": signed_in[1]}


def _add(client, headers, **fields):
    payload = {"item_name": "Jogger", "price": 3000, "stock": 10}
    payload.update(fields)
    return client.post("/api/inventory-presets", json=payload, headers=headers)


def test_alert_level_defaults_to_three(client, headers):
    preset = _add(client, headers).get_json()["preset"]
    assert preset["low_stock_threshold"] == 3
    listed = client.get("/api/inventory-presets").get_json()["presets"][0]
    assert listed["low_stock_threshold"] == 3


def test_alert_level_can_be_set_and_edited(client, headers):
    preset = _add(client, headers, low_stock_threshold=8).get_json()["preset"]
    assert preset["low_stock_threshold"] == 8
    url = f"/api/inventory-presets/{preset['id']}"

    kept = client.put(url, json={"item_name": "Jogger", "price": 3000, "stock": 10}, headers=headers)
    assert kept.get_json()["preset"]["low_stock_threshold"] == 8

    changed = client.put(url, json={"low_stock_threshold": 0}, headers=headers)
    assert changed.get_json()["preset"]["low_stock_threshold"] == 0


@pytest.mark.parametrize("value", [-1, 2.5, "lots", 10001])
def test_invalid_alert_level_is_rejected(client, headers, value):
    assert _add(client, headers, low_stock_threshold=value).status_code == 400


def _dashboard(client):
    return client.get("/dashboard").get_data(as_text=True)


def test_dashboard_uses_each_products_alert_level(client, headers):
    _add(client, headers, item_name="Fine Cap", stock=5, low_stock_threshold=3)
    _add(client, headers, item_name="Low Jogger", stock=5, low_stock_threshold=5)
    page = _dashboard(client)
    assert "Low Jogger (5)" in page
    assert "Fine Cap (5)" not in page
    assert 'data-low-stock-badge class="ml-auto' in page  # badge visible


def test_sale_that_crosses_alert_level_shows_on_dashboard(client, headers):
    preset = _add(client, headers, stock=6, low_stock_threshold=3).get_json()["preset"]
    assert f"{preset['item_name']} (" not in _dashboard(client)
    client.post(
        "/api/checkout",
        json={"checkout_id": "low-1", "amount_paid": 0, "items": [{"inventory_item_id": preset["id"], "quantity": 4}]},
        headers=headers,
    )
    assert "Jogger (2)" in _dashboard(client)


def test_no_badge_when_stock_is_healthy(client, headers):
    _add(client, headers, stock=50)
    assert 'data-low-stock-badge class="hidden ml-auto' in _dashboard(client)
