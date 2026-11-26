"""Accounts: each business has one default account, owners manage the rest, and no business can
touch another's accounts."""

import re
from datetime import datetime, timezone

from api import accounts as acc
from api import permissions as perm
from api.money import kobo_from_amount, naira_text, parse_naira
from server.database import get_db

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return user_id, client, {"X-CSRFToken": token}


def listing(client, headers):
    response = client.get("/api/accounts", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def by_name(client, headers):
    return {a["name"]: a for a in listing(client, headers)["accounts"]}


def add(client, headers, **fields):
    return client.post("/api/accounts", json=fields, headers=headers)


def defaults_in_db(user_id):
    with get_db() as db:
        return db.execute("SELECT COUNT(*) AS n FROM accounts WHERE user_id = ? AND is_default = 1", (user_id,)).fetchone()["n"]


# --- the default account ----------------------------------------------------------------------

def test_a_new_business_gets_exactly_one_default_account_named_cash():
    user_id, client, headers = signed_user()
    data = listing(client, headers)
    assert [a["name"] for a in data["accounts"]] == ["Cash"]
    cash = data["accounts"][0]
    assert cash["is_default"] and not cash["archived"]
    assert cash["opening_balance"] == "0.00"
    assert cash["opening_date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert data["default_id"] == cash["id"]
    assert defaults_in_db(user_id) == 1


def test_reading_accounts_again_does_not_create_another_default():
    user_id, client, headers = signed_user()
    listing(client, headers)
    listing(client, headers)
    assert defaults_in_db(user_id) == 1


import pytest  # noqa: E402


def test_the_database_refuses_a_second_default_for_the_same_business():
    user_id, client, headers = signed_user()
    listing(client, headers)
    with get_db() as db:
        with pytest.raises(Exception):
            db.execute("INSERT INTO accounts (user_id, name, is_default, archived, opening_kobo) VALUES (?, 'Other', 1, 0, 0)", (user_id,))


# --- adding accounts --------------------------------------------------------------------------

def test_an_account_can_be_added_with_an_opening_balance_and_date():
    _, client, headers = signed_user()
    response = add(client, headers, name="Petty Cash", opening_balance="5,000.50", opening_date="2026-01-12")
    assert response.status_code == 201, response.text
    account = response.json()["account"]
    assert account["opening_balance"] == "5000.50" and account["opening_date"] == "2026-01-12"
    assert not account["is_default"]


def test_an_omitted_opening_balance_is_zero_and_an_omitted_date_is_the_day_it_was_created():
    _, client, headers = signed_user()
    account = add(client, headers, name="Bank").json()["account"]
    assert account["opening_balance"] == "0.00"
    assert account["opening_date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_a_negative_opening_balance_is_allowed():
    _, client, headers = signed_user()
    assert add(client, headers, name="Overdraft", opening_balance="-500").json()["account"]["opening_balance"] == "-500.00"


def test_an_amount_that_is_not_money_is_refused():
    _, client, headers = signed_user()
    for bad in ["abc", "12.345", "1e3", "5000 naira"]:
        assert add(client, headers, name=f"Bad {bad}", opening_balance=bad).status_code == 400, bad


def test_a_name_is_required_and_limited():
    _, client, headers = signed_user()
    assert add(client, headers, name="   ").status_code == 400
    assert add(client, headers, name="x" * 61).status_code == 400


def test_names_are_unique_without_regard_to_case_and_archived_names_count():
    _, client, headers = signed_user()
    assert add(client, headers, name="Petty Cash").status_code == 201
    assert add(client, headers, name="petty cash").status_code == 400
    account = by_name(client, headers)["Petty Cash"]
    client.put(f"/api/accounts/{account['id']}", json={"archived": True}, headers=headers)
    assert add(client, headers, name="PETTY CASH").status_code == 400


# --- archiving, the default, and restoring ----------------------------------------------------

def test_an_account_can_be_archived_and_stays_listed_as_archived():
    _, client, headers = signed_user()
    petty = add(client, headers, name="Petty Cash").json()["account"]
    response = client.put(f"/api/accounts/{petty['id']}", json={"archived": True}, headers=headers)
    assert response.status_code == 200
    listed = by_name(client, headers)["Petty Cash"]
    assert listed["archived"] is True


def test_the_default_account_cannot_be_archived():
    _, client, headers = signed_user()
    cash = by_name(client, headers)["Cash"]
    response = client.put(f"/api/accounts/{cash['id']}", json={"archived": True}, headers=headers)
    assert response.status_code == 400
    assert "Make another account the default first" in response.json()["message"]


def test_another_account_can_become_the_default_and_there_is_still_only_one():
    user_id, client, headers = signed_user()
    petty = add(client, headers, name="Petty Cash").json()["account"]
    response = client.put(f"/api/accounts/{petty['id']}", json={"is_default": True}, headers=headers)
    assert response.status_code == 200
    data = listing(client, headers)
    assert data["default_id"] == petty["id"]
    assert [a["name"] for a in data["accounts"] if a["is_default"]] == ["Petty Cash"]
    assert defaults_in_db(user_id) == 1


def test_the_default_cannot_be_turned_off_directly_and_an_archived_account_cannot_be_made_default():
    _, client, headers = signed_user()
    cash = by_name(client, headers)["Cash"]
    assert client.put(f"/api/accounts/{cash['id']}", json={"is_default": False}, headers=headers).status_code == 400
    petty = add(client, headers, name="Petty Cash").json()["account"]
    client.put(f"/api/accounts/{petty['id']}", json={"archived": True}, headers=headers)
    response = client.put(f"/api/accounts/{petty['id']}", json={"is_default": True}, headers=headers)
    assert response.status_code == 400


def test_an_archived_account_can_be_restored():
    _, client, headers = signed_user()
    petty = add(client, headers, name="Petty Cash").json()["account"]
    client.put(f"/api/accounts/{petty['id']}", json={"archived": True}, headers=headers)
    client.put(f"/api/accounts/{petty['id']}", json={"archived": False}, headers=headers)
    assert by_name(client, headers)["Petty Cash"]["archived"] is False


def test_an_account_can_be_renamed_but_not_onto_another_name():
    _, client, headers = signed_user()
    add(client, headers, name="Bank")
    petty = add(client, headers, name="Petty Cash").json()["account"]
    assert client.put(f"/api/accounts/{petty['id']}", json={"name": "Bank"}, headers=headers).status_code == 400
    assert client.put(f"/api/accounts/{petty['id']}", json={"name": "Cash box"}, headers=headers).status_code == 200


# --- ownership ------------------------------------------------------------------------------

def test_one_business_cannot_see_or_change_another_businesss_accounts():
    _, client_a, headers_a = signed_user()
    _, client_b, headers_b = signed_user()
    account_a = add(client_a, headers_a, name="A only").json()["account"]
    assert "A only" not in by_name(client_b, headers_b)
    assert client_b.put(f"/api/accounts/{account_a['id']}", json={"archived": True}, headers=headers_b).status_code == 404


def test_staff_can_read_accounts_but_only_the_owner_can_change_them():
    assert perm.required("GET", "/api/accounts") >= {"sales", "expenses"}
    assert perm.required("POST", "/api/accounts") == perm.OWNER
    assert perm.required("PUT", "/api/accounts/3") == perm.OWNER


def test_the_accounts_page_opens_directly_and_needs_sign_in():
    _, client, headers = signed_user()
    assert client.get("/accounts").status_code == 200
    assert new_client().get("/accounts").status_code == 302


# --- money -----------------------------------------------------------------------------------

def test_naira_amounts_add_up_exactly_in_kobo():
    # 0.10 + 0.20 is not exact in binary floats; in kobo it is exactly 30.
    assert parse_naira("0.10") + parse_naira("0.20") == 30
    assert kobo_from_amount(0.1 + 0.2) == 30


def test_amounts_read_and_write_back_exactly():
    assert parse_naira("1,234.5") == 123450
    assert parse_naira("0.5") == 50
    assert parse_naira("12.345") is None
    assert naira_text(-50000) == "-500.00"
    assert naira_text(7) == "0.07"
