"""Unit tests for Smart Privacy, OCR providers, and sensitive data detection."""

from PySide6.QtCore import QRect
from app.privacy.detection_result import SensitiveType
from app.privacy.detector import SensitiveDataDetector
from app.privacy.ocr import OCRResult
from app.privacy.patterns import validate_iban, validate_luhn
from app.privacy.providers import MockOCRProvider


def test_email_detection():
    detector = SensitiveDataDetector()
    results = [
        OCRResult(text="Contact: john.doe@example.com for info", confidence=0.95, bounding_box=QRect(10, 10, 100, 20)),
        OCRResult(text="Support at support@test.co.uk please", confidence=0.92, bounding_box=QRect(10, 40, 100, 20)),
    ]
    detections = detector.scan(results)
    emails = [d for d in detections if d.type == SensitiveType.EMAIL]
    assert len(emails) == 2
    assert "john.doe@example.com" in emails[0].text
    assert "support@test.co.uk" in emails[1].text


def test_phone_detection():
    detector = SensitiveDataDetector()
    results = [
        OCRResult(text="Call +90 555 123 45 67 now", confidence=0.95, bounding_box=QRect(10, 10, 120, 20)),
    ]
    detections = detector.scan(results)
    phones = [d for d in detections if d.type == SensitiveType.PHONE]
    assert len(phones) >= 1


def test_ip_detection():
    detector = SensitiveDataDetector()
    results = [
        OCRResult(text="Server: 192.168.1.100 is online", confidence=0.99, bounding_box=QRect(10, 10, 100, 20)),
        OCRResult(text="Public: 8.8.8.8 DNS", confidence=0.98, bounding_box=QRect(10, 40, 100, 20)),
    ]
    detections = detector.scan(results)
    ips = [d for d in detections if d.type == SensitiveType.IP_ADDRESS]
    assert len(ips) == 2


def test_url_detection():
    detector = SensitiveDataDetector()
    results = [
        OCRResult(text="https://api.service.com/auth?token=secret12345&user=1", confidence=0.95, bounding_box=QRect(10, 10, 200, 20)),
    ]
    detections = detector.scan(results)
    urls = [d for d in detections if d.type == SensitiveType.URL]
    assert len(urls) == 1
    assert "token" in urls[0].reason


def test_jwt_detection():
    detector = SensitiveDataDetector()
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    results = [
        OCRResult(text=f"Bearer {jwt_token}", confidence=0.99, bounding_box=QRect(10, 10, 300, 20)),
    ]
    detections = detector.scan(results)
    jwts = [d for d in detections if d.type == SensitiveType.JWT or d.type == SensitiveType.API_KEY]
    assert len(jwts) >= 1


def test_api_key_detection():
    detector = SensitiveDataDetector()
    results = [
        OCRResult(text="sk-proj-abc1234567890def1234567890ghij", confidence=0.99, bounding_box=QRect(10, 10, 200, 20)),
        OCRResult(text="AKIAIOSFODNN7EXAMPLE", confidence=0.98, bounding_box=QRect(10, 40, 200, 20)),
        OCRResult(text="ghp_1234567890abcdefghijklmnopqrstuvwxyz", confidence=0.98, bounding_box=QRect(10, 70, 200, 20)),
    ]
    detections = detector.scan(results)
    keys = [d for d in detections if d.type == SensitiveType.API_KEY]
    assert len(keys) >= 3


def test_credit_card_luhn():
    # Valid Visa card candidate
    assert validate_luhn("4532015112830366") is True
    # Invalid card number
    assert validate_luhn("4532015112830367") is False

    detector = SensitiveDataDetector()
    results = [
        OCRResult(text="Card: 4532 0151 1283 0366", confidence=0.99, bounding_box=QRect(10, 10, 150, 20)),
        OCRResult(text="Random order ID: 123456789", confidence=0.90, bounding_box=QRect(10, 40, 150, 20)),
    ]
    detections = detector.scan(results)
    cards = [d for d in detections if d.type == SensitiveType.CREDIT_CARD]
    assert len(cards) == 1
    assert "4532 0151 1283 0366" in cards[0].text


