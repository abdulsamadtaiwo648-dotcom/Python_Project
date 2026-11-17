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
* The app opens offline with the last saved records. Recording sales and
  changes needs a connection; the earlier offline queue was not ported.
* The `/delete/<id>` and `/edit/<id>` expense form pages were removed; the app
  uses the JSON endpoints.

## API surface

`GET /api/session` returns the CSRF token and the signed-in user. Everything
that writes needs that token in `X-CSRFToken`. Interactive schema:
`/api/openapi.json`.
