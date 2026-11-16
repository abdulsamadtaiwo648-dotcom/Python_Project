"""Regression tests for the remaining review items."""

import io

from tests.conftest import PASSWORD, csrf_token
from server.app import get_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _login(client, email, password):
    return client.post("/login", data={"email": email, "password": password, "csrf_token": csrf_token(client)})


def test_logout_needs_a_post_with_csrf(client, signed_in):
    user_id, token = signed_in
    assert client.get("/logout").status_code == 302            # a link cannot sign you out
    with client.session_transaction() as sess:
        assert sess.get("user_id") == user_id
    assert client.post("/logout").status_code in (302, 400)     # no token: refused
    with client.session_transaction() as sess:
        assert sess.get("user_id") == user_id
    client.post("/logout", headers={"X-CSRFToken": token})
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_password_reset_does_not_reveal_which_emails_exist(client, user):
    token = csrf_token(client)
    body = {"code": "123456", "password": "NewPassword1"}
    unknown = client.post("/api/forgot-password/reset", json={**body, "email": "nobody@example.com"}, headers={"X-CSRFToken": token})
    known = client.post("/api/forgot-password/reset", json={**body, "email": user[1]}, headers={"X-CSRFToken": token})
    assert unknown.status_code == known.status_code == 400
    assert unknown.get_json()["message"] == known.get_json()["message"]


def test_user_count_page_is_gone(client):
    assert client.get("/user-count").status_code == 404


def test_removed_legacy_pages(client, signed_in):
    token = signed_in[1]
    assert client.post("/search", data={"csrf_token": token}).status_code in (404, 405)
    assert client.post("/calculate", data={"csrf_token": token}).status_code in (404, 405)


def test_passwords_keep_their_spaces_and_old_accounts_still_sign_in(client, user):
    # `user` was created the old way: its hash is of the trimmed password.
    assert _login(client, user[1], PASSWORD + " ").status_code == 302
    client.post("/logout", data={"csrf_token": csrf_token(client)})

    from werkzeug.security import generate_password_hash
    with get_db() as db:
        db.execute("UPDATE users SET password = ? WHERE id = ?", (generate_password_hash(" spaced Pass1 "), user[0]))
        db.commit()
    assert _login(client, user[1], "spaced Pass1").status_code == 200      # trimmed version is wrong
    assert _login(client, user[1], " spaced Pass1 ").status_code == 302


def test_profile_logo_is_stored_in_the_database(client, signed_in, monkeypatch):
    monkeypatch.setenv("ALLOW_DEV_OTP", "1")
    user_id, token = signed_in
    headers = {"X-CSRFToken": token}
    with get_db() as db:
        email = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()["email"]
    from server.app import upsert_otp
    code, _ = upsert_otp(email, "profile")
    response = client.post("/api/business_profile", data={
        "company_name": "Logo Test", "business_phone": "+2348010000000", "business_address": "Lagos",
        "otp": code, "logo": (io.BytesIO(PNG), "logo.png"),
    }, headers=headers, content_type="multipart/form-data")
    assert response.status_code == 200, response.get_json()
    logo_url = response.get_json()["profile"]["logo_url"]
    assert logo_url.startswith("/media/")
    assert client.get(logo_url).mimetype == "image/png"

    bad = client.post("/api/business_profile", data={
        "company_name": "Logo Test", "business_phone": "+2348010000000", "business_address": "Lagos",
        "otp": "000000", "logo": (io.BytesIO(b"not an image"), "logo.png"),
    }, headers=headers, content_type="multipart/form-data")
    assert bad.status_code == 400


def test_avatar_svg_escapes_names(client, signed_in):
    with get_db() as db:
        db.execute("DELETE FROM business_profiles WHERE store_slug = 'xss-co'")
        db.execute("INSERT INTO business_profiles (user_id, company_name, store_slug, brand_color) VALUES (?, ?, ?, ?)",
                   (signed_in[0], "<&", "xss-co", "#zzzzzz"))
        db.commit()
    svg = client.get("/api/avatar/xss-co").get_data(as_text=True)
    assert "&lt;&amp;" in svg and "<&" not in svg
    assert 'fill="#1D4ED8"' in svg


def test_synced_sales_with_bad_dates_get_a_real_date(client, signed_in):
    headers = {"X-CSRFToken": signed_in[1]}
    client.post("/api/sync-sales", json={"sales": [
        {"description": "Bad date", "total_value": 100, "amount_paid": 100, "date": "yesterday-ish"},
        {"description": "Good date", "total_value": 100, "amount_paid": 100, "date": "2026-01-05T10:00:00.000Z"},
    ]}, headers=headers)
    income = {i["description"]: i["date"] for i in client.get("/api/income").get_json()["income"]}
    assert income["Good date"].startswith("2026-01-05")
    assert income["Bad date"][:4].isdigit() and income["Bad date"][4] == "-"