def test_credit_card_split_across_ocr_words():
    """Card groups returned as separate OCR words must be reunited geometrically."""
    detector = SensitiveDataDetector()
    results = [
        OCRResult("4111", 0.99, QRect(10, 10, 36, 20)),
        OCRResult("1111", 0.99, QRect(70, 10, 36, 20)),
        OCRResult("1111", 0.99, QRect(130, 10, 36, 20)),
        OCRResult("1111", 0.99, QRect(190, 10, 36, 20)),
    ]
    cards = [d for d in detector.scan(results) if d.type == SensitiveType.CREDIT_CARD]
    assert cards
    assert any("4111 1111 1111 1111" in d.text for d in cards)


def test_iban_detection():
    # Valid ISO test IBAN
    assert validate_iban("GB82 WEST 1234 5698 7654 32") is True
    assert validate_iban("TR00 0000 0000 0000 0000 0000 00") is False

    detector = SensitiveDataDetector()
    results = [
        OCRResult(text="IBAN: GB82 WEST 1234 5698 7654 32", confidence=0.98, bounding_box=QRect(10, 10, 200, 20)),
    ]
    detections = detector.scan(results)
    ibans = [d for d in detections if d.type == SensitiveType.IBAN]
    assert len(ibans) == 1


def test_file_path_detection():
    detector = SensitiveDataDetector()
    results = [
        OCRResult(text=r"Log file at C:\Users\Administrator\Documents\secret.key", confidence=0.95, bounding_box=QRect(10, 10, 250, 20)),
        OCRResult(text="/home/alice/project/.env", confidence=0.90, bounding_box=QRect(10, 40, 200, 20)),
    ]
    detections = detector.scan(results)
    paths = [d for d in detections if d.type == SensitiveType.FILE_PATH]
    assert len(paths) == 2


def test_false_positive_handling():
    detector = SensitiveDataDetector()
    # Normal text without any sensitive tokens
    results = [
        OCRResult(text="Hello world, this is a clean regular paragraph.", confidence=0.99, bounding_box=QRect(10, 10, 200, 20)),
        OCRResult(text="Version 1.0.0 released on Tuesday.", confidence=0.95, bounding_box=QRect(10, 40, 180, 20)),
    ]
    detections = detector.scan(results)
    assert len(detections) == 0


def test_multiple_detections():
    detector = SensitiveDataDetector()
    results = [
        OCRResult(text="User: alice@company.com", confidence=0.95, bounding_box=QRect(10, 10, 150, 20)),
        OCRResult(text="API: sk-test1234567890abcdef1234567890", confidence=0.98, bounding_box=QRect(10, 40, 200, 20)),
        OCRResult(text="Host: 10.0.0.1", confidence=0.99, bounding_box=QRect(10, 70, 100, 20)),
    ]
    detections = detector.scan(results)
    assert len(detections) == 3


def test_mock_ocr_provider():
    mock = MockOCRProvider([
        OCRResult(text="test@example.com", confidence=0.99, bounding_box=QRect(0, 0, 50, 20)),
    ])
    assert mock.is_available() is True
    from PySide6.QtGui import QImage
    dummy_img = QImage(100, 100, QImage.Format.Format_RGB32)
    res = mock.detect_text(dummy_img)
    assert len(res) == 1
    assert res[0].text == "test@example.com"


def test_privacy_worker_cancel():
    from PySide6.QtGui import QImage
    from app.privacy.privacy_dialog import PrivacyScanWorker
    dummy_img = QImage(100, 100, QImage.Format.Format_RGB32)
    worker = PrivacyScanWorker(dummy_img)
    worker.cancel()
    assert worker._is_cancelled is True
    worker.run()


def test_privacy_dialog_cleanup_on_reject(qapp):
    from PySide6.QtGui import QImage
    from app.privacy.privacy_dialog import PrivacyResultDialog
    dummy_img = QImage(100, 100, QImage.Format.Format_RGB32)
    dlg = PrivacyResultDialog(dummy_img)
    dlg.reject()
    assert dlg.worker is not None
    assert dlg.worker.isFinished() or dlg.worker._is_cancelled


