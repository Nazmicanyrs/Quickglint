"""Interactive screen GIF recorder with floating recording HUD and mouse tracking."""

import ctypes
import time
from typing import Callable, List, Optional
from PySide6.QtCore import QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QImage, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.capture.engine import CaptureEngine
from app.recorder.countdown_widget import CountdownOverlay
from app.recorder.frame import RecordedFrame
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.logger import logger


class RecordingHUD(QWidget):
    """Floating bar showing elapsed time and Stop button during active recording."""

    stop_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(DARK_THEME_QSS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setStyleSheet(
            "background-color: #1A202C; border: 2px solid #E53E3E; border-radius: 8px; padding: 6px 14px;"
        )
        card_layout = QHBoxLayout(card)
        card_layout.setSpacing(12)

        # Red recording dot
        rec_dot = QLabel("●", card)
        rec_dot.setStyleSheet("color: #E53E3E; font-size: 16px;")
        card_layout.addWidget(rec_dot)

        self.time_lbl = QLabel("00:00", card)
        self.time_lbl.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 14px;")
        card_layout.addWidget(self.time_lbl)

        self.stop_btn = QPushButton("■ Kaydı Bitir (Finish)", card)
        self.stop_btn.setObjectName("cancelActionBtn")
        self.stop_btn.setFixedHeight(30)
        self.stop_btn.setStyleSheet(
            "QPushButton { background-color: #E53E3E; color: #FFFFFF; font-weight: bold; "
            "border-radius: 6px; padding: 4px 12px; font-size: 12px; } "
            "QPushButton:hover { background-color: #C53030; }"
        )
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        card_layout.addWidget(self.stop_btn)

        layout.addWidget(card)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # Exclude HUD window from Windows screen capture APIs (WDA_EXCLUDEFROMCAPTURE = 0x11)
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
        except Exception:
            pass

    def update_time(self, seconds: float) -> None:
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        self.time_lbl.setText(f"{mins:02d}:{secs:02d}")


class ScreenGifRecorder:
    """Manages screen recording at configurable FPS with exact real-time playback speed."""

    def __init__(
        self,
        region: QRect,
        fps: int = 15,
        max_duration_sec: float = 60.0,
        on_finished_callback: Optional[Callable[[List[RecordedFrame]], None]] = None,
        on_cancel_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        self.region = region
        self.fps = fps
        self.max_duration_sec = max_duration_sec
        self.on_finished = on_finished_callback
        self.on_cancel = on_cancel_callback

        self.frames: List[RecordedFrame] = []
        self._start_time = 0.0
        self._countdown_overlay: Optional[CountdownOverlay] = None

        # Capture timer
        self.timer = QTimer()
        self.timer.setInterval(int(1000 / max(1, fps)))
        self.timer.timeout.connect(self._on_capture_tick)

        # Floating HUD
        self.hud = RecordingHUD()
        self.hud.stop_requested.connect(self.stop)

    def start_with_countdown(self) -> None:
        """Show 3-2-1 animated countdown and then start recording."""
        self._countdown_overlay = CountdownOverlay(self.region)
        self._countdown_overlay.countdown_finished.connect(self._start_capture)
        self._countdown_overlay.start()

    def start_immediately(self) -> None:
        """Start recording immediately without countdown."""
        self._start_capture()

    def _start_capture(self) -> None:
        logger.info("GIF Recording started for region %s at %d FPS...", self.region, self.fps)
        self.frames.clear()
        self._start_time = time.time()

        # Capture first initial frame immediately
        self._on_capture_tick()

        # Position HUD outside the recording region (below or above)
        primary_screen = QGuiApplication.primaryScreen()
        screen_geo = primary_screen.geometry() if primary_screen else QRect(0, 0, 1920, 1080)

        hud_w, hud_h = 240, 50
        hx = max(10, min(self.region.right() - hud_w, screen_geo.width() - hud_w - 10))

        # Prefer placing below selection
        if self.region.bottom() + hud_h + 10 <= screen_geo.height():
            hy = self.region.bottom() + 10
        # Otherwise place above selection
        elif self.region.top() - hud_h - 10 >= 0:
            hy = self.region.top() - hud_h - 10
        else:
            # Fallback to bottom-right corner inside with WDA_EXCLUDEFROMCAPTURE
            hy = screen_geo.height() - hud_h - 10

        self.hud.move(hx, hy)
        self.hud.show()
        self.hud.raise_()

        self.timer.start()

    def _on_capture_tick(self) -> None:
        now = time.time()
        elapsed = now - self._start_time
        self.hud.update_time(elapsed)

        if elapsed >= self.max_duration_sec and self._start_time > 0:
            self.stop()
            return

        # Capture region frame
        frame_img = CaptureEngine.capture_region(self.region, include_cursor=False)

        # Track relative cursor pos inside recording region
        global_cursor = QCursor.pos()
        if self.region.contains(global_cursor):
            rel_cursor = QPoint(global_cursor.x() - self.region.x(), global_cursor.y() - self.region.y())
        else:
            rel_cursor = None

        self.frames.append(
            RecordedFrame(
                image=frame_img,
                timestamp=now,
                cursor_pos=rel_cursor,
            )
        )

    def stop(self) -> None:
        """Stop recording and return captured frames."""
        self.timer.stop()
        self.hud.close()
        logger.info("GIF Recording stopped. Total frames captured: %d", len(self.frames))

        if self.on_finished:
            self.on_finished(self.frames)

