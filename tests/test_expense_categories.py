"""Expense categories: each business has its own list; expenses must use it."""

from server.database import get_db

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return user_id, client, {"X-CSRFToken": token}


def names(client, headers):
    return {c["name"]: c for c in client.get("/api/expense-categories", headers=headers).json()["categories"]}


def expense(category="Data & Airtime", amount=10):
    return {"amount": amount, "category": category, "description": "Test"}


def test_a_new_business_starts_with_the_defaults():
    _, client, headers = signed_user()
    got = names(client, headers)
    assert "Fuel & Electricity" in got and "Others" in got
    assert all(not c["archived"] for c in got.values())


def test_a_name_used_on_an_old_expense_is_carried_into_the_list():
    user_id, client, headers = signed_user()
    with get_db() as db:
        db.execute("INSERT INTO expenses (user_id, amount, category, description, date) VALUES (?, 5, 'Bank charges', 'x', '2026-01-01 09:00 AM')", (user_id,))
        db.commit()
    assert "Bank charges" in names(client, headers)


def test_an_expense_can_use_a_listed_category():
    user_id, client, headers = signed_user()
    response = client.post("/add", json=expense("Fuel & Electricity"), headers=headers)
    assert response.status_code in (200, 201), response.text


def test_an_expense_cannot_use_a_name_that_is_not_on_the_list():
    user_id, client, headers = signed_user()
    response = client.post("/add", json=expense("Holiday"), headers=headers)
    assert response.status_code == 400
    assert "from your list" in response.json()["message"]
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?", (user_id,)).fetchone()["n"] == 0


def test_a_category_matches_regardless_of_case():
    _, client, headers = signed_user()
    assert client.post("/add", json=expense("fuel & electricity"), headers=headers).status_code in (200, 201)


def test_a_new_category_can_be_added_and_used():
    _, client, headers = signed_user()
    response = client.post("/api/expense-categories", json={"name": "Generator servicing"}, headers=headers)
    assert response.status_code == 201, response.text
    assert client.post("/add", json=expense("Generator servicing"), headers=headers).status_code in (200, 201)


def test_a_duplicate_name_is_refused_even_in_another_case():
    _, client, headers = signed_user()
    response = client.post("/api/expense-categories", json={"name": "others"}, headers=headers)
    assert response.status_code == 400
    assert "already have" in response.json()["message"]


def test_a_blank_or_long_name_is_refused():
    _, client, headers = signed_user()
    assert client.post("/api/expense-categories", json={"name": "   "}, headers=headers).status_code == 400
    assert client.post("/api/expense-categories", json={"name": "x" * 81}, headers=headers).status_code == 400


def test_renaming_a_category_renames_it_on_existing_expenses():
    user_id, client, headers = signed_user()
    client.post("/add", json=expense("Data & Airtime", amount=30), headers=headers)
    cat_id = names(client, headers)["Data & Airtime"]["id"]
    response = client.put(f"/api/expense-categories/{cat_id}", json={"name": "Phone credit"}, headers=headers)
    assert response.status_code == 200, response.text
    assert "Phone credit" in names(client, headers) and "Data & Airtime" not in names(client, headers)
    with get_db() as db:
        rows = db.execute("SELECT category FROM expenses WHERE user_id = ?", (user_id,)).fetchall()
    assert [r["category"] for r in rows] == ["Phone credit"]


def test_renaming_onto_an_existing_name_is_refused():
    _, client, headers = signed_user()
    cat_id = names(client, headers)["Others"]["id"]
    response = client.put(f"/api/expense-categories/{cat_id}", json={"name": "fuel & electricity"}, headers=headers)
    assert response.status_code == 400


def test_an_archived_category_cannot_be_chosen_for_a_new_expense():
    _, client, headers = signed_user()
    cat_id = names(client, headers)["Data & Airtime"]["id"]
    assert client.put(f"/api/expense-categories/{cat_id}", json={"archived": True}, headers=headers).status_code == 200
    assert client.post("/add", json=expense("Data & Airtime"), headers=headers).status_code == 400


def test_an_old_expense_keeps_its_archived_category_until_it_is_changed():
    user_id, client, headers = signed_user()
    client.post("/add", json=expense("Data & Airtime"), headers=headers)
    with get_db() as db:
        expense_id = db.execute("SELECT id FROM expenses WHERE user_id = ?", (user_id,)).fetchone()["id"]
    cat_id = names(client, headers)["Data & Airtime"]["id"]
    client.put(f"/api/expense-categories/{cat_id}", json={"archived": True}, headers=headers)
    # Saving the same expense with the archived name is allowed...
    same = client.put(f"/api/expenses/{expense_id}", json=expense("Data & Airtime", amount=12), headers=headers)
    assert same.status_code == 200, same.text
    # ...but moving it to another archived name is not.
    other = client.put(f"/api/expenses/{expense_id}", json=expense("Inventory & Materials", amount=12), headers=headers)
    assert other.status_code == 200  # active name, allowed
    assert client.put(f"/api/expenses/{expense_id}", json=expense("Data & Airtime", amount=12), headers=headers).status_code == 400


def test_restoring_an_archived_category_makes_it_available_again():
    _, client, headers = signed_user()
    cat_id = names(client, headers)["Data & Airtime"]["id"]
    client.put(f"/api/expense-categories/{cat_id}", json={"archived": True}, headers=headers)
    client.put(f"/api/expense-categories/{cat_id}", json={"archived": False}, headers=headers)
    assert client.post("/add", json=expense("Data & Airtime"), headers=headers).status_code in (200, 201)


def test_the_last_active_category_cannot_be_archived():
    _, client, headers = signed_user()
    got = names(client, headers)
    for name, c in got.items():
        if name != "Others":
            client.put(f"/api/expense-categories/{c['id']}", json={"archived": True}, headers=headers)
    response = client.put(f"/api/expense-categories/{got['Others']['id']}", json={"archived": True}, headers=headers)
    assert response.status_code == 400
    assert "at least one active category" in response.json()["message"]


def test_one_business_cannot_change_another_businesss_categories():
    _, client_a, headers_a = signed_user()
    _, client_b, headers_b = signed_user()
    cat_id = names(client_a, headers_a)["Others"]["id"]
    response = client_b.put(f"/api/expense-categories/{cat_id}", json={"name": "Hijacked"}, headers=headers_b)
    assert response.status_code == 404
