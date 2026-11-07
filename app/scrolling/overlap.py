"""Vertical overlap detector calling high-precision ZNCC aligner."""

import numpy as np
from PIL import Image
from PySide6.QtGui import QImage

from app.scrolling.aligner import ImageAligner


def find_vertical_overlap(
    prev_image: QImage | Image.Image | np.ndarray,
    curr_image: QImage | Image.Image | np.ndarray,
    min_overlap: int = 30,
    max_search_height: int = 800,
) -> int:
    """
    Find the exact vertical displacement (dy) using feature-rich ZNCC.
    """
    res = ImageAligner.align_frames(prev_image, curr_image, max_search_height=max_search_height)
    return res.dy

