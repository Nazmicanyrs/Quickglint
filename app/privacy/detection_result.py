"""Data structures for sensitive data detection results."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional
from PySide6.QtCore import QRect


class SensitiveType(Enum):
    """Categories of detectable sensitive data."""
    EMAIL = "email"
    PHONE = "phone"
    IP_ADDRESS = "ip_address"
    URL = "url"
    API_KEY = "api_key"
    TOKEN = "token"
    JWT = "jwt"
    PASSWORD = "password"
    CREDIT_CARD = "credit_card"
    IBAN = "iban"
    FILE_PATH = "file_path"
    TCKN = "tckn"
    CUSTOM = "custom"


class PrivacyAction(Enum):
    """Masking method to apply."""
    PIXELATE = "pixelate"
    BLUR = "blur"
    BLACKOUT = "blackout"
    COLOR_BOX = "color_box"
    IGNORE = "ignore"


@dataclass
class DetectionResult:
    """Represents a detected sensitive information region in an image."""
    type: SensitiveType
    text: str
    confidence: float
    bounding_box: QRect
    reason: str
    action: PrivacyAction = PrivacyAction.PIXELATE
    custom_color: str = "#000000"
    is_masked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize metadata (excluding raw sensitive text in logs for security)."""
        return {
            "type": self.type.value,
            "confidence": round(self.confidence, 3),
            "box": (
                self.bounding_box.x(),
                self.bounding_box.y(),
                self.bounding_box.width(),
                self.bounding_box.height(),
            ),
            "reason": self.reason,
            "action": self.action.value,
        }

