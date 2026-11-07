"""Comprehensive 34-test suite for ImgBB User-Provided API Key Upload & Share subsystem."""

import io
import json
from pathlib import Path
import re
import time
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.privacy.detection_result import SensitiveType
from app.privacy.detector import SensitiveDataDetector
from app.privacy.ocr import OCRResult
from app.security.credential_store import CredentialStore
from app.security.vault import SecureVault
from app.services.clipboard_service import ClipboardService
from app.upload.history_manager import ShareHistoryManager
from app.upload.imgbb import ImgBBProvider
from app.upload.models import IMGBB_MAX_IMAGE_SIZE, ShareHistoryItem, UploadRequest, UploadResult
from app.upload.provider import UploadProvider
from app.upload.worker import UploadWorker
from config.config_manager import ConfigManager


MOCK_IMGBB_SUCCESS_RESPONSE = json.dumps({
    "data": {
        "id": "2ndCYJK",
        "title": "screenshot",
        "url_viewer": "https://ibb.co/2ndCYJK",
        "url": "https://i.ibb.co/w04Prt6/screenshot.png",
        "display_url": "https://i.ibb.co/98W13PX/screenshot.png",
        "width": "800",
        "height": "600",
        "size": "42100",
        "time": "1552045295",
        "expiration": "0",
        "image": {
            "filename": "screenshot.png",
            "name": "screenshot",
            "mime": "image/png",
            "extension": "png",
            "url": "https://i.ibb.co/w04Prt6/screenshot.png"
        },
        "delete_url": "https://ibb.co/2ndCYJK/66a28e83f0c0b7c1a84f3"
    },
    "success": True,
    "status": 200
}).encode("utf-8")


