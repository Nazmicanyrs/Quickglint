"""QR Service providing high-level abstraction, session caching, and background execution."""

import hashlib
from typing import Callable, Dict, List, Optional, Union
import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QPixmap

from app.qr.qr_detector import QRDetector
from app.qr.qr_result import QRResult
from app.qr.qr_worker import QRDetectionWorker
from app.utils.logger import logger



def _md5(data: bytes):
    """Non-security cache-key hash (safe on FIPS-enabled systems)."""
    return hashlib.md5(data, usedforsecurity=False)

class QRService(QObject):
    """High-level singleton service for local QR code detection with session caching."""

    _instance: Optional["QRService"] = None

    qr_detected = Signal(list)  # List[QRResult]
    detection_error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.detector = QRDetector()
        self._cache: Dict[str, List[QRResult]] = {}
        self._active_worker: Optional[QRDetectionWorker] = None

    @classmethod
    def get_instance(cls) -> "QRService":
        if cls._instance is None:
            cls._instance = QRService()
        return cls._instance

    def _compute_image_hash(self, image_source: Union[QImage, QPixmap, Image.Image, np.ndarray, bytes]) -> str:
        """Compute fast in-memory hash of image content for session caching."""
        try:
            if isinstance(image_source, QPixmap):
                image_source = image_source.toImage()

            if isinstance(image_source, QImage):
                if image_source.isNull():
                    return ""
                w, h = image_source.width(), image_source.height()
                return _md5(f"{w}x{h}_{image_source.cacheKey()}".encode("utf-8")).hexdigest()

            if isinstance(image_source, Image.Image):
                return _md5(f"{image_source.size}_{image_source.mode}".encode("utf-8")).hexdigest()

            if isinstance(image_source, np.ndarray):
                return _md5(f"{image_source.shape}_{image_source.dtype}".encode("utf-8")).hexdigest()

            if isinstance(image_source, bytes):
                return _md5(image_source[: min(len(image_source), 65536)]).hexdigest()
        except Exception:
            pass

        return ""

    def detect_sync(
        self,
        image_source: Union[QImage, QPixmap, Image.Image, np.ndarray, bytes],
        use_cache: bool = True,
    ) -> List[QRResult]:
        """Run synchronous detection (useful for tests or immediate lookups)."""
        cache_key = self._compute_image_hash(image_source) if use_cache else ""
        if cache_key and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            results = self.detector.detect(image_source)
        except Exception as exc:
            logger.error("QRService detect_sync exception: %s", exc)
            results = []

        if cache_key and results:
            self._cache[cache_key] = results
        return results

    def detect_async(
        self,
        image_source: Union[QImage, QPixmap, Image.Image, np.ndarray, bytes],
        on_finished: Optional[Callable[[List[QRResult]], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        use_cache: bool = True,
    ) -> Optional[QRDetectionWorker]:
        """
        Run asynchronous QR code detection in a background thread.
        Does not block UI thread.
        """
        cache_key = self._compute_image_hash(image_source) if use_cache else ""
        if cache_key and cache_key in self._cache:
            cached_results = self._cache[cache_key]
            self.qr_detected.emit(cached_results)
            if on_finished:
                on_finished(cached_results)
            return None

        # Cancel any previous active worker
        if self._active_worker is not None and self._active_worker.isRunning():
            self._active_worker.cancel()
            self._active_worker.wait(100)

        worker = QRDetectionWorker(image_source=image_source, detector=self.detector)

        def _handle_finished(results: List[QRResult]) -> None:
            if cache_key:
                self._cache[cache_key] = results
            self.qr_detected.emit(results)
            if on_finished:
                on_finished(results)

        def _handle_error(err_msg: str) -> None:
            self.detection_error.emit(err_msg)
            if on_error:
                on_error(err_msg)

        worker.finished.connect(_handle_finished)
        worker.error.connect(_handle_error)

        self._active_worker = worker
        worker.start()
        return worker

    def clear_cache(self) -> None:
        """Clear memory cache."""
        self._cache.clear()

