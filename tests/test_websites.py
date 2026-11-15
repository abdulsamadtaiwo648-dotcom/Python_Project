"""Business websites on automatic subdomains."""

import io
import uuid

import pytest

from server import websites
from server.app import get_db

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def host(slug):
    return f"http://{slug}.solobiz.dev"


@pytest.fixture
def headers(signed_in):
    return {"X-CSRFToken": signed_in[1]}


def make_profile(user_id, name="DLNZ", slug="dlnz", **extra):
    fields = {"company_name": name, "business_phone": "+2348011112222", "business_address": "5 Balogun Market, Lagos",
              "whatsapp_number": "08033334444", "store_slug": slug, "brand_color": "#0F766E"}
    fields.update(extra)
    with get_db() as db:
        db.execute("DELETE FROM business_profiles WHERE store_slug = ? OR user_id = ?", (fields["store_slug"], user_id))
        db.execute("DELETE FROM business_websites WHERE user_id = ?", (user_id,))
        db.execute(
            "INSERT INTO business_profiles (user_id, company_name, business_phone, business_address, whatsapp_number, store_slug, brand_color) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, fields["company_name"], fields["business_phone"], fields["business_address"],
             fields["whatsapp_number"], fields["store_slug"], fields["brand_color"]),
        )
        db.execute("DELETE FROM business_websites WHERE slug = ?", (fields["store_slug"],))
        db.commit()


def add_product(client, headers, name="Jogger", price=3000, stock=5):
    return client.post("/api/inventory-presets", json={"item_name": name, "price": price, "stock": stock}, headers=headers).get_json()["preset"]


def draft(client):
    return client.get("/api/website").get_json()["website"]


def save(client, headers, **changes):
    content = draft(client)["content"]
    content.update(changes)
    return client.put("/api/website", json=content, headers=headers)


def other_account(app):
    """A second signed-in client: (client, user_id, headers)."""
    user_id = f"user_test_{uuid.uuid4().hex[:10]}"
    with get_db() as db:
        db.execute("INSERT INTO users (id, email) VALUES (?, ?)", (user_id, f"{user_id}@example.com"))
        db.commit()
    other = app.test_client()
    with other.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["csrf_token"] = "t"
    return other, user_id, {"X-CSRFToken": "t"}


# --- Slugs and hostnames -----------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("dlnz", True), ("aisha-wears", True), ("a1", True),
    ("a", False), ("-dlnz", False), ("dlnz-", False), ("DLNZ", False), ("has_underscore", False),
    ("www", False), ("api", False), ("admin", False), ("xn--abc", False), ("a" * 41, False), ("a.b", False),
])
def test_slug_validation(value, expected):
    assert websites.is_valid_slug(value) is expected


@pytest.mark.parametrize("request_host,label", [
    ("solobiz.dev", None), ("www.solobiz.dev", None), ("admin.solobiz.dev", None), ("api.solobiz.dev", None),
    ("solobiz-app.onrender.com", None), ("localhost:5000", None), ("evil-solobiz.dev", None),
    ("dlnz.solobiz.dev", "dlnz"), ("DLNZ.SoloBiz.dev:443", "dlnz"), ("a.b.solobiz.dev", "a.b"),
])
def test_host_resolution(request_host, label):
    assert websites.site_label_for_host(request_host) == label


def test_main_app_and_reserved_hosts_keep_working(client):
    assert client.get("/login").status_code == 200
    assert client.get("/login", base_url="http://www.solobiz.dev").status_code == 200
    assert client.get("/privacy", base_url="http://admin.solobiz.dev").status_code == 200


def test_unknown_subdomain_is_a_public_404(client):
    response = client.get("/", base_url=host("nobody-here"))
    assert response.status_code == 404
    assert "no website here" in response.get_data(as_text=True)
    assert "Set-Cookie" not in response.headers
    assert client.get("/", base_url="http://a.b.solobiz.dev").status_code == 404


# --- First setup --------------------------------------------------------------

