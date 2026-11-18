"""Server-rendered pages (landing, legal, business websites) and the React shell."""

import html as html_lib
import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from server import websites
from server.database import get_db

from .deps import current_user_id
from .settings import CLIENT_ROOT, WEB_DIST, settings

templates = Jinja2Templates(directory=str(CLIENT_ROOT / "templates"))
router = APIRouter()

# Pages the React app owns. Each serves the same shell; the router takes over.
APP_PATHS = ("/login", "/register", "/dashboard", "/sales", "/inventory", "/expenses",
             "/budget", "/profile", "/reports", "/website", "/plans")
AUTH_PATHS = ("/login", "/register")


def render(request: Request, name: str, context: dict | None = None, status: int = 200, **headers):
    response = templates.TemplateResponse(request, name, context or {}, status_code=status)
    for key, value in headers.items():
        response.headers[key.replace("_", "-")] = value
    return response


# --- Business websites ------------------------------------------------------
def site_404(request: Request):
    return render(request, "site_404.html", status=404, Cache_Control="no-store", X_Robots_Tag="noindex")


def site_context(content, user_id, slug, preview=False):
    """Everything the public template needs, for live sites and previews alike."""
    with get_db() as db:
        products = websites.public_products(db, user_id) if content.get("layout") == "product" else []
    name = content.get("display_name") or "Your business"
    action = content.get("action") or {}
    href = websites.action_href(action, name)
    action_label = action.get("label") or websites.ACTION_TYPES.get(action.get("type"), "Contact us")
    whatsapp = websites.whatsapp_digits(content.get("whatsapp")) if content.get("whatsapp") else ""
    order_base = ""
    if content.get("layout") == "product":
        order_number = whatsapp or (websites.whatsapp_digits(action.get("value")) if action.get("type") == "whatsapp" and href else "")
        order_base = f"https://wa.me/{order_number}" if order_number else ""
    description = content.get("tagline") or (content.get("about") or "")[:160] or f"{name} on SoloBiz"
    return {
        "site": content, "name": name, "palette": websites.brand_palette(content.get("brand_color")),
        "products": products, "services": content.get("services") or [], "gallery": content.get("gallery") or [],
        "action_href": href, "action_label": action_label, "action_type": action.get("type"),
        "order_base": order_base, "whatsapp_digits": whatsapp,
        "has_contact": any(content.get(k) for k in ("phone", "whatsapp", "email", "instagram", "address", "hours")),
        "site_url": websites.website_url(slug),
        "media_origin": websites.website_url(slug) if websites.subdomains_enabled() else websites.main_origin(),
        "meta_description": description, "preview": preview, "naira": websites.format_naira,
    }


SITE_PASSTHROUGH_PREFIXES = ("/static/", "/media/")
SITE_PASSTHROUGH_PATHS = ("/favicon.ico",)


async def business_subdomain_middleware(request: Request, call_next):
    """A business subdomain only ever serves its public site: no sessions, no app."""
    label = websites.site_label_for_host(request.headers.get("host", ""))
    if not label:
        return await call_next(request)
    if request.method not in ("GET", "HEAD"):
        return site_404(request)
    path = request.url.path
    if path.startswith(SITE_PASSTHROUGH_PREFIXES) or path in SITE_PASSTHROUGH_PATHS:
        return await call_next(request)
    with get_db() as db:
        site = websites.find_published_site(db, label)
    if not site:
        return site_404(request)
    origin = f"{request.url.scheme}://{request.headers.get('host')}"
    if path == "/robots.txt":
        return Response(f"User-agent: *\nAllow: /\n\nSitemap: {origin}/sitemap.xml\n", media_type="text/plain")
    if path == "/sitemap.xml":
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               f"  <url><loc>{origin}/</loc></url>\n</urlset>")
        return Response(xml, media_type="application/xml")
    if path != "/":
        return site_404(request)
    # The page differs per hostname; never let a shared cache mix businesses.
    return render(request, "website.html", site_context(site["content"], site["user_id"], site["slug"]),
                  Cache_Control="no-cache", Vary="Host")


@router.get("/site/{slug}")
def website_by_path(slug: str, request: Request):
    """The same published website at https://<base>/site/<slug>; needs no DNS."""
    with get_db() as db:
        site = websites.find_published_site(db, slug.lower())
    if not site:
        return site_404(request)
    return render(request, "website.html", site_context(site["content"], site["user_id"], site["slug"]),
                  Cache_Control="no-cache")


@router.get("/media/{token}")
def website_media(token: str):
    with get_db() as db:
        row = db.execute("SELECT content_type, data FROM website_media WHERE token = ?", (token,)).fetchone()
    if not row:
        return Response("Not found", status_code=404)
    return Response(bytes(row["data"]), media_type=row["content_type"], headers={
        "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"})


@router.get("/website/preview")
def website_preview(request: Request):
    """The owner's private preview of their draft, drawn by the public template."""
    user_id = current_user_id(request)
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    from .routers.website import _state

    try:
        with get_db() as db:
            state = _state(db, user_id)
    except Exception:
        logging.exception("Could not build website preview")
        raise
    return render(request, "website.html", site_context(state["content"], user_id, state["slug"], preview=True),
                  Cache_Control="no-store", X_Robots_Tag="noindex")


