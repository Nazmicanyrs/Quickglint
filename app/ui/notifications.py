"""Modern floating toast notification system for instant user feedback."""

from typing import Optional
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.ui.styles import DARK_THEME_QSS, get_icon


class ToastNotification(QFrame):
    """Floating non-intrusive toast popup showing status messages."""

    def __init__(
        self,
        title: str,
        message: str,
        icon_name: str = "camera",
        duration_ms: int = 3000,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toastNotification")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(DARK_THEME_QSS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 18, 12)
        layout.setSpacing(12)

        # Icon
        icon_label = QLabel(self)
        icon_label.setPixmap(get_icon(icon_name, "#38BDF8", 24).pixmap(24, 24))
        layout.addWidget(icon_label)

        # Text Container
        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        title_label = QLabel(title, self)
        title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 13.5px;")
        text_layout.addWidget(title_label)

        if message:
            msg_label = QLabel(message, self)
            msg_font = QFont("Segoe UI", 9)
            msg_label.setFont(msg_font)
            msg_label.setStyleSheet("color: #CBD5E1; font-size: 12px; line-height: 1.4;")
            text_layout.addWidget(msg_label)

        layout.addLayout(text_layout)

        self.adjustSize()
        self._position_on_screen()

        # Auto-dismiss timer
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self._fade_out_and_close)
        self.dismiss_timer.start(duration_ms)

        # Fade in animation
        self.setWindowOpacity(0.0)
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(250)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()

    def _position_on_screen(self) -> None:
        """Position the toast in bottom right of primary screen above taskbar."""
        primary_screen = QGuiApplication.primaryScreen()
        if not primary_screen:
            return

        avail_geo = primary_screen.availableGeometry()
        margin = 24
        x = avail_geo.right() - self.width() - margin
        y = avail_geo.bottom() - self.height() - margin
        self.move(x, y)

    def _fade_out_and_close(self) -> None:
        """Animate fade out and delete widget."""
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.finished.connect(self.close)
        self.fade_anim.start()


class NotificationManager:
    """Helper for showing toast notifications."""

    _active_toasts = []

    @classmethod
    def show_toast(
        cls,
        title: str,
        message: str = "",
        icon_name: str = "camera",
        duration_ms: int = 3000,
    ) -> None:
        toast = ToastNotification(title, message, icon_name, duration_ms)
        cls._active_toasts.append(toast)
        toast.show()