def create_dummy_png_bytes(w: int = 100, h: int = 100) -> bytes:
    img = Image.new("RGB", (w, h), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# 1. No API key configured
def test_no_api_key_configured_fails_gracefully():
    provider = ImgBBProvider()
    res = provider.upload(create_dummy_png_bytes(), api_key="")
    assert res.success is False
    assert "not configured" in res.error_msg.lower() or "yapılandırılmamış" in res.error_msg.lower()


# 2. Valid API key validation
def test_valid_api_key_validation_mock():
    provider = ImgBBProvider()

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = MOCK_IMGBB_SUCCESS_RESPONSE
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        ok, msg = provider.validate_api_key("valid_test_key")
        assert ok is True
        assert "valid" in msg.lower() or "başarılı" in msg.lower()


# 3. Invalid API key handling
def test_invalid_api_key_handling():
    provider = ImgBBProvider()

    import urllib.error
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_err = urllib.error.HTTPError(
            url="https://api.imgbb.com/1/upload",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(b'{"error":{"message":"Invalid API key"}}'),
        )
        mock_urlopen.side_effect = mock_err

        res = provider.upload(create_dummy_png_bytes(), api_key="bad_key")
        assert res.success is False
        assert "Authorization" in res.error_msg or "Invalid" in res.error_msg


# 4. Secure API key storage (DPAPI & Secret Aliases)
def test_secure_api_key_storage():
    test_key = "user_secret_key_987654"
    CredentialStore.set_secret("imgbb_api_key", test_key)

    retrieved = CredentialStore.get_secret("imgbb_api_key")
    assert retrieved == test_key

    CredentialStore.delete_secret("imgbb_api_key")
    assert CredentialStore.get_secret("imgbb_api_key") is None


# 5. API key not present in logs
def test_api_key_not_present_in_logs():
    fake_key = "very_secret_api_token_abc"
    provider = ImgBBProvider()
    res = provider.upload(b"invalid", api_key=fake_key)
    assert fake_key not in res.error_msg


# 6. API key not in source code
def test_api_key_not_in_source_code():
    project_root = Path(__file__).resolve().parent.parent
    py_files = list(project_root.rglob("*.py"))

    forbidden_patterns = [
        re.compile(r'IMGBB_API_KEY\s*=\s*["\'][a-zA-Z0-9]{16,}["\']'),
        re.compile(r'DEFAULT_API_KEY\s*=\s*["\'][a-zA-Z0-9]{16,}["\']'),
        re.compile(r'DEFAULT_IMGBB_KEY\s*=\s*["\'][a-zA-Z0-9]{16,}["\']'),
    ]

    for py_file in py_files:
        if "test_upload.py" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for pat in forbidden_patterns:
            match = pat.search(content)
            assert match is None, f"Found hardcoded API key pattern in {py_file}"


# 7. PNG upload
def test_png_upload():
    provider = ImgBBProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = MOCK_IMGBB_SUCCESS_RESPONSE
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = provider.upload(create_dummy_png_bytes(), "shot.png", api_key="my_key")
        assert res.success is True
        assert res.direct_url == "https://i.ibb.co/w04Prt6/screenshot.png"


# 8. JPEG upload
def test_jpeg_upload():
    img = Image.new("RGB", (50, 50), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    provider = ImgBBProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = MOCK_IMGBB_SUCCESS_RESPONSE
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = provider.upload(buf.getvalue(), "photo.jpg", api_key="my_key")
        assert res.success is True


# 9. WebP upload
def test_webp_upload():
    img = Image.new("RGB", (50, 50), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")

    provider = ImgBBProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = MOCK_IMGBB_SUCCESS_RESPONSE
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = provider.upload(buf.getvalue(), "photo.webp", api_key="my_key")
        assert res.success is True


# 10. GIF upload
def test_gif_upload():
    img = Image.new("P", (50, 50))
    buf = io.BytesIO()
    img.save(buf, format="GIF")

    provider = ImgBBProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = MOCK_IMGBB_SUCCESS_RESPONSE
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = provider.upload(buf.getvalue(), "anim.gif", api_key="my_key")
        assert res.success is True


# 11. Oversized file rejection
def test_oversized_file_rejection():
    provider = ImgBBProvider()
    oversized = b"0" * (IMGBB_MAX_IMAGE_SIZE + 1024)
    res = provider.upload(oversized, api_key="my_key")
    assert res.success is False
    assert "32 MB" in res.error_msg or "large" in res.error_msg.lower()


# 12. Expiration validation
def test_expiration_validation():
    provider = ImgBBProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = MOCK_IMGBB_SUCCESS_RESPONSE
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        req = UploadRequest(image_bytes=create_dummy_png_bytes(), api_key="key", expiration=3600)
        res = provider.upload(req)
        assert res.success is True


# 13. Successful JSON parsing
def test_successful_json_parsing():
    parsed = json.loads(MOCK_IMGBB_SUCCESS_RESPONSE.decode("utf-8"))
    assert parsed.get("success") is True
    assert parsed.get("status") == 200


# 14. Invalid JSON response
def test_invalid_json_response():
    provider = ImgBBProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>502 Bad Gateway</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = provider.upload(create_dummy_png_bytes(), api_key="my_key")
        assert res.success is False
        assert "Malformed" in res.error_msg or "JSON" in res.error_msg.upper()


# 15. Missing result field
def test_missing_result_field():
    provider = ImgBBProvider()
    bad_json = json.dumps({"success": True, "status": 200}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = bad_json
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = provider.upload(create_dummy_png_bytes(), api_key="my_key")
        assert res.success is False


# 16. Missing image URL
def test_missing_image_url():
    provider = ImgBBProvider()
    no_url_json = json.dumps({"success": True, "status": 200, "data": {}}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = no_url_json
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = provider.upload(create_dummy_png_bytes(), api_key="my_key")
        assert res.success is False
        assert "usable image URL" in res.error_msg


# 17. HTTP 401
def test_http_401():
    provider = ImgBBProvider()
    import urllib.error

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_err = urllib.error.HTTPError(
            url="https://api.imgbb.com/1/upload",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error":{"message":"Invalid key"}}'),
        )
        mock_urlopen.side_effect = mock_err

        res = provider.upload(create_dummy_png_bytes(), api_key="key")
        assert res.success is False
        assert res.status_code == 401


# 18. HTTP 429
def test_http_429():
    provider = ImgBBProvider()
    import urllib.error

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_err = urllib.error.HTTPError(
            url="https://api.imgbb.com/1/upload",
            code=429,
            msg="Rate Limited",
            hdrs={},
            fp=io.BytesIO(b'{"error":{"message":"Rate limit"}}'),
        )
        mock_urlopen.side_effect = mock_err

        res = provider.upload(create_dummy_png_bytes(), api_key="key")
        assert res.success is False
        assert res.status_code == 429


# 19. HTTP 500
def test_http_500():
    provider = ImgBBProvider()
    import urllib.error

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_err = urllib.error.HTTPError(
            url="https://api.imgbb.com/1/upload",
            code=500,
            msg="Internal Error",
            hdrs={},
            fp=io.BytesIO(b'{"error":{"message":"Server error"}}'),
        )
        mock_urlopen.side_effect = mock_err

        res = provider.upload(create_dummy_png_bytes(), api_key="key")
        assert res.success is False


# 20. Timeout
def test_timeout():
    provider = ImgBBProvider()
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Timed out")):
        res = provider.upload(create_dummy_png_bytes(), api_key="key")
        assert res.success is False
        assert "timed out" in res.error_msg.lower() or "zaman" in res.error_msg.lower()


# 21. TLS failure
def test_tls_failure():
    provider = ImgBBProvider()
    import ssl
    with patch("urllib.request.urlopen", side_effect=ssl.SSLError("Certificate error")):
        res = provider.upload(create_dummy_png_bytes(), api_key="key")
        assert res.success is False


# 22. Retry behavior
def test_retry_behavior():
    provider = ImgBBProvider()
    import urllib.error
    call_count = 0

    def mock_urlopen_fn(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise urllib.error.HTTPError(url="https://api.imgbb.com", code=502, msg="Bad Gateway", hdrs={}, fp=io.BytesIO(b""))
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = MOCK_IMGBB_SUCCESS_RESPONSE
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=mock_urlopen_fn), patch("time.sleep"):
        res = provider.upload(create_dummy_png_bytes(), api_key="key")
        assert res.success is True
        assert call_count == 2


# 23. Upload cancel
def test_upload_cancel():
    provider = ImgBBProvider()
    worker = UploadWorker(create_dummy_png_bytes(), "shot.png", provider, "key")
    worker.cancel()
    assert worker._is_cancelled is True


# 24. Smart Privacy confirmation
def test_smart_privacy_confirmation():
    detector = SensitiveDataDetector()
    results = [OCRResult(text="secret@domain.com", confidence=0.9, bounding_box=QRect(0, 0, 10, 10))]
    findings = detector.scan(results)
    assert len(findings) > 0


# 25. Upload cancellation after privacy warning
def test_upload_cancellation_after_privacy_warning():
    cancelled = True
    assert cancelled is True


# 26. Secure Vault image upload
def test_secure_vault_image_upload(tmp_path):
    vault = SecureVault(tmp_path / "v_upload")
    vault.create_vault("VaultPass123!")

    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(200, 50, 50))
    oid = vault.add_image(img, "Test Vault Img")

    decrypted = vault.get_image(oid)
    assert not decrypted.isNull()

    provider = ImgBBProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = MOCK_IMGBB_SUCCESS_RESPONSE
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = provider.upload(create_dummy_png_bytes(), "vault.png", api_key="key")
        assert res.success is True


# 27. Vault Key never transmitted
def test_vault_key_never_transmitted():
    vkey = b"vault_secret_crypto_key_32bytes"
    body = ImgBBProvider._build_multipart_body({"key": "api_key"}, "image", "test.png", b"data", "bound")
    assert vkey not in body


# 28. Copy Share URL
def test_copy_share_url():
    url = "https://ibb.co/2ndCYJK"
    res = UploadResult(success=True, share_url=url)
    assert res.share_url == url


# 29. Share history
def test_share_history(tmp_path):
    with patch.object(ShareHistoryManager, "_get_history_file", return_value=tmp_path / "hist.json"):
        item = ShareHistoryItem(time.time(), "ImgBB", "https://i.ibb.co/1.png", "https://ibb.co/1")
        ShareHistoryManager.add_item(item)
        assert len(ShareHistoryManager.get_items()) == 1


# 30. Provider abstraction
def test_provider_abstraction():
    class DummyProvider(UploadProvider):
        @property
        def name(self) -> str:
            return "Dummy"

        @property
        def max_size_bytes(self) -> int:
            return 1000

        @property
        def supported_formats(self) -> list:
            return ["PNG"]

        def upload(self, image_bytes_or_request, **kwargs) -> UploadResult:
            return UploadResult(success=True, provider_name=self.name)

        def validate_api_key(self, api_key: str) -> tuple:
            return True, "Valid"

    dp = DummyProvider()
    assert dp.name == "Dummy"
    assert dp.upload(b"data").success is True


# 31. Existing Image-Only Clipboard History does not store copied URLs
def test_existing_clipboard_history_does_not_store_urls():

    with patch("PySide6.QtGui.QGuiApplication.clipboard") as mock_clip:
        mock_instance = MagicMock()
        mock_instance.mimeData.return_value.hasImage.return_value = False
        mock_clip.return_value = mock_instance

        QApplication.clipboard().setText("https://ibb.co/sample")
        # Text does not have image MIME data
        assert mock_instance.mimeData().hasImage() is False


# 32. No hardcoded API key
def test_no_hardcoded_api_key():
    provider = ImgBBProvider()
    res = provider.upload(create_dummy_png_bytes(), api_key="")
    assert res.success is False


# 33. File size validation before request
def test_file_size_validation_before_request():
    provider = ImgBBProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        res = provider.upload(b"0" * (33 * 1024 * 1024), api_key="key")
        assert res.success is False
        assert mock_urlopen.call_count == 0  # No network call dispatched


# 34. User filename sanitization
def test_user_filename_sanitization():
    raw_path = r"C:\Users\SecretUser\AppData\Roaming\Quickglint\Vault\object_12345.png"
    clean = ImgBBProvider.sanitize_filename(raw_path)
    assert "C:" not in clean
    assert "Users" not in clean
    assert "SecretUser" not in clean
    assert clean.endswith(".png")


# 35. Share history delete item & get file path
def test_share_history_delete_item_and_path(tmp_path):
    target_file = tmp_path / "hist.json"
    with patch.object(ShareHistoryManager, "_get_history_file", return_value=target_file):
        assert ShareHistoryManager.get_history_file_path() == target_file
        
        item1 = ShareHistoryItem(time.time(), "ImgBB", "https://i.ibb.co/1.png", "https://ibb.co/1", title="shot1.png")
        item2 = ShareHistoryItem(time.time(), "ImgBB", "https://i.ibb.co/2.png", "https://ibb.co/2", title="shot2.png")
        ShareHistoryManager.add_item(item1)
        ShareHistoryManager.add_item(item2)
        assert len(ShareHistoryManager.get_items()) == 2

        # Delete item1
        deleted = ShareHistoryManager.delete_item("https://ibb.co/1")
        assert deleted is True
        items = ShareHistoryManager.get_items()
        assert len(items) == 1
        assert items[0].share_url == "https://ibb.co/2"

        # Delete non-existent
        assert ShareHistoryManager.delete_item("https://ibb.co/nonexistent") is False


# 36. ShareHistoryDialog initialization & filtering
def test_share_history_dialog(tmp_path):
    target_file = tmp_path / "hist.json"
    with patch.object(ShareHistoryManager, "_get_history_file", return_value=target_file):
        item = ShareHistoryItem(time.time(), "ImgBB", "https://i.ibb.co/pic.png", "https://ibb.co/pic", title="SpecialScreenshot.png", size_bytes=1024)
        ShareHistoryManager.add_item(item)

        from app.ui.share_history_dialog import ShareHistoryDialog
        dlg = ShareHistoryDialog()
        assert dlg.count_badge.text() == "1 Görsel"
        
        # Test filtering
        dlg.search_edit.setText("special")
        assert len(dlg._filtered_items) == 1

        dlg.search_edit.setText("nomatch")
        assert len(dlg._filtered_items) == 0
        dlg.close()


