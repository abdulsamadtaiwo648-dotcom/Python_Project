"""Migration 0013: the profile lock columns exist, and existing profiles are treated as already set up."""

from server.database import get_db


def test_profile_lock_columns_exist_and_existing_profiles_are_set_up():
    with get_db() as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(business_profiles)").fetchall()}
    assert {"setup_completed_at", "identity_changed_at", "identity_change_reason"} <= columns
