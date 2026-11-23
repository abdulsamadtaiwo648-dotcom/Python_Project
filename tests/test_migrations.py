"""The schema migration runner: each step runs once, failures are not recorded."""

import pytest

from server import database
from server.database import get_db, run_migrations


def _recorded():
    with get_db() as db:
        return [r["version"] for r in db.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()]


def _forget(*versions):
    with get_db() as db:
        for v in versions:
            db.execute("DELETE FROM schema_migrations WHERE version = ?", (v,))
        db.commit()


def test_steps_run_once_and_are_recorded():
    calls = []
    steps = [("9001_test_a", lambda: calls.append("a")), ("9002_test_b", lambda: calls.append("b"))]
    _forget("9001_test_a", "9002_test_b")
    assert run_migrations(steps) == ["9001_test_a", "9002_test_b"]
    assert run_migrations(steps) == []
    assert calls == ["a", "b"]
    assert {"9001_test_a", "9002_test_b"} <= set(_recorded())
    _forget("9001_test_a", "9002_test_b")


def test_a_failing_step_is_not_recorded_and_the_error_is_raised():
    def boom():
        raise RuntimeError("disk on fire")

    _forget("9010_boom")
    with pytest.raises(RuntimeError):
        run_migrations([("9010_boom", boom)])
    assert "9010_boom" not in _recorded()


def test_a_step_that_is_not_ready_waits_for_next_start():
    state = {"ready": False}

    def later():
        return state["ready"] or False

    _forget("9020_later")
    assert run_migrations([("9020_later", later)]) == []
    assert "9020_later" not in _recorded()
    state["ready"] = True
    assert run_migrations([("9020_later", later)]) == ["9020_later"]
    _forget("9020_later")


def test_startup_applies_the_real_migrations_only_once(monkeypatch):
    calls = []
    real_baseline = database._baseline_schema
    monkeypatch.setattr(database, "_baseline_schema", lambda: calls.append(1) or real_baseline())
    monkeypatch.setattr(database, "MIGRATIONS", [("0001_baseline", database._baseline_schema), ("0002_drop_floor_tables", database._drop_floor_tables)])
    monkeypatch.delenv("DROP_FLOOR_TABLES", raising=False)
    _forget("0002_drop_floor_tables")          # another test may have set the flag earlier
    database.init_db()
    database.init_db()
    assert calls == []                             # baseline is already recorded, so it does not run again
    assert "0001_baseline" in _recorded()
    assert "0002_drop_floor_tables" not in _recorded()    # waiting for the flag
