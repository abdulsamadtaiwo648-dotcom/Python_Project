"""Website builder: draft, publish, product visibility and image upload."""

import json
import secrets
from typing import Any

from fastapi import Body, File, Request, UploadFile

from server import websites
from server.database import get_db

from .. import core
from ..compat import JsonRouter, jsonify
from ..deps import current_user_id

record_user_activity = core.record_user_activity
router = JsonRouter()



def _unauthorized():
    return jsonify({"status": "error", "message": "Unauthorized"}), 401


@router.api_route("/api/website/media", methods=['POST'])
def website_media_upload(request: Request, image: UploadFile = File(None)):
    user_id = current_user_id(request)
    if not user_id:
        return _unauthorized()
    upload = image
    if not upload or not upload.filename:
        return jsonify({"status": "error", "message": "Choose an image to upload."}), 400
    data = upload.file.read(websites.MAX_MEDIA_BYTES + 1)
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


@router.api_route("/api/website", methods=['GET', 'PUT'])
def website_api(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return _unauthorized()
    with get_db() as db:
        if request.method == "GET":
            return jsonify({"status": "success", "website": _state(db, user_id)})

        data = payload
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


@router.api_route("/api/website/publish", methods=['POST'])
def website_publish(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
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


@router.api_route("/api/website/unpublish", methods=['POST'])
def website_unpublish(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
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


@router.api_route("/api/website/products/{product_id}", methods=['PUT'])
def website_product(product_id: int, request: Request, payload: Any = Body(None)):
    """Website-only product settings: visibility and photo (live, not drafted)."""
    user_id = current_user_id(request)
    if not user_id:
        return _unauthorized()
    data = payload or {}
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


