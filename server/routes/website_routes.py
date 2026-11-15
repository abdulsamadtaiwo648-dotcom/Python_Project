"""Business website routes: public sites on subdomains, and the owner's setup."""

import json
import logging
import secrets

from flask import Response, g, jsonify, redirect, render_template, request

from .. import websites
from ..app import app, get_current_user_id, get_db, record_user_activity

# What a business subdomain may serve besides its home page. Everything else
# (login, dashboard, APIs) answers 404 there, so those hosts are public-only.
_SITE_PASSTHROUGH_PREFIXES = ("/static/", "/media/")
_SITE_PASSTHROUGH_PATHS = ("/favicon.ico",)


def _unauthorized():
    return jsonify({"status": "error", "message": "Unauthorized"}), 401


def _site_not_found():
    response = app.make_response((render_template("site_404.html"), 404))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response


def _site_context(content, user_id, slug, preview=False):
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
        # Products are ordered by message: WhatsApp when published, else the main action.
        order_number = whatsapp or (websites.whatsapp_digits(action.get("value")) if action.get("type") == "whatsapp" and href else "")
        order_base = f"https://wa.me/{order_number}" if order_number else ""

    description = content.get("tagline") or (content.get("about") or "")[:160] or f"{name} on SoloBiz"
    return {
        "site": content,
        "name": name,
        "palette": websites.brand_palette(content.get("brand_color")),
        "products": products,
        "services": content.get("services") or [],
        "gallery": content.get("gallery") or [],
        "action_href": href,
        "action_label": action_label,
        "action_type": action.get("type"),
        "order_base": order_base,
        "whatsapp_digits": whatsapp,
        "has_contact": any(content.get(k) for k in ("phone", "whatsapp", "email", "instagram", "address", "hours")),
        "site_url": websites.website_url(slug),
        # Images are addressed from the host that serves them.
        "media_origin": websites.website_url(slug) if websites.subdomains_enabled() else websites.main_origin(),
        "meta_description": description,
        "preview": preview,
        "naira": websites.format_naira,
    }


# ---------------------------------------------------------------------------
# Hostname routing. Runs before every other request hook so a business
# subdomain never touches sessions, CSRF tokens or the dashboard.
# ---------------------------------------------------------------------------
def route_business_subdomain():
    label = websites.site_label_for_host(request.host)
    if not label:
        return None
    g.site_label = label

    if request.method not in ("GET", "HEAD"):
        return _site_not_found()
    path = request.path
    if path.startswith(_SITE_PASSTHROUGH_PREFIXES) or path in _SITE_PASSTHROUGH_PATHS:
        return None

    with get_db() as db:
        site = websites.find_published_site(db, label)
    if not site:
        return _site_not_found()

    own_origin = f"{request.scheme}://{request.host}"
    if path == "/robots.txt":
        return Response(f"User-agent: *\nAllow: /\n\nSitemap: {own_origin}/sitemap.xml\n", mimetype="text/plain")
    if path == "/sitemap.xml":
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               f"  <url><loc>{own_origin}/</loc></url>\n</urlset>")
        return Response(xml, mimetype="application/xml")
    if path != "/":
        return _site_not_found()

    response = app.make_response(render_template(
        "website.html", **_site_context(site["content"], site["user_id"], site["slug"])
    ))
    # The page differs per hostname; never let a shared cache mix businesses.
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Vary"] = "Host"
    return response


app.before_request_funcs.setdefault(None, []).insert(0, route_business_subdomain)


@app.route("/site/<slug>")
def website_by_path(slug):
    """The same published website at https://<base>/site/<slug>.

    Needs no DNS, so it works before (and after) subdomains are switched on.
    """
    with get_db() as db:
        site = websites.find_published_site(db, slug.lower())
    if not site:
        return _site_not_found()
    response = app.make_response(render_template(
        "website.html", **_site_context(site["content"], site["user_id"], site["slug"])
    ))
    response.headers["Cache-Control"] = "no-cache"
    return response


