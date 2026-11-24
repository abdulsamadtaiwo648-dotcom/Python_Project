"""API input that carries script or active markup is refused before any route runs."""

import pytest

from api.input_guard import find_unsafe


@pytest.mark.parametrize("value", [
    "<script>alert(1)</script>",
    "<SCRIPT src=x>",
    "<img src=x onerror=alert(1)>",
    '<a href="javascript:alert(1)">x</a>',
    '<div onclick="steal()">',
    "<iframe src=evil></iframe>",
    "data:text/html,<h1>hi</h1>",
])
def test_active_markup_is_flagged(value):
    assert find_unsafe({"customer_name": value}) == "customer_name"


def test_nested_values_report_their_location():
    assert find_unsafe({"items": [{"name": "<iframe>"}]}) == "items[0].name"


@pytest.mark.parametrize("value", [
    "Ahmed Ali",
    "Rice & beans",
    "Price < 5",
    "one = 1",
    "season = winter",
    "<b>bold</b>",
])
def test_ordinary_text_is_allowed(value):
    assert find_unsafe({"description": value}) is None


def test_guarded_endpoint_refuses_script_before_auth(client):
    response = client.post("/api/sales/checkout", json={"customer_name": "<script>alert(1)</script>"})
    assert response.status_code == 400
    assert "customer_name" in response.json()["message"]
    assert "<script>" not in response.text


def test_oversize_body_is_refused(client):
    response = client.post("/api/sales/checkout", json={"d": "a" * 1_100_000})
    assert response.status_code == 413
