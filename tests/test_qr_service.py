"""Unit tests for QRService, background worker, caching, failure tolerance, and privacy/vault safety."""

import os
import tempfile
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest
import qrcode
from PySide6.QtCore import QEventLoop, QRect, QTimer
from PySide6.QtWidgets import QApplication

from app.qr.qr_detector import QRDetector
from app.qr.qr_result import QRDataType, QRResult
from app.qr.qr_service import QRService
from app.qr.qr_worker import QRDetectionWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def generate_test_qr(text: str) -> Image.Image:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


# 18. QR result copy test
def test_qr_result_copy(qapp):
    from app.services.clipboard_service import ClipboardService

    res = QRResult.create("https://example.com/copy-test", QRect(10, 10, 50, 50))
    ok, err = ClipboardService.copy_text(res.normalized_url)
    assert ok is True
    QApplication.processEvents()
    assert (QApplication.clipboard().text() or ClipboardService._last_copied_text) == "https://example.com/copy-test"


# 19. QR detection does not block UI (async background worker execution)
def test_qr_detection_does_not_block_ui(qapp):
    service = QRService()
    img = generate_test_qr("https://non-blocking.test")

    loop = QEventLoop()
    results_received = []

    def on_finished(results):
        results_received.extend(results)
        loop.quit()

    worker = service.detect_async(img, on_finished=on_finished, use_cache=False)
    assert worker is not None
    assert worker.isRunning()

    # Wait for completion without freezing
    QTimer.singleShot(4000, loop.quit)
    loop.exec()

    assert len(results_received) >= 1
    assert results_received[0].data == "https://non-blocking.test"


# 20. QR detector failure does not break workflow
def test_qr_detector_failure_handled_gracefully():
    service = QRService()
    # Mock detector to raise unexpected error
    with patch.object(service.detector, "detect", side_effect=RuntimeError("Simulated decoder crash")):
        # Sync detection should return []
        results = service.detect_sync(Image.new("RGB", (100, 100)), use_cache=False)
        assert results == []


# 21. Secure Vault screenshot does not create plaintext QR temp files
def test_secure_vault_no_plaintext_temp_files(tmp_path):
    temp_dir_before = set(os.listdir(tempfile.gettempdir()))

    img = generate_test_qr("otpauth://totp/VaultSecret:alice?secret=JBSWY3DPEHPK3PXP")
    service = QRService()
    results = service.detect_sync(img, use_cache=False)

    temp_dir_after = set(os.listdir(tempfile.gettempdir()))
    # Ensure no new plaintext files were written to temp directory
    new_files = temp_dir_after - temp_dir_before
    for f in new_files:
        full_path = os.path.join(tempfile.gettempdir(), f)
        if os.path.isfile(full_path) and os.path.getsize(full_path) > 0:
            with open(full_path, "rb") as fp:
                content = fp.read()
                assert b"JBSWY3DPEHPK3PXP" not in content, "Plaintext QR secret found in temp file!"


# 22. QR data is not written to logs
def test_qr_data_not_written_to_logs(caplog):
    import logging
    caplog.set_level(logging.DEBUG)

    secret_payload = "SUPER_SECRET_AUTHENTICATION_PAYLOAD_12345"
    img = generate_test_qr(secret_payload)
    service = QRService()
    results = service.detect_sync(img, use_cache=False)

    assert len(results) >= 1
    # Check that sensitive payload string is never dumped to caplog
    for record in caplog.records:
        assert secret_payload not in record.message


# Session Caching test
def test_qr_service_session_caching():
    service = QRService()
    service.clear_cache()
    img = generate_test_qr("https://cached.example.com")

    # First call runs detector
    res1 = service.detect_sync(img, use_cache=True)
    assert len(res1) >= 1

    # Second call should return from cache
    with patch.object(service.detector, "detect", side_effect=Exception("Should not be called")):
        res2 = service.detect_sync(img, use_cache=True)
        assert res1 == res2

