"""Local offline QR code detector engine supporting multiple QR codes, multi-scale, and fallbacks."""

import io
from typing import List, Optional, Union
import numpy as np
from PIL import Image
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRect
from PySide6.QtGui import QImage, QPixmap

from app.qr.qr_result import QRResult
from app.utils.logger import logger

try:
    import zxingcpp
    HAS_ZXING = True
except ImportError:
    zxingcpp = None  # type: ignore
    HAS_ZXING = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    cv2 = None  # type: ignore
    HAS_CV2 = False


class QRDetector:
    """Offline, in-memory QR code detection and decoding engine."""

    def __init__(
        self,
        enable_preprocessing: bool = True,
        max_dimension: int = 4096,
        downscale_large_images: bool = True,
    ) -> None:
        self.enable_preprocessing = enable_preprocessing
        self.max_dimension = max_dimension
        self.downscale_large_images = downscale_large_images

    def detect(
        self,
        image_source: Union[QImage, QPixmap, Image.Image, np.ndarray, bytes],
    ) -> List[QRResult]:
        """
        Detect all QR codes in given image source without writing to disk.
        Returns a list of QRResult objects, ordered and deduplicated.
        """
        try:
            np_img = self._to_numpy_rgb(image_source)
            if np_img is None or np_img.size == 0:
                return []

            h, w = np_img.shape[:2]
            if w <= 10 or h <= 10:
                return []

            raw_results: List[QRResult] = []

            # 1. Primary detection with zxing-cpp
            if HAS_ZXING:
                raw_results.extend(self._detect_zxing(np_img))

            # 2. If nothing found or to catch missed codes, try OpenCV fallback
            if HAS_CV2 and (not raw_results or len(raw_results) == 0):
                raw_results.extend(self._detect_cv2(np_img))

            # 3. If image is large and nothing found yet, try scaled pass
            if not raw_results and self.downscale_large_images and (w > 2000 or h > 2000):
                raw_results.extend(self._detect_scaled(np_img))

            # 4. If nothing found and preprocessing is enabled, try contrast / grayscale enhancement
            if not raw_results and self.enable_preprocessing and HAS_CV2:
                raw_results.extend(self._detect_preprocessed(np_img))

            # 5. Deduplicate and index results
            deduped = self._deduplicate(raw_results)

            # Re-index
            final_results = [
                QRResult(
                    data=r.data,
                    type=r.type,
                    bounding_box=r.bounding_box,
                    is_url=r.is_url,
                    normalized_url=r.normalized_url,
                    confidence=r.confidence,
                    index=i + 1,
                    parsed_details=r.parsed_details,
                )
                for i, r in enumerate(deduped)
            ]

            return final_results

        except Exception as exc:
            logger.error("Error during offline QR detection: %s", exc)
            return []

    def _to_numpy_rgb(
        self,
        image_source: Union[QImage, QPixmap, Image.Image, np.ndarray, bytes],
    ) -> Optional[np.ndarray]:
        """Convert various image formats to RGB numpy array in-memory."""
        if image_source is None:
            return None

        if isinstance(image_source, np.ndarray):
            if len(image_source.shape) == 2:
                if HAS_CV2:
                    return cv2.cvtColor(image_source, cv2.COLOR_GRAY2RGB)
                return np.stack((image_source,) * 3, axis=-1)
            elif len(image_source.shape) == 3:
                if image_source.shape[2] == 4:
                    if HAS_CV2:
                        return cv2.cvtColor(image_source, cv2.COLOR_RGBA2RGB)
                    return image_source[:, :, :3]
                return image_source
            return None

        if isinstance(image_source, Image.Image):
            return np.array(image_source.convert("RGB"))

        if isinstance(image_source, QPixmap):
            image_source = image_source.toImage()

        if isinstance(image_source, QImage):
            if image_source.isNull():
                return None
            converted = image_source.convertToFormat(QImage.Format.Format_RGB888)
            w = converted.width()
            h = converted.height()
            bpl = converted.bytesPerLine()
            ptr = converted.constBits()
            # Read exact size from memoryview buffer safely
            raw_bytes = bytes(ptr)[: converted.sizeInBytes()]
            arr = np.frombuffer(raw_bytes, dtype=np.uint8, count=min(len(raw_bytes), bpl * h)).copy()
            if arr.size == 0 or arr.size < h * bpl:
                # Fallback to PNG/PIL conversion if memory layout differs
                from app.utils.helpers import qimage_to_pil
                pil = qimage_to_pil(image_source)
                return np.array(pil.convert("RGB"))
            arr = arr.reshape((h, bpl))
            arr = arr[:, : w * 3].reshape((h, w, 3)).copy()
            return np.ascontiguousarray(arr)


        if isinstance(image_source, bytes):
            pil_img = Image.open(io.BytesIO(image_source))
            return np.array(pil_img.convert("RGB"))

        return None

    def _detect_zxing(self, np_img: np.ndarray, scale_factor: float = 1.0) -> List[QRResult]:
        """Run zxing-cpp barcode reader."""
        if not HAS_ZXING:
            return []

        results: List[QRResult] = []
        try:
            # We look for all 2D QR-compatible formats
            formats = [
                zxingcpp.BarcodeFormat.QRCode,
                zxingcpp.BarcodeFormat.MicroQRCode,
                zxingcpp.BarcodeFormat.RMQRCode,
            ]
            barcodes = zxingcpp.read_barcodes(np_img, formats=formats)

            for b in barcodes:
                if not b.text:
                    continue

                pos = b.position
                pts = [
                    (pos.top_left.x, pos.top_left.y),
                    (pos.top_right.x, pos.top_right.y),
                    (pos.bottom_right.x, pos.bottom_right.y),
                    (pos.bottom_left.x, pos.bottom_left.y),
                ]

                min_x = int(min(p[0] for p in pts) / scale_factor)
                min_y = int(min(p[1] for p in pts) / scale_factor)
                max_x = int(max(p[0] for p in pts) / scale_factor)
                max_y = int(max(p[1] for p in pts) / scale_factor)

                box = QRect(min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y))
                results.append(QRResult.create(data=b.text, bounding_box=box, confidence=1.0))
        except Exception as exc:
            logger.debug("zxing-cpp detection notice: %s", exc)

        return results

    def _detect_cv2(self, np_img: np.ndarray, scale_factor: float = 1.0) -> List[QRResult]:
        """Run OpenCV QRCodeDetector as fallback."""
        if not HAS_CV2:
            return []

        results: List[QRResult] = []
        try:
            detector = cv2.QRCodeDetector()
            gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
            retval, decoded_info, points, _ = detector.detectAndDecodeMulti(gray)

            if retval and points is not None:
                for i, text in enumerate(decoded_info):
                    if not text:
                        continue
                    pts = points[i]  # shape: (4, 2)
                    min_x = int(np.min(pts[:, 0]) / scale_factor)
                    min_y = int(np.min(pts[:, 1]) / scale_factor)
                    max_x = int(np.max(pts[:, 0]) / scale_factor)
                    max_y = int(np.max(pts[:, 1]) / scale_factor)

                    box = QRect(min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y))
                    results.append(QRResult.create(data=text, bounding_box=box, confidence=0.9))
        except Exception as exc:
            logger.debug("OpenCV QR detection notice: %s", exc)

        return results

    def _detect_scaled(self, np_img: np.ndarray) -> List[QRResult]:
        """Downscale massive screenshot to speed up search or find large QR codes."""
        h, w = np_img.shape[:2]
        max_dim = 1920
        scale = max_dim / max(w, h)
        if scale >= 1.0:
            return []

        new_w, new_h = int(w * scale), int(h * scale)
        if HAS_CV2:
            resized = cv2.resize(np_img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        else:
            pil_img = Image.fromarray(np_img).resize((new_w, new_h), Image.Resampling.BOX)
            resized = np.array(pil_img)

        results = []
        if HAS_ZXING:
            results.extend(self._detect_zxing(resized, scale_factor=scale))
        if not results and HAS_CV2:
            results.extend(self._detect_cv2(resized, scale_factor=scale))

        return results

    def _detect_preprocessed(self, np_img: np.ndarray) -> List[QRResult]:
        """Apply contrast / adaptive thresholding for difficult, low-contrast or blurred screenshots."""
        if not HAS_CV2:
            return []

        results = []
        try:
            gray = cv2.cvtColor(np_img, cv2.COLOR_RGB2GRAY)
            # CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            enhanced_rgb = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)

            if HAS_ZXING:
                results.extend(self._detect_zxing(enhanced_rgb))
            if not results:
                # Try Otsu threshold
                _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                thresh_rgb = cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB)
                if HAS_ZXING:
                    results.extend(self._detect_zxing(thresh_rgb))
                elif HAS_CV2:
                    results.extend(self._detect_cv2(thresh_rgb))
        except Exception:
            pass

        return results

    def _deduplicate(self, results: List[QRResult]) -> List[QRResult]:
        """Filter out duplicates comparing payload string and bounding box proximity."""
        if not results:
            return []

        unique: List[QRResult] = []
        for r in results:
            is_dup = False
            for u in unique:
                if r.data == u.data:
                    # Same payload -> check bounding box overlap or proximity
                    if self._boxes_overlap_or_close(r.bounding_box, u.bounding_box):
                        is_dup = True
                        break
            if not is_dup:
                unique.append(r)

        return unique

    def _boxes_overlap_or_close(self, r1: QRect, r2: QRect, distance_threshold: int = 50) -> bool:
        """Check if two bounding boxes overlap or are within close proximity."""
        if r1.intersects(r2):
            return True
        c1 = r1.center()
        c2 = r2.center()
        dist_sq = (c1.x() - c2.x()) ** 2 + (c1.y() - c2.y()) ** 2
        return dist_sq < (distance_threshold ** 2)

