"""QR code detection, decoding, and notification components for Quickglint."""

from app.qr.qr_detector import QRDetector
from app.qr.qr_panel import QRItemWidget, QRNotificationPanel
from app.qr.qr_result import ALLOWED_URL_SCHEMES, QRDataType, QRResult, parse_qr_payload, sanitize_url
from app.qr.qr_service import QRService
from app.qr.qr_worker import QRDetectionWorker

__all__ = [
    "ALLOWED_URL_SCHEMES",
    "QRDataType",
    "QRDetectionWorker",
    "QRDetector",
    "QRItemWidget",
    "QRNotificationPanel",
    "QRResult",
    "QRService",
    "parse_qr_payload",
    "sanitize_url",
]

