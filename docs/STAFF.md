# Staff accounts and page access

The owner creates a login for each staff member and sets their password. No
email is sent. Staff sign in on the normal sign-in page with the email and
password the owner gave them.

## Roles

| Role | Pages |
| --- | --- |
| Sales | Sales and receipts (records sales, payments, prints receipts) |
| Inventory | Inventory (products, stock, restocking) |
| Accountant | Dashboard, Expenses, Budget, Reports |
| Custom | Any combination the owner ticks |

Sales staff can read the product list (to pick items on a sale) and the
business name and address (for receipts). They cannot change products or
expenses.

## Always owner-only

- Team (adding, editing, removing staff, setting passwords)
- Plans and payments
- Changing their own password. A staff member's password can only be set or
  changed by the owner. Forgot-password emails are never sent to staff.

## Seats

| Plan | Staff accounts |
| --- | --- |
| Free | 0 |
| Basic | 3 |
| Pro | 10 |

If the owner downgrades, staff beyond the new limit are switched off (oldest
accounts stay on). They are switched back on when the owner upgrades.

## How it is enforced

- **Server (the real check):** every request is checked against the signed-in
  person's pages (`api/permissions.py`). A staff member who asks for a page
  they don't have gets `403` with `code: "not_allowed"`, and owner-only
  requests get `code: "owner_only"`.
- **App:** the sidebar, bottom bar and page routes only show what the person
  may use. A staff member who opens another page is sent to their first page.

Staff work on the owner's business. Their sales, products and expenses are
stored under the owner's account, so the owner sees everything they record.

## Removing staff

Removing a staff member deletes their login. Records they created stay with the
business.

## Tests

`tests/test_staff.py` covers every role, the owner-only rules, the password
rules, seats, downgrades and removal.
