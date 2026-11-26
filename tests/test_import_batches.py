"""CSV imports: preview before anything is written, the rules for accounts and transfers, duplicates
the owner can keep, retries that cannot import twice, and undo that removes only its own batch."""

from server.database import get_db

from .conftest import new_client, sign_in, make_user


def signed_user():
    user_id, email = make_user()
    client = new_client()
    response, token = sign_in(client, email)
    assert response.status_code == 200
    return user_id, client, {"X-CSRFToken": token}


def add_account(client, headers, name, archived=False):
    account = client.post("/api/accounts", json={"name": name}, headers=headers).json()["account"]
    if archived:
        client.put(f"/api/accounts/{account['id']}", json={"archived": True}, headers=headers)
    return account["id"]


def preview(client, headers, kind, rows):
    response = client.post("/api/import/preview", json={"kind": kind, "rows": rows}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def commit(client, headers, kind, rows, batch_key="k1", keep=None):
    body = {"kind": kind, "rows": rows, "batch_key": batch_key, "keep_rows": keep or []}
    response = client.post("/api/import/commit", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def count(user_id, table):
    with get_db() as db:
        return db.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id = ?", (user_id,)).fetchone()["n"]


def expense_row(**over):
    row = {"date": "2026-01-13", "amount": "1,500", "category": "Others", "description": "Generator fuel"}
    row.update(over)
    return row


def money_row(**over):
    row = {"date": "2026-01-13", "amount": "5000", "type": "Owner contribution", "description": "Float", "received_into": ""}
    row.update(over)
    return row


# --- preview writes nothing and explains each problem -----------------------------------------

def test_preview_writes_nothing():
    user_id, client, headers = signed_user()
    result = preview(client, headers, "expenses", [expense_row()])
    assert result["counts"]["ok"] == 1
    assert count(user_id, "expenses") == 0


def test_an_unknown_account_is_flagged_and_never_created_and_direct_pay_is_not_guessed():
    user_id, client, headers = signed_user()
    accounts_before = client.get("/api/accounts", headers=headers).json()["accounts"]
    result = preview(client, headers, "expenses", [expense_row(paid_from="Direct Pay"), expense_row(paid_from="Petty Cash")])
    assert result["rows"][0]["status"] == "error"
    assert "is not on your list" in result["rows"][0]["reasons"][0]
    assert result["rows"][1]["status"] == "error"
    assert len(client.get("/api/accounts", headers=headers).json()["accounts"]) == len(accounts_before)


def test_an_archived_account_is_flagged_for_correction():
    _, client, headers = signed_user()
    add_account(client, headers, "Old till", archived=True)
    result = preview(client, headers, "expenses", [expense_row(paid_from="Old till")])
    assert result["rows"][0]["status"] == "error" and "archived" in result["rows"][0]["reasons"][0]


def test_a_blank_account_uses_the_default_and_a_known_account_is_used():
    user_id, client, headers = signed_user()
    petty = add_account(client, headers, "Petty Cash")
    commit(client, headers, "expenses", [expense_row(), expense_row(paid_from="Petty Cash", description="Market")], batch_key="a1")
    with get_db() as db:
        rows = {r["description"]: r["account_id"] for r in db.execute("SELECT description, account_id FROM expenses WHERE user_id = ?", (user_id,)).fetchall()}
    assert rows["Generator fuel"] == client.get("/api/accounts", headers=headers).json()["default_id"]
    assert rows["Market"] == petty


def test_bad_dates_amounts_and_types_are_flagged():
    _, client, headers = signed_user()
    result = preview(client, headers, "expenses", [expense_row(date="13/01/2026"), expense_row(amount="abc"), expense_row(amount="-5")])
    assert [r["status"] for r in result["rows"]] == ["error", "error", "error"]
    money = preview(client, headers, "money_in", [money_row(type="Winnings")])
    assert money["rows"][0]["status"] == "error" and "Choose a type" in money["rows"][0]["reasons"][0]


def test_a_transfer_needs_two_different_active_accounts_and_both_are_named():
    _, client, headers = signed_user()
    add_account(client, headers, "Petty Cash")
    no_source = money_row(type="Transfer", received_into="Petty Cash", from_account="")
    same = money_row(type="Transfer", received_into="Petty Cash", from_account="Petty Cash")
    unknown = money_row(type="Transfer", received_into="Petty Cash", from_account="Nowhere")
    rows = preview(client, headers, "money_in", [no_source, same, unknown])["rows"]
    assert [r["status"] for r in rows] == ["error", "error", "error"]
    assert "two different accounts" in rows[1]["reasons"][0]


def test_a_money_in_row_received_into_nothing_uses_the_default_and_a_from_account_needs_a_transfer():
    _, client, headers = signed_user()
    ok = preview(client, headers, "money_in", [money_row()])["rows"][0]
    assert ok["status"] == "ok"
    flagged = preview(client, headers, "money_in", [money_row(from_account="Cash")])["rows"][0]
    assert flagged["status"] == "error" and "Only a transfer" in flagged["reasons"][0]


# --- duplicates -------------------------------------------------------------------------------

def test_a_repeat_of_an_existing_record_or_of_a_row_in_the_file_is_flagged_and_can_be_kept():
    user_id, client, headers = signed_user()
    commit(client, headers, "expenses", [expense_row()], batch_key="first")
    again = preview(client, headers, "expenses", [expense_row(), expense_row(description="Diesel"), expense_row(description="Diesel")])
    assert again["rows"][0]["status"] == "duplicate" and again["rows"][0]["duplicate_of"]["kind"] == "existing"
    assert again["rows"][2]["status"] == "duplicate" and again["rows"][2]["duplicate_of"] == {"kind": "file", "row": 2}
    result = commit(client, headers, "expenses", [expense_row(), expense_row(description="Diesel"), expense_row(description="Diesel")],
                    batch_key="second", keep=[3])
    assert result["imported"] == 2  # the genuine repeat (row 3) is kept; the existing one and row 2 are not
    assert count(user_id, "expenses") == 3


# --- retries and batches ----------------------------------------------------------------------

def test_a_retried_commit_with_the_same_batch_key_changes_nothing():
    user_id, client, headers = signed_user()
    first = commit(client, headers, "expenses", [expense_row(description="A"), expense_row(description="B")], batch_key="retry-1")
    second = commit(client, headers, "expenses", [expense_row(description="A"), expense_row(description="B")], batch_key="retry-1")
    assert first["imported"] == 2 and second["already_imported"] is True
    assert count(user_id, "expenses") == 2


def test_an_imported_transfer_is_one_record_and_undo_removes_both_sides_together():
    user_id, client, headers = signed_user()
    cash = client.get("/api/accounts", headers=headers).json()["default_id"]
    petty = add_account(client, headers, "Petty Cash")
    rows = [money_row(type="Transfer", received_into="Petty Cash", from_account="Cash", amount="3000", description="Top up")]
    result = commit(client, headers, "money_in", rows, batch_key="t1")
    assert result["imported"] == 1
    plan = client.get(f"/api/import-batches/{result['batch_id']}/undo", headers=headers).json()
    assert plan["remove"]["money_in"] == 1
    assert client.post(f"/api/import-batches/{result['batch_id']}/undo", headers=headers).status_code == 200
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM money_in WHERE user_id = ?", (user_id,)).fetchone()["n"] == 0


# --- undo -------------------------------------------------------------------------------------

def test_undo_removes_only_its_own_batch_and_a_second_undo_changes_nothing():
    user_id, client, headers = signed_user()
    keep = commit(client, headers, "expenses", [expense_row(description="Earlier")], batch_key="keep")
    target = commit(client, headers, "expenses", [expense_row(description="Imported"), expense_row(description="Also imported")], batch_key="target")
    assert client.post(f"/api/import-batches/{target['batch_id']}/undo", headers=headers).json()["removed"]["expenses"] == 2
    assert client.post(f"/api/import-batches/{target['batch_id']}/undo", headers=headers).json()["removed"] is None
    with get_db() as db:
        descriptions = [r["description"] for r in db.execute("SELECT description FROM expenses WHERE user_id = ?", (user_id,)).fetchall()]
    assert descriptions == ["Earlier"]
    assert keep["imported"] == 1


def test_an_expense_edited_after_the_import_is_kept_and_reported():
    user_id, client, headers = signed_user()
    result = commit(client, headers, "expenses", [expense_row(description="Edited later"), expense_row(description="Untouched")], batch_key="e1")
    rows = client.get("/api/expenses", headers=headers).json()["expenses"]
    edited = next(r for r in rows if r["description"] == "Edited later")
    body = {"amount": 9999, "category": "Others", "description": "Edited later"}
    assert client.put(f"/api/expenses/{edited['server_id']}", json=body, headers=headers).status_code == 200
    plan = client.get(f"/api/import-batches/{result['batch_id']}/undo", headers=headers).json()
    assert plan["remove"]["expenses"] == 1
    assert plan["keep"] == [{"table": "expenses", "id": edited["server_id"], "reason": "Changed after the import"}]
    client.post(f"/api/import-batches/{result['batch_id']}/undo", headers=headers)
    assert [r["description"] for r in client.get("/api/expenses", headers=headers).json()["expenses"]] == ["Edited later"]


def test_a_sale_that_gained_a_later_payment_is_kept_with_its_payments():
    user_id, client, headers = signed_user()
    rows = [{"date": "2026-01-10", "description": "Rice", "amount": "900", "customer": "Ada", "payment_mode": "Cash"}]
    result = commit(client, headers, "sales", rows, batch_key="s1")
    with get_db() as db:
        income_id = db.execute("SELECT MAX(id) AS id FROM income WHERE user_id = ?", (user_id,)).fetchone()["id"]
    # An imported sale is recorded as fully paid, so a payment through the app would apply nothing.
    # This simulates a payment linked to it after the import, which the undo rule must protect.
    with get_db() as db:
        account = db.execute("SELECT id FROM accounts WHERE user_id = ? AND is_default = 1", (user_id,)).fetchone()["id"]
        db.execute("INSERT INTO sale_payments (user_id, income_id, account_id, amount_kobo, payment_date, is_approximate, created_at) "
                   "VALUES (?, ?, ?, 10000, '2026-01-12', 0, '2026-01-12')", (user_id, income_id, account))
        db.commit()
    plan = client.get(f"/api/import-batches/{result['batch_id']}/undo", headers=headers).json()
    assert plan["remove"]["income"] == 0
    assert any(k["reason"].startswith("Payments were made") for k in plan["keep"])
    client.post(f"/api/import-batches/{result['batch_id']}/undo", headers=headers)
    assert count(user_id, "income") == 1


def test_an_undo_of_a_plain_sale_import_removes_its_sale_and_payment():
    user_id, client, headers = signed_user()
    rows = [{"date": "2026-01-10", "description": "Rice", "amount": "900", "customer": "Ada", "payment_mode": "Cash"}]
    result = commit(client, headers, "sales", rows, batch_key="s2")
    client.post(f"/api/import-batches/{result['batch_id']}/undo", headers=headers)
    assert count(user_id, "income") == 0 and count(user_id, "sale_payments") == 0


def test_a_batch_belonging_to_another_business_is_not_found():
    _, client_a, headers_a = signed_user()
    result = commit(client_a, headers_a, "expenses", [expense_row()], batch_key="mine")
    _, client_b, headers_b = signed_user()
    assert client_b.get(f"/api/import-batches/{result['batch_id']}/undo", headers=headers_b).status_code == 404
    assert client_b.post(f"/api/import-batches/{result['batch_id']}/undo", headers=headers_b).status_code == 404


def test_the_old_import_endpoints_still_answer_as_before_and_record_a_batch():
    user_id, client, headers = signed_user()
    response = client.post("/api/import/expenses", json={"rows": [expense_row(description="Old endpoint")]}, headers=headers)
    assert response.status_code == 200 and response.json()["imported"] == 1
    assert response.json()["batch_id"] is not None
    assert client.get("/api/import-batches", headers=headers).json()["batches"][0]["kind"] == "expenses"
