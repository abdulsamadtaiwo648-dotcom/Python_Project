"""Staff accounts: which pages a staff member may use, and the rules that
decide what each request needs.

The owner is never restricted. A staff person works on the owner's business:
their requests read and write the owner's records, but only inside the pages
the owner gave them. Some things are owner-only and are never given to staff:
team management, plans and payments, and changing their own password.
"""

import json
from datetime import datetime, timezone

from server.database import get_db

from . import plans as catalogue

OWNER = "owner"

PAGES = {
    "dashboard": "Dashboard",
    "sales": "Sales and receipts",
    "inventory": "Inventory",
    "expenses": "Expenses",
    "budget": "Budget",
    "reports": "Reports",
    "profile": "Business profile",
    "website": "Website",
}

# Preset roles. "custom" uses whatever pages the owner ticks.
ROLES = {
    "sales": {"label": "Sales", "pages": ["sales"], "blurb": "Records sales, payments and receipts."},
    "inventory": {"label": "Inventory", "pages": ["inventory"], "blurb": "Products, stock and restocking."},
    "accountant": {"label": "Accountant", "pages": ["dashboard", "expenses", "budget", "reports"], "blurb": "Expenses, budgets and reports."},
    "custom": {"label": "Custom", "pages": [], "blurb": "The owner chooses the pages."},
}

_READ = {"GET", "HEAD"}


def required(method, path):
    """What a request needs: None (anyone signed in), OWNER, or a set of pages
    of which the staff member must hold at least one."""
    read = method in _READ
    if path.startswith("/api/staff") or path == "/plans":
        return OWNER
    if path.startswith("/api/subscription"):
        return None if read else OWNER
    if path in ("/api/session", "/api/logout", "/healthz") or path.startswith(("/api/push", "/api/avatar")):
        return None
    # Deleting a sale removes money from the records: only the owner may do it.
    if path.startswith("/api/income/") and method.upper() == "DELETE":
        return OWNER
    if path == "/api/income" or path.startswith("/api/income/") or path.startswith("/update_payment/") \
            or path in ("/add_income", "/api/checkout", "/api/sync-sales"):
        return frozenset({"sales", "dashboard", "reports"}) if read else frozenset({"sales"})
    # Imports write rows, so they need the page they write to. Only the owner may import
    # by default, but the page keys below let staff who hold that page import too.
    if path == "/api/import/sales":
        return frozenset({"sales"})
    if path == "/api/import/expenses":
        return frozenset({"expenses"})
    # Money in is recorded with sales. Removing it is owner-only, as removing a sale is.
    if path.startswith("/api/money-in"):
        if method.upper() == "DELETE":
            return OWNER
        return frozenset({"sales", "dashboard", "reports"}) if read else frozenset({"sales"})
    if path.startswith("/api/inventory-presets"):
        return frozenset({"inventory", "sales", "dashboard"}) if read else frozenset({"inventory"})
    if path.startswith("/api/expenses") or path == "/add":
        return frozenset({"expenses", "dashboard", "reports", "budget"}) if read else frozenset({"expenses"})
    if path == "/api/dashboard":
        return frozenset({"dashboard", "reports"})
    if path.startswith("/api/business_profile"):
        if read and not path.endswith("request-otp"):
            return None            # receipts need the business name and address
        return frozenset({"profile"})
    if path.startswith("/api/website") or path.startswith("/website"):
        return frozenset({"website"})
    return OWNER                   # anything not listed is owner-only


def is_gated(path):
    return path.startswith(("/api/", "/website", "/add", "/update_payment/"))


def staff_row(db, user_id):
    row = db.execute("SELECT * FROM staff_members WHERE user_id = ?", (str(user_id),)).fetchone()
    return dict(row) if row else None


def staff_pages(row):
    try:
        return [p for p in json.loads(row.get("pages") or "[]") if p in PAGES]
    except (TypeError, ValueError):
        return []


def seats_for(owner_id):
    from .subscriptions import entitlements

    plan = catalogue.plans()[entitlements(owner_id)["plan"]]
    return plan.staff_seats


def seat_usage(owner_id):
    with get_db() as db:
        used = db.execute("SELECT COUNT(*) AS n FROM staff_members WHERE owner_id = ?", (str(owner_id),)).fetchone()["n"]
    return int(used), seats_for(owner_id)


def staff_in_seats(owner_id, user_id):
    """Staff beyond the owner's seat count (after a downgrade) are switched off, oldest first kept."""
    with get_db() as db:
        rows = db.execute(
            "SELECT user_id FROM staff_members WHERE owner_id = ? ORDER BY created_at, user_id", (str(owner_id),)
        ).fetchall()
    order = [r["user_id"] for r in rows]
    limit = seats_for(owner_id)
    return str(user_id) in order[:limit] if user_id in order else False


def actor(request):
    """Who is making this request, and what they may use. Cached per request.

    Returns None when nobody is signed in, otherwise a dict with:
      user_id   the account that signed in
      owner_id  the business whose data the request reads and writes
      is_staff  False for the owner
      pages     set of page keys (the owner has all of them)
      role      'owner' or the staff role
    """
    from .deps import _load_actor  # local import avoids a cycle

    cached = getattr(request.state, "actor", "unset")
    if cached != "unset":
        return cached
    value = _load_actor(request)
    request.state.actor = value
    return value


def permission_error(request):
    """A JSON 403 response if this request is not allowed for the signed-in
    person, or None if it may go ahead."""
    from fastapi.responses import JSONResponse

    path = request.url.path
    if not is_gated(path):
        return None
    need = required(request.method, path)
    if need is None:
        return None
    who = actor(request)
    if not who or not who["is_staff"]:
        return None
    if need == OWNER:
        return JSONResponse({"status": "error", "code": "owner_only",
                             "message": "Only the business owner can do this."}, status_code=403)
    if not (who["pages"] & need):
        return JSONResponse({"status": "error", "code": "not_allowed",
                             "message": "Your role does not include this page. Ask the owner for access."}, status_code=403)
    return None


def access_for(who):
    """What the app needs to know to show the right pages."""
    if not who:
        return None
    if not who["is_staff"]:
        return {"is_owner": True, "is_staff": False, "role": "owner", "pages": sorted(PAGES)}
    return {"is_owner": False, "is_staff": True, "role": who["role"], "pages": sorted(who["pages"]),
            "business_id": who["owner_id"]}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def record(db, owner_id, event_type, summary):
    """Activity log entry for the business (who changed the team)."""
    db.execute(
        "INSERT INTO user_activity_logs (user_id, event_type, summary) VALUES (?, ?, ?)",
        (str(owner_id), str(event_type)[:60], str(summary)[:240]),
    )
