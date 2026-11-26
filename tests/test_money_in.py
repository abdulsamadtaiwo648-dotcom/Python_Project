"""Money in that is not a sale: recorded apart from sales, with its own kinds and dates."""

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


def today():
    return datetime.now(timezone.utc).date()


def body(**over):
    data = {"amount": 50000, "kind": "Owner contribution", "description": "Put in to restock", "entry_date": today().isoformat()}
    data.update(over)
    return data


def stored(user_id):
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM money_in WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()]


def test_money_in_is_recorded_with_its_business_date():
    user_id, client, headers = signed_user()
    past = (today() - timedelta(days=4)).isoformat()
    response = client.post("/api/money-in", json=body(entry_date=past), headers=headers)
    assert response.status_code == 201, response.text
    row = stored(user_id)[0]
    assert row["entry_date"] == past and row["kind"] == "Owner contribution" and row["entered_at"]


def test_money_in_is_not_a_sale_and_does_not_appear_in_sales():
    user_id, client, headers = signed_user()
    client.post("/api/money-in", json=body(), headers=headers)
    assert client.get("/api/income", headers=headers).json()["income"] == []


def test_only_known_kinds_are_accepted():
    user_id, client, headers = signed_user()
    assert client.post("/api/money-in", json=body(kind="Winnings"), headers=headers).status_code == 400
    assert stored(user_id) == []


def test_amount_must_be_positive():
    user_id, client, headers = signed_user()
    for amount in [0, -5, "abc"]:
        assert client.post("/api/money-in", json=body(amount=amount), headers=headers).status_code == 400
    assert stored(user_id) == []


def test_a_future_or_too_old_date_is_refused():
    user_id, client, headers = signed_user()
    assert client.post("/api/money-in", json=body(entry_date=(today() + timedelta(days=5)).isoformat()), headers=headers).status_code == 400
    assert client.post("/api/money-in", json=body(entry_date=(today() - timedelta(days=900)).isoformat()), headers=headers).status_code == 400
    assert stored(user_id) == []


def test_a_long_note_is_refused():
    user_id, client, headers = signed_user()
    assert client.post("/api/money-in", json=body(description="n" * 201), headers=headers).status_code == 400


def test_money_in_can_be_edited_and_deleted():
    user_id, client, headers = signed_user()
    client.post("/api/money-in", json=body(), headers=headers)
    item_id = stored(user_id)[0]["id"]
    edited = client.put(f"/api/money-in/{item_id}", json=body(kind="Loan", amount=12000), headers=headers)
    assert edited.status_code == 200, edited.text
    row = stored(user_id)[0]
    assert row["kind"] == "Loan" and row["amount"] == 12000
    assert client.delete(f"/api/money-in/{item_id}", headers=headers).status_code == 200
    assert stored(user_id) == []


def test_another_business_cannot_change_or_delete_money_in():
    owner_id, owner_client, owner_headers = signed_user()
    _, other_client, other_headers = signed_user()
    owner_client.post("/api/money-in", json=body(), headers=owner_headers)
    item_id = stored(owner_id)[0]["id"]
    assert other_client.put(f"/api/money-in/{item_id}", json=body(amount=1), headers=other_headers).status_code == 404
    assert other_client.delete(f"/api/money-in/{item_id}", headers=other_headers).status_code == 404
    assert stored(owner_id)[0]["amount"] == 50000


def test_sales_staff_can_record_money_in_but_only_the_owner_can_delete_it():
    sales = frozenset({"sales"})
    assert perm.required("POST", "/api/money-in") == sales
    assert perm.required("PUT", "/api/money-in/3") == sales
    assert perm.required("GET", "/api/money-in") >= {"sales"}
    assert perm.required("DELETE", "/api/money-in/3") == perm.OWNER
