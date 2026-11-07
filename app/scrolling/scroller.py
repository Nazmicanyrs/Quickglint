"""Automated page scrolling driver using smooth mouse wheel event dispatching."""

import ctypes
import sys
import time
from typing import Optional
from PySide6.QtCore import QPoint, QRect

from app.utils.logger import logger


class PageScroller:
    """Simulates smooth mouse wheel scrolling over a target window or region."""

    def __init__(self, step_clicks: int = 4, delay_seconds: float = 0.35) -> None:
        self.step_clicks = step_clicks
        self.delay_seconds = delay_seconds

    def scroll_down(self, target_pos: Optional[QPoint] = None) -> None:
        """Scroll down by step_clicks units smoothly."""
        if target_pos:
            self._set_cursor_pos(target_pos.x(), target_pos.y())

        if sys.platform == "win32":
            # MOUSEEVENTF_WHEEL = 0x0800
            for _ in range(self.step_clicks):
                ctypes.windll.user32.mouse_event(0x0800, 0, 0, -120, 0)
                time.sleep(0.03)
        else:
            try:
                import pyautogui
                pyautogui.scroll(-self.step_clicks)
            except Exception as exc:
                logger.warning("pyautogui scroll unavailable: %s", exc)

        time.sleep(self.delay_seconds)

    def _set_cursor_pos(self, x: int, y: int) -> None:
        if sys.platform == "win32":
            ctypes.windll.user32.SetCursorPos(x, y)

