"""Business profile: details, logo and verified changes."""

import re
import uuid

from typing import Any

from fastapi import Body, Request
from fastapi.concurrency import run_in_threadpool

from server import websites
from server.database import get_db

from .. import core
from ..compat import JsonRouter, jsonify, to_response
from ..deps import current_user_id
from ..profile_lock import changed_locked_fields, date_text, lock_status, now_utc

record_user_activity = core.record_user_activity
sanitize_brand_color = core.sanitize_brand_color
sanitize_logo_url = core.sanitize_logo_url
send_and_store_otp = core.send_and_store_otp
verify_otp = core.verify_otp
router = JsonRouter()

PROFILE_CHANGE_REASONS = {
    "business_rebrand": "Business rebrand",
    "contact_update": "Contact information update",
    "business_relocation": "Business location change",
    "business_details": "Business details correction",
    "other": "Other",
}


def slugify(text):
    if not text:
        return "store"
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-') or "store"


def get_unique_store_slug(company_name, user_id, current_slug=None):
    """Return a public storefront slug that cannot point at another user."""
    base_slug = slugify(company_name)
    if current_slug:
        with get_db() as db:
            current_owner = db.execute(
                "SELECT user_id FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
                (current_slug,)
            ).fetchone()
        if current_owner and str(current_owner["user_id"]) == str(user_id):
            return current_slug

    with get_db() as db:
        existing = db.execute(
            "SELECT user_id FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
            (base_slug,)
        ).fetchone()

    if not existing or str(existing["user_id"]) == str(user_id):
        return base_slug

    owner_suffix = re.sub(r"[^a-z0-9]", "", str(user_id).lower())[-8:] or "vendor"
    candidate = f"{base_slug}-{owner_suffix}"
    with get_db() as db:
        collision = db.execute(
            "SELECT user_id FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
            (candidate,)
        ).fetchone()
    if not collision or str(collision["user_id"]) == str(user_id):
        return candidate

    return f"{candidate}-{uuid.uuid4().hex[:6]}"



def save_uploaded_logo(upload, user_id):
    """Store a logo in the database (the host's disk is wiped on deploy)."""
    import secrets

    data = upload.file.read(core.MAX_LOGO_BYTES + 1)
    if len(data) > core.MAX_LOGO_BYTES:
        return None, "Logo must be smaller than 2MB."
    content_type = websites.sniff_image_type(data)
    if not content_type:
        return None, "Logo must be a PNG, JPG or WEBP image."
    token = secrets.token_urlsafe(18)
    with get_db() as db:
        db.execute(
            "INSERT INTO website_media (user_id, token, content_type, data, size, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(user_id), token, content_type, data, len(data), websites.utcnow_iso()),
        )
        db.commit()
    return f"/media/{token}", None


@router.post("/api/business_profile/request-otp")
def request_profile_otp(request: Request, payload: Any = Body(None)):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # Check the lock before sending anything. A locked profile gets no code.
    body = payload if isinstance(payload, dict) else {}
    with get_db() as db:
        existing = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()
    existing_dict = dict(existing) if existing else {}
    proposed = {
        "company_name": str(body.get("company_name", "")).strip(),
        "business_phone": str(body.get("business_phone", "")).strip(),
        "business_address": str(body.get("business_address", "")).strip(),
    }
    locked_changed = changed_locked_fields(existing_dict, proposed) if existing else []
    lock = lock_status(
        now_utc(),
        existing_dict.get("setup_completed_at") if existing else None,
        existing_dict.get("identity_changed_at") if existing else None,
    )
    if locked_changed and lock["state"] == "locked":
        return jsonify({
            "status": "locked",
            "message": f"Name, phone and address can change after {date_text(lock['until'])}. For an urgent change, contact support.",
            "locked_until": lock["until"].isoformat(),
        }), 403
    if not locked_changed or lock["state"] not in ("grace", "open"):
        return jsonify({"status": "not_needed", "message": "No code is needed for this change."})

    with get_db() as db:
        user = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        if user:
            record_user_activity(db, user_id, "profile_change_code_requested", "Requested a verification code for a business profile change")

    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    email = user["email"]
    ok, message, status, _ = send_and_store_otp(email, "profile", None, "Profile Update Verification")
    if not ok:
        return jsonify({"status": "error", "message": message}), status
    return jsonify({"status": "success", "message": message})


