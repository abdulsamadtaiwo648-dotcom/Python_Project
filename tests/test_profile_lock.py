"""The business profile lock rules: which fields lock, when, and for how long."""

from datetime import datetime, timedelta, timezone

from api.profile_lock import LOCK_DAYS, changed_locked_fields, date_text, lock_status

SETUP = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


def at(days: float) -> datetime:
    return SETUP + timedelta(days=days)


def test_first_setup_starts_no_lock_and_needs_no_pin():
    assert lock_status(at(0), None, None)["state"] == "setup"


def test_a_change_on_day_three_is_a_correction_and_does_not_start_a_lock():
    status = lock_status(at(3), SETUP.isoformat(), None)
    assert status["state"] == "grace"
    assert date_text(status["until"]) == "27 Nov 2026"


def test_a_change_after_the_grace_period_starts_a_ninety_day_lock():
    assert lock_status(at(10), SETUP.isoformat(), None)["state"] == "open"
    changed_on_day_ten = at(10).isoformat()
    status = lock_status(at(11), SETUP.isoformat(), changed_on_day_ten)
    assert status["state"] == "locked"
    assert status["until"] == at(10) + timedelta(days=LOCK_DAYS)


def test_the_lock_ends_after_ninety_days():
    changed = at(10).isoformat()
    assert lock_status(at(10 + LOCK_DAYS - 1), SETUP.isoformat(), changed)["state"] == "locked"
    assert lock_status(at(10 + LOCK_DAYS + 1), SETUP.isoformat(), changed)["state"] == "open"


def test_only_name_phone_and_address_are_locked():
    before = {"company_name": "Ada Atelier", "business_phone": "+2348012345678", "business_address": "12 Market St", "instagram_handle": "ada", "logo_url": "/a.png", "brand_color": "#1d4ed8", "whatsapp_number": "", "store_policy": ""}
    after_unlocked_only = dict(before, instagram_handle="adaatelier", logo_url="/b.png", brand_color="#0f766e", whatsapp_number="+2348000000000", store_policy="No returns after 7 days")
    assert changed_locked_fields(before, after_unlocked_only) == []
    assert changed_locked_fields(before, dict(before, company_name="Ada Atelier Lagos")) == ["company_name"]
    assert changed_locked_fields(before, dict(before, business_phone="+2348099999999", business_address="2 Main Rd")) == ["business_phone", "business_address"]


def test_surrounding_spaces_are_not_a_change():
    assert changed_locked_fields({"company_name": "Ada"}, {"company_name": " Ada "}) == []


def test_unreadable_setup_date_is_treated_as_setup_not_as_a_lock():
    assert lock_status(at(1), "not-a-date", None)["state"] == "setup"
