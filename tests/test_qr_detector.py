"""Comprehensive unit tests for QR detector, decoding, security validation, and multi-resolution handling."""

import os
import numpy as np
from PIL import Image, ImageDraw
import pytest
import qrcode
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPixmap

from app.qr.qr_detector import QRDetector
from app.qr.qr_result import (
    ALLOWED_URL_SCHEMES,
    DISALLOWED_URL_SCHEMES,
    QRDataType,
    QRResult,
    parse_qr_payload,
    sanitize_url,
)


@pytest.fixture
def qr_detector():
    return QRDetector()


def generate_qr_image(text: str, box_size: int = 10, border: int = 4) -> Image.Image:
    """Helper to generate a clean PIL QR code image."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(text)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


# 1. QR URL detection
def test_qr_url_detection(qr_detector):
    img = generate_qr_image("https://github.com/Quickglint/Quickglint")
    results = qr_detector.detect(img)
    assert len(results) >= 1
    assert results[0].data == "https://github.com/Quickglint/Quickglint"
    assert results[0].is_url is True
    assert results[0].type == QRDataType.URL
    assert results[0].normalized_url == "https://github.com/Quickglint/Quickglint"


# 2. Plain text QR detection
def test_plain_text_qr_detection(qr_detector):
    img = generate_qr_image("Hello World from Quickglint!")
    results = qr_detector.detect(img)
    assert len(results) >= 1
    assert results[0].data == "Hello World from Quickglint!"
    assert results[0].is_url is False
    assert results[0].type == QRDataType.TEXT


# 3. Multiple QR detection
def test_multiple_qr_detection(qr_detector):
    qr1 = generate_qr_image("https://example.com/one", box_size=6)
    qr2 = generate_qr_image("https://example.com/two", box_size=6)
    qr3 = generate_qr_image("Plain text content #3", box_size=6)

    # Composite into a larger canvas
    composite = Image.new("RGB", (1200, 600), color="white")
    composite.paste(qr1, (50, 100))
    composite.paste(qr2, (450, 100))
    composite.paste(qr3, (850, 100))

    results = qr_detector.detect(composite)
    assert len(results) == 3
    payloads = {r.data for r in results}
    assert "https://example.com/one" in payloads
    assert "https://example.com/two" in payloads
    assert "Plain text content #3" in payloads


# 4. Duplicate QR filtering
def test_duplicate_qr_filtering(qr_detector):
    # Two duplicate results with overlapping bounding boxes
    r1 = QRResult.create("https://example.com", QRect(50, 50, 100, 100))
    r2 = QRResult.create("https://example.com", QRect(52, 52, 98, 98))
    deduped = qr_detector._deduplicate([r1, r2])
    assert len(deduped) == 1
    assert deduped[0].data == "https://example.com"


# 5. Invalid QR image
def test_invalid_qr_image(qr_detector):
    # Noise/blank image with no valid QR pattern
    noise = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    results = qr_detector.detect(noise)
    assert results == []

    # None and empty array
    assert qr_detector.detect(None) == []
    assert qr_detector.detect(np.array([])) == []


# 6. No QR image
def test_no_qr_image(qr_detector):
    blank = Image.new("RGB", (500, 500), color="white")
    results = qr_detector.detect(blank)
    assert results == []


# 7. Small QR detection
def test_small_qr_detection(qr_detector):
    # 1px per box -> small QR
    small_qr = generate_qr_image("https://small.example.com", box_size=2, border=2)
    results = qr_detector.detect(small_qr)
    assert len(results) >= 1
    assert results[0].data == "https://small.example.com"


# 8. Large QR detection
def test_large_qr_detection(qr_detector):
    large_qr = generate_qr_image("https://large.example.com", box_size=25, border=6)
    assert large_qr.width > 800
    results = qr_detector.detect(large_qr)
    assert len(results) >= 1
    assert results[0].data == "https://large.example.com"


# 9. High-resolution screenshot
def test_high_resolution_screenshot(qr_detector):
    qr_img = generate_qr_image("https://highres.example.com", box_size=8)
    canvas = Image.new("RGB", (2560, 1440), color="#1E293B")
    canvas.paste(qr_img, (1200, 600))

    results = qr_detector.detect(canvas)
    assert len(results) >= 1
    assert results[0].data == "https://highres.example.com"
    # Ensure bounding box is around (1200, 600)
    box = results[0].bounding_box
    assert 1100 <= box.x() <= 1300
    assert 500 <= box.y() <= 700


# 10. 4K screenshot detection with downscaling and re-projection
def test_4k_screenshot(qr_detector):
    qr_img = generate_qr_image("https://4k.example.com", box_size=12)
    canvas = Image.new("RGB", (3840, 2160), color="#0F172A")
    canvas.paste(qr_img, (2000, 1000))

    results = qr_detector.detect(canvas)
    assert len(results) >= 1
    assert results[0].data == "https://4k.example.com"
    box = results[0].bounding_box
    # Check that coordinate mapping accurately maps back to the 4K canvas coordinate space
    assert 1900 <= box.x() <= 2100
    assert 900 <= box.y() <= 1100


# 11. Multiple QR codes with different payloads
def test_multiple_qr_with_different_payloads(qr_detector):
    qr_wifi = generate_qr_image("WIFI:T:WPA;S:HomeNetwork;P:SuperSecret123;;", box_size=5)
    qr_url = generate_qr_image("https://Quickglint.app", box_size=5)
    qr_otp = generate_qr_image("otpauth://totp/Acme:alice@example.com?secret=HXDMVJECJJWSRB3HWIZR4IFUGFTMXBOZ", box_size=5)
    qr_vcard = generate_qr_image("BEGIN:VCARD\nVERSION:3.0\nFN:John Doe\nTEL:+1234567890\nEMAIL:john@example.com\nEND:VCARD", box_size=5)

    canvas = Image.new("RGB", (1600, 800), color="white")
    canvas.paste(qr_wifi, (50, 50))
    canvas.paste(qr_url, (450, 50))
    canvas.paste(qr_otp, (850, 50))
    canvas.paste(qr_vcard, (1250, 50))

    results = qr_detector.detect(canvas)
    assert len(results) == 4
    types = {r.type for r in results}
    assert QRDataType.WIFI in types
    assert QRDataType.URL in types
    assert QRDataType.OTP in types
    assert QRDataType.VCARD in types


# 12. URL scheme validation
def test_url_scheme_validation():
    # Valid
    ok, url = sanitize_url("https://example.com/test")
    assert ok is True
    assert url == "https://example.com/test"

    ok, url = sanitize_url("http://example.com")
    assert ok is True

    # Missing scheme but valid domain
    ok, url = sanitize_url("example.com/path?foo=bar")
    assert ok is True
    assert url == "https://example.com/path?foo=bar"


# 13. HTTP URL detection
def test_http_url_detection():
    data_type, is_url, norm_url, details = parse_qr_payload("http://insecure-site.org/page")
    assert data_type == QRDataType.URL
    assert is_url is True
    assert norm_url == "http://insecure-site.org/page"


# 14. HTTPS URL detection
def test_https_url_detection():
    data_type, is_url, norm_url, details = parse_qr_payload("https://secure.example.com:8443/login")
    assert data_type == QRDataType.URL
    assert is_url is True
    assert norm_url == "https://secure.example.com:8443/login"


# 15. javascript scheme rejection
def test_javascript_scheme_rejection():
    dangerous = "javascript:alert(document.cookie)"
    ok, norm = sanitize_url(dangerous)
    assert ok is False
    assert norm is None

    data_type, is_url, norm_url, details = parse_qr_payload(dangerous)
    assert data_type == QRDataType.TEXT
    assert is_url is False
    assert norm_url is None


# 16. data scheme rejection
def test_data_scheme_rejection():
    dangerous = "data:text/html,<script>window.location='http://evil.com'</script>"
    ok, norm = sanitize_url(dangerous)
    assert ok is False
    assert norm is None

    data_type, is_url, norm_url, details = parse_qr_payload(dangerous)
    assert data_type == QRDataType.TEXT
    assert is_url is False
    assert norm_url is None


# 17. file scheme rejection
def test_file_scheme_rejection():
    dangerous = "file:///C:/Windows/System32/calc.exe"
    ok, norm = sanitize_url(dangerous)
    assert ok is False
    assert norm is None

    data_type, is_url, norm_url, details = parse_qr_payload(dangerous)
    assert data_type == QRDataType.TEXT
    assert is_url is False
    assert norm_url is None


# 25. Bounding box coordinates are correctly mapped after downscaling
def test_bounding_box_scale_mapping(qr_detector):
    qr_img = generate_qr_image("https://scale-test.com", box_size=8)
    canvas = Image.new("RGB", (3000, 3000), color="white")
    canvas.paste(qr_img, (1500, 1500))

    results = qr_detector.detect(canvas)
    assert len(results) == 1
    box = results[0].bounding_box
    assert 1400 <= box.x() <= 1600
    assert 1400 <= box.y() <= 1600

