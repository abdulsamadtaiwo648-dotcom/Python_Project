"""Create a super-admin account from a trusted local or server shell."""

import argparse
import getpass
import os
import re
import sys

from werkzeug.security import generate_password_hash

from .database import HAS_PSYCOPG2, get_db, init_admin_db


def main():
    parser = argparse.ArgumentParser(description="Provision or manage a SoloBiz super-admin account.")
    parser.add_argument(
        "action", nargs="?", choices=("create", "reset", "disable", "enable", "check"), default="create"
    )
    action = parser.parse_args().action
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url and not HAS_PSYCOPG2:
        print(
            "DATABASE_URL is set, but psycopg2 is not installed. "
            "Install server/requirements.txt in this Python environment; refusing to use local SQLite.",
            file=sys.stderr,
        )
        return 1
    print(
        "Database target: PostgreSQL (DATABASE_URL is set)."
        if database_url else
        "Database target: local SQLite. Render cannot see accounts created in this local database."
    )
    init_admin_db()
    email = input("Super-admin email: ").strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        print("Enter a valid email address.", file=sys.stderr)
        return 1

    password_hash = None
    if action in {"create", "reset"}:
        password = getpass.getpass("Super-admin password (minimum 12 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if len(password) < 12 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            print("Use at least 12 characters, including a letter and a number.", file=sys.stderr)
            return 1
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr)
            return 1
        password_hash = generate_password_hash(password)

    try:
        with get_db() as db:
            existing = db.execute(
                "SELECT id, is_active FROM super_admins WHERE LOWER(email) = LOWER(?)", (email,)
            ).fetchone()
            if action == "check":
                if not existing:
                    print("No admin account with that email exists in this database.")
                    return 1
                status = "active" if existing["is_active"] else "disabled"
                print(f"Admin account found in this database; status: {status}.")
                return 0
            if action == "create" and existing:
                print("A super-admin account already exists for that email.", file=sys.stderr)
                return 1
            if action != "create" and not existing:
                print("No super-admin account exists for that email.", file=sys.stderr)
                return 1
            if action == "create":
                db.execute(
                    "INSERT INTO super_admins (email, password_hash) VALUES (?, ?)",
                    (email, password_hash),
                )
                target = db.execute(
                    "SELECT id FROM super_admins WHERE LOWER(email) = LOWER(?)", (email,)
                ).fetchone()
                audit_action = "admin account created via server shell"
            elif action == "reset":
                db.execute(
                    "UPDATE super_admins SET password_hash = ?, "
                    "session_version = session_version + 1 WHERE id = ?",
                    (password_hash, existing["id"]),
                )
                db.execute("DELETE FROM admin_login_attempts")
                target = existing
                audit_action = "admin password reset via server shell"
            elif action in {"disable", "enable"}:
                new_status = 0 if action == "disable" else 1
                confirmation = input(
                    f"Type YES to {action} admin access for {email}: "
                )
                if confirmation.strip() != "YES":
                    print("No changes made.")
                    return 0
                db.execute(
                    "UPDATE super_admins SET is_active = ?, "
                    "session_version = session_version + 1 WHERE id = ?",
                    (new_status, existing["id"]),
                )
                target = existing
                audit_action = f"admin access {action}d via server shell"
            db.execute(
                "INSERT INTO admin_audit_logs "
                "(admin_id, action, target_type, target_id, reason) VALUES (?, ?, ?, ?, ?)",
                (target["id"], audit_action, "admin", str(target["id"]), "Trusted server-shell operation"),
            )
            db.commit()
    except Exception as error:
        print(f"Could not create the super-admin account: {error}", file=sys.stderr)
        return 1

    messages = {
        "create": f"Super-admin account created for {email}.",
        "reset": f"Super-admin password reset for {email}.",
        "disable": f"Super-admin access disabled for {email}.",
        "enable": f"Super-admin access enabled for {email}.",
    }
    print(messages[action])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
