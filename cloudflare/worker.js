// Cloudflare Worker: serves each published business website at
// https://<name>.solobiz.dev without needing a wildcard domain on Render.
//
// A request for <name>.solobiz.dev/ is answered with the page SoloBiz already
// serves at https://solobiz.dev/site/<name>. Only the public pieces a website
// needs are forwarded (the page, /static, /media, /favicon.ico); there is no
// sign-in, dashboard or API on these hostnames, and no cookies are passed.
//
// Deploy: see docs/CLOUDFLARE_SUBDOMAINS.md. Route: *.solobiz.dev/*

const BASE = "solobiz.dev";
const ORIGIN = "https://solobiz.dev";

// Keep in step with RESERVED_SLUGS in server/websites.py. These names belong to
// SoloBiz itself (www, admin, api ...) and are passed straight through.
const RESERVED = new Set(`
  www www1 www2 api admin administrator app apps dashboard account accounts login logout
  register signup signin auth oauth sso mail email webmail smtp imap pop pop3 mx ftp sftp
  ns ns1 ns2 dns cdn static assets media img images files uploads download downloads
  store stores shop site sites website websites web blog docs help support status contact
  about legal privacy terms security billing pay payment payments checkout
  dev staging stage test testing demo preview beta internal root system
  solobiz solo-biz team staff official m mobile go link links
  autoconfig autodiscover localhost
`.split(/\s+/).filter(Boolean));

const LABEL = /^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$/;

const notFound = () =>
  new Response(
    "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>" +
      "<meta name=robots content=noindex><title>No website here</title>" +
      "<body style='font:16px system-ui;padding:48px 24px;text-align:center;color:#0f172a'>" +
      "<h1>No website here</h1><p style='color:#64748b'>This address is not in use yet.</p></body>",
    { status: 404, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex" } },
  );

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const host = url.hostname.toLowerCase();
    if (host === BASE || !host.endsWith("." + BASE)) return fetch(request);

    const label = host.slice(0, -(BASE.length + 1));
    if (RESERVED.has(label)) return fetch(request); // www, admin ...: the normal site
    if (!LABEL.test(label)) return notFound();
    if (request.method !== "GET" && request.method !== "HEAD") return notFound();

    const own = `${url.protocol}//${host}`;
    if (url.pathname === "/robots.txt") {
      return new Response(`User-agent: *\nAllow: /\n\nSitemap: ${own}/sitemap.xml\n`, { headers: { "Content-Type": "text/plain" } });
    }

    let target;
    let assets = false;
    if (url.pathname === "/" ) target = `${ORIGIN}/site/${label}`;
    else if (url.pathname.startsWith("/static/") || url.pathname.startsWith("/media/") || url.pathname === "/favicon.ico") {
      target = `${ORIGIN}${url.pathname}${url.search}`;
      assets = true;
    } else if (url.pathname === "/sitemap.xml") {
      // Only list the site if it exists.
      const probe = await fetch(`${ORIGIN}/site/${label}`, { method: "HEAD", headers: { Accept: "text/html" } });
      if (!probe.ok) return notFound();
      return new Response(
        `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>${own}/</loc></url>\n</urlset>`,
        { headers: { "Content-Type": "application/xml" } },
      );
    } else return notFound();

    // Public content only: never forward cookies or other request headers.
    const upstream = await fetch(target, {
      method: request.method,
      headers: { Accept: request.headers.get("Accept") || "*/*", "Accept-Language": request.headers.get("Accept-Language") || "" },
      redirect: "manual",
      ...(assets ? { cf: { cacheEverything: true, cacheTtl: 86400 } } : {}),
    });
    if (upstream.status >= 300 && upstream.status < 400) return notFound();

    const response = new Response(upstream.body, upstream);
    response.headers.delete("Set-Cookie");
    if (!assets) response.headers.set("Cache-Control", "public, max-age=60, stale-while-revalidate=300");
    return response;
  },
};
