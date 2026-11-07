"""OCR provider abstraction and data models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage
from PIL import Image


@dataclass
class OCRResult:
    """Represents an extracted text segment and its bounding box."""
    text: str
    confidence: float
    bounding_box: QRect
    line_number: int = 0
    word_number: int = 0


class OCRProvider(ABC):
    """Abstract base class for pluggable OCR engines."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the underlying OCR runtime/binary is ready to use."""
        pass

    @abstractmethod
    def detect_text(self, image: QImage | Image.Image) -> List[OCRResult]:
        """
        Extract text tokens and their exact bounding boxes from the given image.
        Returns: List of OCRResult instances.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider display name."""
        pass

