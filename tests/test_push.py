"""Push notifications for stock alerts."""

import base64
import json
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from server import push
from server.app import get_db
from server.tools.generate_vapid_keys import generate

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def browser_keys():
    """A subscription's keys, made the way a browser makes them."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    auth = os.urandom(16)
    return private_key, {"p256dh": _b64(public), "auth": _b64(auth)}, auth


@pytest.fixture
def vapid(monkeypatch):
    public_key, private_key = generate()
    monkeypatch.setenv("VAPID_PUBLIC_KEY", public_key)
    monkeypatch.setenv("VAPID_PRIVATE_KEY", private_key)
    monkeypatch.setenv("VAPID_SUBJECT", "mailto:alerts@example.com")
    monkeypatch.setattr(push, "SEND_INLINE", True)
    return public_key


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(push, "webpush", lambda **kwargs: calls.append(kwargs))
    return calls


@pytest.fixture
def headers(signed_in):
    return {"X-CSRFToken": signed_in[1]}


def _subscribe(client, headers, endpoint=ENDPOINT, keys=None):
    keys = keys or browser_keys()[1]
    return client.post(
        "/api/push/subscribe", json={"subscription": {"endpoint": endpoint, "keys": keys}}, headers=headers
    )


def _add_product(client, headers, stock=6, threshold=3, name="Jogger"):
    return client.post(
        "/api/inventory-presets",
        json={"item_name": name, "price": 3000, "stock": stock, "low_stock_threshold": threshold},
        headers=headers,
    ).get_json()["preset"]


def _sell(client, headers, preset, quantity, checkout_id):
    return client.post(
        "/api/checkout",
        json={"checkout_id": checkout_id, "amount_paid": 0,
              "items": [{"inventory_item_id": preset["id"], "quantity": quantity}]},
        headers=headers,
    )


def test_config_reports_disabled_without_keys(client, signed_in, monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    body = client.get("/api/push/config").get_json()
    assert body["enabled"] is False and body["public_key"] is None


def test_config_returns_public_key(client, signed_in, vapid):
    body = client.get("/api/push/config").get_json()
    assert body["enabled"] is True and body["public_key"] == vapid


def test_push_endpoints_require_sign_in(client, vapid):
    assert client.get("/api/push/config").status_code == 401


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/x",       # not https
    "https://127.0.0.1/steal",                      # internal address
    "https://evil.example.com/fcm.googleapis.com",  # not a push service
    "https://googleapis.com.evil.com/x",
])
def test_subscribe_rejects_non_push_service_endpoints(client, headers, vapid, endpoint):
    assert _subscribe(client, headers, endpoint=endpoint).status_code == 400


def test_subscribe_rejects_bad_keys(client, headers, vapid):
    assert _subscribe(client, headers, keys={"p256dh": "short", "auth": "x"}).status_code == 400


def test_sale_that_makes_stock_low_sends_notification(client, headers, signed_in, vapid, sent):
    assert _subscribe(client, headers).status_code == 200
    preset = _add_product(client, headers, stock=6, threshold=3)

    _sell(client, headers, preset, 2, "p1")       # 6 -> 4: still fine
    assert sent == []

    _sell(client, headers, preset, 2, "p2")       # 4 -> 2: low
    assert len(sent) == 1
    payload = json.loads(sent[0]["data"])
    assert payload["title"] == "Low stock: Jogger"
    assert "Only 2 left" in payload["body"]
    assert payload["url"] == "/inventory"
    assert sent[0]["subscription_info"]["endpoint"] == ENDPOINT

    _sell(client, headers, preset, 1, "p3")       # 2 -> 1: already low, no repeat
    assert len(sent) == 1

    _sell(client, headers, preset, 1, "p4")       # 1 -> 0: sold out
    assert json.loads(sent[1]["data"])["title"] == "Out of stock: Jogger"


def test_one_notification_per_product_in_a_sale(client, headers, vapid, sent):
    _subscribe(client, headers)
    a = _add_product(client, headers, stock=4, name="Jogger")
    b = _add_product(client, headers, stock=1, name="Cap")
    client.post("/api/checkout", json={"checkout_id": "multi", "amount_paid": 0, "items": [
        {"inventory_item_id": a["id"], "quantity": 2, "checkout_line_id": "a"},
        {"inventory_item_id": b["id"], "quantity": 1, "checkout_line_id": "b"},
    ]}, headers=headers)
    titles = sorted(json.loads(call["data"])["title"] for call in sent)
    assert titles == ["Low stock: Jogger", "Out of stock: Cap"]


def test_no_notifications_without_subscription(client, headers, vapid, sent):
    preset = _add_product(client, headers, stock=1)
    _sell(client, headers, preset, 1, "none")
    assert sent == []


def test_alerts_only_go_to_the_owners_devices(client, app, headers, vapid, sent):
    _subscribe(client, headers)
    other_id = "user_test_other_push"
    with get_db() as db:
        db.execute("INSERT INTO users (id, email) VALUES (?, ?)", (other_id, "other-push@example.com"))
        db.commit()
    with app.test_client() as other:
        with other.session_transaction() as sess:
            sess["user_id"] = other_id
            sess["csrf_token"] = "t"
        preset = other.post("/api/inventory-presets", json={"item_name": "X", "price": 1, "stock": 1},
                            headers={"X-CSRFToken": "t"}).get_json()["preset"]
        other.post("/api/checkout", json={"checkout_id": "o1", "amount_paid": 0,
                   "items": [{"inventory_item_id": preset["id"], "quantity": 1}]}, headers={"X-CSRFToken": "t"})
    assert sent == []


def test_same_device_moves_to_newly_signed_in_account(client, app, headers, signed_in, vapid):
    _subscribe(client, headers)
    other_id = "user_test_device_move"
    with get_db() as db:
        db.execute("INSERT INTO users (id, email) VALUES (?, ?)", (other_id, "device-move@example.com"))
        db.commit()
    with app.test_client() as other:
        with other.session_transaction() as sess:
            sess["user_id"] = other_id
            sess["csrf_token"] = "t"
        assert _subscribe(other, {"X-CSRFToken": "t"}).status_code == 200
    with get_db() as db:
        owners = [r["user_id"] for r in db.execute(
            "SELECT user_id FROM push_subscriptions WHERE endpoint = ?", (ENDPOINT,)).fetchall()]
    assert owners == [other_id]


def test_sign_out_stops_this_device_getting_alerts(client, headers, signed_in, vapid):
    _subscribe(client, headers)
    client.get("/logout")
    with get_db() as db:
        row = db.execute("SELECT 1 FROM push_subscriptions WHERE user_id = ?", (signed_in[0],)).fetchone()
    assert row is None


def test_unsubscribe(client, headers, signed_in, vapid):
    _subscribe(client, headers)
    assert client.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT}, headers=headers).status_code == 200
    with get_db() as db:
        assert db.execute("SELECT 1 FROM push_subscriptions WHERE user_id = ?", (signed_in[0],)).fetchone() is None


def test_expired_subscription_is_removed(client, headers, signed_in, vapid, monkeypatch):
    _subscribe(client, headers)

    class Gone:
        status_code = 410

    def fail(**kwargs):
        raise push.WebPushException("gone", response=Gone())

    monkeypatch.setattr(push, "webpush", fail)
    assert client.post("/api/push/test", headers=headers).status_code == 502
    with get_db() as db:
        assert db.execute("SELECT 1 FROM push_subscriptions WHERE user_id = ?", (signed_in[0],)).fetchone() is None


def test_real_encrypted_push_can_be_read_by_the_browser(client, headers, vapid, monkeypatch):
    """Runs the real pywebpush encryption and VAPID signing, captures the HTTP
    request instead of sending it, and decrypts it with the browser's keys."""
    import http_ece
    import requests

    browser_private, keys, auth = browser_keys()
    _subscribe(client, headers, keys=keys)
    captured = {}

    class Ok:
        status_code = 201
        text = ""

    def fake_post(url, data=None, headers=None, timeout=None, **kwargs):
        captured.update(url=url, data=data, headers=headers)
        return Ok()

    monkeypatch.setattr(requests, "post", fake_post)
    assert client.post("/api/push/test", headers=headers).get_json()["delivered"] == 1

    assert captured["url"] == ENDPOINT
    assert captured["headers"]["Authorization"].startswith("vapid t=")
    assert captured["headers"]["Content-Encoding"] == "aes128gcm"
    plaintext = http_ece.decrypt(captured["data"], private_key=browser_private, auth_secret=auth, version="aes128gcm")
    assert json.loads(plaintext)["title"] == "SoloBiz alerts are on"
