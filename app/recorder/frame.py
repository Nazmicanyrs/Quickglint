"""Frame representation and metadata container for screen recording."""

from dataclasses import dataclass
from typing import Optional
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage


@dataclass
class RecordedFrame:
    """Represents a single captured video/GIF frame."""
    image: QImage
    timestamp: float
    cursor_pos: Optional[QPoint] = None
    is_left_clicked: bool = False
    is_right_clicked: bool = False

