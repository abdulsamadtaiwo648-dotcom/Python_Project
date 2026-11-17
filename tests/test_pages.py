"""Server-rendered pages and the React app shell."""


def test_landing_page_is_server_rendered(client):
    page = client.get("/")
    assert page.status_code == 200 and "SoloBiz" in page.text


def test_public_pages_render(client):
    for path in ("/privacy", "/data-access", "/robots.txt", "/sitemap.xml", "/sw.js"):
        assert client.get(path).status_code == 200, path


def test_app_pages_need_sign_in(client):
    for path in ("/dashboard", "/sales", "/inventory", "/expenses", "/budget", "/profile", "/reports", "/website"):
        response = client.get(path)
        assert response.status_code == 302 and response.headers["location"] == "/login", path


def test_signed_in_users_get_the_app_shell(client, signed_in):
    for path in ("/dashboard", "/sales", "/website"):
        response = client.get(path)
        assert response.status_code == 200 and 'id=root' in response.text, path
    # Already signed in: the sign-in page and landing page go to the app.
    assert client.get("/login").headers["location"] == "/dashboard"
    assert client.get("/").headers["location"] == "/dashboard"


def test_sign_in_page_serves_the_shell_when_signed_out(client):
    response = client.get("/login")
    assert response.status_code == 200 and "no-store" in response.headers["cache-control"]


def test_unknown_page_is_a_404_page_and_unknown_api_is_json(client):
    assert client.get("/nope").status_code == 404 and "text/html" in client.get("/nope").headers["content-type"]
    api = client.get("/api/nope")
    assert api.status_code == 404 and api.json()["status"] == "error"


def test_service_worker_carries_the_version(client):
    body = client.get("/sw.js")
    assert "application/javascript" in body.headers["content-type"] and "solobiz-offline-" in body.text


def test_health_check(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
