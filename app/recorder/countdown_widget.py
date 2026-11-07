"""Animated 3-2-1 countdown overlay widget shown before GIF recording starts."""

from typing import Optional
from PySide6.QtCore import QRect, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget


class CountdownOverlay(QWidget):
    """Full or region overlay displaying an animated 3... 2... 1 countdown."""

    countdown_finished = Signal()

    def __init__(self, region: QRect, start_num: int = 3, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.region = region
        self.current_num = start_num

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(region)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        self.show()
        self.raise_()
        self.timer.start(800)

    def _on_tick(self) -> None:
        self.current_num -= 1
        if self.current_num <= 0:
            self.timer.stop()
            self.close()
            self.countdown_finished.emit()
        else:
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Translucent dark tint
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        # Circular badge in center
        center = self.rect().center()
        radius = 50
        painter.setBrush(QColor(49, 130, 206, 220))
        painter.setPen(QColor("#FFFFFF"))
        painter.drawEllipse(center, radius, radius)

        # Number text
        font = QFont("Segoe UI", 36, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        text = str(self.current_num)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, text)

        painter.end()

