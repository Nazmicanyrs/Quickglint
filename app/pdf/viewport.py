"""Zoomable and pannable viewport hosting rulers and the PDFCanvasWidget."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QScrollBar,
    QScrollArea,
    QWidget,
)

from app.pdf.canvas import CanvasMode, PDFCanvasWidget
from app.pdf.history import PDFHistoryManager
from app.pdf.rulers import PDFRulerWidget, RulerUnit


class PDFViewportWidget(QWidget):
    """Container with top/left rulers and a central pan/zoom scrollable PDF canvas."""

    zoom_changed = Signal(float)

    ZOOM_PRESETS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]

    def __init__(self, history_manager: Optional[PDFHistoryManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.canvas = PDFCanvasWidget(history_manager=history_manager, parent=self)
        self.ruler_h = PDFRulerWidget(is_horizontal=True, unit=RulerUnit.MM, parent=self)
        self.ruler_v = PDFRulerWidget(is_horizontal=False, unit=RulerUnit.MM, parent=self)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidget(self.canvas)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #0B0F19;
                border: none;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background-color: #0F172A;
                width: 10px;
                height: 10px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background-color: #334155;
                border-radius: 4px;
                min-height: 20px;
                min-width: 20px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background-color: #2563EB;
            }
        """)

        # Layout setup
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        corner = QWidget(self)
        corner.setFixedSize(22, 22)
        corner.setStyleSheet("background-color: #1E293B; border-right: 1px solid #334155; border-bottom: 1px solid #334155;")

        layout.addWidget(corner, 0, 0)
        layout.addWidget(self.ruler_h, 0, 1)
        layout.addWidget(self.ruler_v, 1, 0)
        layout.addWidget(self.scroll_area, 1, 1)

        # Pan state
        self._is_space_panning = False
        self._last_pan_pos = QPoint()

        # Connect signals
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self._sync_rulers)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._sync_rulers)
        self.canvas.cursor_position_changed.connect(self._on_cursor_pos)

    def _sync_rulers(self) -> None:
        origin = self.canvas.get_page_origin()
        h_scroll = self.scroll_area.horizontalScrollBar().value()
        v_scroll = self.scroll_area.verticalScrollBar().value()

        self.ruler_h.set_view_params(self.canvas.zoom_factor, origin.x() - h_scroll)
        self.ruler_v.set_view_params(self.canvas.zoom_factor, origin.y() - v_scroll)

    def _on_cursor_pos(self, x_pt: float, y_pt: float) -> None:
        self.ruler_h.set_cursor_pos(x_pt)
        self.ruler_v.set_cursor_pos(y_pt)

    def set_zoom(self, zoom: float) -> None:
        self.canvas.set_zoom(zoom)
        self._sync_rulers()
        self.zoom_changed.emit(self.canvas.zoom_factor)

    def zoom_in(self) -> None:
        cur = self.canvas.zoom_factor
        for p in self.ZOOM_PRESETS:
            if p > cur + 0.05:
                self.set_zoom(p)
                return
        self.set_zoom(min(5.0, cur * 1.25))

    def zoom_out(self) -> None:
        cur = self.canvas.zoom_factor
        for p in reversed(self.ZOOM_PRESETS):
            if p < cur - 0.05:
                self.set_zoom(p)
                return
        self.set_zoom(max(0.2, cur / 1.25))

    def fit_page(self) -> None:
        page = self.canvas.current_page
        if not page:
            return
        w_pt, h_pt = page.get_dimensions_pt()
        avail_w = self.scroll_area.viewport().width() - 80
        avail_h = self.scroll_area.viewport().height() - 80
        if avail_w <= 0 or avail_h <= 0:
            return

        scale_x = avail_w / w_pt
        scale_y = avail_h / h_pt
        self.set_zoom(min(scale_x, scale_y))

    def fit_width(self) -> None:
        page = self.canvas.current_page
        if not page:
            return
        w_pt, _ = page.get_dimensions_pt()
        avail_w = self.scroll_area.viewport().width() - 80
        if avail_w <= 0:
            return
        self.set_zoom(avail_w / w_pt)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._is_space_panning = True
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._is_space_panning = False
            self.canvas.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._is_space_panning or event.button() == Qt.MouseButton.MiddleButton:
            self._last_pan_pos = event.globalPosition().toPoint()
            self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (self._is_space_panning or event.buttons() & Qt.MouseButton.MiddleButton) and not self._last_pan_pos.isNull():
            delta = event.globalPosition().toPoint() - self._last_pan_pos
            self._last_pan_pos = event.globalPosition().toPoint()

            self.scroll_area.horizontalScrollBar().setValue(
                self.scroll_area.horizontalScrollBar().value() - delta.x()
            )
            self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().value() - delta.y()
            )
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._is_space_panning:
            self.canvas.setCursor(Qt.CursorShape.OpenHandCursor)
            self._last_pan_pos = QPoint()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

