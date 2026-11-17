# `<name>.solobiz.dev` through Cloudflare (no wildcard domain on Render)

Render needs a card on file to add `*.solobiz.dev`. This route needs none: a
small Cloudflare Worker (free plan) answers `https://<name>.solobiz.dev` with
the page SoloBiz already serves at `https://solobiz.dev/site/<name>`.

```
visitor -> <name>.solobiz.dev  -> Cloudflare Worker -> solobiz.dev/site/<name> (Render)
```

Only the public pieces are forwarded: the site page, `/static/`, `/media/`,
`/favicon.ico`, `robots.txt` and `sitemap.xml`. Everything else (login,
dashboard, API) answers 404 on a business address, and no cookies are passed.
`www`, `admin` and the other reserved names go to the normal site.

The code is `cloudflare/worker.js`; `node cloudflare/worker.test.mjs` runs its
tests.

## One-time setup

Moving DNS is the one risky step: Cloudflare must answer for every record the
domain has today, or things that depend on them (email sending, the admin
site) stop working.

1. **Add the domain to Cloudflare.** Create a free account, choose *Add a
   domain*, enter `solobiz.dev`, pick the **Free** plan. Cloudflare imports the
   existing DNS records. Compare them with your current DNS provider's list and
   add anything missing, in particular:
   - the apex (`solobiz.dev`) and `www` records that point at Render,
   - `admin` if it exists,
   - every `MX` / `TXT` / `CNAME` record used for email (for example the
     Resend verification and DKIM records).
2. **Set apex, `www` and `admin` to "DNS only"** (grey cloud) so Render keeps
   issuing and renewing their certificates as it does now.
3. **Point the domain at Cloudflare.** At the registrar, replace the name
   servers with the two Cloudflare shows. Wait until Cloudflare says the site
   is *Active* (minutes to a few hours). Check that
   `https://solobiz.dev/healthz` still works.
4. **Add the wildcard record** in Cloudflare DNS: type `A`, name `*`, IPv4
   `192.0.2.1` (a placeholder, never contacted), **Proxied** (orange cloud).
   The free Universal certificate covers `*.solobiz.dev`.
5. **Create the Worker.** Workers & Pages -> Create -> Worker -> paste
   `cloudflare/worker.js` -> Deploy. Under the Worker's *Settings -> Domains &
   Routes* add the route `*.solobiz.dev/*` on the `solobiz.dev` zone.
6. **Turn the short address on.** Set the Render environment variable
   `SITE_SUBDOMAINS=1`. Owners are then shown `<name>.solobiz.dev`. The
   `/site/<name>` address keeps working.

## Check it

Publish a website, then open `https://<name>.solobiz.dev`. Also:

```bash
curl -sI https://www.solobiz.dev/ | head -1             # normal site
curl -s  https://no-such-name.solobiz.dev/ | head -c 80  # "No website here"
curl -sI https://<name>.solobiz.dev/login | head -1      # 404 on a business address
```

## Limits

- The Workers free plan allows 100,000 requests a day, which a few hundred
  small business sites will not reach. Past that, the paid plan is about $5 a
  month.
- If a business address is requested while the Render service is asleep (free
  plan), the first visit waits for it to wake up.
- Keep `RESERVED` in `cloudflare/worker.js` in step with `RESERVED_SLUGS` in
  `server/websites.py`.