# --- Public pages -----------------------------------------------------------
@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def landing(request: Request):
    if current_user_id(request):
        return RedirectResponse("/dashboard", status_code=302)
    return render(request, "landing.html")


@router.api_route("/privacy", methods=["GET", "HEAD"], response_class=HTMLResponse)
def privacy(request: Request):
    return render(request, "privacy.html")


@router.api_route("/data-access", methods=["GET", "HEAD"], response_class=HTMLResponse)
def data_access(request: Request):
    return render(request, "data_access.html")


@router.get("/sw.js")
def service_worker():
    body = templates.get_template("sw.js").render(version=settings.app_version)
    return Response(body, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@router.get("/sitemap.xml")
def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://solobiz.dev/</loc><lastmod>2026-09-20</lastmod><priority>1.0</priority></url>
  <url><loc>https://solobiz.dev/login</loc><priority>0.8</priority></url>
  <url><loc>https://solobiz.dev/register</loc><priority>0.8</priority></url>
  <url><loc>https://solobiz.dev/privacy</loc><priority>0.5</priority></url>
</urlset>"""
    return Response(xml, media_type="application/xml")


@router.get("/robots.txt")
def robots():
    txt = ("User-agent: *\nAllow: /\nAllow: /login\nAllow: /register\nAllow: /privacy\n"
           "Disallow: /dashboard\nDisallow: /api/\n\nSitemap: https://solobiz.dev/sitemap.xml")
    return Response(txt, media_type="text/plain; charset=utf-8")


@router.get("/favicon.ico")
def favicon():
    return FileResponse(CLIENT_ROOT / "static" / "favicon.png", media_type="image/png")


@router.get("/analytics")
def analytics_redirect():
    return RedirectResponse("/dashboard", status_code=302)


@router.get("/dashboard/{section}")
def legacy_section(section: str, request: Request):
    if section == "analytics":
        return RedirectResponse("/dashboard", status_code=302)
    if section in {"expenses", "sales", "inventory", "budget", "profile"}:
        return RedirectResponse(f"/{section}", status_code=302)
    return render(request, "404.html", status=404)


# --- Storefront (kept from the first release) --------------------------------
@router.get("/api/avatar/{store_slug}")
def avatar(store_slug: str):
    company_name = store_slug
    color_hex = "1D4ED8"
    with get_db() as db:
        profile = db.execute(
            "SELECT company_name, brand_color FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
            (store_slug,),
        ).fetchone()
        if profile:
            if profile["company_name"]:
                company_name = profile["company_name"]
            if profile["brand_color"]:
                color_hex = profile["brand_color"].replace("#", "")
    if not re.fullmatch(r"[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6}", color_hex):
        color_hex = "1D4ED8"
    initials = html_lib.escape((company_name[:2] if len(company_name) >= 2 else (company_name[:1] or "B")).upper())
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="120" fill="#{color_hex}"/>
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-weight="900" font-size="210">{initials}</text>
</svg>'''
    return Response(svg, media_type="image/svg+xml")


@router.get("/store/{store_slug}")
def public_storefront(store_slug: str, request: Request):
    with get_db() as db:
        profile = db.execute(
            "SELECT * FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)", (store_slug,)
        ).fetchone()
    if not profile:
        return render(request, "landing.html", status=404)
    profile_dict = dict(profile)
    base_url = f"{request.url.scheme}://{request.headers.get('host', '')}"
    logo_path = profile_dict.get("logo_url")
    if logo_path:
        logo_absolute_url = logo_path if logo_path.startswith(("http://", "https://")) else base_url + (
            logo_path if logo_path.startswith("/") else "/" + logo_path)
    else:
        logo_absolute_url = f"{base_url}/api/avatar/{store_slug}"
    sales_count = 0
    try:
        with get_db() as db:
            res = db.execute("SELECT COUNT(*) as count FROM income WHERE user_id = ?", (profile_dict["user_id"],)).fetchone()
            sales_count = res["count"] if res else 0
    except Exception:
        pass
    return render(request, "storefront.html", {"profile": profile_dict, "sales_count": sales_count,
                                               "logo_absolute_url": logo_absolute_url})


# --- React app shell ---------------------------------------------------------
def spa_shell():
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return HTMLResponse(
        "<!doctype html><title>SoloBiz</title><p>The app has not been built yet. "
        "Run <code>npm run build</code> in <code>web/</code>.</p>", status_code=503)


def make_app_page(path: str):
    def page(request: Request):
        signed_in = bool(current_user_id(request))
        if path in AUTH_PATHS and signed_in:
            return RedirectResponse("/dashboard", status_code=302)
        if path not in AUTH_PATHS and not signed_in:
            return RedirectResponse("/login", status_code=302)
        response = spa_shell()
        if path in AUTH_PATHS:
            response.headers["Cache-Control"] = "no-store"
        return response

    page.__name__ = "app_page_" + path.strip("/")
    return page


for _path in APP_PATHS:
    router.add_api_route(_path, make_app_page(_path), methods=["GET", "HEAD"], include_in_schema=False)
