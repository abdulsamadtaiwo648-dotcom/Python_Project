"""Opening or refreshing /money-in directly must serve the app, like the other app pages."""


def test_money_in_needs_sign_in_when_signed_out(client):
    response = client.get("/money-in")
    assert response.status_code == 302 and response.headers["location"] == "/login"


def test_money_in_serves_the_app_shell_when_signed_in(client, signed_in):
    response = client.get("/money-in")
    assert response.status_code == 200 and "id=root" in response.text


def test_money_in_refresh_keeps_working(client, signed_in):
    # A refresh is the same request again; the page must not depend on a previous visit.
    for _ in range(2):
        assert client.get("/money-in").status_code == 200