# ---------------------------------------------------------------------------
# Images (stored in the database; addresses are unguessable)
# ---------------------------------------------------------------------------
@app.route("/media/<token>")
def website_media(token):
    with get_db() as db:
        row = db.execute("SELECT content_type, data FROM website_media WHERE token = ?", (token,)).fetchone()
    if not row:
        return ("Not found", 404)
    response = Response(bytes(row["data"]), mimetype=row["content_type"])
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route("/api/website/media", methods=["POST"])
def website_media_upload():
    user_id = get_current_user_id()
    if not user_id:
        return _unauthorized()
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify({"status": "error", "message": "Choose an image to upload."}), 400
    data = upload.read(websites.MAX_MEDIA_BYTES + 1)
    if len(data) > websites.MAX_MEDIA_BYTES:
        return jsonify({"status": "error", "message": "That image is larger than 2 MB. Choose a smaller one."}), 400
    content_type = websites.sniff_image_type(data)
    if not content_type:
        return jsonify({"status": "error", "message": "Use a JPG, PNG or WebP image."}), 400

    token = secrets.token_urlsafe(18)
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) AS total FROM website_media WHERE user_id = ?", (user_id,)).fetchone()
        if int(dict(count)["total"]) >= websites.MAX_MEDIA_PER_USER:
            return jsonify({"status": "error", "message": "You have reached the image limit for your website."}), 400
        db.execute(
            "INSERT INTO website_media (user_id, token, content_type, data, size, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, token, content_type, data, len(data), websites.utcnow_iso()),
        )
        db.commit()
    return jsonify({"status": "success", "url": f"/media/{token}"}), 201


# ---------------------------------------------------------------------------
# Owner setup (main SoloBiz host only; every call acts on the caller's own site)
# ---------------------------------------------------------------------------
def _state(db, user_id):
    profile = websites.get_profile(db, user_id)
    site = websites.get_website(db, user_id)
    if site:
        content, slug = site["draft"], site["slug"]
    else:
        content = websites.default_content(profile)
        slug = websites.choose_slug(db, user_id, profile.get("store_slug"), content.get("display_name"))
    rows = db.execute(
        "SELECT id, item_name, price, stock, track_stock, image_url, COALESCE(show_on_website, 1) AS show_on_website "
        "FROM inventory_presets WHERE user_id = ? ORDER BY id ASC", (user_id,),
    ).fetchall()
    products = [{
        "id": dict(r)["id"], "name": dict(r)["item_name"], "price": float(dict(r)["price"]),
        "image_url": dict(r).get("image_url") or "", "show_on_website": bool(dict(r)["show_on_website"]),
        "sold_out": bool(dict(r).get("track_stock")) and int(dict(r).get("stock") or 0) <= 0,
    } for r in rows]
    shown = sum(1 for p in products if p["show_on_website"])
    published = bool(site and site["is_published"])
    return {
        "exists": bool(site),
        "content": content,
        "slug": slug,
        "address": websites.website_address(slug),
        "url": websites.website_url(slug),
        "is_published": published,
        "published_at": (site or {}).get("published_at") or "",
        "has_unpublished_changes": bool(published and site["published"] != site["draft"]),
        "publish_problems": websites.publish_problems(content, shown),
        "products": products,
        "profile_logo": profile.get("logo_url") or "",
        "store_url": f"/store/{profile['store_slug']}" if profile.get("store_slug") else "",
        "action_types": websites.ACTION_TYPES,
    }


@app.route("/website")
def website_builder_page():
    if not get_current_user_id():
        return redirect("/login")
    return render_template("website_builder.html")


@app.route("/api/website", methods=["GET", "PUT"])
def website_api():
    user_id = get_current_user_id()
    if not user_id:
        return _unauthorized()
    with get_db() as db:
        if request.method == "GET":
            return jsonify({"status": "success", "website": _state(db, user_id)})

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Website details must be sent as JSON."}), 400
        profile = websites.get_profile(db, user_id)
        content, errors = websites.clean_content(data, user_id, db, profile.get("logo_url") or "")
        websites.ensure_website(db, user_id, content)
        db.commit()
        return jsonify({
            "status": "success",
            "message": "Draft saved." if not errors else "Draft saved, but some details need fixing.",
            "errors": errors,
            "website": _state(db, user_id),
        })


