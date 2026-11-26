"""Migration 0010: default accounts, and the backfill of existing expenses and Money In. Rerunning it
must change nothing, and staff members must not get accounts of their own."""

from server import database
from server.database import get_db

from .conftest import make_user


def expense_row(user_id, account_id=None):
    with get_db() as db:
        db.execute("INSERT INTO expenses (user_id, amount, category, description, date, entry_date, account_id) "
                   "VALUES (?, 250, 'Others', 'Tea', '2026-01-12 09:00 AM', '2026-01-12', ?)", (user_id, account_id))
        db.commit()


def money_in_row(user_id, account_id=None):
    with get_db() as db:
        db.execute("INSERT INTO money_in (user_id, amount, kind, description, date, entry_date, account_id) "
                   "VALUES (?, 4000, 'Loan', 'Ada', '2026-01-13 09:00 AM', '2026-01-13', ?)", (user_id, account_id))
        db.commit()


def default_of(user_id):
    with get_db() as db:
        return db.execute("SELECT id FROM accounts WHERE user_id = ? AND is_default = 1", (user_id,)).fetchone()["id"]


def test_the_migration_can_be_run_again_without_changing_anything():
    user_id, _ = make_user()
    database._accounts()
    with get_db() as db:
        before = db.execute("SELECT COUNT(*) AS n FROM accounts WHERE user_id = ?", (user_id,)).fetchone()["n"]
    database._accounts()
    database._accounts()
    with get_db() as db:
        after = db.execute("SELECT COUNT(*) AS n FROM accounts WHERE user_id = ?", (user_id,)).fetchone()["n"]
    assert before == after == 1


def test_existing_expenses_and_money_in_are_backfilled_to_the_default_account():
    user_id, _ = make_user()
    database._accounts()
    expense_row(user_id, None)
    money_in_row(user_id, None)
    database._accounts()
    with get_db() as db:
        assert db.execute("SELECT account_id FROM expenses WHERE user_id = ?", (user_id,)).fetchone()["account_id"] == default_of(user_id)
        assert db.execute("SELECT account_id FROM money_in WHERE user_id = ?", (user_id,)).fetchone()["account_id"] == default_of(user_id)


def test_a_row_already_on_an_account_is_not_moved_by_a_rerun():
    user_id, _ = make_user()
    database._accounts()
    with get_db() as db:
        db.execute("INSERT INTO accounts (user_id, name, is_default, archived, opening_kobo) VALUES (?, 'Petty Cash', 0, 0, 0)", (user_id,))
        petty = db.execute("SELECT id FROM accounts WHERE user_id = ? AND name = 'Petty Cash'", (user_id,)).fetchone()["id"]
        db.commit()
    expense_row(user_id, petty)
    database._accounts()
    with get_db() as db:
        assert db.execute("SELECT account_id FROM expenses WHERE user_id = ?", (user_id,)).fetchone()["account_id"] == petty


def test_staff_members_do_not_get_their_own_default_account():
    owner_id, _ = make_user()
    staff_id, _ = make_user()
    with get_db() as db:
        db.execute("INSERT INTO staff_members (user_id, owner_id, role, pages, created_at) VALUES (?, ?, 'sales', '[]', '2026-01-01')",
                   (staff_id, owner_id))
        db.execute("DELETE FROM accounts WHERE user_id = ?", (staff_id,))
        db.commit()
    database._accounts()
    with get_db() as db:
        assert db.execute("SELECT COUNT(*) AS n FROM accounts WHERE user_id = ?", (staff_id,)).fetchone()["n"] == 0
        assert db.execute("SELECT COUNT(*) AS n FROM accounts WHERE user_id = ?", (owner_id,)).fetchone()["n"] == 1
