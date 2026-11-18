"""Plans API, Flutterwave checkout, callback and webhook (Flutterwave is mocked)."""

import itertools

import pytest

from api import flutterwave as flw
from api import subscriptions as subs
from server.database import get_db


class FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("FLW_SECRET_KEY", "FLWSECK_TEST-x")
    monkeypatch.setenv("FLW_SECRET_HASH", "hash-123")


@pytest.fixture
def flutterwave(monkeypatch, keys):
    """Replace the HTTP calls. `server.transactions` is what verification returns."""
    state = {"calls": [], "transactions": {}, "plan_seq": 0}
    with get_db() as db:
        db.execute("DELETE FROM provider_plans")
        db.commit()

    def fake(method, url, **kw):
        path = url.split("/v3", 1)[1]
        state["calls"].append((method, path, kw))
        if path == "/payment-plans":
            state["plan_seq"] += 1
            return FakeResponse({"status": "success", "data": {"id": 9000 + state["plan_seq"]}})
        if path == "/payments":
            return FakeResponse({"status": "success", "data": {"link": "https://checkout.flutterwave.com/v3/hosted/pay/abc"}})
        if path == "/transactions/verify_by_reference":
            tx = state["transactions"].get(kw["params"]["tx_ref"])
            return FakeResponse({"status": "success", "data": tx}) if tx else FakeResponse({"status": "error", "message": "No transaction"}, 404)
        if path.startswith("/transactions/") and path.endswith("/verify"):
            tx = state["transactions"].get(path.split("/")[2])
            return FakeResponse({"status": "success", "data": tx})
        if path == "/subscriptions":
            return FakeResponse({"status": "success", "data": [{"id": 55}]})
        if path.startswith("/subscriptions/"):
            return FakeResponse({"status": "success", "data": {}})
        return FakeResponse({"status": "error", "message": "unexpected"}, 500)

    monkeypatch.setattr(flw.requests, "request", fake)
    return state


def start_checkout(client, token, plan="basic"):
    response = client.post("/api/subscription/checkout", json={"plan": plan}, headers={"X-CSRFToken": token})
    with get_db() as db:
        tx_ref = db.execute("SELECT tx_ref FROM payments ORDER BY id DESC LIMIT 1").fetchone()["tx_ref"]
    return response, tx_ref


_ids = itertools.count(1000)


def tx(tx_ref, amount=2500, status="successful", tx_id=None, **extra):
    tx_id = tx_id or next(_ids)
    return {"id": tx_id, "tx_ref": tx_ref, "amount": amount, "currency": "NGN", "status": status, **extra}


def test_subscription_endpoint_lists_plans_and_current_state(client, signed_in):
    body = client.get("/api/subscription").json()
    assert [p["key"] for p in body["plans"]] == ["free", "basic", "pro"]
    assert body["current"]["state"] == "trial" and body["current"]["plan"] == "pro"
    assert body["payments_ready"] is False
    assert body["plans"][2]["features"]["website"] is True and body["plans"][1]["features"]["website"] is False


def test_subscription_requires_sign_in(client):
    assert client.get("/api/subscription").status_code == 401


def test_checkout_says_not_set_up_without_keys(client, signed_in):
    response = client.post("/api/subscription/checkout", json={"plan": "basic"}, headers={"X-CSRFToken": signed_in[1]})
    assert response.status_code == 503


def test_checkout_rejects_unknown_plans(client, signed_in, keys):
    for plan in ("free", "gold", ""):
        assert client.post("/api/subscription/checkout", json={"plan": plan}, headers={"X-CSRFToken": signed_in[1]}).status_code == 400


def test_checkout_creates_a_recurring_plan_once_and_returns_the_link(client, signed_in, flutterwave):
    response, _ = start_checkout(client, signed_in[1])
    assert response.status_code == 200 and response.json()["link"].startswith("https://checkout.flutterwave.com/")
    start_checkout(client, signed_in[1])
    plan_calls = [c for c in flutterwave["calls"] if c[1] == "/payment-plans"]
    assert len(plan_calls) == 1 and plan_calls[0][2]["json"]["interval"] == "monthly"
    sent = [c for c in flutterwave["calls"] if c[1] == "/payments"][0][2]["json"]
    assert sent["amount"] == 2500 and sent["currency"] == "NGN" and sent["payment_plan"] == "9001"
    assert sent["customer"]["email"] and sent["redirect_url"].endswith("/billing/callback")


