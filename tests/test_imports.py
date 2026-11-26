"""Importing past sales and expenses from a spreadsheet."""

from datetime import datetime, timedelta, timezone

from api import permissions as perm
from server.database import get_db

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return user_id, client, {"X-CSRFToken": token}


def day(back=3):
    return (datetime.now(timezone.utc).date() - timedelta(days=back)).isoformat()


def expense_row(**over):
    row = {"date": day(), "amount": "1,500", "category": "Fuel & Electricity", "description": "Generator fuel"}
    row.update(over)
    return row


def sale_row(**over):
    row = {"date": day(), "description": "Rice 5kg", "amount": "9000", "customer": "Ada", "payment_mode": "Cash"}
    row.update(over)
    return row


def count(user_id, table):
    with get_db() as db:
        return db.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?", (user_id,)).fetchone()["n"]


def test_expenses_are_imported_on_their_own_dates():
    user_id, client, headers = signed_user()
    response = client.post("/api/import/expenses", json={"rows": [expense_row(), expense_row(description="Diesel", amount="800")]}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 2
    with get_db() as db:
        row = db.execute("SELECT entry_date FROM expenses WHERE user_id = ? ORDER BY id LIMIT 1", (user_id,)).fetchone()
    assert row["entry_date"] == day()


def test_a_bad_row_is_skipped_and_the_rest_are_still_imported():
    user_id, client, headers = signed_user()
    rows = [expense_row(), expense_row(amount="abc"), expense_row(amount="-5"),
            expense_row(date="2099-01-01"), expense_row(description=""), expense_row(description="Diesel", amount="800")]
    body = client.post("/api/import/expenses", json={"rows": rows}, headers=headers).json()
    assert body["imported"] == 2
    reasons = {s["row"]: s["reason"] for s in body["skipped"]}
    assert set(reasons) == {2, 3, 4, 5}
    assert count(user_id, "expenses") == 2


def test_importing_the_same_file_twice_does_not_double_it():
    user_id, client, headers = signed_user()
    rows = [expense_row()]
    client.post("/api/import/expenses", json={"rows": rows}, headers=headers)
    again = client.post("/api/import/expenses", json={"rows": rows}, headers=headers).json()
    assert again["imported"] == 0 and again["skipped"][0]["reason"] == "Already recorded."
    assert count(user_id, "expenses") == 1


def test_an_unknown_category_is_added_to_the_list():
    user_id, client, headers = signed_user()
    client.post("/api/import/expenses", json={"rows": [expense_row(category="Generator servicing")]}, headers=headers)
    names = [c["name"] for c in client.get("/api/expense-categories", headers=headers).json()["categories"]]
    assert "Generator servicing" in names


def test_an_archived_category_is_not_revived_by_an_import():
    user_id, client, headers = signed_user()
    cats = client.get("/api/expense-categories", headers=headers).json()["categories"]
    old = next(c for c in cats if c["name"] == "Data & Airtime")
    client.put(f"/api/expense-categories/{old['id']}", json={"archived": True}, headers=headers)
    body = client.post("/api/import/expenses", json={"rows": [expense_row(category="Data & Airtime")]}, headers=headers).json()
    assert body["imported"] == 0 and "archived" in body["skipped"][0]["reason"]


def test_sales_are_imported_as_paid_sales_on_their_dates():
    user_id, client, headers = signed_user()
    body = client.post("/api/import/sales", json={"rows": [sale_row(), sale_row(description="Sugar", amount="2,000", customer="")]}, headers=headers).json()
    assert body["imported"] == 2
    with get_db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM income WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()]
    assert rows[0]["total_value"] == 9000 and rows[0]["amount_paid"] == 9000
    assert rows[0]["entry_date"] == day() and rows[1]["customer_name"] == "Walk-in Customer"


def test_a_sale_with_an_unknown_payment_mode_is_skipped():
    user_id, client, headers = signed_user()
    body = client.post("/api/import/sales", json={"rows": [sale_row(payment_mode="Crypto")]}, headers=headers).json()
    assert body["imported"] == 0 and "payment mode" in body["skipped"][0]["reason"]


def test_too_many_rows_are_refused():
    _, client, headers = signed_user()
    rows = [expense_row()] * 501
    assert client.post("/api/import/expenses", json={"rows": rows}, headers=headers).status_code == 400


def test_import_permissions_follow_the_page_they_write_to():
    assert perm.required("POST", "/api/import/sales") == frozenset({"sales"})
    assert perm.required("POST", "/api/import/expenses") == frozenset({"expenses"})
