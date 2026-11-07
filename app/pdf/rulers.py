"""Interactive horizontal and vertical PDF rulers with unit selection (mm, cm, inch, px) and cursor tracker."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from app.pdf.geometry import MM_PER_INCH, POINTS_PER_INCH


class RulerUnit(str, Enum):
    MM = "mm"
    CM = "cm"
    INCH = "inch"
    PX = "px"


class PDFRulerWidget(QWidget):
    """Ruler bar tracking cursor position and drawing unit tick marks."""

    def __init__(self, is_horizontal: bool = True, unit: RulerUnit = RulerUnit.MM, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.is_horizontal = is_horizontal
        self.unit = unit
        self.scale_factor: float = 1.0  # pixels per PDF point
        self.offset: float = 0.0        # view offset in screen pixels
        self.cursor_pos: Optional[float] = None
        self.grid_snap: bool = True
        self.grid_spacing_pt: float = 20.0

        self.setFixedHeight(22) if is_horizontal else self.setFixedWidth(22)
        self.setStyleSheet("background-color: #0F172A; border: none;")

    def set_view_params(self, scale: float, offset: float) -> None:
        self.scale_factor = max(0.1, scale)
        self.offset = offset
        self.update()

    def set_cursor_pos(self, pt_coord: Optional[float]) -> None:
        self.cursor_pos = pt_coord
        self.update()

    def set_unit(self, unit: RulerUnit) -> None:
        self.unit = unit
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1E293B"))

        painter.setPen(QPen(QColor("#334155"), 1))
        if self.is_horizontal:
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        else:
            painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#94A3B8"), 1))

        # Convert unit to PDF points step
        if self.unit == RulerUnit.MM:
            step_unit = 10.0  # 10 mm
            step_pt = 10.0 * POINTS_PER_INCH / MM_PER_INCH
        elif self.unit == RulerUnit.CM:
            step_unit = 1.0
            step_pt = 10.0 * POINTS_PER_INCH / MM_PER_INCH
        elif self.unit == RulerUnit.INCH:
            step_unit = 1.0
            step_pt = POINTS_PER_INCH
        else:  # PX
            step_unit = 50.0
            step_pt = 50.0

        step_screen = step_pt * self.scale_factor
        if step_screen < 25:
            step_screen *= 2
            step_unit *= 2

        length = self.width() if self.is_horizontal else self.height()
        start_coord = -self.offset / self.scale_factor

        # Draw tick marks
        curr_screen = self.offset % step_screen
        unit_val = (curr_screen - self.offset) / (step_pt * self.scale_factor) * step_unit

        while curr_screen < length:
            if curr_screen >= 0:
                if self.is_horizontal:
                    painter.drawLine(int(curr_screen), self.height() - 7, int(curr_screen), self.height())
                    painter.drawText(int(curr_screen) + 2, self.height() - 8, f"{int(round(unit_val))}")
                else:
                    painter.drawLine(self.width() - 7, int(curr_screen), self.width(), int(curr_screen))
                    painter.save()
                    painter.translate(self.width() - 8, int(curr_screen) + 10)
                    painter.rotate(-90)
                    painter.drawText(0, 0, f"{int(round(unit_val))}")
                    painter.restore()

            curr_screen += step_screen
            unit_val += step_unit

        # Draw Cursor Indicator
        if self.cursor_pos is not None:
            screen_pos = self.cursor_pos * self.scale_factor + self.offset
            painter.setPen(QPen(QColor("#38BDF8"), 1))
            if self.is_horizontal:
                painter.drawLine(int(screen_pos), 0, int(screen_pos), self.height())
            else:
                painter.drawLine(0, int(screen_pos), self.width(), int(screen_pos))

