"""Business websites on automatic subdomains (https://<slug>.solobiz.dev).

Each account can have one website. Its branding and text are edited as a
draft and copied to `published` when the owner publishes; products are read
live from the inventory. The address is a stable DNS-safe slug assigned once.

Configuration (environment):
  SITE_BASE_DOMAIN  domain the subdomains hang off (default "solobiz.dev").
                    May include a port for local testing ("localhost:5000").
  SITE_URL_SCHEME   scheme used in public links (default "https").
  SITE_SUBDOMAINS   set to "1" once wildcard DNS and HTTPS for the base domain
                    are live. Until then owners are given the address
                    https://<base>/site/<slug>, which needs no DNS. Both
                    addresses always serve a published site.
"""

import hashlib
import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit


LAYOUTS = ("product", "service")
ACTION_TYPES = {
    "whatsapp": "Chat on WhatsApp",
    "call": "Call us",
    "link": "Request a quote",
}
MAX_SERVICES = 30
MAX_GALLERY = 12
MAX_MEDIA_PER_USER = 80
MAX_MEDIA_BYTES = 2 * 1024 * 1024

# Subdomains that belong to SoloBiz itself (admin.solobiz.dev is the admin
# portal) or that a business must never be able to claim.
RESERVED_SLUGS = frozenset("""
    www www1 www2 api admin administrator app apps dashboard account accounts login logout
    register signup signin auth oauth sso mail email webmail smtp imap pop pop3 mx ftp sftp
    ns ns1 ns2 dns cdn static assets media img images files uploads download downloads
    store stores shop site sites website websites web blog docs help support status contact
    about legal privacy terms security billing pay payment payments checkout
    dev staging stage test testing demo preview beta internal root system
    solobiz solo-biz team staff official m mobile go link links
    autoconfig autodiscover localhost
""".split())

_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
_PHONE_CHARS_RE = re.compile(r"[\s().-]")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MEDIA_URL_RE = re.compile(r"^/media/([A-Za-z0-9_-]{16,40})$")
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def utcnow_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Hostnames and addresses
# ---------------------------------------------------------------------------
def base_domain():
    return (os.environ.get("SITE_BASE_DOMAIN") or "solobiz.dev").strip().lower()


def _strip_port(host):
    return host.rsplit(":", 1)[0] if ":" in host and not host.endswith("]") else host


def site_label_for_host(host):
    """Return the business subdomain label for a request host, else None.

    None means "serve the main SoloBiz app": the bare domain, any reserved
    first-party name (www, admin, api...), and hosts outside the base domain
    such as the hosting provider's own address. A label with dots (a.b) is
    returned as-is and simply matches no website.
    """
    host = _strip_port((host or "").strip().lower()).rstrip(".")
    base = _strip_port(base_domain())
    if not host or host == base or not host.endswith("." + base):
        return None
    label = host[: -len(base) - 1]
    return None if label in RESERVED_SLUGS else label


def subdomains_enabled():
    return (os.environ.get("SITE_SUBDOMAINS") or "").strip().lower() in ("1", "true", "yes")


def main_origin():
    scheme = (os.environ.get("SITE_URL_SCHEME") or "https").strip()
    return f"{scheme}://{base_domain()}"


def website_address(slug):
    """The address shown to owners, without the scheme."""
    return f"{slug}.{base_domain()}" if subdomains_enabled() else f"{base_domain()}/site/{slug}"


def website_url(slug):
    scheme = (os.environ.get("SITE_URL_SCHEME") or "https").strip()
    return f"{scheme}://{website_address(slug)}"


def is_valid_slug(slug):
    """A usable hostname label: a-z, 0-9 and inner hyphens, 2-40 chars."""
    return (
        isinstance(slug, str)
        and len(slug) >= 2
        and bool(_LABEL_RE.match(slug))
        and not slug.startswith("xn--")
        and slug not in RESERVED_SLUGS
    )


def slug_candidate(text):
    """Best-effort DNS label from a store slug or business name ('' if none)."""
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)[:40].strip("-")
    return text if is_valid_slug(text) else ""


def _slug_taken(db, slug, user_id):
    row = db.execute("SELECT user_id FROM business_websites WHERE slug = ?", (slug,)).fetchone()
    return bool(row) and str(row["user_id"]) != str(user_id)


