"""Accounts: where a business's money is held (Cash, Bank, Petty Cash).

Rules:
- Every business has exactly one default account, named Cash until renamed. The default is created
  when the business is created, or the first time its accounts are read.
- An account's opening balance is the money it held before any recorded activity. It is dated by
  its opening date. If the owner gives no opening date, it is dated to the day the account was
  created, so it is never counted before that day. An account with no opening balance has no effect
  on any period.
- The default account cannot be archived. To archive it, make another account the default first.
- Archived accounts keep their transactions and stay in history. New transactions cannot choose them.
- Accounts belong to a business. Every lookup is scoped to the business id, so an account from one
  business can never be used by another."""

from datetime import datetime, timezone

from . import record_rules as rules
from .money import today_iso

DEFAULT_NAME = "Cash"
NAME_MAX = 60


def ensure_default(db, owner_id):
    """Create the business's default Cash account if it has no accounts yet. Safe to call often."""
    if db.execute("SELECT 1 FROM accounts WHERE user_id = ? LIMIT 1", (owner_id,)).fetchone():
        return
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO accounts (user_id, name, is_default, archived, opening_kobo, opening_date, created_at) "
        "VALUES (?, ?, 1, 0, 0, ?, ?)",
        (owner_id, DEFAULT_NAME, today_iso(now), now.isoformat()),
    )
    db.commit()


def all_accounts(db, owner_id):
    """Every account of the business: the default first, then active, then archived."""
    return db.execute(
        "SELECT * FROM accounts WHERE user_id = ? ORDER BY archived ASC, is_default DESC, name ASC, id ASC",
        (owner_id,),
    ).fetchall()


def active_accounts(db, owner_id):
    return [r for r in all_accounts(db, owner_id) if not r["archived"]]


def default_account(db, owner_id):
    return db.execute(
        "SELECT * FROM accounts WHERE user_id = ? AND is_default = 1", (owner_id,)
    ).fetchone()


def account_for_business(db, owner_id, account_id):
    """The account if it belongs to this business, or None. Use this before assigning an account."""
    if account_id in (None, ""):
        return None
    try:
        account_id = int(account_id)
    except (TypeError, ValueError):
        return None
    return db.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ?", (account_id, owner_id)
    ).fetchone()


def name_taken(db, owner_id, name, exclude_id=None):
    """Names are compared without regard to case, and archived accounts count too."""
    key = name.lower()
    for row in db.execute("SELECT id, name FROM accounts WHERE user_id = ?", (owner_id,)).fetchall():
        if row["name"].lower() == key and row["id"] != exclude_id:
            return row
    return None


def name_problem(name):
    if not name:
        return "Enter a name for the account."
    if len(name) > NAME_MAX:
        return f"The name must be {NAME_MAX} characters or fewer."
    return None


def opening_date_for(value, now=None):
    """(date, None) for the opening date. Blank means the day the account is created."""
    if value in (None, ""):
        return today_iso(now), None
    day, error = rules.check_entry_date(value)
    if error:
        return None, f"The opening date: {error}."
    return day, None


def view(row):
    from .money import naira_text
    return {
        "id": row["id"],
        "name": row["name"],
        "is_default": bool(row["is_default"]),
        "archived": bool(row["archived"]),
        "opening_balance": naira_text(row["opening_kobo"]),
        "opening_date": row["opening_date"],
    }
