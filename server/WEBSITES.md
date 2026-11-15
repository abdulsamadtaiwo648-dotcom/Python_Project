# Business websites on `<name>.solobiz.dev`

Owners build a website from **More → Website** in the dashboard: pick a layout
(Product Store or Service Business), fill in public details, preview, publish.
The site is then served at `https://<slug>.solobiz.dev`.

## How it works

- **Routing** (`server/routes/website_routes.py`): a hook that runs before every
  other request looks at the hostname. `<label>.solobiz.dev` serves only that
  business's published site (plus `/static/`, `/media/`, `robots.txt`,
  `sitemap.xml`); every other path there is 404, so there is no login, dashboard
  or API on business subdomains and they never set cookies. The bare domain,
  reserved names (`www`, `admin`, `api`, ... see `RESERVED_SLUGS` in
  `server/websites.py`) and any other hostname (for example the
  `*.onrender.com` address) get the normal SoloBiz app.
- **Address**: assigned once, on first save or publish, and never changes
  afterwards. It is the store slug when that is a valid hostname label
  (a-z, 0-9, hyphens, 2-40 characters, not reserved, not taken); otherwise a
  shortened or generated one. `/store/<slug>` links are untouched.
- **Draft vs live**: branding, text, services and gallery are a draft until
  the owner publishes. Products are read live from Inventory (only those with
  "Show" switched on), so price and stock changes appear immediately.
- **Images** are stored in the database (`website_media`), not on disk, so
  they survive deploys. Their addresses are random and unguessable.
- **Preview** is `/website/preview` on the main site and needs sign-in.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SITE_BASE_DOMAIN` | `solobiz.dev` | Domain the subdomains hang off |
| `SITE_URL_SCHEME` | `https` | Scheme used in links shown to owners |

Nothing needs setting in production if the domain is `solobiz.dev`. For local
testing: `SITE_BASE_DOMAIN=localhost:5000 SITE_URL_SCHEME=http`, then open
`http://<slug>.localhost:5000` (browsers resolve `*.localhost` by themselves).

## One-time DNS and HTTPS setup (Render)

Publishing needs no per-business DNS. It needs one wildcard, set up once.
These steps are written from Render's wildcard custom domain feature as
documented at the time of writing; confirm the exact record values in the
Render dashboard, which shows them when you add the domain.

1. Render dashboard → the **main SoloBiz web service** (not the admin
   service) → Settings → Custom Domains → Add `*.solobiz.dev`.
2. At the DNS provider for `solobiz.dev`, add the records Render lists. For a
   wildcard these are normally three CNAMEs:

   | Type | Name | Target |
   | --- | --- | --- |
   | CNAME | `*` | `<main-service-name>.onrender.com` |
   | CNAME | `_acme-challenge` | value shown by Render (ends `.verify.renderdns.com`) |
   | CNAME | `_cf-custom-hostname` | value shown by Render (ends `.hostname.renderdns.com`) |

   The two verification records let Render issue and renew the wildcard TLS
   certificate. Their targets are unique to the service and only visible in
   the dashboard.
3. Wait for Render to show the domain as verified and the certificate as
   issued.

Notes:

- `admin.solobiz.dev` keeps working: its own explicit DNS record takes
  priority over the wildcard, and the app also treats `admin` as reserved.
- If the DNS provider is Cloudflare, set the wildcard record to "DNS only"
  (grey cloud) unless Render's instructions say otherwise.
- Wildcard custom domains may require a paid Render plan; check the plan.

## Checks after DNS is live

```bash
curl -sI https://solobiz.dev/login | head -1
```

```bash
curl -sI https://this-name-is-not-used.solobiz.dev/ | head -1
```

The first should be `200`, the second `404` with a valid certificate. Then
publish a site from the dashboard and open its address.
