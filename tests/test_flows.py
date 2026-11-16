"""End-to-end checks for the core bookkeeping APIs."""

import uuid

from server.app import get_db


def test_requests_without_a_session_are_unauthorized(client):
    assert client.get("/api/expenses").status_code == 401
    assert client.get("/api/income").status_code == 401


def test_session_for_deleted_user_is_rejected(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "user_that_does_not_exist"
    assert client.get("/api/expenses").status_code == 401


def test_expense_add_update_delete(client, signed_in):
    _, token = signed_in
    headers = {"X-CSRFToken": token}

    added = client.post(
        "/add",
        json={"amount": 150.5, "category": "Fuel", "description": "Generator fuel"},
        headers=headers,
    )
    assert added.status_code == 201
    expense_id = added.get_json()["expense"]["id"]

    updated = client.put(
        f"/api/expenses/{expense_id}",
        json={"amount": 199.99, "category": "Others", "description": "Updated fuel"},
        headers=headers,
    )
    assert updated.status_code == 200

    listed = client.get("/api/expenses").get_json()
    item = next(e for e in listed["expenses"] if e["server_id"] == expense_id)
    assert float(item["amount"]) == 199.99

    deleted = client.post(f"/delete/{expense_id}", headers=headers)
    assert deleted.status_code == 302
    listed = client.get("/api/expenses").get_json()
    assert all(e["server_id"] != expense_id for e in listed["expenses"])


def test_expense_requires_csrf_token(client, signed_in):
    response = client.post("/add", json={"amount": 10, "category": "x", "description": "y"})
    assert response.status_code == 400


def test_checkout_decrements_stock_and_delete_restores_it(client, signed_in):
    _, token = signed_in
    headers = {"X-CSRFToken": token}

    preset = client.post(
        "/api/inventory-presets",
        json={"item_name": "Soap", "price": 500, "stock": 5},
        headers=headers,
    ).get_json()["preset"]

    checkout = client.post(
        "/api/checkout",
        json={
            "checkout_id": "checkout-1",
            "amount_paid": 1000,
            "items": [{"inventory_item_id": preset["id"], "quantity": 2}],
        },
        headers=headers,
    )
    assert checkout.status_code == 201
    body = checkout.get_json()
    assert body["stock"][str(preset["id"])] == 3

    # Replaying the same checkout is idempotent.
    replay = client.post(
        "/api/checkout",
        json={
            "checkout_id": "checkout-1",
            "amount_paid": 1000,
            "items": [{"inventory_item_id": preset["id"], "quantity": 2}],
        },
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.get_json()["stock"][str(preset["id"])] == 3

    too_many = client.post(
        "/api/checkout",
        json={
            "checkout_id": "checkout-2",
            "amount_paid": 0,
            "items": [{"inventory_item_id": preset["id"], "quantity": 10}],
        },
        headers=headers,
    )
    assert too_many.status_code == 409

    sale_id = body["items"][0]["id"]
    removed = client.delete(f"/api/income/{sale_id}", headers=headers)
    assert removed.status_code == 200
    assert removed.get_json()["stock"][str(preset["id"])] == 5


def test_users_cannot_see_each_others_data(client, app, signed_in):
    _, token = signed_in
    client.post(
        "/add",
        json={"amount": 42, "category": "Private", "description": "Mine"},
        headers={"X-CSRFToken": token},
    )

    other_id = f"user_test_{uuid.uuid4().hex[:10]}"
    with get_db() as db:
        db.execute(
            "INSERT INTO users (id, email, password) VALUES (?, ?, ?)",
            (other_id, f"{other_id}@example.com", None),
        )
        db.commit()

    with app.test_client() as other:
        with other.session_transaction() as sess:
            sess["user_id"] = other_id
        expenses = other.get("/api/expenses").get_json()["expenses"]
        assert expenses == []