def test_callback_verifies_with_flutterwave_then_activates(client, signed_in, flutterwave):
    user_id = signed_in[0]
    _, tx_ref = start_checkout(client, signed_in[1])
    flutterwave["transactions"][tx_ref] = tx(tx_ref)
    redirect = client.get(f"/billing/callback?status=successful&tx_ref={tx_ref}&transaction_id=111")
    assert redirect.status_code == 303 and redirect.headers["location"] == "/plans?payment=success"
    ent = subs.entitlements(user_id)
    assert (ent["plan"], ent["state"]) == ("basic", "active")
    again = client.get(f"/billing/callback?status=successful&tx_ref={tx_ref}")
    assert again.headers["location"] == "/plans?payment=success"
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM payments WHERE status = 'successful' AND user_id = ?", (user_id,)).fetchone()["n"] == 1


def test_callback_does_not_trust_the_address(client, signed_in, flutterwave):
    user_id = signed_in[0]
    _, tx_ref = start_checkout(client, signed_in[1])
    flutterwave["transactions"][tx_ref] = tx(tx_ref, status="failed")
    redirect = client.get(f"/billing/callback?status=successful&tx_ref={tx_ref}")
    assert redirect.headers["location"] == "/plans?payment=failed"
    assert subs.entitlements(user_id)["state"] == "trial"       # nothing was activated


def test_amount_too_low_is_not_activated(client, signed_in, flutterwave):
    user_id = signed_in[0]
    _, tx_ref = start_checkout(client, signed_in[1], "pro")
    flutterwave["transactions"][tx_ref] = tx(tx_ref, amount=100)
    assert client.get(f"/billing/callback?status=successful&tx_ref={tx_ref}").headers["location"] == "/plans?payment=failed"
    assert subs.entitlements(user_id)["plan"] == "pro" and subs.entitlements(user_id)["state"] == "trial"


def test_cancelled_checkout_goes_back_to_plans(client, signed_in, keys):
    assert client.get("/billing/callback?status=cancelled&tx_ref=x").headers["location"] == "/plans?payment=cancelled"


def test_webhook_needs_the_secret_hash(client, keys):
    body = {"event": "charge.completed", "data": {"id": 111}}
    assert client.post("/api/billing/webhook", json=body).status_code == 401
    assert client.post("/api/billing/webhook", json=body, headers={"verif-hash": "wrong"}).status_code == 401


def test_webhook_activates_once_without_a_session_or_csrf_token(client, signed_in, flutterwave):
    user_id = signed_in[0]
    _, tx_ref = start_checkout(client, signed_in[1], "pro")
    paid = tx(tx_ref, amount=6000)
    flutterwave["transactions"][str(paid["id"])] = paid
    body = {"event": "charge.completed", "data": {"id": paid["id"], "tx_ref": tx_ref, "status": "successful"}}
    from tests.conftest import new_client

    anonymous = new_client()
    for _ in range(2):
        assert anonymous.post("/api/billing/webhook", json=body, headers={"verif-hash": "hash-123"}).status_code == 200
    ent = subs.entitlements(user_id)
    assert (ent["plan"], ent["state"]) == ("pro", "active")
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM payments WHERE provider_tx_id = ?", (str(paid["id"]),)).fetchone()["n"] == 1


def test_webhook_renewal_found_by_plan_and_email(client, signed_in, flutterwave):
    user_id = signed_in[0]
    _, tx_ref = start_checkout(client, signed_in[1])            # creates the provider plan row (id 9001)
    with get_db() as db:
        email = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()["email"]
    renewal = tx("flw-renewal-1", tx_id=4242, payment_plan="9001", customer={"email": email.upper()})
    flutterwave["transactions"]["4242"] = renewal
    body = {"event": "charge.completed", "data": {"id": 4242}}
    from tests.conftest import new_client

    assert new_client().post("/api/billing/webhook", json=body, headers={"verif-hash": "hash-123"}).status_code == 200
    assert subs.entitlements(user_id)["state"] == "active"


def test_webhook_for_an_unknown_account_is_ignored(client, flutterwave):
    flutterwave["transactions"]["333"] = tx("someone-else", tx_id=333, payment_plan="404", customer={"email": "nobody@example.com"})
    from tests.conftest import new_client

    response = new_client().post("/api/billing/webhook", json={"event": "charge.completed", "data": {"id": 333}}, headers={"verif-hash": "hash-123"})
    assert response.status_code == 200


def test_cancel_keeps_the_plan_until_the_period_ends(client, signed_in, flutterwave):
    user_id = signed_in[0]
    subs.activate(user_id, "basic")
    response = client.post("/api/subscription/cancel", headers={"X-CSRFToken": signed_in[1]})
    assert response.status_code == 200 and response.json()["current"]["cancel_at_period_end"] is True
    assert any(c[0] == "PUT" and c[1] == "/subscriptions/55/cancel" for c in flutterwave["calls"])
    assert subs.entitlements(user_id)["plan"] == "basic"


def test_cancel_without_a_paid_plan_is_refused(client, signed_in):
    assert client.post("/api/subscription/cancel", headers={"X-CSRFToken": signed_in[1]}).status_code == 400
