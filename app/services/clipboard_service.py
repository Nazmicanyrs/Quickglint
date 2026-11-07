"""Clipboard service for copying images to system clipboard."""

from typing import Optional, Tuple
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from app.utils.logger import logger


class ClipboardService:
    """Handles copying images and pixmaps to the OS clipboard."""

    @staticmethod
    def copy_image(image: QImage) -> Tuple[bool, Optional[str]]:
        """Copy a QImage to the OS clipboard."""
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is None:
                return False, "System clipboard is not accessible."
            
            clipboard.setImage(image)
            logger.info("Successfully copied image (%dx%d) to clipboard.", image.width(), image.height())
            return True, None
        except Exception as exc:
            error_msg = f"Failed to copy image to clipboard: {exc}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    _last_copied_text: str = ""

    @staticmethod
    def copy_text(text: str) -> Tuple[bool, Optional[str]]:
        """Copy a text string to the OS clipboard."""
        ClipboardService._last_copied_text = text
        try:
            clipboard = QGuiApplication.clipboard()
            if clipboard is None:
                return False, "System clipboard is not accessible."
            from PySide6.QtGui import QClipboard
            clipboard.setText(text, QClipboard.Mode.Clipboard)
            clipboard.setText(text)
            return True, None
        except Exception as exc:
            error_msg = f"Failed to copy text to clipboard: {exc}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    @staticmethod
    def copy_pixmap(pixmap: QPixmap) -> Tuple[bool, Optional[str]]:
        """Copy a QPixmap to the OS clipboard."""
        return ClipboardService.copy_image(pixmap.toImage())

