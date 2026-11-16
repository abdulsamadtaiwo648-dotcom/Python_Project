"""Optional bulk pricing on inventory products.

A product can have a bundle price (e.g. 5 joggers for 10,000) alongside its
piece price (3,000 each). The bundle price is used only for sale lines the
seller marks as bulk; selling 5 pieces normally still charges 5 x 3,000.
"""

import pytest


@pytest.fixture
def headers(signed_in):
    return {"X-CSRFToken": signed_in[1]}


def _add_jogger(client, headers, **extra):
    payload = {"item_name": "Jogger", "price": 3000, "stock": 20, "bulk_quantity": 5, "bulk_price": 10000}
    payload.update(extra)
    return client.post("/api/inventory-presets", json=payload, headers=headers)


def _checkout(client, headers, checkout_id, items, amount_paid=0):
    return client.post(
        "/api/checkout",
        json={"checkout_id": checkout_id, "amount_paid": amount_paid, "items": items},
        headers=headers,
    )


def test_product_saves_and_returns_bulk_pricing(client, headers):
    created = _add_jogger(client, headers)
    assert created.status_code == 201
    preset = created.get_json()["preset"]
    assert preset["bulk_quantity"] == 5
    assert preset["bulk_price"] == 10000

    listed = client.get("/api/inventory-presets").get_json()["presets"]
    assert listed[0]["bulk_quantity"] == 5
    assert listed[0]["bulk_price"] == 10000


def test_bulk_pricing_is_optional(client, headers):
    preset = client.post(
        "/api/inventory-presets", json={"item_name": "Cap", "price": 1500, "stock": 4}, headers=headers
    ).get_json()["preset"]
    assert preset["bulk_quantity"] is None
    assert preset["bulk_price"] is None


@pytest.mark.parametrize("bulk", [
    {"bulk_quantity": 5},                       # price missing
    {"bulk_price": 10000},                      # quantity missing
    {"bulk_quantity": 1, "bulk_price": 10000},  # a bundle needs 2+ units
    {"bulk_quantity": 2.5, "bulk_price": 100},
    {"bulk_quantity": 5, "bulk_price": -1},
])
def test_invalid_bulk_pricing_is_rejected(client, headers, bulk):
    response = client.post(
        "/api/inventory-presets", json={"item_name": "Bad", "price": 100, "stock": 1, **bulk}, headers=headers
    )
    assert response.status_code == 400


def test_edit_keeps_or_clears_bulk_pricing(client, headers):
    preset = _add_jogger(client, headers).get_json()["preset"]
    url = f"/api/inventory-presets/{preset['id']}"

    kept = client.put(url, json={"item_name": "Jogger", "price": 3200, "stock": 20}, headers=headers)
    assert kept.get_json()["preset"]["bulk_price"] == 10000

    cleared = client.put(
        url, json={"item_name": "Jogger", "price": 3200, "stock": 20, "bulk_quantity": None, "bulk_price": None},
        headers=headers,
    )
    assert cleared.get_json()["preset"]["bulk_quantity"] is None


def test_buying_five_pieces_is_not_a_bulk_sale(client, headers):
    preset = _add_jogger(client, headers).get_json()["preset"]
    result = _checkout(client, headers, "pieces", [{"inventory_item_id": preset["id"], "quantity": 5}])
    assert result.status_code == 201
    line = result.get_json()["items"][0]
    assert line["total_value"] == 15000
    assert line["sale_type"] == "unit"
    assert result.get_json()["stock"][str(preset["id"])] == 15


def test_bulk_and_single_in_one_sale(client, headers):
    """The scenario from the request: 5 joggers at bulk (10,000) + 1 at 3,000."""
    preset = _add_jogger(client, headers).get_json()["preset"]
    result = _checkout(client, headers, "mixed", [
        {"inventory_item_id": preset["id"], "quantity": 1, "sale_type": "bulk", "checkout_line_id": "a"},
        {"inventory_item_id": preset["id"], "quantity": 1, "checkout_line_id": "b"},
    ], amount_paid=13000)
    assert result.status_code == 201
    body = result.get_json()
    bulk, single = body["items"]
    assert bulk["sale_type"] == "bulk"
    assert bulk["bundle_count"] == 1 and bulk["bundle_size"] == 5
    assert bulk["quantity"] == 5
    assert bulk["total_value"] == 10000
    assert single["total_value"] == 3000
    assert body["stock"][str(preset["id"])] == 14

    income = client.get("/api/income").get_json()["income"]
    saved_bulk = next(i for i in income if i["checkout_line_id"] == "a")
    assert saved_bulk["sale_type"] == "bulk"
    assert saved_bulk["bundle_count"] == 1


def test_multiple_bundles_take_all_units_from_stock(client, headers):
    preset = _add_jogger(client, headers).get_json()["preset"]
    result = _checkout(client, headers, "two-bundles", [
        {"inventory_item_id": preset["id"], "quantity": 2, "sale_type": "bulk"},
    ])
    assert result.get_json()["items"][0]["total_value"] == 20000
    assert result.get_json()["stock"][str(preset["id"])] == 10


def test_bulk_sale_needs_enough_stock_across_lines(client, headers):
    preset = _add_jogger(client, headers, stock=6).get_json()["preset"]
    result = _checkout(client, headers, "too-many", [
        {"inventory_item_id": preset["id"], "quantity": 1, "sale_type": "bulk", "checkout_line_id": "a"},
        {"inventory_item_id": preset["id"], "quantity": 2, "checkout_line_id": "b"},
    ])
    assert result.status_code == 409
    stock = client.get("/api/inventory-presets").get_json()["presets"][0]["stock"]
    assert stock == 6


def test_bulk_requires_a_product_with_bulk_price(client, headers):
    preset = client.post(
        "/api/inventory-presets", json={"item_name": "Cap", "price": 1500, "stock": 10}, headers=headers
    ).get_json()["preset"]
    result = _checkout(client, headers, "no-bulk", [
        {"inventory_item_id": preset["id"], "quantity": 1, "sale_type": "bulk"},
    ])
    assert result.status_code == 409

    custom = _checkout(client, headers, "custom-bulk", [
        {"item_name": "Gift wrap", "unit_price": 500, "quantity": 1, "sale_type": "bulk"},
    ])
    assert custom.status_code == 400


def test_deleting_a_bulk_sale_restores_every_unit(client, headers):
    preset = _add_jogger(client, headers).get_json()["preset"]
    sale = _checkout(client, headers, "undo", [
        {"inventory_item_id": preset["id"], "quantity": 2, "sale_type": "bulk"},
    ]).get_json()
    removed = client.delete(f"/api/income/{sale['items'][0]['id']}", headers=headers)
    assert removed.get_json()["stock"][str(preset["id"])] == 20
