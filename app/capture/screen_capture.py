"""High-definition screen capture module capturing 100% raw uncompressed hardware pixels."""

from typing import List, Tuple
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPixmap, QPolygon, QScreen

from app.utils.logger import logger


class ScreenCaptureManager:
    """Captures single or multi-monitor screens at 100% native physical resolution."""

    @staticmethod
    def get_virtual_geometry() -> QRect:
        """Calculate the unified bounding rectangle encompassing all connected screens."""
        screens = QGuiApplication.screens()
        if not screens:
            return QRect(0, 0, 1920, 1080)

        virtual_rect = screens[0].geometry()
        for screen in screens[1:]:
            virtual_rect = virtual_rect.united(screen.geometry())

        return virtual_rect

    @classmethod
    def capture_all_screens(cls, include_cursor: bool = False) -> Tuple[QPixmap, QRect]:
        """
        Capture all screens at full native hardware resolution without any scaling or downsampling.
        Returns: (combined_pixmap, virtual_geometry_rect)
        """
        screens: List[QScreen] = QGuiApplication.screens()
        virtual_rect = cls.get_virtual_geometry()

        if not screens:
            blank = QPixmap(1920, 1080)
            blank.fill(QColor(0, 0, 0))
            return blank, virtual_rect

        if len(screens) == 1:
            screen = screens[0]
            combined_pixmap = screen.grabWindow(0)
            logger.info(
                "Captured single screen at 1:1 hardware resolution: %dx%d px (Bounds: %s)",
                combined_pixmap.width(),
                combined_pixmap.height(),
                virtual_rect,
            )
        else:
            combined_pixmap = QPixmap(virtual_rect.size())
            combined_pixmap.fill(QColor(0, 0, 0))

            painter = QPainter(combined_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

            try:
                for screen in screens:
                    geo = screen.geometry()
                    grab = screen.grabWindow(0)
                    offset_x = geo.x() - virtual_rect.x()
                    offset_y = geo.y() - virtual_rect.y()
                    painter.drawPixmap(offset_x, offset_y, grab)
            finally:
                painter.end()

            logger.info(
                "Captured %d multi-screens combined buffer: %dx%d px (Bounds: %s)",
                len(screens),
                combined_pixmap.width(),
                combined_pixmap.height(),
                virtual_rect,
            )

        # Draw mouse cursor if requested
        if include_cursor:
            painter = QPainter(combined_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            try:
                cursor_pos = QCursor.pos()
                cx = cursor_pos.x() - virtual_rect.x()
                cy = cursor_pos.y() - virtual_rect.y()

                painter.setPen(QColor(255, 255, 255))
                painter.setBrush(QColor(0, 0, 0))
                cursor_poly = QPolygon([
                    QPoint(cx, cy),
                    QPoint(cx, cy + 18),
                    QPoint(cx + 5, cy + 14),
                    QPoint(cx + 11, cy + 19),
                    QPoint(cx + 14, cy + 17),
                    QPoint(cx + 9, cy + 12),
                    QPoint(cx + 14, cy + 12),
                ])
                painter.drawPolygon(cursor_poly)
            finally:
                painter.end()

        return combined_pixmap, virtual_rect

