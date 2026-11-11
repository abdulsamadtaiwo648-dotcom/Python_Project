"""Regression tests for the secret key, CSRF and login rate-limit fixes."""

import os
import subprocess
import sys

from tests.conftest import PASSWORD, csrf_token

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _import_app(env_overrides, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("SECRET_KEY", "DATABASE_URL", "RENDER")}
    env["SQLITE_DATABASE_PATH"] = str(tmp_path / "import.db")
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", "import server.app"],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def test_hosted_app_refuses_to_start_without_secret_key(tmp_path):
    result = _import_app({"RENDER": "true"}, tmp_path)
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_local_app_starts_without_secret_key(tmp_path):
    result = _import_app({}, tmp_path)
    assert result.returncode == 0, result.stderr


def test_old_hardcoded_key_is_gone():
    with open(os.path.join(PROJECT_ROOT, "server", "app.py"), encoding="utf-8") as handle:
        assert "solobiz_production_secret_key" not in handle.read()


# --- CSRF -------------------------------------------------------------------

def test_login_without_csrf_token_is_rejected(client, user):
    csrf_token(client)
    response = client.post("/login", data={"email": user[1], "password": PASSWORD})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_login_with_csrf_token_succeeds(client, user):
    token = csrf_token(client)
    response = client.post(
        "/login", data={"email": user[1], "password": PASSWORD, "csrf_token": token}
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as sess:
        assert sess["user_id"] == user[0]


def test_register_form_without_csrf_token_is_rejected(client):
    csrf_token(client)
    response = client.post("/register", data={"email": "new@example.com"})
    assert response.status_code == 302


def test_auth_json_endpoints_require_csrf_token(client, user):
    csrf_token(client)
    for path in (
        "/api/register/request",
        "/api/register/verify",
        "/api/register/resend",
        "/api/forgot-password/request",
        "/api/forgot-password/resend",
        "/api/forgot-password/reset",
    ):
        response = client.post(path, json={"email": user[1]})
        assert response.status_code == 400, path
        assert "token" in response.get_json()["message"].lower(), path


def test_forgot_password_request_works_with_csrf_header(client, user):
    token = csrf_token(client)
    response = client.post(
        "/api/forgot-password/request", json={"email": user[1]}, headers={"X-CSRFToken": token}
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_auth_pages_send_csrf_header():
    templates = os.path.join(PROJECT_ROOT, "client", "templates")
    for name in ("login.html", "register.html"):
        with open(os.path.join(templates, name), encoding="utf-8") as handle:
            source = handle.read()
        assert "await fetch(" not in source, name
        assert "X-CSRFToken" in source, name


# --- Login rate limiting ----------------------------------------------------

def _login(client, email, password):
    token = csrf_token(client)
    return client.post("/login", data={"email": email, "password": password, "csrf_token": token})


def test_login_locks_after_repeated_failures(client, user):
    for _ in range(5):
        assert _login(client, user[1], "WrongPass1").status_code == 200
    # Even the correct password is refused while locked.
    locked = _login(client, user[1], PASSWORD)
    assert locked.status_code == 429
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_lockout_applies_to_unknown_emails_too(client):
    for _ in range(5):
        _login(client, "nobody-here@example.com", "WrongPass1")
    assert _login(client, "nobody-here@example.com", "WrongPass1").status_code == 429


def test_lockout_is_per_account(client, user):
    for _ in range(5):
        _login(client, "someone-else@example.com", "WrongPass1")
    assert _login(client, user[1], PASSWORD).status_code == 302


def test_successful_login_resets_failure_count(client, user):
    for _ in range(4):
        _login(client, user[1], "WrongPass1")
    assert _login(client, user[1], PASSWORD).status_code == 302
    client.get("/logout")
    for _ in range(4):
        _login(client, user[1], "WrongPass1")
    assert _login(client, user[1], PASSWORD).status_code == 302