def test_first_setup_suggests_product_store_prefilled_and_unpublished(client, signed_in, headers):
    make_profile(signed_in[0])
    site = draft(client)
    assert site["exists"] is False and site["is_published"] is False
    assert site["content"]["layout"] == "product"
    assert site["content"]["display_name"] == "DLNZ"
    assert site["content"]["brand_color"] == "#0F766E"
    assert site["content"]["action"] == {"type": "whatsapp", "label": "", "value": "08033334444"}
    assert site["address"] == "dlnz.solobiz.dev"
    assert client.get("/", base_url=host("dlnz")).status_code == 404  # nothing live until published


def test_old_storefront_link_still_works(client, signed_in):
    make_profile(signed_in[0])
    response = client.get("/store/dlnz")
    assert response.status_code == 200 and "DLNZ" in response.get_data(as_text=True)


# --- Publishing ---------------------------------------------------------------

def test_publish_product_store_and_serve_it_on_the_subdomain(client, signed_in, headers):
    make_profile(signed_in[0])
    add_product(client, headers, "Jogger", 3000)
    assert save(client, headers, tagline="Streetwear made in Lagos").status_code == 200

    published = client.post("/api/website/publish", headers=headers)
    assert published.status_code == 200
    assert published.get_json()["website"]["url"] == "https://dlnz.solobiz.dev"

    page = client.get("/", base_url=host("dlnz"))
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "<title>DLNZ — Streetwear made in Lagos</title>" in html
    assert "Jogger" in html and "₦3,000" in html
    assert "--brand: #0f766e" in html
    assert "wa.me/2348033334444" in html            # 080... becomes international
    assert page.headers["Vary"] == "Host" and "Set-Cookie" not in page.headers


def test_publishing_twice_keeps_one_site_and_the_same_url(client, signed_in, headers):
    make_profile(signed_in[0])
    add_product(client, headers)
    first = client.post("/api/website/publish", headers=headers).get_json()["website"]["url"]
    second = client.post("/api/website/publish", headers=headers).get_json()["website"]["url"]
    assert first == second
    with get_db() as db:
        rows = db.execute("SELECT COUNT(*) AS n FROM business_websites WHERE user_id = ?", (signed_in[0],)).fetchone()
    assert rows["n"] == 1


def test_address_stays_the_same_when_the_store_slug_changes(client, signed_in, headers):
    make_profile(signed_in[0])
    add_product(client, headers)
    client.post("/api/website/publish", headers=headers)
    with get_db() as db:
        db.execute("UPDATE business_profiles SET store_slug = 'renamed-shop' WHERE user_id = ?", (signed_in[0],))
        db.commit()
    assert draft(client)["address"] == "dlnz.solobiz.dev"
    assert client.get("/", base_url=host("dlnz")).status_code == 200


def test_product_changes_show_live_but_branding_waits_for_publish(client, signed_in, headers):
    make_profile(signed_in[0])
    product = add_product(client, headers, "Jogger", 3000)
    client.post("/api/website/publish", headers=headers)

    client.put(f"/api/inventory-presets/{product['id']}", json={"item_name": "Jogger", "price": 3500, "stock": 5}, headers=headers)
    save(client, headers, display_name="DLNZ Rebrand", tagline="Draft only")
    html = client.get("/", base_url=host("dlnz")).get_data(as_text=True)
    assert "₦3,500" in html                                  # product edit is live
    assert "DLNZ Rebrand" not in html and "Draft only" not in html
    assert draft(client)["has_unpublished_changes"] is True

    client.post("/api/website/publish", headers=headers)
    assert "DLNZ Rebrand" in client.get("/", base_url=host("dlnz")).get_data(as_text=True)


def test_hidden_and_sold_out_products(client, signed_in, headers):
    make_profile(signed_in[0])
    shown = add_product(client, headers, "Jogger", 3000, stock=0)
    hidden = add_product(client, headers, "Secret Cap", 1500)
    client.put(f"/api/inventory-presets/{shown['id']}", json={"item_name": "Jogger", "price": 3000, "stock": 0}, headers=headers)
    with get_db() as db:
        db.execute("UPDATE inventory_presets SET track_stock = 1, stock = 0 WHERE id = ?", (shown["id"],))
        db.commit()
    client.put(f"/api/website/products/{hidden['id']}", json={"show_on_website": False}, headers=headers)
    client.post("/api/website/publish", headers=headers)
    html = client.get("/", base_url=host("dlnz")).get_data(as_text=True)
    assert "Secret Cap" not in html
    assert "Sold out" in html


