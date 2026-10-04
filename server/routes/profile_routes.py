"""Profile Routes HTTP routes."""

from datetime import datetime, timezone
from flask import Response, jsonify, render_template, request
import calendar, re, uuid
from ..app import (
    app,
    get_current_user_id,
    get_db,
    record_user_activity,
    sanitize_brand_color,
    sanitize_logo_url,
    save_uploaded_logo,
    send_and_store_otp,
    verify_otp,
)

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


@app.route("/api/avatar/<store_slug>")
def dynamic_business_avatar(store_slug):
    company_name = store_slug
    color_hex = "4F46E5"
    with get_db() as db:
        profile = db.execute(
            "SELECT company_name, brand_color FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)",
            (store_slug,)
        ).fetchone()
        if profile:
            if profile["company_name"]:
                company_name = profile["company_name"]
            if profile["brand_color"]:
                color_hex = profile["brand_color"].replace("#", "")

    if len(color_hex) not in [3, 6]:
        color_hex = "4F46E5"

    initials = (company_name[:2] if len(company_name) >= 2 else (company_name[:1] or "B")).upper()
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="120" fill="#{color_hex}"/>
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-weight="900" font-size="210">{initials}</text>
</svg>'''
    return Response(svg, mimetype="image/svg+xml")


@app.route("/store/<store_slug>")
def public_storefront(store_slug):
    with get_db() as db:
        profile = db.execute(
            "SELECT * FROM business_profiles WHERE LOWER(store_slug) = LOWER(?)", (store_slug,)
        ).fetchone()

    if not profile:
        return render_template("landing.html"), 404

    profile_dict = dict(profile)
    user_id = profile_dict["user_id"]
    base_url = request.host_url.rstrip("/")

    if profile_dict.get("logo_url"):
        logo_path = profile_dict["logo_url"]
        if logo_path.startswith("http://") or logo_path.startswith("https://"):
            logo_absolute_url = logo_path
        else:
            logo_absolute_url = base_url + (logo_path if logo_path.startswith("/") else "/" + logo_path)
    else:
        logo_absolute_url = f"{base_url}/api/avatar/{store_slug}"

    sales_count = 0
    try:
        with get_db() as db:
            res = db.execute("SELECT COUNT(*) as count FROM income WHERE user_id = ?", (user_id,)).fetchone()
            if res:
                sales_count = res["count"] if hasattr(res, "__getitem__") else 0
    except Exception:
        pass

    return render_template(
        "storefront.html",
        profile=profile_dict,
        sales_count=sales_count,
        logo_absolute_url=logo_absolute_url
    )


@app.route("/api/business_profile/request-otp", methods=["POST"])
def request_profile_otp():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

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


@app.route("/api/business_profile", methods=["GET", "POST"])
def api_business_profile():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    if request.method == "GET":
        with get_db() as db:
            profile = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)).fetchone()

        if not profile:
            return jsonify({
                "status": "success",
                "profile": {
                    "company_name": "", "business_phone": "", "business_address": "",
                    "instagram_handle": "", "whatsapp_number": "", "store_policy": "",
                    "brand_color": "#4F46E5", "logo_url": "", "store_slug": "",
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
                "brand_color": profile_dict.get("brand_color") or "#4F46E5",
                "logo_url": profile_dict.get("logo_url") or "",
                "store_slug": profile_dict.get("store_slug") or "",
                "profile_updated_at": profile_dict.get("profile_updated_at") or "",
                "profile_change_reason": profile_dict.get("profile_change_reason") or "",
                "profile_change_note": profile_dict.get("profile_change_note") or ""
            }
        }), 200

    elif request.method == "POST":
        data = request.form if request.form else (request.get_json(silent=True) or {})

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
            "brand_color": sanitize_brand_color(data.get("brand_color", "#4F46E5")),
        }
        profile_changed = any(
            str(existing_dict.get(field) or ("#4F46E5" if field == "brand_color" else "")) != value
            for field, value in next_profile.items()
        )
        uploaded_logo = request.files.get("logo")
        requested_logo_url = sanitize_logo_url(data.get("logo_url")) if data.get("logo_url") else None
        if uploaded_logo and uploaded_logo.filename:
            profile_changed = True
        elif requested_logo_url is not None and requested_logo_url != (existing_dict.get("logo_url") or ""):
            profile_changed = True

        reason_code = str(data.get("profile_change_reason", "")).strip()
        reason_label = PROFILE_CHANGE_REASONS.get(reason_code, "")
        reason_note = str(data.get("profile_change_note", "")).strip()[:100]
        if profile_changed and existing and not reason_label:
            with get_db() as db:
                record_user_activity(db, user_id, "profile_change_rejected", "Business profile change submitted without a valid reason")
            return jsonify({"status": "error", "message": "Select a reason for changing your business profile."}), 400
        if profile_changed and existing and reason_code == "other" and not reason_note:
            with get_db() as db:
                record_user_activity(db, user_id, "profile_change_rejected", "Business profile change submitted without the required reason details")
            return jsonify({"status": "error", "message": "Add a short explanation for the reason you selected."}), 400

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

        last_changed_at = existing_dict.get("profile_updated_at")
        if profile_changed and last_changed_at:
            try:
                previous_change = datetime.fromisoformat(str(last_changed_at).replace("Z", "+00:00"))
                if previous_change.tzinfo is None:
                    previous_change = previous_change.replace(tzinfo=timezone.utc)
                month_number = previous_change.month - 1 + 3
                target_year = previous_change.year + month_number // 12
                target_month = month_number % 12 + 1
                target_day = min(previous_change.day, calendar.monthrange(target_year, target_month)[1])
                allowed_after = previous_change.replace(year=target_year, month=target_month, day=target_day)
                if datetime.now(timezone.utc) < allowed_after:
                    available_date = allowed_after.strftime("%B %d, %Y").replace(" 0", " ")
                    reason_text = f" — {reason_note}" if reason_code == "other" and reason_note else ""
                    with get_db() as db:
                        record_user_activity(
                            db, user_id, "profile_change_requested",
                            f"Business profile change requested during the 3-month edit window: {reason_label}{reason_text}",
                        )
                    return jsonify({
                        "status": "locked",
                        "request_recorded": True,
                        "message": f"Your request has been recorded. Profile changes will be available after {available_date}. For an urgent update, please contact support.",
                    }), 403
            except (TypeError, ValueError):
                with get_db() as db:
                    record_user_activity(db, user_id, "profile_change_rejected", "Business profile change could not be verified against the last update date")
                return jsonify({
                    "status": "error",
                    "message": "We couldnâ€™t verify when this profile was last updated. Please contact our support team before making changes.",
                }), 400

        # OTP Validation â€” verify against the hashed code stored in otp_codes table
        # A locked profile change is stored as a request in the activity log,
        # after identity verification, but the profile values remain unchanged.

        instagram_handle = str(data.get("instagram_handle", "")).strip()
        whatsapp_number = str(data.get("whatsapp_number", "")).strip()
        store_policy = str(data.get("store_policy", "")).strip()
        brand_color = sanitize_brand_color(data.get("brand_color", "#4F46E5"))

        logo_url = None
        if "logo" in request.files:
            file = request.files["logo"]
            if file and file.filename:
                saved_url, logo_err = save_uploaded_logo(file, user_id)
                if logo_err:
                    return jsonify({"status": "error", "message": logo_err}), 400
                logo_url = saved_url
        elif data.get("logo_url"):
            logo_url = sanitize_logo_url(data.get("logo_url"))

        profile_updated_at = (
            datetime.now(timezone.utc).isoformat() if profile_changed
            else existing_dict.get("profile_updated_at")
        )
        profile_change_reason = (
            reason_label if profile_changed and existing else
            ("Initial setup" if profile_changed else existing_dict.get("profile_change_reason"))
        )
        profile_change_note = (
            reason_note if profile_changed and existing and reason_code == "other" else
            (None if profile_changed else existing_dict.get("profile_change_note"))
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
                           profile_change_reason=?, profile_change_note=?
                       WHERE user_id=?""",
                    (company_name, business_phone, business_address,
                     instagram_handle, whatsapp_number, store_policy,
                     brand_color, current_logo, store_slug,
                     profile_updated_at, profile_change_reason, profile_change_note,
                     user_id)
                )
                profile_id = existing_dict["id"]
            else:
                cursor = db.execute(
                    """INSERT INTO business_profiles
                       (user_id, company_name, business_phone, business_address, instagram_handle,
                        whatsapp_number, store_policy, brand_color, logo_url, store_slug, profile_updated_at,
                        profile_change_reason, profile_change_note)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, company_name, business_phone, business_address,
                     instagram_handle, whatsapp_number, store_policy,
                     brand_color, current_logo, store_slug, profile_updated_at,
                     profile_change_reason, profile_change_note)
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
