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
current domain. The portal includes a platform overview, searchable business
accounts, cross-business sales and expense views, amount and payment-status
filters, reversible account pausing, reason-gated data views, login throttling,
an administrator audit history, and a user activity feed for sign-ins, password
resets, transactions, inventory changes, and profile updates or requests.
Financial records can be reviewed but are not changed through the portal.
Admin and user activity records are retained for approximately one year.
