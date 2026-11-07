"""Unified Capture Engine abstraction for screenshots, scrolling frames, and video/GIF recording."""

import time
from typing import Callable, Generator, List, Optional, Tuple
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QCursor, QGuiApplication, QImage, QPixmap

from app.capture.screen_capture import ScreenCaptureManager
from app.utils.logger import logger


class CaptureEngine:
    """Unified engine for capturing single frames, rectangular regions, and continuous sequences."""

    @staticmethod
    def get_virtual_geometry() -> QRect:
        """Get the full virtual bounding rectangle across all monitors."""
        return ScreenCaptureManager.get_virtual_geometry()

    @staticmethod
    def capture_full_desktop(include_cursor: bool = False) -> Tuple[QPixmap, QRect]:
        """Capture entire multi-screen virtual desktop."""
        return ScreenCaptureManager.capture_all_screens(include_cursor)

    @classmethod
    def capture_region(cls, region: QRect, include_cursor: bool = False) -> QImage:
        """
        Capture a specific rectangular screen region at native 1:1 hardware pixel resolution.
        """
        screens = QGuiApplication.screens()
        if not screens:
            blank = QImage(region.size(), QImage.Format.Format_RGB32)
            blank.fill(0)
            return blank

        # Single or multi-screen capture
        full_pixmap, virtual_rect = cls.capture_full_desktop(include_cursor=include_cursor)

        # Offset target region relative to virtual desktop coordinate system
        target_x = region.x() - virtual_rect.x()
        target_y = region.y() - virtual_rect.y()
        target_rect = QRect(target_x, target_y, region.width(), region.height())

        cropped = full_pixmap.copy(target_rect)
        return cropped.toImage()

    @classmethod
    def capture_frame(cls, region: Optional[QRect] = None, include_cursor: bool = False) -> Tuple[QImage, float]:
        """
        Capture a single timestamped frame.
        Returns: (QImage, timestamp_in_seconds)
        """
        ts = time.time()
        if region is None:
            full_pix, _ = cls.capture_full_desktop(include_cursor=include_cursor)
            return full_pix.toImage(), ts
        else:
            return cls.capture_region(region, include_cursor=include_cursor), ts

