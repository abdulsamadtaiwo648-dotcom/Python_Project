"""Delete all test transactions: test businesses only, owners only, typed confirmation, setup kept."""

from server.database import get_db

from .conftest import new_client, sign_in, make_user


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


def count(user_id, table):
    with get_db() as db:
        return db.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?", (user_id,)).fetchone()["n"]


def seed(client, headers):
    client.post("/api/accounts", json={"name": "Petty Cash"}, headers=headers)
    client.post("/add", json={"amount": 500, "category": "Others", "description": "Test fuel"}, headers=headers)
    client.post("/api/money-in", json={"amount": 2000, "kind": "Owner contribution", "description": "Test float"}, headers=headers)
    client.post("/api/income", json={"description": "Test rice", "total_value": 900, "amount_paid": 900, "customer_name": "Ada", "payment_mode": "Cash"}, headers=headers)


def test_a_live_business_cannot_use_the_reset_and_keeps_its_data():
    user_id, client, headers = signed_user(test=False)
    seed(client, headers)
    assert client.get("/api/test-reset", headers=headers).status_code == 403
    assert client.post("/api/test-reset", json={"confirm": "DELETE"}, headers=headers).status_code == 403
    assert count(user_id, "expenses") == 1 and count(user_id, "income") == 1


def test_a_test_business_must_type_delete_exactly():
    user_id, client, headers = signed_user(test=True)
    seed(client, headers)
    assert client.post("/api/test-reset", json={"confirm": "delete"}, headers=headers).status_code == 400
    assert client.post("/api/test-reset", json={}, headers=headers).status_code == 400
    assert count(user_id, "expenses") == 1


def test_the_preview_lists_exactly_what_will_be_cleared_and_what_is_kept():
    user_id, client, headers = signed_user(test=True)
    seed(client, headers)
    data = client.get("/api/test-reset", headers=headers).json()
    assert data["clears"]["expenses"] == 1 and data["clears"]["sales"] == 1
    assert data["clears"]["sale_payments"] == 1 and data["clears"]["money_in"] == 1
    assert data["clears"]["kept"]["accounts"] == 2  # Cash and Petty Cash


def test_a_confirmed_reset_clears_transactions_and_keeps_the_setup():
    user_id, client, headers = signed_user(test=True)
    seed(client, headers)
    response = client.post("/api/test-reset", json={"confirm": "DELETE"}, headers=headers)
    assert response.status_code == 200, response.text
    for table in ("expenses", "income", "sale_payments", "money_in", "import_batches"):
        assert count(user_id, table) == 0, table
    assert count(user_id, "accounts") == 2
    assert client.get("/api/accounts", headers=headers).json()["default_id"] is not None


def test_stock_sold_in_a_cleared_sale_is_restored():
    user_id, client, headers = signed_user(test=True)
    product = client.post("/api/inventory-presets", json={"item_name": "Test soap", "price": 100, "stock": 10, "track_stock": True}, headers=headers).json()
    product_id = product.get("id") or product.get("preset", {}).get("id") or product.get("item", {}).get("id")
    body = {"checkout_id": "chk-reset-1", "customer_name": "Ada", "payment_mode": "Cash", "amount_paid": 300,
            "items": [{"checkout_line_id": "line-1", "inventory_item_id": product_id, "quantity": 3, "unit_price": 100, "sale_type": "unit"}]}
    assert client.post("/api/checkout", json=body, headers=headers).status_code in (200, 201)
    with get_db() as db:
        assert db.execute("SELECT stock FROM inventory_presets WHERE id = ?", (product_id,)).fetchone()["stock"] == 7
    client.post("/api/test-reset", json={"confirm": "DELETE"}, headers=headers)
    with get_db() as db:
        assert db.execute("SELECT stock FROM inventory_presets WHERE id = ?", (product_id,)).fetchone()["stock"] == 10
    assert count(user_id, "inventory_presets") == 1


def test_staff_cannot_use_the_reset_even_in_a_test_business():
    owner_id, owner_client, owner_headers = signed_user(test=True)
    staff_id, staff_email = make_user()
    with get_db() as db:
        db.execute("INSERT INTO staff_members (user_id, owner_id, role, pages, created_at) VALUES (?, ?, 'sales', '[\"sales\"]', '2026-01-01')",
                   (staff_id, owner_id))
        db.commit()
    client = new_client()
    response, token = sign_in(client, staff_email)
    assert response.status_code == 200
    headers = {"X-CSRFToken": token}
    assert client.get("/api/test-reset", headers=headers).status_code == 403
    assert client.post("/api/test-reset", json={"confirm": "DELETE"}, headers=headers).status_code == 403
