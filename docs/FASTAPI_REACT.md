# SoloBiz on FastAPI and React

One service serves everything:

| Part | Where | Notes |
| --- | --- | --- |
| JSON API | `api/routers/*` | FastAPI. Cookie session, CSRF header `X-CSRFToken`. |
| Public pages | `api/pages.py`, `client/templates/*` | Landing, privacy, data access, business websites (`/site/<slug>` and subdomains), shop pages. Server-rendered with Jinja, as before. |
| Signed-in app | `web/` | React + TypeScript (Vite). Sign in, register, Dashboard, Sales, Inventory, Expenses, Budget, Reports, Profile, Website builder. |
| Database | `server/database.py` | Unchanged: SQLite locally, PostgreSQL (Neon) when `DATABASE_URL` is set. |

## Run it locally

```bash
pip install -r requirements-dev.txt
cd web && npm install && npm run build && cd ..
python -m api.run            # http://localhost:5000
```

For front-end work run the API on port 8000 (`uvicorn app:app --port 8000`) and
`npm run dev` in `web/`; Vite proxies `/api`, `/static` and `/media` to it.

`npm run typecheck` checks the TypeScript; `pytest` runs the backend tests.

## Deploy on Render

Change the existing service to (or create it from `render.yaml`):

* Build command: `pip install -r requirements.txt && cd web && npm ci && npm run build`
* Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'`
* Health check path: `/healthz`

The environment variables are the same as before (`SECRET_KEY`, `DATABASE_URL`,
`SITE_BASE_DOMAIN`, mail and push keys). The old start command
`gunicorn app:app` no longer works: the app is ASGI now. Run
`python -m server.tools.smoke_test <url>` against the new release before it
takes traffic.

## What changed for users

* Existing sessions are signed out once: the cookie format changed.
* The app is one page that switches views without reloading.
* Budgets are still stored per device (browser storage).
* Offline works. The app opens without a connection and shows the last saved
  records. Sales, payments, expenses (add, edit, delete) and sale deletions made
  offline are saved on the device, shown straight away marked "Not synced", and
  sent in order when the connection returns. Each carries an id the server
  remembers (`X-Client-Op`, table `client_ops`), so nothing is applied twice.
  The waiting changes are written to two places on the device (localStorage and
  IndexedDB) and the browser is asked to keep them; they survive closing the app,
  restarting or switching off the device, and signing out. A payment on a sale
  that has not synced yet is merged into that waiting sale. Changes are only
  discarded when the server rejects them for a reason about the change itself;
  being signed out, a stale token or a server error keeps them for the next try.
  A change the server rejects (for example, not enough stock) is reported in a
  banner. Inventory, profile and website changes still need a connection.
* The `/delete/<id>` and `/edit/<id>` expense form pages were removed; the app
  uses the JSON endpoints.

## API surface

`GET /api/session` returns the CSRF token and the signed-in user. Everything
that writes needs that token in `X-CSRFToken`. Interactive schema:
`/api/openapi.json`.
