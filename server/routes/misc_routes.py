"""Misc Routes HTTP routes."""

from ..app import (
    app,
    get_db,
)


@app.route("/user-count")
def user_count():
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) AS total FROM users").fetchone()
        total = row["total"] if (isinstance(row, dict) or hasattr(row, "keys")) else (row[0] if row else 0)
    return f"<h1>Total Registered Users: {total}</h1>"
