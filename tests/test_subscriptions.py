"""Trial, paid period, grace and lapse rules."""

from datetime import datetime, timedelta, timezone

from api import plans, subscriptions as subs

from .conftest import make_user

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def days(n):
    return T0 + timedelta(days=n)


def test_new_account_gets_a_14_day_pro_trial():
    user_id, _ = make_user()
    ent = subs.entitlements(user_id, T0)
    assert (ent["plan"], ent["state"], ent["days_left"]) == ("pro", "trial", 14)
    assert plans.WEBSITE in ent["features"] and ent["max_products"] is None


def test_trial_ends_on_the_free_plan():
    user_id, _ = make_user()
    subs.ensure_subscription(user_id, T0)
    ent = subs.entitlements(user_id, days(15))
    assert (ent["plan"], ent["state"], ent["features"]) == ("free", "free", [])
    assert ent["max_products"] == 10 and ent["history_days"] == 30 and ent["trial_used"] is True


def test_paying_starts_a_30_day_period_on_that_plan():
    user_id, _ = make_user()
    subs.ensure_subscription(user_id, T0)
    subs.activate(user_id, "basic", days(2))
    ent = subs.entitlements(user_id, days(3))
    assert (ent["plan"], ent["state"]) == ("basic", "active")
    assert plans.WEBSITE not in ent["features"] and plans.REPORTS in ent["features"]
    assert ent["max_products"] == 50 and ent["history_days"] == 365
    assert subs.entitlements(user_id, days(2 + 30))["state"] == "active"


def test_paid_plan_replaces_the_trial_even_if_trial_remains():
    user_id, _ = make_user()
    subs.ensure_subscription(user_id, T0)
    subs.activate(user_id, "basic", days(1))
    assert subs.entitlements(user_id, days(2))["plan"] == "basic"


def test_missed_renewal_keeps_working_for_7_days_then_drops_to_free():
    user_id, _ = make_user()
    subs.ensure_subscription(user_id, days(-60))      # trial long over
    subs.activate(user_id, "pro", T0)
    end = T0 + timedelta(days=30)
    grace = subs.entitlements(user_id, end + timedelta(days=3))
    assert (grace["plan"], grace["state"], grace["days_left"]) == ("pro", "grace", 4)
    lapsed = subs.entitlements(user_id, end + timedelta(days=8))
    assert (lapsed["plan"], lapsed["state"]) == ("free", "free")


def test_renewing_early_extends_from_the_current_end():
    user_id, _ = make_user()
    subs.ensure_subscription(user_id, days(-60))
    subs.activate(user_id, "basic", T0)
    subs.activate(user_id, "basic", days(10))
    assert subs.entitlements(user_id, days(50))["state"] == "active"      # 30 + 30 days from T0
    assert subs.entitlements(user_id, days(61))["state"] == "grace"


def test_cancelled_plan_runs_to_the_end_of_the_period_without_grace():
    user_id, _ = make_user()
    subs.ensure_subscription(user_id, days(-60))
    subs.activate(user_id, "pro", T0)
    subs.set_cancel(user_id, True, days(5))
    ent = subs.entitlements(user_id, days(10))
    assert ent["state"] == "active" and ent["cancel_at_period_end"] is True
    assert subs.entitlements(user_id, days(31))["plan"] == "free"
    subs.set_cancel(user_id, False, days(11))
    assert subs.entitlements(user_id, days(31))["state"] == "grace"


def test_history_cutoff_follows_the_plan():
    user_id, _ = make_user()
    subs.ensure_subscription(user_id, days(-60))
    assert subs.history_cutoff(user_id, T0) == (T0 - timedelta(days=30)).strftime("%Y-%m-%d")
    subs.activate(user_id, "pro", T0)
    assert subs.history_cutoff(user_id, days(1)) is None


def test_unknown_plan_cannot_be_activated():
    user_id, _ = make_user()
    try:
        subs.activate(user_id, "gold")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
