"""Automatic privacy redaction: scan an image and burn masks into a copy of it.

Used right before an image is saved / copied so sensitive data never leaves the
application unmasked when the user enabled "auto redact on save".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from app.privacy.detection_result import DetectionResult, PrivacyAction, SensitiveType
from app.utils.logger import logger

# Which privacy.* config flag enables each detection category.
TYPE_CONFIG_KEYS: Dict[SensitiveType, str] = {
    SensitiveType.EMAIL: "detect_emails",
    SensitiveType.PHONE: "detect_phones",
    SensitiveType.IP_ADDRESS: "detect_ips",
    SensitiveType.URL: "detect_urls",
    SensitiveType.API_KEY: "detect_api_keys",
    SensitiveType.TOKEN: "detect_tokens",
    SensitiveType.JWT: "detect_tokens",
    SensitiveType.PASSWORD: "detect_tokens",
    SensitiveType.CREDIT_CARD: "detect_credit_cards",
    SensitiveType.IBAN: "detect_iban",
    SensitiveType.FILE_PATH: "detect_file_paths",
    SensitiveType.TCKN: "detect_tckn",
}

_EFFECTS = {
    "pixelate": PrivacyAction.PIXELATE,
    "blur": PrivacyAction.BLUR,
    "blackout": PrivacyAction.BLACKOUT,
}


@dataclass
class RedactionResult:
    """Outcome of an automatic redaction pass."""

    image: QImage
    count: int = 0
    error: str = ""


class AutoRedactor:
    """Detects sensitive text with OCR and masks it directly in the pixels."""

    @staticmethod
    def is_enabled(config_manager: Any) -> bool:
        """True when both Smart Privacy and 'auto redact on save' are switched on."""
        if config_manager is None:
            return False
        return bool(
            config_manager.get("privacy", "enabled", True)
            and config_manager.get("privacy", "auto_redact_on_save", False)
        )

    @staticmethod
    def filter_detections(detections: Iterable[DetectionResult], config_manager: Any) -> List[DetectionResult]:
        """Keep only categories the user enabled in Smart Privacy settings."""
        kept: List[DetectionResult] = []
        for det in detections:
            key = TYPE_CONFIG_KEYS.get(det.type)
            if key is not None and config_manager is not None and not config_manager.get("privacy", key, True):
                continue
            kept.append(det)
        return kept

    @classmethod
    def redact(
        cls,
        image: QImage,
        config_manager: Any,
        scan_func: Optional[Callable[[QImage], List[DetectionResult]]] = None,
    ) -> RedactionResult:
        """Return a redacted copy of ``image``.

        Never raises: if OCR/detection fails the original image is returned with
        ``error`` set so the caller can decide to continue or warn the user.
        """
        if image is None or image.isNull():
            return RedactionResult(image=image if image is not None else QImage())

        try:
            detections = (scan_func or cls._default_scan)(image)
            detections = cls.filter_detections(detections, config_manager)
        except Exception as exc:
            logger.warning("Auto redaction scan failed: %s", exc)
            return RedactionResult(image=image, error=str(exc))

        if not detections:
            return RedactionResult(image=image)

        effect = _EFFECTS.get(
            str(config_manager.get("privacy", "default_effect", "pixelate")) if config_manager else "pixelate",
            PrivacyAction.PIXELATE,
        )
        pixel_size = int(config_manager.get("editor", "pixel_size", 12)) if config_manager else 12
        blur_radius = int(config_manager.get("editor", "blur_radius", 15)) if config_manager else 15

        masked = cls.apply_masks(image, [d.bounding_box for d in detections], effect, pixel_size, blur_radius)
        return RedactionResult(image=masked, count=len(detections))

    @staticmethod
    def _default_scan(image: QImage) -> List[DetectionResult]:
        from app.privacy.detector import SensitiveDataDetector
        from app.privacy.providers import AutoOCRProvider

        tokens = AutoOCRProvider().detect_text(image)
        return SensitiveDataDetector().scan(tokens)

    @staticmethod
    def apply_masks(
        image: QImage,
        boxes: Iterable[QRect],
        effect: PrivacyAction = PrivacyAction.PIXELATE,
        pixel_size: int = 12,
        blur_radius: int = 15,
    ) -> QImage:
        """Burn masks for the given boxes into a copy of ``image``."""
        result = image.convertToFormat(QImage.Format.Format_ARGB32)
        bounds = result.rect()
        pixel_size = max(2, int(pixel_size))
        blur_factor = max(3, int(blur_radius) // 2)

        painter = QPainter(result)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            for raw in boxes:
                # A small margin covers OCR boxes that are slightly too tight.
                rect = raw.adjusted(-2, -2, 2, 2).intersected(bounds)
                if rect.isEmpty():
                    continue

                if effect == PrivacyAction.BLACKOUT:
                    painter.fillRect(rect, QColor(0, 0, 0))
                    continue

                factor = blur_factor if effect == PrivacyAction.BLUR else pixel_size
                mode = (
                    Qt.TransformationMode.SmoothTransformation
                    if effect == PrivacyAction.BLUR
                    else Qt.TransformationMode.FastTransformation
                )
                region = result.copy(rect)
                small = region.scaled(
                    max(1, rect.width() // factor),
                    max(1, rect.height() // factor),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    mode,
                )
                restored = small.scaled(
                    rect.width(),
                    rect.height(),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    mode,
                )
                painter.drawImage(rect.topLeft(), restored)
        finally:
            painter.end()
        return result