def choose_slug(db, user_id, store_slug, display_name):
    """Pick a stable, unique address for this account.

    Prefers the existing store slug, then the business name. If neither can
    be a hostname (non-Latin name, reserved word, already taken), falls back
    to a generated one that is the same every time for this account.
    """
    suffix = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:6]
    wanted = slug_candidate(store_slug) or slug_candidate(display_name)
    options = []
    if wanted:
        options.append(wanted)
        options.append(f"{wanted[:33].strip('-')}-{suffix}")
    options.append(f"shop-{suffix}")
    for option in options:
        if is_valid_slug(option) and not _slug_taken(db, option, user_id):
            return option
    while True:  # practically unreachable; keeps the function total
        option = f"shop-{secrets.token_hex(4)}"
        if not _slug_taken(db, option, user_id):
            return option


# ---------------------------------------------------------------------------
# Contact details and the main action
# ---------------------------------------------------------------------------
def normalize_phone(value):
    """Return a cleaned phone number ('+2348012345678' / '08012345678') or None."""
    text = _PHONE_CHARS_RE.sub("", str(value or "").strip())
    if not text:
        return None
    digits = text[1:] if text.startswith("+") else text
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        return None
    return text


def whatsapp_digits(phone):
    """International digits for wa.me links; Nigerian 080... becomes 23480..."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("0"):
        digits = "234" + digits[1:]
    return digits


def normalize_link(value):
    text = str(value or "").strip()
    if not text or len(text) > 300 or " " in text:
        return None
    parts = urlsplit(text)
    if parts.scheme != "https" or not parts.netloc or "." not in parts.netloc:
        return None
    return text


def action_href(action, business_name=""):
    """Public link for the main action, or '' when it is not usable."""
    kind = (action or {}).get("type")
    value = (action or {}).get("value") or ""
    if kind == "whatsapp" and normalize_phone(value):
        message = f"Hello {business_name}, I found your website and would like to ask about".strip()
        return f"https://wa.me/{whatsapp_digits(value)}?text={quote(message)}"
    if kind == "call" and normalize_phone(value):
        return f"tel:{normalize_phone(value)}"
    if kind == "link" and normalize_link(value):
        return normalize_link(value)
    return ""


# ---------------------------------------------------------------------------
# Brand colour
# ---------------------------------------------------------------------------
def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _luminance(rgb):
    def channel(value):
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def brand_palette(color):
    """Colours derived from the brand colour that stay readable.

    brand     the colour itself, used for button and banner backgrounds
    on_brand  text colour on top of it (white or near-black)
    ink       the brand colour darkened until it reads on a white page
    tint      a very light wash of it for section backgrounds
    """
    color = color if _COLOR_RE.match(color or "") else "#1d4ed8"
    rgb = _rgb(color)
    white, dark = (255, 255, 255), (15, 23, 42)
    on_brand = "#ffffff" if _contrast(rgb, white) >= _contrast(rgb, dark) else "#0f172a"
    ink = rgb
    for _ in range(40):
        if _contrast(ink, white) >= 4.5:
            break
        ink = tuple(int(v * 0.9) for v in ink)
    tint = tuple(int(255 - (255 - v) * 0.08) for v in rgb)
    to_hex = lambda value: "#%02x%02x%02x" % value  # noqa: E731
    return {"brand": color.lower(), "on_brand": on_brand, "ink": to_hex(ink), "tint": to_hex(tint)}


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------
def default_content(profile=None):
    """First-time draft, prefilled from what SoloBiz already knows."""
    profile = dict(profile or {})
    whatsapp = normalize_phone(profile.get("whatsapp_number")) or ""
    phone = normalize_phone(profile.get("business_phone")) or ""
    action_value = whatsapp or phone
    logo = profile.get("logo_url") or ""
    return {
        "layout": "product",
        "display_name": (profile.get("company_name") or "").strip()[:80],
        "tagline": "",
        "about": "",
        "brand_color": profile.get("brand_color") if _COLOR_RE.match(profile.get("brand_color") or "") else "#1d4ed8",
        "logo_url": logo if logo.startswith(("/static/uploads/logos/", "/media/")) else "",
        "cover_url": "",
        "phone": phone,
        "whatsapp": whatsapp,
        "email": "",
        "instagram": (profile.get("instagram_handle") or "").strip().lstrip("@")[:40],
        "address": (profile.get("business_address") or "").strip()[:200],
        "hours": "",
        "action": {
            "type": "whatsapp" if whatsapp or not phone else "call",
            "label": "",
            "value": action_value,
        },
        "services": [],
        "gallery": [],
    }


def _text(value, limit, multiline=False):
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n") if multiline else re.sub(r"\s+", " ", text)
    return text.strip()[:limit]


def clean_content(data, user_id, db, profile_logo=""):
    """Validate an owner's draft. Returns (content, errors).

    `errors` maps a field name to a message for anything that was wrong and
    had to be dropped, so the owner sees why. Images must be uploads that
    belong to this account (or their existing profile logo).
    """
    data = data if isinstance(data, dict) else {}
    errors = {}

    owned = {
        row["token"] for row in db.execute(
            "SELECT token FROM website_media WHERE user_id = ?", (str(user_id),)
        ).fetchall()
    }

    def image(value, field):
        value = str(value or "").strip()
        if not value:
            return ""
        match = _MEDIA_URL_RE.match(value)
        if match and match.group(1) in owned:
            return value
        if field == "logo_url" and profile_logo and value == profile_logo:
            return value
        errors[field] = "That image could not be used. Upload it again."
        return ""

    def phone(value, field, label):
        value = str(value or "").strip()
        if not value:
            return ""
        cleaned = normalize_phone(value)
        if not cleaned:
            errors[field] = f"Enter a valid {label}, for example +2348012345678."
            return ""
        return cleaned

    content = {
        "layout": data.get("layout") if data.get("layout") in LAYOUTS else "product",
        "display_name": _text(data.get("display_name"), 80),
        "tagline": _text(data.get("tagline"), 160),
        "about": _text(data.get("about"), 1200, multiline=True),
        "brand_color": data.get("brand_color").upper() if _COLOR_RE.match(str(data.get("brand_color") or "")) else "#1d4ed8",
        "logo_url": image(data.get("logo_url"), "logo_url"),
        "cover_url": image(data.get("cover_url"), "cover_url"),
        "phone": phone(data.get("phone"), "phone", "phone number"),
        "whatsapp": phone(data.get("whatsapp"), "whatsapp", "WhatsApp number"),
        "email": "",
        "instagram": re.sub(r"[^A-Za-z0-9._]", "", str(data.get("instagram") or ""))[:40],
        "address": _text(data.get("address"), 200),
        "hours": _text(data.get("hours"), 300, multiline=True),
        "services": [],
        "gallery": [],
    }

    email = str(data.get("email") or "").strip()[:120]
    if email:
        if _EMAIL_RE.match(email):
            content["email"] = email
        else:
            errors["email"] = "Enter a valid email address."

    action = data.get("action") if isinstance(data.get("action"), dict) else {}
    action_type = action.get("type") if action.get("type") in ACTION_TYPES else "whatsapp"
    action_value = str(action.get("value") or "").strip()[:300]
    if action_value:
        if action_type == "link":
            if normalize_link(action_value):
                action_value = normalize_link(action_value)
            else:
                errors["action"] = "Enter a full link that starts with https://"
        else:
            cleaned = normalize_phone(action_value)
            if cleaned:
                action_value = cleaned
            else:
                errors["action"] = "Enter a valid phone number, for example +2348012345678."
    content["action"] = {"type": action_type, "label": _text(action.get("label"), 30), "value": action_value}

    services = data.get("services") if isinstance(data.get("services"), list) else []
    if len(services) > MAX_SERVICES:
        errors["services"] = f"You can list up to {MAX_SERVICES} services."
    for index, raw in enumerate(services[:MAX_SERVICES]):
        if not isinstance(raw, dict):
            continue
        name = _text(raw.get("name"), 80)
        if not name:
            continue
        price = None
        raw_price = raw.get("price")
        if raw_price not in (None, ""):
            try:
                price = float(str(raw_price).replace(",", ""))
                if not 0 <= price < 1e12:
                    raise ValueError
            except (TypeError, ValueError):
                price = None
                errors[f"services.{index}.price"] = f"The price for “{name}” was not a valid amount, so it was left blank."
        content["services"].append({
            "name": name,
            "description": _text(raw.get("description"), 300),
            "price": price,
            "image_url": image(raw.get("image_url"), f"services.{index}.image"),
        })

    gallery = data.get("gallery") if isinstance(data.get("gallery"), list) else []
    for raw in gallery[:MAX_GALLERY]:
        url = image(raw, "gallery")
        if url and url not in content["gallery"]:
            content["gallery"].append(url)
    return content, errors


def publish_problems(content, product_count):
    """Reasons this draft cannot go live yet (empty list means ready)."""
    problems = []
    if not content.get("display_name"):
        problems.append("Add your business name.")
    action = content.get("action") or {}
    if not action_href(action, content.get("display_name", "")):
        need = "a link starting with https://" if action.get("type") == "link" else "a phone number"
        problems.append(f"Set your main button: enter {need}.")
    if content.get("layout") == "service" and not content.get("services"):
        problems.append("Add at least one service.")
    if content.get("layout") == "product" and product_count == 0:
        problems.append("Add at least one product in Inventory and show it on your website.")
    return problems


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def get_profile(db, user_id):
    row = db.execute("SELECT * FROM business_profiles WHERE user_id = ?", (str(user_id),)).fetchone()
    return dict(row) if row else {}


def get_website(db, user_id):
    row = db.execute("SELECT * FROM business_websites WHERE user_id = ?", (str(user_id),)).fetchone()
    if not row:
        return None
    site = dict(row)
    site["draft"] = json.loads(site["draft"])
    site["published"] = json.loads(site["published"]) if site.get("published") else None
    return site


def ensure_website(db, user_id, content):
    """Create the account's single website row (with its permanent address)
    if it does not exist yet, then store `content` as the draft."""
    payload = json.dumps(content)
    existing = get_website(db, user_id)
    if existing:
        db.execute(
            "UPDATE business_websites SET draft = ?, updated_at = ? WHERE user_id = ?",
            (payload, utcnow_iso(), str(user_id)),
        )
        return get_website(db, user_id)
    profile = get_profile(db, user_id)
    slug = choose_slug(db, user_id, profile.get("store_slug"), content.get("display_name"))
    try:
        db.execute(
            "INSERT INTO business_websites (user_id, slug, draft, updated_at) VALUES (?, ?, ?, ?)",
            (str(user_id), slug, payload, utcnow_iso()),
        )
    except Exception as error:
        # Two requests raced to create it (double click). Keep the first row.
        if not _is_unique_violation(error):
            raise
        db.conn.rollback()
        if not get_website(db, user_id):
            raise
        db.execute(
            "UPDATE business_websites SET draft = ?, updated_at = ? WHERE user_id = ?",
            (payload, utcnow_iso(), str(user_id)),
        )
    return get_website(db, user_id)


def _is_unique_violation(error):
    if isinstance(error, sqlite3.IntegrityError):
        return True
    message = str(error).lower()
    return "unique" in message or "duplicate" in message


def public_products(db, user_id):
    """Products shown on a Product Store site, read live from inventory."""
    rows = db.execute(
        "SELECT id, item_name, price, stock, track_stock, bulk_quantity, bulk_price, image_url "
        "FROM inventory_presets WHERE user_id = ? AND COALESCE(show_on_website, 1) = 1 ORDER BY id ASC",
        (str(user_id),),
    ).fetchall()
    products = []
    for row in rows:
        item = dict(row)
        bulk = None
        if item.get("bulk_quantity") and item.get("bulk_price") is not None and float(item["bulk_price"]) > 0:
            bulk = {"quantity": int(item["bulk_quantity"]), "price": float(item["bulk_price"])}
        products.append({
            "id": item["id"],
            "name": item["item_name"],
            "price": float(item["price"]),
            "image_url": item.get("image_url") or "",
            "sold_out": bool(item.get("track_stock")) and int(item.get("stock") or 0) <= 0,
            "bulk": bulk,
        })
    return products


def find_published_site(db, label):
    """The one published website for a subdomain label, or None."""
    if not is_valid_slug(label):
        return None
    row = db.execute(
        "SELECT w.user_id, w.slug, w.published FROM business_websites w "
        "JOIN users u ON u.id = w.user_id "
        "WHERE w.slug = ? AND w.is_published = 1 AND u.account_status = 'active'",
        (label,),
    ).fetchone()
    if not row or not row["published"]:
        return None
    return {"user_id": row["user_id"], "slug": row["slug"], "content": json.loads(row["published"])}


def format_naira(value):
    """₦3,000 for whole amounts, ₦3,000.50 otherwise (matches the app)."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    return f"₦{amount:,.0f}" if amount == int(amount) else f"₦{amount:,.2f}"


def sniff_image_type(data):
    """Content type from the file's own bytes; None unless the header structure is intact.
    Pillow is not installed, so this checks each format's required header, not every pixel."""
    if len(data) < 32:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff" and (b"\xff\xc0" in data or b"\xff\xc2" in data):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and int.from_bytes(data[4:8], "little") <= len(data) - 8:
        return "image/webp"
    return None
