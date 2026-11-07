"""OCR Provider Abstraction and Concrete Engines."""

from abc import ABC, abstractmethod
import asyncio
import os
import time
from typing import List, Optional
from PIL import Image
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage

from app.ocr.layout import LayoutAnalyzer
from app.ocr.models import OCRStructuredResult, OCRWord
from app.ocr.preprocessing import ImagePreprocessor, qimage_to_pil
from app.utils.logger import logger


class OCRProvider(ABC):
    """Abstract base class for pluggable OCR engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider display name."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if underlying OCR runtime/binary is installed and ready."""
        pass

    @abstractmethod
    def detect_structured(
        self,
        image: QImage | Image.Image,
        languages: Optional[List[str]] = None,
        enhance: bool = False,
    ) -> OCRStructuredResult:
        """Extract structured text tokens and return an OCRStructuredResult."""
        pass


class MockOCRProvider(OCRProvider):
    """Deterministic mock provider for automated unit testing."""

    def __init__(
        self,
        mock_words: Optional[List[OCRWord]] = None,
        available: bool = True,
        delay_seconds: float = 0.0,
    ) -> None:
        self.mock_words: List[OCRWord] = mock_words or []
        self._available: bool = available
        self.delay_seconds: float = delay_seconds

    @property
    def name(self) -> str:
        return "Mock OCR Engine"

    def is_available(self) -> bool:
        return self._available

    def set_available(self, available: bool) -> None:
        self._available = available

    def set_mock_words(self, words: List[OCRWord]) -> None:
        self.mock_words = words

    def detect_structured(
        self,
        image: QImage | Image.Image,
        languages: Optional[List[str]] = None,
        enhance: bool = False,
    ) -> OCRStructuredResult:
        if not self._available:
            return OCRStructuredResult(
                blocks=[],
                full_text="",
                average_confidence=0.0,
                provider_name=self.name,
            )

        if self.delay_seconds > 0:
            time.sleep(self.delay_seconds)

        w = image.width() if isinstance(image, QImage) else image.width
        h = image.height() if isinstance(image, QImage) else image.height

        lang_str = "+".join(languages) if languages else "tr"
        start_t = time.perf_counter()

        result = LayoutAnalyzer.structure_tokens(
            words=list(self.mock_words),
            image_width=w,
            image_height=h,
            language=lang_str,
            provider_name=self.name,
        )
        result.is_enhanced = enhance
        result.execution_time_ms = (time.perf_counter() - start_t) * 1000
        return result


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
                self._available = (engine is not None)
        except Exception:
            self._available = False

        return self._available

    def detect_structured(
        self,
        image: QImage | Image.Image,
        languages: Optional[List[str]] = None,
        enhance: bool = False,
    ) -> OCRStructuredResult:
        if not self.is_available():
            return OCRStructuredResult(blocks=[], full_text="", provider_name=self.name)

        start_time = time.perf_counter()
        orig_w = image.width() if isinstance(image, QImage) else image.width
        orig_h = image.height() if isinstance(image, QImage) else image.height

        # Preprocess on copy
        proc_img, rot_angle, was_upscaled = ImagePreprocessor.preprocess(
            image,
            enhance=enhance,
            upscale_small_text=True,
            detect_orientation=True,
        )

        try:
            import winocr
            import winrt.windows.media.ocr as ocr

            lang = "tr"
            if languages and len(languages) > 0:
                lang = languages[0]
            elif self._lang_tag:
                lang = self._lang_tag

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                ocr_data = loop.run_until_complete(winocr.recognize_pil(proc_img, lang))
            finally:
                loop.close()

            scale_x = orig_w / float(proc_img.width)
            scale_y = orig_h / float(proc_img.height)

            words: List[OCRWord] = []
            for line_idx, line in enumerate(ocr_data.lines):
                line_words = list(line.words)
                for w_idx, w in enumerate(line_words):
                    text = str(w.text).strip()
                    if text:
                        bx = int(w.bounding_rect.x * scale_x)
                        by = int(w.bounding_rect.y * scale_y)
                        bw = max(1, int(w.bounding_rect.width * scale_x))
                        bh = max(1, int(w.bounding_rect.height * scale_y))

                        words.append(
                            OCRWord(
                                text=text,
                                confidence=0.98,
                                bounding_box=QRect(bx, by, bw, bh),
                                word_index=w_idx,
                                line_index=line_idx,
                            )
                        )

            result = LayoutAnalyzer.structure_tokens(
                words=words,
                image_width=orig_w,
                image_height=orig_h,
                language=lang,
                provider_name=self.name,
            )
            result.is_enhanced = enhance
            result.orientation_degrees = rot_angle
            result.execution_time_ms = (time.perf_counter() - start_time) * 1000
            logger.info("Windows Native OCR extracted %d words in %.1f ms", len(words), result.execution_time_ms)
            return result

        except Exception as exc:
            logger.error("Windows Native OCR error: %s", exc)
            return OCRStructuredResult(blocks=[], full_text="", provider_name=self.name)