@router.get("/api/business_profile")
def get_business_profile(request: Request):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    with get_db() as db:
        profile = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()

    if not profile:
        return jsonify({
            "status": "success",
            "profile": {
                "company_name": "", "business_phone": "", "business_address": "",
                "instagram_handle": "", "whatsapp_number": "", "store_policy": "",
                "brand_color": "#1d4ed8", "logo_url": "", "store_slug": "",
                "profile_updated_at": "", "profile_change_reason": "", "profile_change_note": ""
            }
        }), 200

    profile_dict = dict(profile)
    return jsonify({
        "status": "success",
        "profile": {
            "id": profile_dict.get("id"),
            "user_id": profile_dict.get("user_id"),
            "company_name": profile_dict.get("company_name") or "",
            "business_phone": profile_dict.get("business_phone") or "",
            "business_address": profile_dict.get("business_address") or "",
            "instagram_handle": profile_dict.get("instagram_handle") or "",
            "whatsapp_number": profile_dict.get("whatsapp_number") or "",
            "store_policy": profile_dict.get("store_policy") or "",
            "brand_color": profile_dict.get("brand_color") or "#1d4ed8",
            "logo_url": profile_dict.get("logo_url") or "",
            "store_slug": profile_dict.get("store_slug") or "",
            "profile_updated_at": profile_dict.get("profile_updated_at") or "",
            "profile_change_reason": profile_dict.get("profile_change_reason") or "",
            "profile_change_note": profile_dict.get("profile_change_note") or ""
        }
    }), 200



