"""Asynchronous worker thread for non-blocking OCR recognition."""

from typing import List, Optional
from PIL import Image
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.ocr.cache import OCRMemoryCache
from app.ocr.models import OCRStructuredResult
from app.ocr.provider import AutoOCRProvider, OCRProvider
from app.utils.logger import logger


class OCRWorker(QThread):
    """Executes OCR extraction in a background thread with progress reporting and cancellation."""

    progress = Signal(int, str)
    finished = Signal(OCRStructuredResult)
    error = Signal(str)

    def __init__(
        self,
        image: QImage | Image.Image,
        provider: Optional[OCRProvider] = None,
        languages: Optional[List[str]] = None,
        enhance: bool = False,
        use_cache: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.image = image
        self.provider = provider or AutoOCRProvider()
        self.languages = languages or ["tr", "en"]
        self.enhance = enhance
        self.use_cache = use_cache
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request worker thread to cancel processing."""
        self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def run(self) -> None:
        try:
            if self._is_cancelled:
                return

            self.progress.emit(15, "Önbellek ve motor kontrol ediliyor...")

            # Check cache if enabled
            lang_key = "+".join(sorted(self.languages)) + ("_enh" if self.enhance else "")
            cache = OCRMemoryCache.get_instance()

            if self.use_cache and not self.enhance:
                cached_res = cache.get(self.image, lang_key)
                if cached_res is not None:
                    self.progress.emit(100, "Önbellekten yüklendi.")
                    self.finished.emit(cached_res)
                    return

            if self._is_cancelled:
                return

            if not self.provider.is_available():
                self.error.emit(
                    "Yerel OCR motoru bulunamadı veya başlatılamadı.\n"
                    "Lütfen Windows OCR dil paketini veya Tesseract-OCR kurulumunu kontrol edin."
                )
                return

            self.progress.emit(40, "Görüntü analiz ediliyor ve metinler çıkarılıyor...")

            if self._is_cancelled:
                return

            result = self.provider.detect_structured(
                image=self.image,
                languages=self.languages,
                enhance=self.enhance,
            )

            if self._is_cancelled:
                return

            self.progress.emit(85, "Sayfa düzeni ve okuma sırası oluşturuluyor...")

            if self.use_cache and result.blocks:
                cache.put(self.image, result, lang_key)

            self.progress.emit(100, "Tamamlandı.")
            self.finished.emit(result)

        except Exception as exc:
            logger.error("OCRWorker execution error: %s", exc)
            self.error.emit(f"OCR işlemi sırasında hata oluştu: {exc}")