class TesseractProvider(OCRProvider):
    """OCR provider using pytesseract and Tesseract-OCR binary."""

    def __init__(self) -> None:
        self._available: Optional[bool] = None
        self._setup_binary_path()

    def _setup_binary_path(self) -> None:
        try:
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

    def detect_structured(
        self,
        image: QImage | Image.Image,
        languages: Optional[List[str]] = None,
        enhance: bool = False,
    ) -> OCRStructuredResult:
        if not self.is_available():
            return OCRStructuredResult(blocks=[], full_text="", provider_name=self.name)

        start_time = time.perf_counter()
        orig_w = image.width() if isinstance(image, QImage) else image.width
        orig_h = image.height() if isinstance(image, QImage) else image.height

        proc_img, rot_angle, was_upscaled = ImagePreprocessor.preprocess(
            image,
            enhance=enhance,
            upscale_small_text=True,
            detect_orientation=True,
        )

        try:
            import pytesseract

            lang_arg = "tur+eng"
            if languages:
                lang_map = {"tr": "tur", "en": "eng", "de": "deu", "fr": "fra", "es": "spa", "it": "ita"}
                mapped = [lang_map.get(l, l) for l in languages]
                lang_arg = "+".join(mapped)

            data = pytesseract.image_to_data(
                proc_img,
                lang=lang_arg,
                output_type=pytesseract.Output.DICT,
            )

            scale_x = orig_w / float(proc_img.width)
            scale_y = orig_h / float(proc_img.height)

            words: List[OCRWord] = []
            n_boxes = len(data["text"])

            for i in range(n_boxes):
                text = str(data["text"][i]).strip()
                if not text:
                    continue

                conf_val = float(data["conf"][i])
                if conf_val < 0:
                    continue

                conf = conf_val / 100.0
                x = int(int(data["left"][i]) * scale_x)
                y = int(int(data["top"][i]) * scale_y)
                w = max(1, int(int(data["width"][i]) * scale_x))
                h = max(1, int(int(data["height"][i]) * scale_y))

                words.append(
                    OCRWord(
                        text=text,
                        confidence=conf,
                        bounding_box=QRect(x, y, w, h),
                        line_index=int(data.get("line_num", [0])[i]),
                        word_index=int(data.get("word_num", [0])[i]),
                        block_index=int(data.get("block_num", [0])[i]),
                    )
                )

            result = LayoutAnalyzer.structure_tokens(
                words=words,
                image_width=orig_w,
                image_height=orig_h,
                language=lang_arg,
                provider_name=self.name,
            )
            result.is_enhanced = enhance
            result.orientation_degrees = rot_angle
            result.execution_time_ms = (time.perf_counter() - start_time) * 1000
            logger.info("Tesseract OCR extracted %d words in %.1f ms", len(words), result.execution_time_ms)
            return result

        except Exception as exc:
            logger.error("Tesseract detection failed: %s", exc)
            return OCRStructuredResult(blocks=[], full_text="", provider_name=self.name)


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

    def detect_structured(
        self,
        image: QImage | Image.Image,
        languages: Optional[List[str]] = None,
        enhance: bool = False,
    ) -> OCRStructuredResult:
        if not self.is_available():
            return OCRStructuredResult(blocks=[], full_text="", provider_name=self.name)

        start_time = time.perf_counter()
        orig_w = image.width() if isinstance(image, QImage) else image.width
        orig_h = image.height() if isinstance(image, QImage) else image.height

        proc_img, rot_angle, was_upscaled = ImagePreprocessor.preprocess(
            image,
            enhance=enhance,
            upscale_small_text=True,
            detect_orientation=True,
        )

        try:
            import easyocr
            import numpy as np

            langs = languages or ["tr", "en"]
            if self._reader is None:
                self._reader = easyocr.Reader(langs, gpu=False)

            np_img = np.array(proc_img)
            detections = self._reader.readtext(np_img)

            scale_x = orig_w / float(proc_img.width)
            scale_y = orig_h / float(proc_img.height)

            words: List[OCRWord] = []
            for det_idx, (bbox, text, conf) in enumerate(detections):
                clean_text = str(text).strip()
                if not clean_text:
                    continue

                pts = [[int(pt[0]), int(pt[1])] for pt in bbox]
                min_x = int(min(p[0] for p in pts) * scale_x)
                min_y = int(min(p[1] for p in pts) * scale_y)
                max_x = int(max(p[0] for p in pts) * scale_x)
                max_y = int(max(p[1] for p in pts) * scale_y)

                # Split detected phrase into individual words for fine-grained selection
                token_words = clean_text.split()
                if len(token_words) <= 1:
                    words.append(
                        OCRWord(
                            text=clean_text,
                            confidence=float(conf),
                            bounding_box=QRect(min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y)),
                            word_index=0,
                            line_index=det_idx,
                        )
                    )
                else:
                    total_chars = max(1, len(clean_text))
                    cur_x = min_x
                    box_w = max(1, max_x - min_x)
                    box_h = max(1, max_y - min_y)
                    for w_i, sub_w in enumerate(token_words):
                        sub_len = len(sub_w)
                        sub_w_width = max(1, int(box_w * (sub_len / total_chars)))
                        words.append(
                            OCRWord(
                                text=sub_w,
                                confidence=float(conf),
                                bounding_box=QRect(cur_x, min_y, sub_w_width, box_h),
                                word_index=w_i,
                                line_index=det_idx,
                            )
                        )
                        cur_x += sub_w_width + 4

            result = LayoutAnalyzer.structure_tokens(
                words=words,
                image_width=orig_w,
                image_height=orig_h,
                language="+".join(langs),
                provider_name=self.name,
            )
            result.is_enhanced = enhance
            result.orientation_degrees = rot_angle
            result.execution_time_ms = (time.perf_counter() - start_time) * 1000
            return result

        except Exception as exc:
            logger.error("EasyOCR detection error: %s", exc)
            return OCRStructuredResult(blocks=[], full_text="", provider_name=self.name)


