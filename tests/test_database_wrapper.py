"""PostgreSQL INSERT rewriting (checked with a fake connection, no server needed)."""

import pytest

from server import database
from server.database import DBWrapper


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.rows = conn, []

    def execute(self, sql, params=()):
        self.conn.executed.append(sql)
        if "information_schema.columns" in sql:
            self.rows = [(1,)] if params[0] in self.conn.tables_with_id else []
        elif "RETURNING id" in sql:
            self.rows = [(42,)]
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConn:
    def __init__(self, tables_with_id):
        self.tables_with_id, self.executed = tables_with_id, []

    def cursor(self):
        return FakeCursor(self)


@pytest.fixture(autouse=True)
def fresh_cache():
    database._TABLE_HAS_ID.clear()
    yield
    database._TABLE_HAS_ID.clear()


def inserts(conn):
    return [q for q in conn.executed if q.lstrip().upper().startswith("INSERT")]


def test_insert_into_a_table_with_an_id_asks_for_it_back():
    conn = FakeConn({"expenses"})
    cursor = DBWrapper(conn, is_postgres=True).execute("INSERT INTO expenses (user_id) VALUES (?)", ("u",))
    assert inserts(conn)[0].endswith("RETURNING id") and cursor.lastrowid == 42


@pytest.mark.parametrize("table", ["subscriptions", "client_ops", "provider_plans", "otp_codes", "user_login_attempts"])
def test_tables_without_an_id_are_not_asked_for_one(table):
    conn = FakeConn({"expenses"})
    DBWrapper(conn, is_postgres=True).execute(f"INSERT INTO {table} (a) VALUES (?)", ("x",))
    assert "RETURNING" not in inserts(conn)[0]


def test_an_unknown_table_is_looked_up_once_and_remembered():
    conn = FakeConn(set())
    wrapper = DBWrapper(conn, is_postgres=True)
    wrapper.execute("INSERT INTO brand_new_table (a) VALUES (?)", ("x",))
    wrapper.execute("INSERT INTO brand_new_table (a) VALUES (?)", ("y",))
    assert all("RETURNING" not in q for q in inserts(conn))
    assert sum("information_schema" in q for q in conn.executed) == 1


def test_an_existing_returning_clause_is_left_alone():
    conn = FakeConn({"expenses"})
    DBWrapper(conn, is_postgres=True).execute("INSERT INTO expenses (a) VALUES (?) RETURNING id", ("x",))
    assert inserts(conn)[0].count("RETURNING") == 1
