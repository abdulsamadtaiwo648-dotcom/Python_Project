"""The business profile lock on the save path: setup, grace, lock, and the PIN rules."""

from datetime import datetime, timedelta, timezone

from api.core import upsert_otp
from server.database import get_db

FIELDS = {"company_name": "Ada Atelier", "business_phone": "+2348012345678", "business_address": "12 Market St"}


def _email(user_id):
    with get_db() as db:
        return db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()["email"]


def _pin(user_id):
    code, _ = upsert_otp(_email(user_id), "profile")
    return code


def _save(client, headers, **fields):
    return client.post("/api/business_profile", data=fields, headers=headers, content_type="multipart/form-data")


def _row(user_id):
    with get_db() as db:
        return dict(db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone())


def _age_setup(user_id, days):
    when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_db() as db:
        db.execute("UPDATE business_profiles SET setup_completed_at = ? WHERE user_id = ?", (when, user_id))


def test_initial_setup_needs_no_pin(client, signed_in):
    user_id, token = signed_in
    response = _save(client, {"X-CSRFToken": token}, **FIELDS)
    assert response.status_code == 200, response.get_json()
    assert _row(user_id)["setup_completed_at"]
    assert _row(user_id)["identity_changed_at"] in (None, "")


def test_a_correction_in_the_grace_period_needs_a_pin_and_starts_no_lock(client, signed_in):
    user_id, token = signed_in
    headers = {"X-CSRFToken": token}
    _save(client, headers, **FIELDS)
    no_pin = _save(client, headers, **dict(FIELDS, company_name="Ada Atelier Lagos"))
    assert no_pin.status_code == 400
    with_pin = _save(client, headers, **dict(FIELDS, company_name="Ada Atelier Lagos",
                                             profile_change_reason=next(iter(_reasons())), otp=_pin(user_id)))
    assert with_pin.status_code == 200, with_pin.get_json()
    assert _row(user_id)["identity_changed_at"] in (None, "")


def test_a_change_after_grace_needs_a_pin_and_starts_the_ninety_day_lock(client, signed_in):
    user_id, token = signed_in
    headers = {"X-CSRFToken": token}
    _save(client, headers, **FIELDS)
    _age_setup(user_id, 10)
    response = _save(client, headers, **dict(FIELDS, company_name="Ada Atelier Lagos",
                                             profile_change_reason=next(iter(_reasons())), otp=_pin(user_id)))
    assert response.status_code == 200, response.get_json()
    assert _row(user_id)["identity_changed_at"]


def test_during_the_lock_unlocked_fields_save_without_a_pin_and_locked_fields_are_refused(client, signed_in):
    user_id, token = signed_in
    headers = {"X-CSRFToken": token}
    _save(client, headers, **FIELDS)
    _age_setup(user_id, 10)
    _save(client, headers, **dict(FIELDS, company_name="Ada Atelier Lagos",
                                  profile_change_reason=next(iter(_reasons())), otp=_pin(user_id)))
    other = _save(client, headers, **dict(FIELDS, company_name="Ada Atelier Lagos", instagram_handle="adaatelier"))
    assert other.status_code == 200, other.get_json()
    refused = _save(client, headers, **dict(FIELDS, company_name="A new name"))
    assert refused.status_code == 403 and refused.get_json()["status"] == "locked"


def test_the_pin_is_not_sent_while_locked(client, signed_in):
    user_id, token = signed_in
    headers = {"X-CSRFToken": token}
    _save(client, headers, **FIELDS)
    _age_setup(user_id, 10)
    _save(client, headers, **dict(FIELDS, company_name="Ada Atelier Lagos",
                                  profile_change_reason=next(iter(_reasons())), otp=_pin(user_id)))
    response = client.post("/api/business_profile/request-otp", json=dict(FIELDS, company_name="A new name"), headers=headers)
    assert response.status_code == 403 and response.get_json()["status"] == "locked"


def test_no_pin_is_sent_when_no_locked_field_changes(client, signed_in):
    user_id, token = signed_in
    headers = {"X-CSRFToken": token}
    _save(client, headers, **FIELDS)
    response = client.post("/api/business_profile/request-otp", json=dict(FIELDS, instagram_handle="x"), headers=headers)
    assert response.get_json()["status"] == "not_needed"


def _reasons():
    from api.routers.profile import PROFILE_CHANGE_REASONS
    return PROFILE_CHANGE_REASONS.keys()