@app.route("/api/website/publish", methods=["POST"])
def website_publish():
    user_id = get_current_user_id()
    if not user_id:
        return _unauthorized()
    with get_db() as db:
        site = websites.get_website(db, user_id)
        if not site:
            site = websites.ensure_website(db, user_id, websites.default_content(websites.get_profile(db, user_id)))
        shown = db.execute(
            "SELECT COUNT(*) AS total FROM inventory_presets WHERE user_id = ? AND COALESCE(show_on_website, 1) = 1",
            (user_id,),
        ).fetchone()
        problems = websites.publish_problems(site["draft"], int(dict(shown)["total"]))
        if problems:
            db.commit()
            return jsonify({"status": "error", "message": "Your website is not ready to publish yet.", "problems": problems}), 400

        first_time = not site["is_published"]
        now = websites.utcnow_iso()
        # Publishing again is safe: the same row and address are reused.
        db.execute(
            "UPDATE business_websites SET published = ?, is_published = 1, published_at = ?, updated_at = ? WHERE user_id = ?",
            (json.dumps(site["draft"]), now, now, user_id),
        )
        record_user_activity(db, user_id, "website_published", "Published the business website" if first_time else "Published website changes")
        db.commit()
        return jsonify({"status": "success", "message": "Your website is live.", "website": _state(db, user_id)})


@app.route("/api/website/unpublish", methods=["POST"])
def website_unpublish():
    user_id = get_current_user_id()
    if not user_id:
        return _unauthorized()
    with get_db() as db:
        db.execute(
            "UPDATE business_websites SET is_published = 0, updated_at = ? WHERE user_id = ?",
            (websites.utcnow_iso(), user_id),
        )
        record_user_activity(db, user_id, "website_unpublished", "Took the business website offline")
        db.commit()
        return jsonify({"status": "success", "message": "Your website is offline.", "website": _state(db, user_id)})


@app.route("/api/website/products/<int:product_id>", methods=["PUT"])
def website_product(product_id):
    """Website-only product settings: visibility and photo (live, not drafted)."""
    user_id = get_current_user_id()
    if not user_id:
        return _unauthorized()
    data = request.get_json(silent=True) or {}
    with get_db() as db:
        row = db.execute("SELECT id FROM inventory_presets WHERE id = ? AND user_id = ?", (product_id, user_id)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Product not found."}), 404
        if "show_on_website" in data:
            db.execute(
                "UPDATE inventory_presets SET show_on_website = ? WHERE id = ? AND user_id = ?",
                (1 if data.get("show_on_website") else 0, product_id, user_id),
            )
        if "image_url" in data:
            image_url = str(data.get("image_url") or "").strip()
            if image_url:
                match = websites._MEDIA_URL_RE.match(image_url)
                owned = match and db.execute(
                    "SELECT 1 FROM website_media WHERE token = ? AND user_id = ?", (match.group(1), user_id)
                ).fetchone()
                if not owned:
                    return jsonify({"status": "error", "message": "That image could not be used. Upload it again."}), 400
            db.execute(
                "UPDATE inventory_presets SET image_url = ? WHERE id = ? AND user_id = ?",
                (image_url or None, product_id, user_id),
            )
        db.commit()
        return jsonify({"status": "success", "website": _state(db, user_id)})


@app.route("/website/preview")
def website_preview():
    """The owner's private preview of their draft, drawn by the public template."""
    user_id = get_current_user_id()
    if not user_id:
        return redirect("/login")
    try:
        with get_db() as db:
            state = _state(db, user_id)
    except Exception:
        logging.exception("Could not build website preview")
        raise
    response = app.make_response(render_template(
        "website.html", **_site_context(state["content"], user_id, state["slug"], preview=True)
    ))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    return response
