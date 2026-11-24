"""Logo URLs and uploaded images: only safe links and real image files are accepted."""

import os
import struct
import sys
import zlib

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
os.environ.setdefault("SECRET_KEY", "logo-test-secret-key-that-is-long-enough-0123456789")
os.environ.setdefault("SQLITE_DATABASE_PATH", os.path.join(os.path.dirname(REPO_ROOT), "unused-logo-test.db"))

import pytest  # noqa: E402

from api.core import sanitize_logo_url  # noqa: E402
from server.websites import sniff_image_type  # noqa: E402


def png_bytes(width=2, height=2):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def jpeg_bytes():
    # Start of image, a baseline frame header (SOF0), then end of image.
    return b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00" + b"\xff\xd9"


def webp_bytes():
    body = b"WEBP" + b"VP8 " + struct.pack("<I", 40) + b"\x00" * 40
    return b"RIFF" + struct.pack("<I", len(body)) + body


# --- Logo URLs ------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://shop.example.com/logo.png",
    "https://cdn-images.example.ng/brand/logo.webp?v=2",
    "/media/Abcdef0123456789_-xyz",
    "/static/uploads/logos/shop-logo.png",
])
def test_safe_logo_urls_are_kept(url):
    assert sanitize_logo_url(url) == url


@pytest.mark.parametrize("url", [
    'https://x.example.com/a"onerror=alert(1)',
    "https://x.example.com/a'b",
    "https://x.example.com/<img>",
    "https://x.example.com/a\\b",
    "https://x.example.com/a`b",
    "https://x.example.com/a b.png",
    "https://x.example.com/a\nb.png",
    "javascript:alert(1)",
    "data:image/svg+xml;base64,PHN2Zz4=",
    "//evil.example.com/logo.png",
    "http://shop.example.com/logo.png",
    "https://user:pass@shop.example.com/logo.png",
    "https://localhost/logo.png",
    "https://192.168.0.1/logo.png",
    "https://shop.example.com:8443/logo.png",
    "https://-bad.example.com/logo.png",
    "/media/../../etc/passwd",
    "/media/short",
    "/static/uploads/logos/../secret.png",
    "/static/uploads/logos/x.svg",
    "https://" + "a" * 600 + ".example.com/logo.png",
    "",
    None,
])
def test_unsafe_or_unknown_logo_urls_are_dropped(url):
    assert sanitize_logo_url(url) == ""


# --- Uploaded image content --------------------------------------------------------

def test_real_png_jpeg_and_webp_are_recognised():
    assert sniff_image_type(png_bytes()) == "image/png"
    assert sniff_image_type(jpeg_bytes()) == "image/jpeg"
    assert sniff_image_type(webp_bytes()) == "image/webp"


def test_a_script_or_html_file_renamed_to_png_is_refused():
    assert sniff_image_type(b"<script>alert(1)</script>" + b"\x00" * 40) is None
    assert sniff_image_type(b"\x89PNG\r\n\x1a\n" + b"<svg onload=alert(1)>" * 4) is None


def test_a_png_signature_without_a_header_is_refused():
    assert sniff_image_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40) is None


def test_a_jpeg_signature_without_a_frame_header_is_refused():
    assert sniff_image_type(b"\xff\xd8\xff\xe0" + b"hello world, not a picture" * 3) is None


def test_a_webp_container_with_a_wrong_length_is_refused():
    body = b"WEBP" + b"VP8 " + struct.pack("<I", 40) + b"\x00" * 40
    assert sniff_image_type(b"RIFF" + struct.pack("<I", 9999) + body) is None


def test_tiny_or_empty_files_are_refused():
    assert sniff_image_type(b"") is None
    assert sniff_image_type(b"\x89PNG\r\n\x1a\n") is None
