"""Create a super-admin account from a trusted local or server shell."""

import argparse
import getpass
import re
import sys

from werkzeug.security import generate_password_hash

from .database import get_db, init_admin_db


def main():
    parser = argparse.ArgumentParser(description="Provision or manage a SoloBiz super-admin account.")
    parser.add_argument(
        "action", nargs="?", choices=("create", "reset", "disable", "enable"), default="create"
    )
    action = parser.parse_args().action
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
                target = existing
                audit_action = "admin password reset via server shell"
            else:
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
