# Subscriptions

Three plans, a free trial, and Flutterwave for payment. Plan rules live in one
file, `api/plans.py`; the rest of the code asks "does this account have
feature X?" and never checks a plan name.

## Plans

| | Free | Basic | Pro |
| --- | --- | --- | --- |
| Price (naira / month) | 0 | 2,500 | 6,000 |
| Products | 10 | 50 | unlimited |
| Sales and expense history shown | 30 days | 12 months | all |
| Offline recording | no | yes | yes |
| Reports | no | yes | yes |
| Stock alerts on the phone | no | yes | yes |
| Receipts with logo, no SoloBiz credit | no | yes | yes |
| Business website (publish) | no | no | yes |

The prices are placeholders. Change them in `api/plans.py`, or set `PRICE_BASIC`
and `PRICE_PRO` (whole naira) on the service. Changing a price creates a new
Flutterwave payment plan for it the next time someone checks out; accounts
already subscribed keep paying the price they started on.

## Lifecycle

- Every account starts a **14-day Pro trial**. Existing accounts start it the
  first time they open the app after this release.
- After the trial the account is on **Free**.
- Paying starts a **30-day period** on the chosen plan. Paying early extends it.
- A missed renewal gets a **7-day grace period** on the same plan, then Free.
- Cancelling keeps the plan until the period ends, with no grace.
- Nothing is deleted when a plan drops. Records stay; sales and expenses older
  than the plan's history window are hidden until the account upgrades again;
  a published website goes offline; paid features switch off.

State is worked out from stored dates (`subscriptions` table), so no scheduled
job is needed.

## Where it is enforced

| Rule | Where |
| --- | --- |
| Product limit | `POST /api/inventory-presets` |
| History window | `GET /api/income`, `GET /api/expenses` |
| Publishing a website | `POST /api/website/publish`; the public page (`/site/<name>`, subdomains) answers 404 when the owner's plan has no website |
| Alerts | `POST /api/push/subscribe`; no alert is sent for a plan without alerts |
| Credit line on websites | `client/templates/website.html` |
| Reports, offline recording, receipts logo | the React app (`useData().can(...)`); offline writes are also refused in `web/src/data.tsx` |

A refusal is HTTP 403 with `{"code": "upgrade_required", "feature": ...}`; the
app turns it into a "See plans" prompt.

## Flutterwave setup

Set these on the Render service (use **test** keys first):

| Variable | Value |
| --- | --- |
| `FLW_SECRET_KEY` | Secret key from Flutterwave -> Settings -> API keys |
| `FLW_SECRET_HASH` | Any long random string; enter the same string as the webhook secret hash |

In the Flutterwave dashboard (Settings -> Webhooks) set:

- URL: `https://solobiz.dev/api/billing/webhook`
- Secret hash: the same value as `FLW_SECRET_HASH`
- Enable "Receive webhook" events for charges.

The customer is sent back to `https://solobiz.dev/billing/callback`, which
asks Flutterwave to confirm the payment before activating anything. The webhook
does the same check, so a forged request cannot give a plan: the amount,
currency and status come from Flutterwave, not from the request. A payment is
applied once, however many times it is reported.

Monthly renewals are charged by Flutterwave on its own schedule (a payment plan
is created on first use). Each renewal arrives as a webhook and is matched to
the account by payment-plan id and e-mail.

Until the keys are set the plans screens work and checkout answers "payments are
not set up yet".

## Tests

`tests/test_subscriptions.py` (rules), `tests/test_billing.py` (checkout,
callback, webhook, renewal, cancel; Flutterwave is mocked) and
`tests/test_plan_limits.py` (enforcement). The live Flutterwave API has not been
exercised from this repository: run one test-mode payment end to end before
taking real money.