def test_unpublish_takes_the_site_offline(client, signed_in, headers):
    make_profile(signed_in[0])
    add_product(client, headers)
    client.post("/api/website/publish", headers=headers)
    assert client.post("/api/website/unpublish", headers=headers).status_code == 200
    assert client.get("/", base_url=host("dlnz")).status_code == 404
    assert client.get("/store/dlnz").status_code == 200       # old link unaffected


def test_cannot_publish_until_ready(client, signed_in, headers):
    make_profile(signed_in[0])
    refused = client.post("/api/website/publish", headers=headers)       # no products yet
    assert refused.status_code == 400 and refused.get_json()["problems"]
    add_product(client, headers)
    save(client, headers, action={"type": "link", "label": "Book", "value": "not a link"})
    refused = client.post("/api/website/publish", headers=headers)
    assert refused.status_code == 400
    assert any("main button" in problem for problem in refused.get_json()["problems"])


def test_invalid_contact_details_are_reported(client, signed_in, headers):
    make_profile(signed_in[0])
    response = save(client, headers, phone="12", email="nope", action={"type": "whatsapp", "label": "", "value": "abc"})
    errors = response.get_json()["errors"]
    assert {"phone", "email", "action"} <= set(errors)


# --- Second business: Service layout -----------------------------------------

def test_service_business_site_is_separate(client, app, signed_in, headers):
    make_profile(signed_in[0])
    add_product(client, headers, "Jogger", 3000)
    client.post("/api/website/publish", headers=headers)

    other, other_id, other_headers = other_account(app)
    make_profile(other_id, name="Glow Salon", slug="glow-salon", brand_color="#BE185D", whatsapp_number="+2347055556666")
    content = other.get("/api/website").get_json()["website"]["content"]
    content.update({
        "layout": "service", "tagline": "Braids, nails and lashes",
        "action": {"type": "call", "label": "Call to book", "value": "+2347055556666"},
        "services": [{"name": "Knotless braids", "description": "Waist length", "price": 15000},
                     {"name": "Bridal styling", "description": "", "price": ""}],
        "hours": "Mon-Sat 9am-7pm",
    })
    assert other.put("/api/website", json=content, headers=other_headers).status_code == 200
    assert other.post("/api/website/publish", headers=other_headers).status_code == 200

    salon = other.get("/", base_url=host("glow-salon")).get_data(as_text=True)
    assert "Glow Salon" in salon and "Knotless braids" in salon and "₦15,000" in salon
    assert "Ask for a quote" in salon                       # service without a price
    assert "tel:+2347055556666" in salon and "Call to book" in salon
    assert "--brand: #be185d" in salon and "Mon-Sat 9am-7pm" in salon
    assert "Jogger" not in salon and "DLNZ" not in salon

    shop = client.get("/", base_url=host("dlnz")).get_data(as_text=True)
    assert "Jogger" in shop and "Glow Salon" not in shop and "Knotless" not in shop


def test_optional_sections_and_links_are_hidden_when_empty(client, signed_in, headers):
    make_profile(signed_in[0])
    add_product(client, headers)
    save(client, headers, phone="", whatsapp="", email="", instagram="", address="", hours="", about="",
         action={"type": "link", "label": "", "value": "https://example.com/order"})
    client.post("/api/website/publish", headers=headers)
    html = client.get("/", base_url=host("dlnz")).get_data(as_text=True)
    assert 'href="#about"' not in html and 'id="about"' not in html
    assert 'href="#contact"' not in html and 'id="contact"' not in html
    assert 'href="#gallery"' not in html
    assert 'href="#items"' in html


# --- Legacy slugs and collisions ---------------------------------------------

def test_legacy_slug_gets_a_valid_stable_address(client, signed_in, headers):
    make_profile(signed_in[0], name="Ọjà Àṣà", slug="ọjà-àṣà")
    address = draft(client)["slug"]
    assert websites.is_valid_slug(address)
    add_product(client, headers)
    client.post("/api/website/publish", headers=headers)
    assert draft(client)["slug"] == address
    assert client.get("/", base_url=host(address)).status_code == 200
    assert client.get("/store/ọjà-àṣà").status_code == 200  # original public link kept


