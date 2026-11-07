"""Smart Privacy and sensitive information detection package."""

from app.privacy.detection_result import DetectionResult, PrivacyAction, SensitiveType
from app.privacy.detector import SensitiveDataDetector
from app.privacy.ocr import OCRProvider, OCRResult
from app.privacy.privacy_dialog import PrivacyResultDialog, PrivacyScanWorker
from app.privacy.providers import AutoOCRProvider, EasyOCRProvider, MockOCRProvider, TesseractProvider

__all__ = [
    "DetectionResult",
    "SensitiveType",
    "PrivacyAction",
    "OCRResult",
    "OCRProvider",
    "MockOCRProvider",
    "TesseractProvider",
    "EasyOCRProvider",
    "AutoOCRProvider",
    "SensitiveDataDetector",
    "PrivacyScanWorker",
    "PrivacyResultDialog",
]

