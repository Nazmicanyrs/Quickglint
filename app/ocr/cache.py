"""In-memory OCR cache using image SHA-256 content hashes (Zero disk persistence)."""

import hashlib
from collections import OrderedDict
from typing import Optional
from PIL import Image
from PySide6.QtGui import QImage

from app.ocr.models import OCRStructuredResult
from app.ocr.preprocessing import qimage_to_pil


class OCRMemoryCache:
    """Session-only LRU in-memory cache for OCR extraction results."""

    _instance: Optional["OCRMemoryCache"] = None

    def __init__(self, max_entries: int = 50) -> None:
        self.max_entries = max_entries
        self._cache: OrderedDict[str, OCRStructuredResult] = OrderedDict()

    @classmethod
    def get_instance(cls) -> "OCRMemoryCache":
        if cls._instance is None:
            cls._instance = OCRMemoryCache()
        return cls._instance

    @staticmethod
    def compute_image_hash(image: QImage | Image.Image) -> str:
        """Compute SHA-256 hash of the image pixel data."""
        if isinstance(image, QImage):
            pil_img = qimage_to_pil(image)
        else:
            pil_img = image

        hasher = hashlib.sha256()
        # Include image dimensions in the hash
        hasher.update(f"{pil_img.width}x{pil_img.height}".encode("ascii"))
        hasher.update(pil_img.tobytes())
        return hasher.hexdigest()

    def get(self, image: QImage | Image.Image, lang_key: str = "tr") -> Optional[OCRStructuredResult]:
        """Retrieve cached OCR result if available."""
        img_hash = f"{self.compute_image_hash(image)}_{lang_key}"
        if img_hash in self._cache:
            self._cache.move_to_end(img_hash)
            return self._cache[img_hash]
        return None

    def put(self, image: QImage | Image.Image, result: OCRStructuredResult, lang_key: str = "tr") -> None:
        """Store OCR result in memory cache with LRU eviction."""
        img_hash = f"{self.compute_image_hash(image)}_{lang_key}"
        if img_hash in self._cache:
            self._cache.move_to_end(img_hash)
        self._cache[img_hash] = result

        while len(self._cache) > self.max_entries:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Purge all cached results."""
        self._cache.clear()

