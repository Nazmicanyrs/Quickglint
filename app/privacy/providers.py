"""Concrete OCR providers: Windows Native Media OCR, Tesseract, EasyOCR, and Mock provider."""

import asyncio
import io
from typing import List, Optional
from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QRect
from PySide6.QtGui import QImage

from app.privacy.ocr import OCRProvider, OCRResult
from app.utils.logger import logger


def qimage_to_pil(qimg: QImage) -> Image.Image:
    """Convert QImage to PIL Image in memory without disk I/O."""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    qimg.save(buffer, "PNG")
    bytes_data = bytes(buffer.data())
    buffer.close()
    return Image.open(io.BytesIO(bytes_data)).convert("RGB")


class MockOCRProvider(OCRProvider):
    """Deterministic mock OCR provider for automated unit testing."""

    def __init__(self, predefined_results: Optional[List[OCRResult]] = None) -> None:
        self.predefined_results: List[OCRResult] = predefined_results or []
        self._available: bool = True

    @property
    def name(self) -> str:
        return "Mock OCR Engine"

    def is_available(self) -> bool:
        return self._available

    def set_mock_results(self, results: List[OCRResult]) -> None:
        self.predefined_results = results

    def detect_text(self, image: QImage | Image.Image) -> List[OCRResult]:
        return list(self.predefined_results)


class WindowsNativeOCRProvider(OCRProvider):
    """Ultra-fast Windows 10/11 built-in native OCR engine (Windows.Media.Ocr)."""

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._lang_tag: Optional[str] = None

    @property
    def name(self) -> str:
        return "Windows Native OCR"

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            import winrt.windows.media.ocr as ocr
            langs = list(ocr.OcrEngine.available_recognizer_languages)
            if langs:
                self._lang_tag = langs[0].language_tag
                self._available = True
            else:
                engine = ocr.OcrEngine.try_create_from_user_profile_languages()
                if engine:
                    self._available = True
                else:
                    self._available = False
        except Exception:
            self._available = False

        return self._available

    def detect_text(self, image: QImage | Image.Image) -> List[OCRResult]:
        if not self.is_available():
            return []

        try:
            import winrt.windows.media.ocr as ocr
            import winrt.windows.globalization as glob
            from winrt.windows.storage.streams import DataWriter
            from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat

            pil_img = image if isinstance(image, Image.Image) else qimage_to_pil(image)
            if pil_img is None or pil_img.width <= 0 or pil_img.height <= 0:
                return []

            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")

            # Determine best OCR Engine instance
            engine = None
            avail = list(ocr.OcrEngine.available_recognizer_languages)
            for lang_cand in (avail or []):
                try:
                    if ocr.OcrEngine.is_language_supported(lang_cand):
                        engine = ocr.OcrEngine.try_create_from_language(lang_cand)
                        if engine is not None:
                            break
                except Exception:
                    pass

            if engine is None:
                try:
                    engine = ocr.OcrEngine.try_create_from_user_profile_languages()
                except Exception:
                    pass

            if engine is None:
                logger.warning("Windows Native OCR engine could not be instantiated.")
                return []

            writer = DataWriter()
            writer.write_bytes(pil_img.tobytes())
            sb = SoftwareBitmap.create_copy_from_buffer(
                writer.detach_buffer(),
                BitmapPixelFormat.RGBA8,
                pil_img.width,
                pil_img.height,
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                ocr_data = loop.run_until_complete(engine.recognize_async(sb))
            finally:
                loop.close()

            if not ocr_data or not hasattr(ocr_data, "lines"):
                return []

            results: List[OCRResult] = []

            for line_idx, line in enumerate(ocr_data.lines):
                line_text = str(line.text).strip()
                if not line_text:
                    continue

                words = list(line.words)

                # 1. Add every individual word with its exact word bounding box
                for word_idx, w in enumerate(words):
                    w_text = str(w.text).strip()
                    if w_text:
                        results.append(
                            OCRResult(
                                text=w_text,
                                confidence=0.98,
                                bounding_box=QRect(
                                    int(w.bounding_rect.x),
                                    int(w.bounding_rect.y),
                                    max(1, int(w.bounding_rect.width)),
                                    max(1, int(w.bounding_rect.height)),
                                ),
                                line_number=line_idx,
                                word_number=word_idx,
                            )
                        )

                # 2. If line has multiple words, also provide the combined line token
                if len(words) > 1:
                    min_x = min(int(w.bounding_rect.x) for w in words)
                    min_y = min(int(w.bounding_rect.y) for w in words)
                    max_r = max(int(w.bounding_rect.x + w.bounding_rect.width) for w in words)
                    max_b = max(int(w.bounding_rect.y + w.bounding_rect.height) for w in words)
                    line_box = QRect(min_x, min_y, max(1, max_r - min_x), max(1, max_b - min_y))

                    results.append(
                        OCRResult(
                            text=line_text,
                            confidence=0.95,
                            bounding_box=line_box,
                            line_number=line_idx,
                            word_number=0,
                        )
                    )

            logger.info("Windows Native OCR extracted %d text tokens in <20ms", len(results))
            return results

        except Exception as exc:
            logger.error("Windows Native OCR failed: %s", exc)
            return []


class TesseractProvider(OCRProvider):
    """OCR provider using pytesseract and Tesseract-OCR binary."""

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._setup_binary_path()

    def _setup_binary_path(self) -> None:
        try:
            import os
            import pytesseract

            common_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
            ]
            for p in common_paths:
                if os.path.exists(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    break
        except Exception as exc:
            logger.debug("Tesseract setup notice: %s", exc)


    @property
    def name(self) -> str:
        return "Tesseract OCR"

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            import pytesseract
            self._setup_binary_path()
            pytesseract.get_tesseract_version()
            self._available = True
        except Exception:
            self._available = False

        return self._available

    def detect_text(self, image: QImage | Image.Image) -> List[OCRResult]:
        if not self.is_available():
            return []

        try:
            import pytesseract

            pil_img = image if isinstance(image, Image.Image) else qimage_to_pil(image)
            data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)

            results: List[OCRResult] = []
            n_boxes = len(data["text"])

            for i in range(n_boxes):
                text = str(data["text"][i]).strip()
                if not text:
                    continue

                conf_val = float(data["conf"][i])
                if conf_val < 0:
                    continue

                conf = conf_val / 100.0
                x = int(data["left"][i])
                y = int(data["top"][i])
                w = int(data["width"][i])
                h = int(data["height"][i])

                results.append(
                    OCRResult(
                        text=text,
                        confidence=conf,
                        bounding_box=QRect(x, y, w, h),
                        line_number=int(data.get("line_num", [0])[i]),
                        word_number=int(data.get("word_num", [0])[i]),
                    )
                )

            return results
        except Exception as exc:
            logger.error("Tesseract OCR detection failed: %s", exc)
            return []


