"""Asynchronous background worker thread for non-blocking QR code detection."""

from typing import List, Optional, Union
import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage, QPixmap

from app.qr.qr_detector import QRDetector
from app.qr.qr_result import QRResult
from app.utils.logger import logger


class QRDetectionWorker(QThread):
    """Background worker executing QR detection without blocking UI event loop."""

    progress = Signal(int, str)
    finished = Signal(list)  # List[QRResult]
    error = Signal(str)

    def __init__(
        self,
        image_source: Union[QImage, QPixmap, Image.Image, np.ndarray, bytes],
        detector: Optional[QRDetector] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if isinstance(image_source, (QImage, QPixmap)):
            self.image_source = image_source.copy()
        elif isinstance(image_source, np.ndarray):
            self.image_source = image_source.copy()
        else:
            self.image_source = image_source
        self.detector = detector or QRDetector()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request worker thread to cancel."""
        self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self) -> None:
        try:
            if self._is_cancelled:
                return

            self.progress.emit(20, "QR kod taraması başlatılıyor...")

            if self._is_cancelled:
                return

            results = self.detector.detect(self.image_source)

            if self._is_cancelled:
                return

            self.progress.emit(100, "QR kod taraması tamamlandı.")
            self.finished.emit(results)

        except Exception as exc:
            logger.error("QRDetectionWorker error: %s", exc)
            self.error.emit(f"QR tarama hatası: {exc}")

