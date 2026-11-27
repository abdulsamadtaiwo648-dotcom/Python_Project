"""The transfers list: each transfer shows where the money came from and where it went."""

from datetime import datetime, timezone

from .conftest import make_user, new_client, sign_in


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200, response.text
    return user_id, client, {"X-CSRFToken": token}


def test_a_transfer_lists_its_from_and_to_accounts_and_stays_out_of_money_in():
    user_id, client, headers = signed_user()
    accounts = client.get("/api/accounts", headers=headers).json()["accounts"]
    cash = next(a for a in accounts if a["is_default"])["id"]
    bank = client.post("/api/accounts", json={"name": "Bank"}, headers=headers).json()["account"]["id"]
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.post("/api/money-in", json={"amount": 25000, "kind": "Transfer", "description": "Top up",
                                                  "entry_date": today, "account_id": bank, "from_account_id": cash}, headers=headers)
    assert response.status_code == 201, response.text

    transfers = client.get("/api/transfers", headers=headers).json()["transfers"]
    assert len(transfers) == 1
    assert transfers[0]["amount"] == 25000
    assert transfers[0]["from_account_id"] == cash and transfers[0]["to_account_id"] == bank
    assert transfers[0]["description"] == "Top up"

    money_in = client.get("/api/money-in", headers=headers).json()["money_in"]
    assert all(item["kind"] != "Transfer" for item in money_in)


def test_transfers_need_a_signed_in_user():
    client = new_client()
    assert client.get("/api/transfers").status_code == 401