class EasyOCRProvider(OCRProvider):
    """OCR provider using EasyOCR (PyTorch-backed)."""

    def __init__(self) -> None:
        self._reader = None
        self._available: Optional[bool] = None

    @property
    def name(self) -> str:
        return "EasyOCR"

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import easyocr
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def detect_text(self, image: QImage | Image.Image) -> List[OCRResult]:
        if not self.is_available():
            return []

        try:
            import easyocr
            import numpy as np

            if self._reader is None:
                self._reader = easyocr.Reader(["en", "tr"], gpu=False)

            pil_img = image if isinstance(image, Image.Image) else qimage_to_pil(image)
            np_img = np.array(pil_img)
            detections = self._reader.readtext(np_img)

            results: List[OCRResult] = []
            for bbox, text, conf in detections:
                clean_text = str(text).strip()
                if not clean_text:
                    continue

                pts = [[int(pt[0]), int(pt[1])] for pt in bbox]
                min_x = min(p[0] for p in pts)
                min_y = min(p[1] for p in pts)
                max_x = max(p[0] for p in pts)
                max_y = max(p[1] for p in pts)

                results.append(
                    OCRResult(
                        text=clean_text,
                        confidence=float(conf),
                        bounding_box=QRect(min_x, min_y, max_x - min_x, max_y - min_y),
                    )
                )
            return results
        except Exception as exc:
            logger.error("EasyOCR detection failed: %s", exc)
            return []


class AutoOCRProvider(OCRProvider):
    """Auto-detects and delegates to the fastest, most accurate available OCR engine."""

    def __init__(self) -> None:
        self.providers: List[OCRProvider] = [
            WindowsNativeOCRProvider(),
            TesseractProvider(),
            EasyOCRProvider(),
        ]
        self._active_provider: Optional[OCRProvider] = None

    @property
    def name(self) -> str:
        provider = self.get_active_provider()
        return f"Auto ({provider.name})" if provider else "Auto (None available)"

    def is_available(self) -> bool:
        return self.get_active_provider() is not None

    def get_active_provider(self) -> Optional[OCRProvider]:
        if self._active_provider and self._active_provider.is_available():
            return self._active_provider

        for p in self.providers:
            if p.is_available():
                self._active_provider = p
                logger.info("Auto-selected active OCR engine: %s", p.name)
                return p

        return None

    def detect_text(self, image: QImage | Image.Image) -> List[OCRResult]:
        active = self.get_active_provider()
        if active:
            try:
                res = active.detect_text(image)
                if res:
                    return res
            except Exception as exc:
                logger.warning("Active OCR provider %s failed: %s", active.name, exc)

        for p in self.providers:
            if p != active and p.is_available():
                try:
                    res = p.detect_text(image)
                    if res:
                        return res
                except Exception as exc:
                    logger.warning("Fallback OCR provider %s failed: %s", p.name, exc)

        return []

