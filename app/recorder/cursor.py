"""Cursor rendering, glowing halo highlighter, and click ripples for recording."""

from typing import Optional
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPolygon


class CursorRenderer:
    """Renders mouse cursor, yellow highlighter halo, and left/right click ripples onto frames."""

    def __init__(
        self,
        show_cursor: bool = True,
        highlight_cursor: bool = True,
        show_click_effects: bool = True,
    ) -> None:
        self.show_cursor = show_cursor
        self.highlight_cursor = highlight_cursor
        self.show_click_effects = show_click_effects

    def render_to_frame(
        self,
        frame_image: QImage,
        cursor_pos: Optional[QPoint],
        is_left_clicked: bool = False,
        is_right_clicked: bool = False,
    ) -> QImage:
        """Render cursor graphics on top of a frame image copy."""
        if not self.show_cursor or cursor_pos is None:
            return frame_image

        result = frame_image.copy()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        cx, cy = cursor_pos.x(), cursor_pos.y()

        try:
            # 1. Cursor Halo Highlight (Translucent Yellow Circle)
            if self.highlight_cursor:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 235, 59, 90)))
                painter.drawEllipse(QPoint(cx, cy), 16, 16)

            # 2. Click Ripple Effect
            if self.show_click_effects:
                if is_left_clicked:
                    painter.setPen(QPen(QColor(66, 153, 225, 200), 2))
                    painter.setBrush(QBrush(QColor(66, 153, 225, 60)))
                    painter.drawEllipse(QPoint(cx, cy), 14, 14)
                elif is_right_clicked:
                    painter.setPen(QPen(QColor(245, 101, 101, 200), 2))
                    painter.setBrush(QBrush(QColor(245, 101, 101, 60)))
                    painter.drawEllipse(QPoint(cx, cy), 14, 14)

            # 3. Standard Pointer Arrow
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.setBrush(QBrush(QColor(0, 0, 0)))
            cursor_poly = QPolygon([
                QPoint(cx, cy),
                QPoint(cx, cy + 16),
                QPoint(cx + 4, cy + 12),
                QPoint(cx + 9, cy + 17),
                QPoint(cx + 12, cy + 15),
                QPoint(cx + 7, cy + 10),
                QPoint(cx + 12, cy + 10),
            ])
            painter.drawPolygon(cursor_poly)

        finally:
            painter.end()

        return result

