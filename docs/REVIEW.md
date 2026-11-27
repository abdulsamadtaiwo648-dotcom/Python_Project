# Codebase review

Status: **Part 1, first pass (read-only).** No code has been changed yet. Each fix will be a separate commit with a test that fails before the fix and passes after.

Base: `origin/main` at `23964ed`.

## Baseline (before any change)

| Check | Result |
| --- | --- |
| `pytest tests admin_tests` | 545 passed, 0 failed |
| `npx tsc --noEmit` (web) | exit 0, no errors |
| `npm run build` (Vite) | not run yet |
| `e2e/` browser tests | not run yet |

## 1. Endpoint map

The app serves 87 method/path pairs (from `app.openapi()`). Grouped:

- **Auth:** `/api/login`, `/api/logout`, `/api/session`, `/api/register/*`, `/api/forgot-password/*`
- **Money (sales, expenses, money in):** `/api/income`, `/api/checkout`, `/api/sync-sales`, `/api/expenses`, `/api/money-in`, `/api/accounts`, `/api/accounts/{id}/statement`, `/api/dashboard`
- **Inventory and categories:** `/api/inventory-presets*`, `/api/expense-categories*`
- **Imports:** `/api/import/preview`, `/api/import/commit`, `/api/import-batches*`, plus legacy `/api/import/sales`, `/api/import/expenses`
- **Website:** `/api/website*`, `/website/preview`, `/site/{slug}`, `/media/{token}`
- **Profile, staff, push, billing, test reset:** `/api/business_profile*`, `/api/staff*`, `/api/push/*`, `/api/subscription*`, `/api/billing/webhook`, `/api/test-reset`
- **Public and legacy pages:** `/store/{slug}`, `/api/avatar/{slug}`, `/sitemap.xml`, `/robots.txt`, `/sw.js`, `/favicon.ico`, `/analytics`, `/dashboard/{section}`, `/add`, `/add_income`, `/update_payment/{id}`

**Frontend callers.** Every `/api/*` path the frontend uses exists on the backend.

**Backend routes with no caller in `web/`, `client/` or templates:**

| Route | Where | Notes |
| --- | --- | --- |
| `GET/POST /add_income` | `api/routers/sales.py:39` | Flask-era alias. Only referenced in `api/permissions.py:55`. |
| `POST /api/sync-sales` | `api/routers/sales.py:491` | Referenced only by tests and `api/permissions.py:55`. |
| `POST /api/import/sales` | `api/routers/imports.py:314` | Replaced by `/api/import/preview` and `/commit`. |
| `POST /api/import/expenses` | `api/routers/imports.py:309` | Same as above. |
| `POST /api/inventory-presets/{id}/decrement` | `api/routers/inventory.py:210` | No UI caller. Checkout decrements stock on its own. |

These are **not deleted yet**. Clients with an offline queue written against the old API may still post to them, so each needs a deprecation check first.

**Live but not in the frontend's `/api` list (used by the offline queue):** `/add` (`Expenses.tsx:56`) and `/update_payment/{id}` (`SaleSheets.tsx:286`). They are used, so they stay.

## 2. Duplicate and legacy code

| Item | Where | Fix |
| --- | --- | --- |
| Compact naira formatter, copied | `web/src/components/TrendChart.tsx:4`, `web/src/pages/Reports.tsx:128` | Keep one in `web/src/format.ts`, point both at it. |
| WhatsApp `wa.me` link built in four places | `api/pages.py`, `server/websites.py`, `client/templates/storefront.html`, `client/templates/website.html` | Python side keeps one helper; the two HTML templates are legacy (see below). |
| Legacy HTML still served | `client/templates/storefront.html`, `landing.html`, `privacy.html`, `website.html` (served by `api/pages.py`) | Not dead. `landing.html` is replaced by the landing redesign (task #4). Leave until that lands. |
| `client/static/tailwind.js`, `solobiz-ui.css` | Used by `web/index.html` and the legacy 404/500 pages | Keep. |

Money helpers are otherwise in one place: `api/money.py` (`naira_text`, `parse_naira`), and `web/src/format.ts` (`money`). The week and month bounds are in `api/ledger.py` (`week_bounds`, `month_bounds`) only.

## 3. Findings

Severity: critical / high / medium / low. Nothing critical was found in this pass.

| # | Sev | File:line | Issue | Plan |
| --- | --- | --- | --- | --- |
| 1 | high | `api/routers/expenses.py:32-44` | `GET /api/expenses` has no `LIMIT`. It returns every row for the user (1,274 rows, about 240 KB, reported on the live site). | Add paging (`limit`, `before_id` or date range), update the frontend list to request by month, test that a 1,300-row business returns a bounded page. |
| 2 | medium | `api/routers/staff.py:155` | The staff delete check is scoped to `owner_id` (line 150), but the final `DELETE FROM users WHERE id = ?` is not. If one staff account can be linked to more than one owner, removing it for one owner removes it for all. | Confirm the `staff_members` schema allows one account under several owners. If it does, delete the `users` row only when no other `staff_members` row remains. Add a test with two owners. |
| 3 | medium | `api/routers/push.py:59` | The subscribe handler runs `DELETE FROM push_subscriptions WHERE endpoint = ?` with no `user_id`. A signed-in user can remove another user's subscription row for the same push endpoint. Endpoints are unguessable, so risk is low. | Scope it to the caller and handle a reassigned endpoint explicitly. Test that user B cannot delete user A's row. |
| 4 | low | `web/src/components/TrendChart.tsx:4`, `web/src/pages/Reports.tsx:128` | Duplicate compact naira formatter. | See section 2. |
| 5 | low | five routes in section 1 | Legacy endpoints with no caller. | Deprecate first, then delete. Grep proof is in section 1. |

## 4. Checked and fine

- **CSRF:** enforced in middleware for every non-safe method except the billing webhook (`api/main.py:35`).
- **Client op idempotency:** `X-Client-Op` is claimed before the handler runs (`api/main.py:46-63`), so a retried write is not applied twice.
- **Money-in update is tenant-scoped:** `UPDATE money_in ... WHERE id = ? AND user_id = ?` (`api/routers/money_in.py:132-135`).
- **Import duplicates are flagged, not dropped:** rows get `status: "duplicate"` with the match (`api/routers/imports.py:192-202`). Only rows the owner keeps are inserted (`imports.py:252`).
- **Indexes on `(user_id, entry_date)`** exist for sales, expenses and money in (`server/database.py:944`, `:1000`).
- **Frontend API calls:** all resolve to a backend route.

## 5. Not reviewed yet

These are still open. I'd rather say so than report them as clean.

- Money arithmetic in the frontend (`web/src/analytics.ts`, `Dashboard.tsx`, `Reports.tsx`) and rounding of decimal vs float.
- Date handling across the server/browser boundary, and the Africa/Lagos week at month edges.
- The offline queue (`web/src/offline.ts`, 178 lines) and retry behaviour.
- File upload type and size checks, beyond the existing `shrinkImage` path.
- Rate limits on login and OTP.
- Error paths that show success on failure.
- Vite production build and the `e2e/` suite.
- Acceptance numbers for the Ada Test account. These need either a database export of that business or a restored copy. They cannot be checked against the live database from this environment.

## 6. Part 2 items

Not started. Each needs its own failing test first. Several depend on the UI, so they'll be checked in the browser after the fix.
