"""The plan catalogue: what each plan costs and what it unlocks.

Prices are in naira per month. They are plain numbers here (and can be
overridden with the environment variables PRICE_BASIC / PRICE_PRO) so they can
be changed without touching the rest of the code.
"""

import os
from dataclasses import dataclass, field

TRIAL_DAYS = 14          # every account starts with a Pro trial
GRACE_DAYS = 7           # a lapsed renewal keeps working this long
PERIOD_DAYS = 30         # one paid month
CURRENCY = "NGN"

TRIAL_PLAN = "pro"

# Feature keys (what the app asks about).
OFFLINE = "offline"      # record sales and expenses without a connection
WEBSITE = "website"      # a public business website
REPORTS = "reports"      # the Reports page
ALERTS = "alerts"        # stock alert notifications
BRANDING = "branding"    # receipts with the business logo; no SoloBiz credit on the website


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    price: int                      # naira per month
    max_products: int | None        # None = no limit
    history_days: int | None        # how far back sales/expenses are shown; None = all
    features: frozenset = field(default_factory=frozenset)
    tagline: str = ""


def _price(env, default):
    try:
        return int(os.environ.get(env, default))
    except ValueError:
        return default


def plans() -> dict[str, Plan]:
    return {
        "free": Plan("free", "Free", 0, 10, 30, frozenset(), "Try SoloBiz with the basics"),
        "basic": Plan("basic", "Basic", _price("PRICE_BASIC", 2500), 50, 365,
                      frozenset({OFFLINE, REPORTS, ALERTS, BRANDING}), "For a growing shop"),
        "pro": Plan("pro", "Pro", _price("PRICE_PRO", 6000), None, None,
                    frozenset({OFFLINE, REPORTS, ALERTS, BRANDING, WEBSITE}), "Everything, including your website"),
    }


PAID = ("basic", "pro")
FEATURE_LABELS = {
    OFFLINE: "Record sales and expenses offline",
    WEBSITE: "Your business website",
    REPORTS: "Reports",
    ALERTS: "Low-stock alerts on your phone",
    BRANDING: "Receipts with your logo, no SoloBiz credit",
}
