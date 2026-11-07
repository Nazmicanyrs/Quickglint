"""Hardware-accelerated pixel-accurate canvas for Quickglint Measurement Studio."""

import math
import time
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from app.measurement.engine import MeasurementEngine
from app.measurement.models import ColorInfo, MeasurementItem, MeasurementType, SnapMode


class MeasurementCanvas(QWidget):
    """Interactive measurement canvas rendering pixel overlays, grids, and live inspection."""

    measurement_added = Signal(object)  # MeasurementItem
    measurement_selected = Signal(str)  # item_id
    mouse_moved_pixel = Signal(int, int, object)  # x, y, ColorInfo
    zoom_changed = Signal(float)  # zoom_factor

    def __init__(self, image: QImage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.image = image
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Viewport transform
        self.zoom_factor: float = 1.0
        self.pan_offset: QPointF = QPointF(20.0, 20.0)
        self._is_panning: bool = False
        self._last_pan_pos: QPoint = QPoint()

        # Tools and state
        self.active_tool: MeasurementType = MeasurementType.DISTANCE
        self.snap_mode: SnapMode = SnapMode.NONE
        self.grid_size: int = 16
        self.show_grid: bool = False
        self.show_center_guides: bool = False
        self.show_labels: bool = True
        self.measurement_color: str = "#38BDF8"

        # Measurements collection
        self.measurements: List[MeasurementItem] = []
        self.selected_item_id: Optional[str] = None

        # Interactive drawing state
        self._is_drawing: bool = False
        self._temp_points: List[Tuple[float, float]] = []
        self._current_mouse_img: Tuple[float, float] = (0.0, 0.0)

        # Style colors
        self.COLOR_DISTANCE = "#38BDF8"  # Cyan/Sky
        self.COLOR_HORIZONTAL = "#60A5FA"  # Blue
        self.COLOR_VERTICAL = "#818CF8"  # Indigo
        self.COLOR_RECTANGLE = "#34D399"  # Emerald
        self.COLOR_ANGLE = "#A78BFA"  # Purple
        self.COLOR_POINT = "#FBBF24"  # Amber
        self.COLOR_SELECTED = "#F43F5E"  # Rose highlight

    # =========================================================================
    # Coordinate Transforms
    # =========================================================================
    def image_to_widget(self, img_point: Tuple[float, float]) -> QPointF:
        """Converts source image pixel coordinate (X, Y) to widget UI coordinate."""
        ix, iy = img_point
        wx = (ix * self.zoom_factor) + self.pan_offset.x()
        wy = (iy * self.zoom_factor) + self.pan_offset.y()
        return QPointF(wx, wy)

    def widget_to_image(self, widget_point: QPointF) -> Tuple[float, float]:
        """Converts widget UI coordinate to source image pixel space."""
        if self.zoom_factor <= 0.0:
            return 0.0, 0.0
        ix = (widget_point.x() - self.pan_offset.x()) / self.zoom_factor
        iy = (widget_point.y() - self.pan_offset.y()) / self.zoom_factor
        return ix, iy

    def _get_snapped_image_coord(self, raw_img_pt: Tuple[float, float]) -> Tuple[float, float]:
        """Applies configured snapping to image coordinate."""
        if self.image.isNull():
            return raw_img_pt
        return MeasurementEngine.snap_point(
            raw_img_pt,
            img_width=self.image.width(),
            img_height=self.image.height(),
            mode=self.snap_mode,
            grid_size=self.grid_size,
        )

    # =========================================================================
    # Zoom & Viewport Controls
    # =========================================================================
    def set_zoom(self, zoom: float, anchor_widget_pt: Optional[QPointF] = None) -> None:
        """Sets zoom factor (clamped 0.1x to 32.0x) anchoring to a specific widget point."""
        new_zoom = max(0.1, min(32.0, zoom))
        if math.isclose(new_zoom, self.zoom_factor, abs_tol=1e-4):
            return

        anchor = anchor_widget_pt if anchor_widget_pt is not None else QPointF(self.width() / 2.0, self.height() / 2.0)
        img_x, img_y = self.widget_to_image(anchor)

        self.zoom_factor = new_zoom
        self.pan_offset = QPointF(
            anchor.x() - (img_x * self.zoom_factor),
            anchor.y() - (img_y * self.zoom_factor),
        )
        self.zoom_changed.emit(self.zoom_factor)
        self.update()

    def fit_to_view(self) -> None:
        """Centers and scales the image to fit entirely within the widget viewport."""
        if self.image.isNull() or self.width() <= 40 or self.height() <= 40:
            return

        avail_w = max(100.0, float(self.width() - 40))
        avail_h = max(100.0, float(self.height() - 40))
        scale_w = avail_w / float(self.image.width())
        scale_h = avail_h / float(self.image.height())
        fit_zoom = min(scale_w, scale_h, 1.0)

        self.zoom_factor = max(0.1, fit_zoom)
        self.pan_offset = QPointF(
            (self.width() - (self.image.width() * self.zoom_factor)) / 2.0,
            (self.height() - (self.image.height() * self.zoom_factor)) / 2.0,
        )
        self.zoom_changed.emit(self.zoom_factor)
        self.update()

    def zoom_100(self) -> None:
        """Resets zoom factor to 1.0 (1:1 hardware pixel size)."""
        self.set_zoom(1.0)

    # =========================================================================
    # Mouse & Keyboard Event Handlers
    # =========================================================================
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handles mouse wheel zoom centered at cursor position."""
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        pos = QPointF(event.position())
        self.set_zoom(self.zoom_factor * factor, anchor_widget_pt=pos)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Middle click or Space+Left click -> Pan
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier or event.modifiers() & Qt.KeyboardModifier.AltModifier)):
            self._is_panning = True
            self._last_pan_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            raw_img_pt = self.widget_to_image(QPointF(event.pos()))
            snapped_pt = self._get_snapped_image_coord(raw_img_pt)

            if self.active_tool == MeasurementType.POINT:
                # Instant 1-click inspection
                col_info = MeasurementEngine.sample_pixel_color(self.image, int(snapped_pt[0]), int(snapped_pt[1]))
                item = MeasurementItem(
                    mtype=MeasurementType.POINT,
                    points=[snapped_pt],
                    color=self.COLOR_POINT,
                    data={
                        "x": snapped_pt[0],
                        "y": snapped_pt[1],
                        "hex": col_info.hex_value,
                        "rgb": col_info.rgb_str,
                        "hsl": col_info.hsl_str,
                    },
                )
                self.measurements.append(item)
                self.selected_item_id = item.id
                self.measurement_added.emit(item)
                self.update()
                return

            elif self.active_tool == MeasurementType.ANGLE:
                # 3-click mode
                self._temp_points.append(snapped_pt)
                if len(self._temp_points) == 3:
                    pA, pB, pC = self._temp_points
                    ang_data = MeasurementEngine.calculate_angle_3pt(pA, pB, pC)
                    item = MeasurementItem(
                        mtype=MeasurementType.ANGLE,
                        points=[pA, pB, pC],
                        color=self.COLOR_ANGLE,
                        data=ang_data,
                    )
                    self.measurements.append(item)
                    self.selected_item_id = item.id
                    self.measurement_added.emit(item)
                    self._temp_points = []
                    self._is_drawing = False
                else:
                    self._is_drawing = True
                self.update()
                return

            else:
                # Drag mode (Distance, Horizontal, Vertical, Rectangle)
                self._is_drawing = True
                self._temp_points = [snapped_pt, snapped_pt]
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            delta = event.pos() - self._last_pan_pos
            self._last_pan_pos = event.pos()
            self.pan_offset += QPointF(delta.x(), delta.y())
            self.update()
            return

        raw_img_pt = self.widget_to_image(QPointF(event.pos()))
        snapped_pt = self._get_snapped_image_coord(raw_img_pt)
        self._current_mouse_img = snapped_pt

        # Emit live coordinate and color
        ix, iy = int(round(snapped_pt[0])), int(round(snapped_pt[1]))
        col_info = MeasurementEngine.sample_pixel_color(self.image, ix, iy)
        self.mouse_moved_pixel.emit(ix, iy, col_info)

        if self._is_drawing and self._temp_points:
            if self.active_tool in (MeasurementType.DISTANCE, MeasurementType.HORIZONTAL, MeasurementType.VERTICAL, MeasurementType.RECTANGLE):
                self._temp_points[1] = snapped_pt
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        if event.button() == Qt.MouseButton.LeftButton and self._is_drawing:
            if self.active_tool in (MeasurementType.DISTANCE, MeasurementType.HORIZONTAL, MeasurementType.VERTICAL, MeasurementType.RECTANGLE):
                if len(self._temp_points) >= 2:
                    p1 = self._temp_points[0]
                    p2 = self._get_snapped_image_coord(self.widget_to_image(QPointF(event.pos())))
                    
                    # Ignore zero-length drags
                    if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 1.0:
                        item = self._create_measurement_from_2pt(self.active_tool, p1, p2)
                        self.measurements.append(item)
                        self.selected_item_id = item.id
                        self.measurement_added.emit(item)

                self._is_drawing = False
                self._temp_points = []
                self.update()

    def _create_measurement_from_2pt(self, mtype: MeasurementType, p1: Tuple[float, float], p2: Tuple[float, float]) -> MeasurementItem:
        if mtype == MeasurementType.DISTANCE:
            data = MeasurementEngine.calculate_distance(p1, p2)
            color = self.COLOR_DISTANCE
        elif mtype == MeasurementType.HORIZONTAL:
            data = MeasurementEngine.calculate_horizontal(p1, p2)
            color = self.COLOR_HORIZONTAL
        elif mtype == MeasurementType.VERTICAL:
            data = MeasurementEngine.calculate_vertical(p1, p2)
            color = self.COLOR_VERTICAL
        elif mtype == MeasurementType.RECTANGLE:
            data = MeasurementEngine.calculate_rectangle(p1, p2)
            color = self.COLOR_RECTANGLE
        else:
            data = {}
            color = self.COLOR_DISTANCE

        return MeasurementItem(
            mtype=mtype,
            points=[p1, p2],
            color=color,
            data=data,
        )

    # =========================================================================
    # Paint & Render Pipeline
    # =========================================================================
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 1. Dark Studio Workspace Backdrop
        painter.fillRect(self.rect(), QColor("#0A0E17"))

        if self.image.isNull():
            painter.end()
            return

        # 2. Draw Source Image
        img_rect_w = self.image.width() * self.zoom_factor
        img_rect_h = self.image.height() * self.zoom_factor
        target_rect = QRectF(self.pan_offset.x(), self.pan_offset.y(), img_rect_w, img_rect_h)

        # Subtle shadow / outline around image
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawRect(target_rect)
        painter.drawImage(target_rect, self.image)

        # 3. Grid Overlay
        if self.show_grid and self.grid_size > 0:
            self._render_grid(painter, target_rect)

        # 4. Center Guides
        if self.show_center_guides:
            self._render_center_guides(painter, target_rect)

        # 5. Render Completed Measurements
        for item in self.measurements:
            if item.visible:
                is_selected = (item.id == self.selected_item_id)
                self._render_measurement_item(painter, item, is_selected)

        # 6. Render Live In-Progress Drawing
        if self._is_drawing and self._temp_points:
            self._render_drawing_preview(painter)

        # 7. Snapping Indicator
        if self.snap_mode != SnapMode.NONE:
            snap_widget_pt = self.image_to_widget(self._current_mouse_img)
            painter.setPen(QPen(QColor("#38BDF8"), 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(snap_widget_pt, 6, 6)

        painter.end()

    def _render_grid(self, painter: QPainter, img_rect: QRectF) -> None:
        """Draws subtle grid lines over the image area."""
        painter.save()
        painter.setClipRect(img_rect)
        grid_pen = QPen(QColor(255, 255, 255, 25), 1, Qt.PenStyle.DotLine)
        painter.setPen(grid_pen)

        step_img = float(self.grid_size)
        w, h = self.image.width(), self.image.height()

        x = 0.0
        while x <= w:
            p1 = self.image_to_widget((x, 0.0))
            p2 = self.image_to_widget((x, float(h)))
            painter.drawLine(p1, p2)
            x += step_img

        y = 0.0
        while y <= h:
            p1 = self.image_to_widget((0.0, y))
            p2 = self.image_to_widget((float(w), y))
            painter.drawLine(p1, p2)
            y += step_img

        painter.restore()

    def _render_center_guides(self, painter: QPainter, img_rect: QRectF) -> None:
        """Draws center X and Y reference axes with labels."""
        cx = self.image.width() / 2.0
        cy = self.image.height() / 2.0

        p_top = self.image_to_widget((cx, 0.0))
        p_bot = self.image_to_widget((cx, float(self.image.height())))
        p_lft = self.image_to_widget((0.0, cy))
        p_rgt = self.image_to_widget((float(self.image.width()), cy))

        guide_pen = QPen(QColor("#818CF8"), 1.5, Qt.PenStyle.DashDotLine)
        painter.setPen(guide_pen)
        painter.drawLine(p_top, p_bot)
        painter.drawLine(p_lft, p_rgt)

        self._render_floating_badge(painter, p_top + QPointF(0, 15), f"Center X: {cx:.0f}px", bg_color=QColor("#312E81"))
        self._render_floating_badge(painter, p_lft + QPointF(35, 0), f"Center Y: {cy:.0f}px", bg_color=QColor("#312E81"))

    def _render_measurement_item(self, painter: QPainter, item: MeasurementItem, is_selected: bool) -> None:
        col = QColor(self.COLOR_SELECTED if is_selected else item.color)
        pen_width = 2.5 if is_selected else 1.8
        pen = QPen(col, pen_width)
        painter.setPen(pen)

        if item.mtype == MeasurementType.DISTANCE:
            if len(item.points) >= 2:
                p1 = self.image_to_widget(item.points[0])
                p2 = self.image_to_widget(item.points[1])
                painter.drawLine(p1, p2)

                # Endpoint markers
                painter.setBrush(QBrush(col))
                painter.drawEllipse(p1, 4, 4)
                painter.drawEllipse(p2, 4, 4)

                if self.show_labels:
                    mid = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
                    dist = item.data.get("distance", 0.0)
                    dx = item.data.get("dx", 0.0)
                    dy = item.data.get("dy", 0.0)
                    txt = f"{dist:.1f} px\nΔX {abs(dx):.0f} | ΔY {abs(dy):.0f}"
                    self._render_floating_badge(painter, mid, txt, bg_color=QColor("#0F172A"))

        elif item.mtype == MeasurementType.HORIZONTAL:
            if len(item.points) >= 2:
                x1, y1 = item.points[0]
                x2, y2 = item.points[1]
                p1 = self.image_to_widget((x1, y1))
                p2 = self.image_to_widget((x2, y1))  # Horizontal lock
                painter.drawLine(p1, p2)

                # Dimension bracket ticks |---|
                painter.drawLine(p1 + QPointF(0, -6), p1 + QPointF(0, 6))
                painter.drawLine(p2 + QPointF(0, -6), p2 + QPointF(0, 6))

                if self.show_labels:
                    mid = QPointF((p1.x() + p2.x()) / 2.0, p1.y())
                    dx = item.data.get("dx", 0.0)
                    self._render_floating_badge(painter, mid, f"H: {abs(dx):.1f} px", bg_color=QColor("#1E3A8A"))

        elif item.mtype == MeasurementType.VERTICAL:
            if len(item.points) >= 2:
                x1, y1 = item.points[0]
                x2, y2 = item.points[1]
                p1 = self.image_to_widget((x1, y1))
                p2 = self.image_to_widget((x1, y2))  # Vertical lock
                painter.drawLine(p1, p2)

                # Dimension bracket ticks
                painter.drawLine(p1 + QPointF(-6, 0), p1 + QPointF(6, 0))
                painter.drawLine(p2 + QPointF(-6, 0), p2 + QPointF(6, 0))

                if self.show_labels:
                    mid = QPointF(p1.x(), (p1.y() + p2.y()) / 2.0)
                    dy = item.data.get("dy", 0.0)
                    self._render_floating_badge(painter, mid, f"V: {abs(dy):.1f} px", bg_color=QColor("#312E81"))

        elif item.mtype == MeasurementType.RECTANGLE:
            if len(item.points) >= 2:
                p1 = self.image_to_widget(item.points[0])
                p2 = self.image_to_widget(item.points[1])
                rect = QRectF(p1, p2).normalized()

                # Shaded fill + border
                fill_col = QColor(col)
                fill_col.setAlpha(30)
                painter.fillRect(rect, fill_col)
                painter.drawRect(rect)

                # Center cross
                cx, cy = rect.center().x(), rect.center().y()
                painter.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
                painter.drawLine(QPointF(cx, cy - 5), QPointF(cx, cy + 5))

                if self.show_labels:
                    w = item.data.get("width", 0.0)
                    h = item.data.get("height", 0.0)
                    area = item.data.get("area", 0.0)
                    txt = f"{w:.0f} × {h:.0f} px\nAlan: {area:,.0f} px²"
                    self._render_floating_badge(painter, rect.center(), txt, bg_color=QColor("#064E3B"))

        elif item.mtype == MeasurementType.ANGLE:
            if len(item.points) >= 3:
                pA = self.image_to_widget(item.points[0])
                pB = self.image_to_widget(item.points[1])  # Vertex
                pC = self.image_to_widget(item.points[2])

                painter.drawLine(pB, pA)
                painter.drawLine(pB, pC)

                # Vertex marker
                painter.setBrush(QBrush(col))
                painter.drawEllipse(pB, 5, 5)

                if self.show_labels:
                    ang = item.data.get("angle_deg", 0.0)
                    self._render_floating_badge(painter, pB + QPointF(0, -18), f"{ang:.1f}°", bg_color=QColor("#4C1D95"))

        elif item.mtype == MeasurementType.POINT:
            if item.points:
                pt = self.image_to_widget(item.points[0])
                painter.setBrush(QBrush(col))
                painter.drawEllipse(pt, 5, 5)

                # Crosshair
                painter.drawLine(pt + QPointF(-10, 0), pt + QPointF(10, 0))
                painter.drawLine(pt + QPointF(0, -10), pt + QPointF(0, 10))

                if self.show_labels:
                    x = item.data.get("x", 0.0)
                    y = item.data.get("y", 0.0)
                    hex_val = item.data.get("hex", "")
                    self._render_floating_badge(painter, pt + QPointF(0, -22), f"X:{x:.0f} Y:{y:.0f} • {hex_val}", bg_color=QColor("#78350F"))

    def _render_drawing_preview(self, painter: QPainter) -> None:
        """Renders live visual feedback while dragging or picking points."""
        preview_col = QColor("#38BDF8")
        pen = QPen(preview_col, 1.8, Qt.PenStyle.DashLine)
        painter.setPen(pen)

        if self.active_tool == MeasurementType.ANGLE:
            for i, pt in enumerate(self._temp_points):
                wpt = self.image_to_widget(pt)
                painter.setBrush(QBrush(preview_col))
                painter.drawEllipse(wpt, 5, 5)
                lbl = "A" if i == 0 else ("B (Köşe)" if i == 1 else "C")
                painter.drawText(wpt + QPointF(8, -8), lbl)

            if len(self._temp_points) == 1:
                p1 = self.image_to_widget(self._temp_points[0])
                p2 = self.image_to_widget(self._current_mouse_img)
                painter.drawLine(p1, p2)
            elif len(self._temp_points) == 2:
                pA = self.image_to_widget(self._temp_points[0])
                pB = self.image_to_widget(self._temp_points[1])
                pC = self.image_to_widget(self._current_mouse_img)
                painter.drawLine(pB, pA)
                painter.drawLine(pB, pC)

        elif len(self._temp_points) >= 2:
            p1 = self.image_to_widget(self._temp_points[0])
            p2 = self.image_to_widget(self._temp_points[1])

            if self.active_tool == MeasurementType.DISTANCE:
                painter.drawLine(p1, p2)
                dist = math.hypot(self._temp_points[1][0] - self._temp_points[0][0], self._temp_points[1][1] - self._temp_points[0][1])
                mid = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
                self._render_floating_badge(painter, mid, f"{dist:.1f} px")

            elif self.active_tool == MeasurementType.HORIZONTAL:
                p2_h = self.image_to_widget((self._temp_points[1][0], self._temp_points[0][1]))
                painter.drawLine(p1, p2_h)
                dx = abs(self._temp_points[1][0] - self._temp_points[0][0])
                mid = QPointF((p1.x() + p2_h.x()) / 2.0, p1.y())
                self._render_floating_badge(painter, mid, f"H: {dx:.1f} px")

            elif self.active_tool == MeasurementType.VERTICAL:
                p2_v = self.image_to_widget((self._temp_points[0][0], self._temp_points[1][1]))
                painter.drawLine(p1, p2_v)
                dy = abs(self._temp_points[1][1] - self._temp_points[0][1])
                mid = QPointF(p1.x(), (p1.y() + p2_v.y()) / 2.0)
                self._render_floating_badge(painter, mid, f"V: {dy:.1f} px")

            elif self.active_tool == MeasurementType.RECTANGLE:
                rect = QRectF(p1, p2).normalized()
                painter.drawRect(rect)
                w = abs(self._temp_points[1][0] - self._temp_points[0][0])
                h = abs(self._temp_points[1][1] - self._temp_points[0][1])
                self._render_floating_badge(painter, rect.center(), f"{w:.0f} × {h:.0f} px")

    def _render_floating_badge(
        self,
        painter: QPainter,
        center_pt: QPointF,
        text: str,
        bg_color: QColor = QColor("#0F172A"),
        text_color: QColor = QColor("#F8FAFC"),
    ) -> None:
        """Draws high-contrast modern pill badge with multi-line support."""
        painter.save()
        font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        painter.setFont(font)
        fm = QFontMetrics(font)

        lines = text.split("\n")
        max_w = max(fm.horizontalAdvance(l) for l in lines)
        total_h = len(lines) * fm.height()

        padding_x = 8.0
        padding_y = 4.0
        box_w = max_w + (padding_x * 2.0)
        box_h = total_h + (padding_y * 2.0)

        box_rect = QRectF(
            center_pt.x() - (box_w / 2.0),
            center_pt.y() - (box_h / 2.0),
            box_w,
            box_h,
        )

        # Background pill
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        bg_col_trans = QColor(bg_color)
        bg_col_trans.setAlpha(225)
        painter.setBrush(QBrush(bg_col_trans))
        painter.drawRoundedRect(box_rect, 6, 6)

        # Text
        painter.setPen(text_color)
        curr_y = box_rect.top() + padding_y + fm.ascent()
        for l in lines:
            line_w = fm.horizontalAdvance(l)
            curr_x = box_rect.left() + (box_w - line_w) / 2.0
            painter.drawText(QPointF(curr_x, curr_y), l)
            curr_y += fm.height()

        painter.restore()

    def export_image_with_overlays(self) -> QImage:
        """Renders the image with all measurement overlays baked into full native resolution."""
        if self.image.isNull():
            return QImage()

        w, h = self.image.width(), self.image.height()
        out_img = QImage(self.image.size(), QImage.Format.Format_ARGB32_Premultiplied)
        out_img.fill(Qt.GlobalColor.transparent)

        painter = QPainter(out_img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.drawImage(0, 0, self.image)

        # Draw overlays at 1:1 scale
        saved_zoom = self.zoom_factor
        saved_pan = self.pan_offset
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0.0, 0.0)

        for item in self.measurements:
            if item.visible:
                self._render_measurement_item(painter, item, is_selected=False)

        self.zoom_factor = saved_zoom
        self.pan_offset = saved_pan

        painter.end()
        return out_img