class AutoOCRProvider(OCRProvider):
    """Automatically selects the best and fastest available local OCR engine."""

    def __init__(self) -> None:
        self.providers: List[OCRProvider] = [
            WindowsNativeOCRProvider(),
            TesseractProvider(),
            EasyOCRProvider(),
        ]
        self._active_provider: Optional[OCRProvider] = None

    @property
    def name(self) -> str:
        p = self.get_active_provider()
        return f"Auto ({p.name})" if p else "Auto (None available)"

    def is_available(self) -> bool:
        return self.get_active_provider() is not None

    def get_active_provider(self) -> Optional[OCRProvider]:
        if self._active_provider and self._active_provider.is_available():
            return self._active_provider

        for p in self.providers:
            if p.is_available():
                self._active_provider = p
                logger.info("AutoOCRProvider selected: %s", p.name)
                return p
        return None

    def detect_structured(
        self,
        image: QImage | Image.Image,
        languages: Optional[List[str]] = None,
        enhance: bool = False,
    ) -> OCRStructuredResult:
        p = self.get_active_provider()
        if p:
            return p.detect_structured(image, languages=languages, enhance=enhance)
        logger.warning("No local OCR engine available on this system.")
        return OCRStructuredResult(
            blocks=[],
            full_text="",
            average_confidence=0.0,
            provider_name="None",
        )

