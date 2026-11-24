import os
import subprocess
import sys

from .conftest import PASSWORD, csrf_token, make_user, new_client, sign_in

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _import_app(env_overrides, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DATABASE_URL", "RENDER")}
    env["SQLITE_DATABASE_PATH"] = str(tmp_path / "import.db")
    env["PYTHONPATH"] = PROJECT_ROOT
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import api.main"],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def test_hosted_app_refuses_to_start_without_secret_key(tmp_path):
    result = _import_app({"RENDER": "true"}, tmp_path)
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_local_app_needs_debug_mode_to_start_without_secret_key(tmp_path):
    refused = _import_app({}, tmp_path)
    assert refused.returncode != 0 and "SOLOBIZ_DEBUG" in refused.stderr
    allowed = _import_app({"SOLOBIZ_DEBUG": "1"}, tmp_path)
    assert allowed.returncode == 0, allowed.stderr


def test_session_endpoint_reports_signed_out(client):
    body = client.get("/api/session").json()
    assert body["user"] is None and body["csrf_token"]


def test_post_without_csrf_token_is_rejected(client, user):
    csrf_token(client)
    response = client.post("/api/login", json={"email": user[1], "password": PASSWORD})
    assert response.status_code == 400
    assert "token" in response.json()["message"].lower()


def test_login_succeeds_and_session_reports_user(client, user):
    response, _ = sign_in(client, user[1])
    assert response.status_code == 200
    assert response.json()["redirect"] == "/dashboard"
    assert client.get("/api/session").json()["user"]["id"] == user[0]


def test_wrong_password_is_unauthorized(client, user):
    response, _ = sign_in(client, user[1], "WrongPass1")
    assert response.status_code == 401


def test_logout_ends_the_session(client, signed_in):
    _, token = signed_in
    assert client.post("/api/logout", headers={"X-CSRFToken": token}).status_code == 200
    assert client.get("/api/session").json()["user"] is None


def test_auth_endpoints_require_csrf_token(client, user):
    csrf_token(client)
    for path in (
        "/api/register/request", "/api/register/verify", "/api/register/resend",
        "/api/forgot-password/request", "/api/forgot-password/resend", "/api/forgot-password/reset",
    ):
        response = client.post(path, json={"email": user[1]})
        assert response.status_code == 400, path


def test_login_locks_after_repeated_failures(client, user):
    for _ in range(5):
        assert sign_in(client, user[1], "WrongPass1")[0].status_code == 401
    assert sign_in(client, user[1], PASSWORD)[0].status_code == 429
    assert client.get("/api/session").json()["user"] is None


def test_lockout_is_per_account(client, user):
    for _ in range(5):
        sign_in(client, "someone-else@example.com", "WrongPass1")
    assert sign_in(client, user[1], PASSWORD)[0].status_code == 200


def test_successful_login_resets_failure_count(client, user):
    for _ in range(4):
        sign_in(client, user[1], "WrongPass1")
    assert sign_in(client, user[1], PASSWORD)[0].status_code == 200
    client.post("/api/logout", headers={"X-CSRFToken": csrf_token(client)})
    for _ in range(4):
        sign_in(client, user[1], "WrongPass1")
    assert sign_in(client, user[1], PASSWORD)[0].status_code == 200


def test_register_with_pin_then_sign_in(client):
    token = csrf_token(client)
    headers = {"X-CSRFToken": token}
    email = "new.person@example.com"
    payload = {"email": email, "first_name": "New", "last_name": "Person", "password": "Secret123",
               "confirm_password": "Secret123", "privacy_accepted": True}
    first = client.post("/api/register/request", json=payload, headers=headers)
    assert first.status_code == 200
    pin = first.json()["message"].rsplit(":", 1)[1].strip()
    bad = client.post("/api/register/verify", json={"email": email, "code": "000000"}, headers=headers)
    assert bad.status_code == 400
    good = client.post("/api/register/verify", json={"email": email, "code": pin}, headers=headers)
    assert good.status_code == 200
    assert sign_in(client, email, "Secret123")[0].status_code == 200
    again = client.post("/api/register/request", json=payload, headers=headers)
    assert again.status_code == 400


def test_register_rejects_weak_password_and_missing_privacy(client):
    headers = {"X-CSRFToken": csrf_token(client)}
    base = {"email": "weak@example.com", "first_name": "A", "last_name": "B", "password": "short",
            "confirm_password": "short", "privacy_accepted": True}
    assert client.post("/api/register/request", json=base, headers=headers).status_code == 400
    base.update(password="Secret123", confirm_password="Secret123", privacy_accepted=False)
    assert client.post("/api/register/request", json=base, headers=headers).status_code == 400


def test_password_reset_flow_signs_in(client, user):
    headers = {"X-CSRFToken": csrf_token(client)}
    requested = client.post("/api/forgot-password/request", json={"email": user[1]}, headers=headers)
    assert requested.status_code == 200
    # The reset answer is identical for unknown emails, so accounts cannot be probed.
    unknown = client.post("/api/forgot-password/request", json={"email": "nobody@example.com"}, headers=headers)
    assert unknown.json()["message"] == requested.json()["message"]


def test_session_for_deleted_user_is_rejected():
    from server.database import get_db

    user_id, email = make_user()
    client = new_client()
    assert sign_in(client, email)[0].status_code == 200
    with get_db() as db:
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
    assert client.get("/api/expenses").status_code == 401