def test_reserved_and_taken_names_are_avoided(client, app, signed_in, headers):
    make_profile(signed_in[0], name="Admin", slug="admin")
    address = draft(client)["slug"]
    assert address != "admin" and websites.is_valid_slug(address)

    make_profile(signed_in[0])                                  # now "dlnz"
    add_product(client, headers)
    client.post("/api/website/publish", headers=headers)
    mine = draft(client)["slug"]
    other, other_id, _ = other_account(app)
    with get_db() as db:
        db.execute("INSERT INTO business_profiles (user_id, company_name, store_slug) VALUES (?, ?, ?)",
                   (other_id, "Copy", f"{mine}x"))
        db.commit()
    with get_db() as db:
        assert websites.choose_slug(db, other_id, mine, "Copy") != mine


# --- Authorization ------------------------------------------------------------

def test_website_apis_require_sign_in(client):
    assert client.get("/api/website").status_code == 401
    assert client.get("/website/preview").status_code == 302
    assert client.get("/website").status_code == 302


def test_preview_shows_the_draft_only_to_its_owner(client, app, signed_in, headers):
    make_profile(signed_in[0])
    add_product(client, headers)
    save(client, headers, tagline="Unpublished tagline")
    preview = client.get("/website/preview")
    assert preview.status_code == 200 and "Unpublished tagline" in preview.get_data(as_text=True)
    assert "noindex" in preview.headers["X-Robots-Tag"]

    other, _, _ = other_account(app)
    assert "Unpublished tagline" not in other.get("/website/preview").get_data(as_text=True)
    # The preview and dashboard do not exist on business subdomains at all.
    assert client.get("/website/preview", base_url=host("dlnz")).status_code == 404
    assert client.get("/api/website", base_url=host("dlnz")).status_code == 404
    assert client.get("/login", base_url=host("dlnz")).status_code == 404


def test_one_account_cannot_change_another_accounts_site(client, app, signed_in, headers):
    make_profile(signed_in[0])
    product = add_product(client, headers)
    client.post("/api/website/publish", headers=headers)
    upload = client.post("/api/website/media", data={"image": (io.BytesIO(PNG), "a.png")}, headers=headers)
    my_image = upload.get_json()["url"]

    other, other_id, other_headers = other_account(app)
    assert other.put(f"/api/website/products/{product['id']}", json={"show_on_website": False}, headers=other_headers).status_code == 404
    other.post("/api/website/unpublish", headers=other_headers)        # only touches their own (none)
    assert client.get("/", base_url=host("dlnz")).status_code == 200
    # Another account cannot attach my image to their site.
    content = other.get("/api/website").get_json()["website"]["content"]
    content["cover_url"] = my_image
    result = other.put("/api/website", json=content, headers=other_headers).get_json()
    assert "cover_url" in result["errors"] and result["website"]["content"]["cover_url"] == ""


def test_changes_need_a_csrf_token(client, signed_in):
    assert client.post("/api/website/publish").status_code == 400


# --- Images -------------------------------------------------------------------

def test_image_upload_and_serving(client, signed_in, headers):
    upload = client.post("/api/website/media", data={"image": (io.BytesIO(PNG), "cover.png")}, headers=headers)
    assert upload.status_code == 201
    url = upload.get_json()["url"]
    served = client.get(url, base_url=host("dlnz"))
    assert served.status_code == 200 and served.mimetype == "image/png"
    assert "immutable" in served.headers["Cache-Control"] and "Set-Cookie" not in served.headers

    bad = client.post("/api/website/media", data={"image": (io.BytesIO(b"<script>alert(1)</script>"), "x.png")}, headers=headers)
    assert bad.status_code == 400


def test_brand_colours_stay_readable():
    light = websites.brand_palette("#FDE047")      # yellow: dark text on it, darker ink on white
    assert light["on_brand"] == "#0f172a" and light["ink"] != "#fde047"
    dark = websites.brand_palette("#1E3A8A")
    assert dark["on_brand"] == "#ffffff" and dark["ink"] == "#1e3a8a"
