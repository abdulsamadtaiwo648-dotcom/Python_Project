"""Staff accounts: what each role can reach, seats, removal, and plan changes."""

import uuid
from datetime import datetime, timedelta, timezone

from api import subscriptions as subs
from server.database import get_db

from .conftest import make_user, new_client, sign_in


def owner_client(plan="basic"):
    user = make_user()
    client = new_client()
    response, token = sign_in(client, user[1])
    assert response.status_code == 200
    if plan:
        subs.activate(user[0], plan)
    return user, client, {"X-CSRFToken": token}


def add_staff(client, headers, role="sales", pages=None, name="Staff Person"):
    email = f"staff{uuid.uuid4().hex[:8]}@example.com"
    body = {"name": name, "email": email, "password": "Staff1234", "role": role, "pages": pages or []}
    return client.post("/api/staff", json=body, headers=headers), email


def staff_client(email, password="Staff1234"):
    client = new_client()
    response, token = sign_in(client, email, password)
    assert response.status_code == 200, response.text
    return client, {"X-CSRFToken": token}


def test_sales_staff_can_sell_but_not_touch_inventory_or_expenses():
    _, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="sales")
    assert created.status_code == 200, created.text
    staff, sh = staff_client(email)

    assert staff.get("/api/income").status_code == 200
    assert staff.get("/api/inventory-presets").status_code == 200          # product picker on the sale
    assert staff.post("/api/inventory-presets", json={"item_name": "X", "price": 1, "stock": 1}, headers=sh).status_code == 403
    assert staff.post("/add", json={"amount": 5, "category": "Others", "description": "x"}, headers=sh).status_code == 403
    assert staff.get("/api/expenses").status_code == 403
    assert staff.get("/api/website").status_code == 403


def test_sales_staff_record_under_the_owners_business():
    user, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="sales")
    product = owner.post("/api/inventory-presets", json={"item_name": "Soap", "price": 1500, "stock": 10}, headers=oh).json()["preset"]
    staff, sh = staff_client(email)
    response = staff.post("/api/checkout", json={
        "checkout_id": "staff-sale-1", "amount_paid": 1500,
        "items": [{"inventory_item_id": product["id"], "quantity": 1}],
    }, headers=sh)
    assert response.status_code == 201, response.text
    owner_sales = owner.get("/api/income").json()["income"]
    assert any(s["description"] == "Soap" for s in owner_sales)           # the owner sees it
    assert any(s["description"] == "Soap" for s in staff.get("/api/income").json()["income"])


def test_inventory_staff_manage_stock_but_not_sales_history():
    _, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="inventory")
    staff, sh = staff_client(email)
    assert staff.post("/api/inventory-presets", json={"item_name": "Cap", "price": 3000, "stock": 2}, headers=sh).status_code == 201
    assert staff.get("/api/income").status_code == 403


def test_accountant_reads_reports_and_records_expenses_only():
    _, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="accountant")
    staff, sh = staff_client(email)
    assert staff.get("/api/dashboard").status_code == 200
    assert staff.post("/add", json={"amount": 500, "category": "Others", "description": "Fuel"}, headers=sh).status_code == 201
    assert staff.post("/api/checkout", json={"checkout_id": "nope", "amount_paid": 0, "items": []}, headers=sh).status_code == 403


def test_custom_role_gets_exactly_the_ticked_pages():
    _, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="custom", pages=["website"])
    assert created.status_code == 200
    staff, sh = staff_client(email)
    assert staff.get("/api/website").status_code == 200
    assert staff.get("/api/income").status_code == 403
    access = staff.get("/api/session").json()["access"]
    assert access["is_owner"] is False and access["pages"] == ["website"]


def test_custom_role_needs_at_least_one_page():
    _, owner, oh = owner_client()
    created, _ = add_staff(owner, oh, role="custom", pages=[])
    assert created.status_code == 400


def test_staff_can_never_manage_the_team_billing_or_their_password():
    _, owner, oh = owner_client()
    _, email = add_staff(owner, oh, role="sales")
    staff, sh = staff_client(email)
    assert staff.get("/api/staff").status_code == 403
    assert staff.post("/api/staff", json={"name": "A B", "email": "a@x.com", "password": "Abc12345", "role": "sales"}, headers=sh).status_code == 403
    assert staff.post("/api/subscription/checkout", json={"plan": "pro"}, headers=sh).status_code == 403
    assert staff.post("/api/subscription/cancel", headers=sh).status_code == 403
    assert staff.get("/api/subscription").status_code == 200                # banners only
    assert staff.get("/api/business_profile").status_code == 200           # receipts need the name
    assert staff.post("/api/business_profile", json={"company_name": "Hack"}, headers=sh).status_code == 403


