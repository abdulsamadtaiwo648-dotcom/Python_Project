# Standalone SoloBiz admin portal

The admin portal is a separate Flask app. It has its own login, session cookie,
and `super_admins` table; regular SoloBiz accounts cannot sign in to it.

## Run locally

From the repository root, configure `DATABASE_URL` to the Neon database used by
the main SoloBiz app, and set a private `ADMIN_SECRET_KEY`. Then run:

```powershell
$env:ADMIN_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")
python -m server.create_admin
python -m server.admin_run
```

Open `http://localhost:5001`. The account creation command asks for the admin
email and password interactively; it stores only a password hash.

Use `python -m server.create_admin reset` to reset an admin password, or
`python -m server.create_admin disable` / `enable` to revoke or restore portal
access from a trusted shell.

## Deploy separately on Render

Create a second **Web Service** from this same repository. Use:

- Build command: `pip install -r server/requirements.txt`
- Start command: `gunicorn server.admin_run:admin_app`
- Environment: set `DATABASE_URL` to the same Neon database as the main service,
  set `ADMIN_SECRET_KEY` to a new long random secret, and set
  `ADMIN_COOKIE_SECURE=true`.

Create the first admin account from the service shell with:

```text
python -m server.create_admin
```

Add `admin.solobiz.dev` as a custom domain on this second service and configure
the DNS record Render provides. Keep the existing SoloBiz web service on its
current domain. The portal includes an adoption overview, a searchable business
directory, per-business account pages with sales, expenses and activity behind a
support grant, reversible account pausing, test-account marking, admin access review,
an admin activity log, a user activity page, and a system status page. Financial records are read-only in the
portal. Admin and business activity records are retained for approximately one year.

## Roles and access

Every admin route checks the signed-in admin's role on the server, on each request.
Changes to a role or to access take effect at the next request.

| Role | Overview, businesses, business overview, system status | Sales, expenses, business activity | User activity page | Pause or restore accounts, mark test accounts | Admin activity | Manage admins |
|---|---|---|---|---|---|---|
| Owner | Yes | With a support grant | Yes | Yes | Yes | Yes |
| Support | Yes | With a support grant | Yes | Yes | Yes | No |
| Viewer | Yes | No | No | No | No | No |

Existing admins were set to Owner by the migration, so nothing changes for them.
New admins can be given a role from the server shell:

```text
python -m server.create_admin --role support
```

## Support access to a business

Sales, expenses and business activity are hidden until an admin enters a support
ticket reference and a reason on that business's page. The access lasts 20 minutes,
applies to that business only, and every view is written to the admin activity log
with the ticket and reason. A reason alone does not open access.

## Test accounts

Test and demo accounts are excluded from the overview figures. An admin marks an
account with a reason on its business page. The portal never infers this from a name
or email address.

## Adoption figures

- **Active businesses, last 7 days:** businesses with a sale, sale payment, expense or
  inventory change in the last 7 calendar days, counted once each. Sign-ins are shown
  separately and are not counted.
- **Registered accounts, business profiles, paused accounts:** exclude test accounts.

## User activity and system status

User activity lists sales, expenses, inventory, sign-ins and profile changes across
all businesses, as event summaries only (no amounts or customer names). It needs the
Support or Owner role. Each view is recorded in Admin activity.

System status checks that the database answers. Request volume, error rate, p95
response time and recent failures show "Not available": the app does not record
request logs yet.

## Running the admin tests

From the repository root, after installing `server/requirements.txt`:

```bash
python -m pytest admin_tests -q
```

These tests use Flask's test client and a temporary SQLite database. They do not
need the FastAPI test client.