def _save_profile(user_id, data, logo):

    company_name = str(data.get("company_name", "")).strip()
    business_phone = str(data.get("business_phone", "")).strip()
    business_address = str(data.get("business_address", "")).strip()
    missing_profile_fields = [
        label for label, value in (
            ("company / brand name", company_name),
            ("business phone", business_phone),
            ("business address", business_address),
        ) if not value
    ]
    if missing_profile_fields:
        with get_db() as db:
            record_user_activity(db, user_id, "profile_change_rejected", "Business profile submission was missing required fields")
        return jsonify({
            "status": "error",
            "message": "Please complete the required business profile fields: " + ", ".join(missing_profile_fields) + ".",
        }), 400

    with get_db() as db:
        existing = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()
    existing_dict = dict(existing) if existing else {}

    next_profile = {
        "company_name": company_name,
        "business_phone": business_phone,
        "business_address": business_address,
        "instagram_handle": str(data.get("instagram_handle", "")).strip(),
        "whatsapp_number": str(data.get("whatsapp_number", "")).strip(),
        "store_policy": str(data.get("store_policy", "")).strip(),
        "brand_color": sanitize_brand_color(data.get("brand_color", "#1d4ed8")),
    }
    profile_changed = any(
        str(existing_dict.get(field) or ("#1d4ed8" if field == "brand_color" else "")) != value
        for field, value in next_profile.items()
    )
    uploaded_logo = logo
    requested_logo_url = sanitize_logo_url(data.get("logo_url")) if data.get("logo_url") else None
    if uploaded_logo and uploaded_logo.filename:
        profile_changed = True
    elif requested_logo_url is not None and requested_logo_url != (existing_dict.get("logo_url") or ""):
        profile_changed = True

    reason_code = str(data.get("profile_change_reason", "")).strip()
    reason_label = PROFILE_CHANGE_REASONS.get(reason_code, "")
    reason_note = str(data.get("profile_change_note", "")).strip()[:100]

    # Only name, phone and address lock (see api/profile_lock.py). Other fields always save.
    proposed = {"company_name": company_name, "business_phone": business_phone, "business_address": business_address}
    locked_changed = changed_locked_fields(existing_dict, proposed) if existing else []
    lock = lock_status(
        now_utc(),
        existing_dict.get("setup_completed_at") if existing else None,
        existing_dict.get("identity_changed_at") if existing else None,
    )
    if locked_changed and lock["state"] == "locked":
        with get_db() as db:
            record_user_activity(db, user_id, "profile_change_locked", "Tried to change a locked business detail during the lock")
        return jsonify({
            "status": "locked",
            "message": f"Name, phone and address can change after {date_text(lock['until'])}. For an urgent change, contact support.",
            "locked_until": lock["until"].isoformat(),
            "locked_fields": locked_changed,
        }), 403
    # A PIN is needed only when a locked field changes, and not during initial setup.
    needs_pin = bool(locked_changed) and lock["state"] in ("grace", "open")
    if needs_pin and not reason_label:
        return jsonify({"status": "error", "message": "Choose why you are changing your name, phone or address."}), 400
    if needs_pin and reason_code == "other" and not reason_note:
        return jsonify({"status": "error", "message": "Add a short explanation for the reason you selected."}), 400

    if needs_pin:
        provided_otp = str(data.get("otp", "")).strip()
        with get_db() as db:
            user_row = db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user_row:
            return jsonify({"status": "error", "message": "User not found"}), 404

        _record, otp_error = verify_otp(user_row["email"], "profile", provided_otp, consume=True)
        if otp_error:
            with get_db() as db:
                record_user_activity(db, user_id, "profile_change_verification_failed", "Business profile change verification failed")
            return jsonify({"status": "error", "message": otp_error}), 400

    # OTP validation: verify against the hashed code stored in otp_codes table
    # A locked profile change is stored as a request in the activity log,
    # after identity verification, but the profile values remain unchanged.

    instagram_handle = str(data.get("instagram_handle", "")).strip()
    whatsapp_number = str(data.get("whatsapp_number", "")).strip()
    store_policy = str(data.get("store_policy", "")).strip()
    brand_color = sanitize_brand_color(data.get("brand_color", "#1d4ed8"))

    logo_url = None
    if logo is not None:
        file = logo
        if file and file.filename:
            saved_url, logo_err = save_uploaded_logo(file, user_id)
            if logo_err:
                return jsonify({"status": "error", "message": logo_err}), 400
            logo_url = saved_url
    elif data.get("logo_url"):
        logo_url = sanitize_logo_url(data.get("logo_url"))

    now_iso = now_utc().isoformat()
    profile_updated_at = now_iso if profile_changed else existing_dict.get("profile_updated_at")
    profile_change_reason = (
        reason_label if needs_pin else
        ("Initial setup" if profile_changed and not existing else existing_dict.get("profile_change_reason"))
    )
    profile_change_note = (
        reason_note if needs_pin and reason_code == "other" else
        existing_dict.get("profile_change_note")
    )
    # Setup starts the grace period. A change after grace starts the 90-day lock; a grace correction does not.
    setup_completed_at = existing_dict.get("setup_completed_at") if existing else (
        now_iso if company_name and business_phone and business_address else None
    )
    starts_lock = needs_pin and lock["state"] == "open"
    identity_changed_at = now_iso if starts_lock else existing_dict.get("identity_changed_at")
    identity_change_reason = (
        f"{reason_label}" + (f" — {reason_note}" if reason_code == "other" and reason_note else "")
        if needs_pin else existing_dict.get("identity_change_reason")
    )

    with get_db() as db:
        existing = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()
        existing_dict = dict(existing) if existing else {}
        current_logo = logo_url if logo_url is not None else (existing_dict.get("logo_url") or "")
        current_slug = (
            existing_dict.get("store_slug") or ""
            if existing_dict and slugify(existing_dict.get("company_name", "")) == slugify(company_name)
            else ""
        )
        store_slug = get_unique_store_slug(company_name, user_id, current_slug=current_slug)

        if existing:
            db.execute(
                """UPDATE business_profiles
                   SET company_name=?, business_phone=?, business_address=?,
                       instagram_handle=?, whatsapp_number=?, store_policy=?,
                       brand_color=?, logo_url=?, store_slug=?, profile_updated_at=?,
                       profile_change_reason=?, profile_change_note=?,
                       setup_completed_at=?, identity_changed_at=?, identity_change_reason=?
                   WHERE user_id=?""",
                (company_name, business_phone, business_address,
                 instagram_handle, whatsapp_number, store_policy,
                 brand_color, current_logo, store_slug,
                 profile_updated_at, profile_change_reason, profile_change_note,
                 setup_completed_at, identity_changed_at, identity_change_reason,
                 user_id)
            )
            profile_id = existing_dict["id"]
        else:
            cursor = db.execute(
                """INSERT INTO business_profiles
                   (user_id, company_name, business_phone, business_address, instagram_handle,
                    whatsapp_number, store_policy, brand_color, logo_url, store_slug, profile_updated_at,
                    profile_change_reason, profile_change_note, setup_completed_at, identity_changed_at,
                    identity_change_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, company_name, business_phone, business_address,
                 instagram_handle, whatsapp_number, store_policy,
                 brand_color, current_logo, store_slug, profile_updated_at,
                 profile_change_reason, profile_change_note, setup_completed_at, identity_changed_at,
                 identity_change_reason)
            )
            profile_id = cursor.lastrowid
        if profile_changed:
            reason_text = f" — {reason_note}" if reason_code == "other" and reason_note else ""
            event_type = "business_profile_updated" if existing else "business_profile_created"
            summary = "Business profile updated" if existing else "Business profile created"
            if existing:
                summary += f". Reason: {reason_label}{reason_text}"
            record_user_activity(db, user_id, event_type, summary)
        db.commit()

    return jsonify({
        "status": "success",
        "message": "Business profile saved successfully!",
        "profile": {
            "id": profile_id, "user_id": user_id, "company_name": company_name,
            "business_phone": business_phone, "business_address": business_address,
            "instagram_handle": instagram_handle, "whatsapp_number": whatsapp_number,
            "store_policy": store_policy, "brand_color": brand_color,
            "logo_url": current_logo, "store_slug": store_slug,
            "profile_updated_at": profile_updated_at or "",
            "profile_change_reason": profile_change_reason or "",
            "profile_change_note": profile_change_note or ""
        }
    }), 200


@router.post("/api/business_profile")
async def save_business_profile(request: Request):
    user_id = current_user_id(request)
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    content_type = request.headers.get("content-type", "")
    data, logo = {}, None
    if content_type.startswith("multipart/") or "urlencoded" in content_type:
        form = await request.form()
        data = {k: v for k, v in form.items() if isinstance(v, str)}
        upload = form.get("logo")
        logo = upload if hasattr(upload, "filename") else None
    else:
        try:
            body = await request.json()
            data = body if isinstance(body, dict) else {}
        except Exception:
            data = {}
    return to_response(await run_in_threadpool(_save_profile, user_id, data, logo))
