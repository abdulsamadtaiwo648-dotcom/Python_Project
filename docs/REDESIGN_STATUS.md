# SoloBiz mobile-first redesign: status

Branch: `claude/lucid-edison-xzhrl7` (local, 29 commits ahead of origin; not pushed).
Last commit: `c78e7b5`.

Checks at the last commit: `npm test` 62 passing; `tsc --noEmit` clean; `npm run build` clean; Python suite 547 passing (last full run, before the Reports change; Reports is front-end only).

Every feature below was checked in a browser at 360px against a local copy with seeded data, unless marked "not checked".

## Section 1: design system

Done
- Tokens: `web/src/ui/tokens.css` (light values match the app; dark values exist, apply only with `data-theme="dark"`).
- Shared formatters: one money formatter, one compact formatter, date helpers in `format.ts`.
- Components in `web/src/ui/`: Button, Card and StatCard, ListRow and DayGroup, FilterChips, FAB, AppBar, MoneyInput, ToastProvider, DatePicker, ConfirmSheet, SelectSheet, BottomNav, ActionSheet, SwipeRow.
- Undo on deletes: expenses, money in, sales, products.

Not done
- Pages still using their own markup: Sales receipt cards, Budget, Profile, Website, Team, Plans, Settings, login and register.
- Old one-off styles: the Stock card-hack CSS is removed; other one-off styles in `client/static/solobiz-ui.css` and `web/src/styles/app.css` remain.
- The Toast is used for Undo only; other confirm popups remain on Plans (cancel renewal), Team (remove staff), Website (take offline), and sign-out with unsynced items. These are kept on purpose.

## Section 2: navigation

Done
- Bottom bar: Home, Sales, Expenses, Money, More. Stock is under More with a low-stock count. More ends with Sign out.
- Floating + on Home (Sale, Expense, Money in), Money (Money in, Transfer), Sales and Expenses.
- Sales, Expenses and Money in open their form from `?new=1`.
- Android back and swipe-back close an open sheet first.
- Desktop sheets are 440px side panels; tablet content is 720px wide.

Not done
- Pull-to-refresh on lists.
- "Load more" paging (the expense list still loads every row; review bug 1).
- Offline banner and clock icon on unsynced items.
- Help item in More (no help page exists).
- Desktop sidebar not checked against the spec.

## Section 3: screens

Done
- Home: four stat cards, low-stock, overspent-cash and unpaid-sales alerts, month-filtered recent activity, six-month chart ending at the latest month with data, description as title.
- Sales: status chips (All, Paid, Part-paid, Owing); When filter; day groups; sale details sheet; quantity steppers; footer total.
- Expenses: amount keypad; Today/Yesterday chips; categories most-used first; search; top category; remembers last category and account.
- Money: Accounts shows cash at hand; account detail entries grouped by day; transfers list (new endpoint `GET /api/transfers`); money-in type chips.
- Stock: product card grid; table view readable on phones; old card CSS removed.
- Reports: profit and loss card; top products; CSV export; no greeting or repeated cards.

Not done
- Home: budget-over-80% alert (needs budgets moved to the server); bell icon.
- Sales: product picker with photos (the end-to-end test selects the current dropdown by id, so update that test with the change); fixed total bar.
- Expenses: "Save and add another" keeping category and date; filter panel layout.
- Stock: product detail sheet (photos, Show on website, Restock); product photos (needs a database change).
- Reports: Day and Week periods (the range logic only supports Month and Year); PDF export.
- Budget, Website, Profile, Team, Plans, Settings: not started.

## Section 4: interaction rules

Done
- Every tap target is at least 44px on phones and tablets (checked on all 14 signed-in pages).
- Motion is effectively off when the user prefers reduced motion.
- Swipe a row to reveal Edit and Delete (Expenses), with Undo on delete.
- Expense form remembers the last category and account (on this device).
- Sheet footers are sticky inside the scrolling form, so Save stays in view (keyboard behaviour not checked on a real phone).

Not done
- Pull-to-refresh; "load more" paging; swipe on other lists; offline banner and clock icon; animation durations checked against 150–250ms.

## Section 5: wording
Not started.

## Section 6: performance
Not started. Lighthouse not run. First-load and code-splitting not checked.

## Section 7: desktop
Partly covered: sidebar exists, sheets are side panels, tablet width set. Not checked: 1024px, 1280px and 1440px layouts for every screen, and the 1200px content max-width.

## Section 8: bugs

Done
- a) Account statement opening: not changed in this pass; check the statement against the opening date rule.
- b) Home recent activity follows the selected month.
- c) Home chart has no empty months at the end.
- d) Activity rows swapped (description is the title).
- e) Money → Accounts shows balances (existing cards) and a cash-at-hand total.
- g) Reports repeats no dashboard cards (already fixed).
- i) Import duplicates: flagged in preview, kept only when chosen (already in place).
- Test-reset: not changed.

Not done (need decisions or approvals)
- f) Profile lock: check the lock before sending a PIN; show the unlock date on the form. Needs your confirmation of which fields are locked.
- g) Profile lock too strict: only name, phone and address should lock.
- h) PIN sheet: resend button with 60-second cooldown and expiry countdown.
- i) Brand colour picker on the profile, shared with receipts and the website.
- j) Budgets saved on the server (currently browser-only). Needs a database change, a migration, and a confirmed backup.
- k) Product photos. Needs a database change and storage.
- o) Admin-only test-business flag. Needs a decision on how to set it.

## Section 9: acceptance
Not started. Still needed: screenshots at 360, 390, 430, 768, 1024, 1280 and 1440px before and after; the Ada Test numbers (need a database export of that business or your own check); a screen recording; full test and build run; a PR with the list of deleted styles and components.

## Decisions and approvals needed
1. Database changes for server-side budgets and product photos: approve, and confirm a production backup and the migration order before any deploy.
2. Profile lock rules (bugs f and g).
3. Ada Test numbers: a database export, or your own check.
4. Force-push of this branch over the old remote branch: say "push" to approve.

## Notes for the next session
- The end-to-end test `e2e/app.e2e.mjs` selects `#sales-inventory-select`. The sales product picker is still that dropdown, so changing it means updating the test.
- Local test server: `SOLOBIZ_DEBUG=1 SECRET_KEY=... ALLOW_DEV_OTP=1 uvicorn api.main:app --port 8000` with a scratch SQLite database. Restart it after backend changes; the frontend is served from `web/dist` after `npm run build`.
- Browser checks use Playwright at 360px. The audit script (`audit.js`) checks overflow and tap targets on every page.
