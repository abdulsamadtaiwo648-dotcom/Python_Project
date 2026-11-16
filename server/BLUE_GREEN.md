# Blue-green deployment on Render

**Blue** is the live service `solobiz` (branch `main`, `solobiz.dev`).
**Green** is a second service running the new release against the same
database. Green is tested first; visitors are switched only when it passes;
blue stays available for rollback.

## Why this is safe with one shared database

- New releases only add tables and columns (with defaults), so the old code
  keeps working while both versions run.
- The Floor tables, which the old code still uses, are dropped only when
  `DROP_FLOOR_TABLES=1` is set. Leave it unset until blue is retired.
- Use the **same `SECRET_KEY`** on both services so people stay signed in
  across the switch.

Known limit: logos and website photos uploaded through green are served by
`/media/...`, which the old code does not have. After a rollback those images
would not show until green is live again. No data is lost.

## 1. Create green

Render dashboard → New → Web Service → same repository.

| Setting | Value |
| --- | --- |
| Name | `solobiz-green` |
| Branch | the release branch (e.g. `claude/lucid-edison-xzhrl7`) |
| Region | Virginia (same as blue and the database) |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn app:app` |
| Health check path | `/healthz` |
| Instance type | Free |

Environment variables: copy `DATABASE_URL`, `RESEND_API_KEY` and
`SECRET_KEY` from blue (same values). Do not set `DROP_FLOOR_TABLES`.

## 2. Test green

```bash
python -m server.tools.smoke_test https://solobiz-green.onrender.com
```

It is read-only and must end with "All checks passed". Then sign in on the
green address with a real account and check the dashboard, a sale, an
expense and the Website screen. Green uses live data, so anything you save
is real.

Also set **Health check path** to `/healthz` on blue (Settings), so Render
only sends traffic to a version that can reach the database.

## 3. Switch visitors to the new release

**Option A — promote by merge (recommended, no DNS change).** Merge the
release branch into `main`. Blue redeploys the exact code green proved.
Roll back with Render's **Rollback** on the previous deploy (Deploys tab),
or by reverting the merge.

**Option B — move the domain (true traffic switch).** On blue remove
`solobiz.dev` and `www.solobiz.dev`; on green add them; point the `www`
CNAME at `solobiz-green.onrender.com`. The site is unreachable for the few
minutes Render takes to verify the domain and issue the certificate, so do
it at a quiet time. Roll back by moving the domains back. Afterwards green
is the live service and blue becomes the standby.

## 4. After a few stable days

- Set `DROP_FLOOR_TABLES=1` on the live service to remove the Floor tables.
- Keep the standby service for the next release (deploy there first), or
  delete it. Free services sleep when idle, so a standby costs nothing.
