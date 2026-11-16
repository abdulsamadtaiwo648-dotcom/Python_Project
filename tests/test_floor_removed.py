"""The Floor feature and its tables are gone."""

from server.app import get_db
from server.database import init_db

FLOOR_TABLES = ("market_mood", "street_tip", "sabi_plug_request", "sabi_plug_recommendation", "community_vote")


def _tables():
    with get_db() as db:
        return {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}


def test_floor_tables_are_kept_until_the_flag_is_set(monkeypatch):
    monkeypatch.delenv("DROP_FLOOR_TABLES", raising=False)
    with get_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS street_tip (id INTEGER PRIMARY KEY)")
        db.commit()
    init_db()
    assert "street_tip" in _tables()        # an older release can still use it


def test_startup_drops_floor_tables(monkeypatch):
    monkeypatch.setenv("DROP_FLOOR_TABLES", "1")
    with get_db() as db:
        db.execute("CREATE TABLE IF NOT EXISTS sabi_plug_request (id INTEGER PRIMARY KEY, request_text TEXT)")
        db.execute(
            "CREATE TABLE IF NOT EXISTS sabi_plug_recommendation (id INTEGER PRIMARY KEY, "
            "request_id INTEGER REFERENCES sabi_plug_request(id) ON DELETE CASCADE)"
        )
        for table in ("market_mood", "street_tip", "community_vote"):
            db.execute(f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO street_tip (id) VALUES (1)")
        db.commit()
    assert set(FLOOR_TABLES) <= _tables()

    init_db()

    assert not set(FLOOR_TABLES) & _tables()
    assert {"users", "income", "expenses", "inventory_presets"} <= _tables()


def test_floor_pages_are_gone(client, signed_in):
    assert client.get("/floor").status_code == 404
    assert "The Floor" not in client.get("/dashboard").get_data(as_text=True)


def test_health_check(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok" and body["version"]