def test_forgot_password_never_sends_a_code_to_staff():
    _, owner, oh = owner_client()
    _, email = add_staff(owner, oh, role="sales")
    client = new_client()
    response = client.post("/api/forgot-password/request", json={"email": email}, headers={"X-CSRFToken": client.get("/api/session").json()["csrf_token"]})
    assert response.status_code == 200                                      # same answer as any email
    with get_db() as db:
        assert db.execute("SELECT 1 FROM otp_codes WHERE email = ?", (email,)).fetchone() is None


def test_staff_login_shows_only_their_pages():
    _, owner, oh = owner_client()
    _, email = add_staff(owner, oh, role="sales")
    staff, _ = staff_client(email)
    session = staff.get("/api/session").json()
    assert session["access"]["pages"] == ["sales"] and session["access"]["role_label"] == "Sales"
    assert session["user"]["business_owner"]


def test_owner_sees_everything_and_can_reset_a_staff_password():
    _, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="sales")
    staff_id = created.json()["id"]
    assert owner.get("/api/session").json()["access"]["pages"] == sorted(["budget", "dashboard", "expenses", "inventory", "profile", "reports", "sales", "website"])
    changed = owner.put(f"/api/staff/{staff_id}", json={"password": "NewPass999"}, headers=oh)
    assert changed.status_code == 200
    assert staff_client(email, "NewPass999")[0] is not None


def test_owner_can_change_a_role_and_the_change_applies_at_once():
    _, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="sales")
    staff, sh = staff_client(email)
    assert staff.get("/api/inventory-presets").status_code == 200
    assert staff.post("/api/inventory-presets", json={"item_name": "X", "price": 1, "stock": 1}, headers=sh).status_code == 403
    owner.put(f"/api/staff/{created.json()['id']}", json={"role": "inventory"}, headers=oh)
    assert staff.post("/api/inventory-presets", json={"item_name": "X", "price": 1, "stock": 1}, headers=sh).status_code == 201
    assert staff.get("/api/income").status_code == 403


def test_removed_staff_cannot_use_the_app_again():
    _, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="sales")
    staff, sh = staff_client(email)
    assert owner.delete(f"/api/staff/{created.json()['id']}", headers=oh).status_code == 200
    assert staff.get("/api/income").status_code == 401
    assert sign_in(new_client(), email, "Staff1234")[0].status_code == 401


def test_seats_follow_the_plan():
    _, owner, oh = owner_client(plan="basic")          # 3 seats
    for n in range(3):
        assert add_staff(owner, oh, role="sales")[0].status_code == 200
    blocked = add_staff(owner, oh, role="sales")[0]
    assert blocked.status_code == 403 and blocked.json()["code"] == "upgrade_required"
    listing = owner.get("/api/staff").json()
    assert listing["seats"] == {"used": 3, "limit": 3}


def test_free_plan_has_no_staff_seats():
    user, owner, oh = owner_client(plan=None)
    subs.ensure_subscription(user[0], datetime.now(timezone.utc) - timedelta(days=60))   # trial long over: Free
    response = add_staff(owner, oh, role="sales")[0]
    assert response.status_code == 403 and response.json()["code"] == "upgrade_required"


def test_downgrade_switches_staff_off_until_the_owner_upgrades():
    user, owner, oh = owner_client(plan="basic")
    _, email = add_staff(owner, oh, role="sales")
    staff, sh = staff_client(email)
    assert staff.get("/api/income").status_code == 200
    with get_db() as db:
        db.execute("UPDATE subscriptions SET plan = 'free', period_end = NULL, trial_ends_at = NULL WHERE user_id = ?", (user[0],))
        db.commit()
    assert staff.get("/api/income").status_code == 403
    subs.activate(user[0], "basic")
    assert staff.get("/api/income").status_code == 200


def test_staff_cannot_create_a_duplicate_or_weak_account():
    _, owner, oh = owner_client()
    created, email = add_staff(owner, oh, role="sales")
    again = owner.post("/api/staff", json={"name": "Dup", "email": email, "password": "Staff1234", "role": "sales"}, headers=oh)
    assert again.status_code == 400
    weak = owner.post("/api/staff", json={"name": "Weak", "email": "weak@example.com", "password": "short", "role": "sales"}, headers=oh)
    assert weak.status_code == 400
