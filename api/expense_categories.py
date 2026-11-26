"""Expense categories. Each business keeps its own list. An archived name stays on the expenses
that already use it, but no new expense can pick it."""

from datetime import datetime, timezone

from . import record_rules as rules

DEFAULT_CATEGORIES = [
    "Inventory & Materials", "Delivery & Logistics", "Fuel & Electricity",
    "Data & Airtime", "Owner's Draw (Personal)", "Others",
]


def ensure(db, user_id):
    """Create a business's list the first time it is needed: the defaults, plus any name it
    already used on an expense, so nothing it recorded before is orphaned."""
    if db.execute("SELECT 1 FROM expense_categories WHERE user_id = ? LIMIT 1", (user_id,)).fetchone():
        return
    names = list(DEFAULT_CATEGORIES)
    seen = {n.lower() for n in names}
    for row in db.execute("SELECT DISTINCT category FROM expenses WHERE user_id = ?", (user_id,)).fetchall():
        name = (row["category"] or "").strip()
        if name and name.lower() not in seen and not rules.too_long(name, rules.MAX_CATEGORY):
            names.append(name)
            seen.add(name.lower())
    now = datetime.now(timezone.utc).isoformat()
    for name in names:
        db.execute(
            "INSERT INTO expense_categories (user_id, name, archived, created_at) VALUES (?, ?, 0, ?)",
            (user_id, name, now),
        )
    db.commit()


def find_by_name(db, user_id, name, exclude_id=None):
    """The row whose name matches case-insensitively, archived or not, or None."""
    key = name.lower()
    for row in db.execute("SELECT id, name, archived FROM expense_categories WHERE user_id = ?", (user_id,)).fetchall():
        if row["name"].lower() == key and row["id"] != exclude_id:
            return row
    return None


def choice_for_expense(db, user_id, name, current=None):
    """The stored name an expense may use, or None. An active category always qualifies. An
    archived one only when the expense already uses it, so an old entry is not silently changed."""
    row = find_by_name(db, user_id, name)
    if row is None:
        return None
    if not row["archived"]:
        return row["name"]
    if current and current.lower() == row["name"].lower():
        return row["name"]
    return None
