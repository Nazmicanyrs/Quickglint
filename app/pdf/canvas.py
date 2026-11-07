"""Interactive high-precision PDF page canvas with multi-selection, 8-point resize handles, rotation, crop mode, snapping, and rich text editing."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QTextEdit,
    QWidget,
)

from app.pdf.commands import (
    AddObjectCommand,
    BatchCommand,
    CropImageCommand,
    DeleteObjectCommand,
    LayerOrderCommand,
    TextEditCommand,
    TransformObjectCommand,
)
from app.pdf.document import (
    CropRect,
    ObjectType,
    PDFAnnotationObject,
    PDFDocument,
    PDFImageObject,
    PDFLinkObject,
    PDFObject,
    PDFPage,
    PDFShapeObject,
    PDFSignatureObject,
    PDFTextObject,
    ShapeType,
)
from app.pdf.history import PDFHistoryManager
from app.pdf.render_engine import PDFRenderEngine
from app.utils.logger import logger


class HandleType:
    NONE = "none"
    TOP_LEFT = "tl"
    TOP = "t"
    TOP_RIGHT = "tr"
    RIGHT = "r"
    BOTTOM_RIGHT = "br"
    BOTTOM = "b"
    BOTTOM_LEFT = "bl"
    LEFT = "l"
    ROTATION = "rot"


class CanvasMode:
    SELECT = "select"
    PAN = "pan"
    DRAW_SHAPE = "draw_shape"
    DRAW_PEN = "draw_pen"
    DRAW_HIGHLIGHTER = "draw_highlighter"
    ADD_TEXT = "add_text"
    CROP = "crop"


class PDFCanvasWidget(QWidget):
    """Main interactive page canvas rendering vector objects and handling user gestures."""

    selection_changed = Signal(list)  # List[PDFObject]
    page_modified = Signal()
    cursor_position_changed = Signal(float, float)  # (x_pt, y_pt)
    object_double_clicked = Signal(object)  # PDFObject

    HANDLE_SIZE = 8
    ROTATION_HANDLE_OFFSET = 20

    def __init__(self, history_manager: Optional[PDFHistoryManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.history: PDFHistoryManager = history_manager or PDFHistoryManager()
        self.document: Optional[PDFDocument] = None
        self.current_page_index: int = 0

        self.mode: str = CanvasMode.SELECT
        self.active_shape_type: ShapeType = ShapeType.RECTANGLE
        self.active_drawing_color: str = "#EF4444"
        self.active_drawing_width: float = 3.0

        # View and Scaling
        self.zoom_factor: float = 1.0  # 1.0 = 100%
        self.pan_offset = QPointF(0, 0)
        self.show_grid: bool = True
        self.snap_to_grid: bool = True
        self.snap_to_guides: bool = True
        self.grid_spacing_pt: float = 20.0
        self.show_margin_guides: bool = True
        self.show_links_hotspots: bool = True

        # Selection state
        self.selected_objects: List[PDFObject] = []
        self._hovered_handle: str = HandleType.NONE
        self._active_handle: str = HandleType.NONE

        # Dragging / Interaction State
        self._is_dragging: bool = False
        self._drag_start_canvas_pos = QPointF(0, 0)
        self._drag_start_obj_rects: Dict[str, QRectF] = {}
        self._drag_start_obj_rotations: Dict[str, float] = {}

        # Rubber Band Multi-selection
        self._is_rubber_banding: bool = False
        self._rubber_band_rect = QRectF()

        # Freehand stroke drawing
        self._current_stroke_points: List[Tuple[float, float]] = []

        # Snapping indicators
        self._active_snap_lines_x: List[float] = []
        self._active_snap_lines_y: List[float] = []

        # Crop Mode
        self.crop_target_image: Optional[PDFImageObject] = None
        self.crop_aspect_ratio: Optional[float] = None  # None = Free, 1.0, 4/3, 16/9

        # In-place Text Editor
        self._inline_text_editor: Optional[QTextEdit] = None
        self._editing_text_obj: Optional[PDFTextObject] = None

        # Internal Clipboard
        self._clipboard_objects: List[Dict[str, Any]] = []

        self.setStyleSheet("background-color: transparent;")

    @property
    def current_page(self) -> Optional[PDFPage]:
        if self.document and 0 <= self.current_page_index < len(self.document.pages):
            return self.document.pages[self.current_page_index]
        return None

    def set_document(self, doc: PDFDocument, page_index: int = 0) -> None:
        self.document = doc
        self.current_page_index = max(0, min(page_index, len(doc.pages) - 1)) if doc.pages else 0
        self.selected_objects.clear()
        self.selection_changed.emit([])
        self.update_geometry_size()
        self.update()

    def set_page_index(self, index: int) -> None:
        if self.document and 0 <= index < len(self.document.pages):
            self.current_page_index = index
            self.selected_objects.clear()
            self.selection_changed.emit([])
            self.update_geometry_size()
            self.update()

    def set_zoom(self, zoom: float) -> None:
        self.zoom_factor = max(0.15, min(5.0, zoom))
        self.update_geometry_size()
        self.update()

    def update_geometry_size(self) -> None:
        page = self.current_page
        if not page:
            self.setMinimumSize(400, 400)
            return

        w_pt, h_pt = page.get_dimensions_pt()
        padding = 60  # canvas margin
        total_w = int((w_pt * self.zoom_factor) + padding * 2)
        total_h = int((h_pt * self.zoom_factor) + padding * 2)
        self.setMinimumSize(total_w, total_h)
        self.resize(total_w, total_h)

    def get_page_origin(self) -> QPointF:
        """Returns the top-left screen position of the PDF page on canvas."""
        page = self.current_page
        if not page:
            return QPointF(30, 30)
        w_pt, h_pt = page.get_dimensions_pt()
        screen_w = w_pt * self.zoom_factor
        screen_h = h_pt * self.zoom_factor

        # Center in available widget area
        cx = max(30.0, (self.width() - screen_w) / 2.0)
        cy = max(30.0, (self.height() - screen_h) / 2.0)
        return QPointF(cx, cy)

    def screen_to_canvas_pt(self, screen_pos: QPoint | QPointF) -> QPointF:
        """Converts screen pixel coordinates to PDF point coordinates."""
        origin = self.get_page_origin()
        x = (screen_pos.x() - origin.x()) / self.zoom_factor
        y = (screen_pos.y() - origin.y()) / self.zoom_factor
        return QPointF(x, y)

    def canvas_to_screen_pt(self, pt_pos: QPointF) -> QPointF:
        """Converts PDF point coordinates to screen pixel coordinates."""
        origin = self.get_page_origin()
        return QPointF(
            origin.x() + pt_pos.x() * self.zoom_factor,
            origin.y() + pt_pos.y() * self.zoom_factor,
        )

    # --------------------------------------------------------------------------
    # PAINTING & RENDERING
    # --------------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # 1. Fill Workspace Dark Background
        painter.fillRect(self.rect(), QColor("#0B0F19"))

        page = self.current_page
        if not page:
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No PDF Document Loaded")
            painter.end()
            return

        w_pt, h_pt = page.get_dimensions_pt()
        origin = self.get_page_origin()
        page_screen_rect = QRectF(origin.x(), origin.y(), w_pt * self.zoom_factor, h_pt * self.zoom_factor)

        # 2. Draw Soft Drop Shadow for Realistic Paper Sheet
        shadow_color = QColor(0, 0, 0, 90)
        for i in range(8):
            s_rect = page_screen_rect.adjusted(-i, -i, i, i)
            painter.fillRect(s_rect, QColor(0, 0, 0, int(15 / (i + 1))))
        painter.fillRect(page_screen_rect.adjusted(2, 4, 6, 8), shadow_color)

        # 3. Render PDF Page Content scaled via Painter Transform
        painter.save()
        painter.translate(origin.x(), origin.y())
        painter.scale(self.zoom_factor, self.zoom_factor)

        # Draw Grid if enabled
        if self.show_grid:
            self._paint_grid(painter, w_pt, h_pt)

        # Render background & objects
        doc_settings = self.document.settings if self.document else None
        total_p = len(self.document.pages) if self.document else 1
        PDFRenderEngine.render_page(
            painter=painter,
            page=page,
            doc_settings=doc_settings,
            page_index=self.current_page_index + 1,
            total_pages=total_p,
            render_guides=self.show_margin_guides,
            render_links_hotspots=self.show_links_hotspots,
        )

        painter.restore()

        # 3b. Render Active Drawing Stroke (Pen / Highlighter)
        if self._is_dragging and self.mode in (CanvasMode.DRAW_PEN, CanvasMode.DRAW_HIGHLIGHTER) and len(self._current_stroke_points) >= 2:
            painter.save()
            painter.translate(origin.x(), origin.y())
            painter.scale(self.zoom_factor, self.zoom_factor)

            c = QColor(self.active_drawing_color)
            if self.mode == CanvasMode.DRAW_HIGHLIGHTER:
                c.setAlpha(100)
                pen = QPen(c, max(12.0, self.active_drawing_width * 4.0), Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.BevelJoin)
            else:
                pen = QPen(c, self.active_drawing_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)

            path = QPainterPath()
            path.moveTo(self._current_stroke_points[0][0], self._current_stroke_points[0][1])
            for pt in self._current_stroke_points[1:]:
                path.lineTo(pt[0], pt[1])
            painter.drawPath(path)
            painter.restore()

        # 4. Render Active Snapping Guides
        self._paint_snap_lines(painter, origin)

        # 5. Render Selection Box & Transform Handles
        if self.selected_objects:
            self._paint_selection_handles(painter, origin)

        # 6. Render Rubber Band
        if self._is_rubber_banding:
            painter.setPen(QPen(QColor("#38BDF8"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(56, 189, 248, 40)))
            painter.drawRect(self._rubber_band_rect)

        # 7. Render Interactive Crop Overlay if in Crop Mode
        if self.mode == CanvasMode.CROP and self.crop_target_image:
            self._paint_crop_overlay(painter, origin)

        painter.end()

    def _paint_grid(self, painter: QPainter, w_pt: float, h_pt: float) -> None:
        painter.save()
        pen = QPen(QColor(226, 232, 240, 60), 0.5, Qt.PenStyle.DotLine)
        painter.setPen(pen)
        step = self.grid_spacing_pt
        x = step
        while x < w_pt:
            painter.drawLine(QPointF(x, 0), QPointF(x, h_pt))
            x += step
        y = step
        while y < h_pt:
            painter.drawLine(QPointF(0, y), QPointF(w_pt, y))
            y += step
        painter.restore()

    def _paint_snap_lines(self, painter: QPainter, origin: QPointF) -> None:
        painter.save()
        painter.setPen(QPen(QColor("#EC4899"), 1, Qt.PenStyle.DashLine))
        for sx in self._active_snap_lines_x:
            screen_x = origin.x() + sx * self.zoom_factor
            painter.drawLine(int(screen_x), 0, int(screen_x), self.height())
        for sy in self._active_snap_lines_y:
            screen_y = origin.y() + sy * self.zoom_factor
            painter.drawLine(0, int(screen_y), self.width(), int(screen_y))
        painter.restore()

    def _paint_selection_handles(self, painter: QPainter, origin: QPointF) -> None:
        painter.save()
        handles_map = self._get_selection_handles_screen()

        # Bounding box
        if len(self.selected_objects) == 1:
            obj = self.selected_objects[0]
            obj_screen_rect = self._get_object_screen_rect(obj)
            painter.setPen(QPen(QColor("#0088FF"), 1.5, Qt.PenStyle.SolidLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(obj_screen_rect)

            # Rotation line
            if HandleType.ROTATION in handles_map:
                top_center = QPointF(obj_screen_rect.center().x(), obj_screen_rect.top())
                rot_pos = handles_map[HandleType.ROTATION].center()
                painter.setPen(QPen(QColor("#0088FF"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(top_center, rot_pos)
        else:
            # Multi-select composite bounding box
            combo_r = self._get_combined_selection_screen_rect()
            painter.setPen(QPen(QColor("#0088FF"), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(combo_r)

        # Draw handles
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        for h_type, h_rect in handles_map.items():
            if h_type == HandleType.ROTATION:
                painter.setPen(QPen(QColor("#0088FF"), 1.5))
                painter.setBrush(QBrush(QColor("#38BDF8")))
                painter.drawEllipse(h_rect)
            else:
                painter.setPen(QPen(QColor("#0088FF"), 1.5))
                painter.setBrush(QBrush(QColor("#FFFFFF")))
                painter.drawRect(h_rect)

        painter.restore()

    def _paint_crop_overlay(self, painter: QPainter, origin: QPointF) -> None:
        if not self.crop_target_image:
            return
        painter.save()
        img_rect = self._get_object_screen_rect(self.crop_target_image)
        crop = self.crop_target_image.crop

        cx = img_rect.left() + crop.x * img_rect.width()
        cy = img_rect.top() + crop.y * img_rect.height()
        cw = crop.width * img_rect.width()
        ch = crop.height * img_rect.height()
        crop_screen_rect = QRectF(cx, cy, cw, ch)

        # Dim surrounding area
        dim_color = QColor(0, 0, 0, 140)
        painter.fillRect(QRectF(img_rect.left(), img_rect.top(), img_rect.width(), cy - img_rect.top()), dim_color)
        painter.fillRect(QRectF(img_rect.left(), cy + ch, img_rect.width(), img_rect.bottom() - (cy + ch)), dim_color)
        painter.fillRect(QRectF(img_rect.left(), cy, cx - img_rect.left(), ch), dim_color)
        painter.fillRect(QRectF(cx + cw, cy, img_rect.right() - (cx + cw), ch), dim_color)

        # Crop border & 3x3 rule-of-thirds grid
        painter.setPen(QPen(QColor("#FACC15"), 2))
        painter.drawRect(crop_screen_rect)

        painter.setPen(QPen(QColor(250, 204, 21, 100), 1, Qt.PenStyle.DotLine))
        painter.drawLine(QPointF(cx + cw / 3.0, cy), QPointF(cx + cw / 3.0, cy + ch))
        painter.drawLine(QPointF(cx + 2 * cw / 3.0, cy), QPointF(cx + 2 * cw / 3.0, cy + ch))
        painter.drawLine(QPointF(cx, cy + ch / 3.0), QPointF(cx + cw, cy + ch / 3.0))
        painter.drawLine(QPointF(cx, cy + 2 * ch / 3.0), QPointF(cx + cw, cy + 2 * ch / 3.0))

        # Crop Corner handles
        painter.setBrush(QBrush(QColor("#FACC15")))
        painter.setPen(Qt.PenStyle.NoPen)
        hs = 10
        painter.drawRect(QRectF(cx - hs / 2, cy - hs / 2, hs, hs))
        painter.drawRect(QRectF(cx + cw - hs / 2, cy - hs / 2, hs, hs))
        painter.drawRect(QRectF(cx + cw - hs / 2, cy + ch - hs / 2, hs, hs))
        painter.drawRect(QRectF(cx - hs / 2, cy + ch - hs / 2, hs, hs))

        painter.restore()

    # --------------------------------------------------------------------------
    # HIT TESTING & HANDLES
    # --------------------------------------------------------------------------

    def _get_object_screen_rect(self, obj: PDFObject) -> QRectF:
        origin = self.get_page_origin()
        return QRectF(
            origin.x() + obj.x * self.zoom_factor,
            origin.y() + obj.y * self.zoom_factor,
            obj.width * self.zoom_factor,
            obj.height * self.zoom_factor,
        )

    def _get_combined_selection_screen_rect(self) -> QRectF:
        if not self.selected_objects:
            return QRectF()
        rects = [self._get_object_screen_rect(o) for o in self.selected_objects]
        min_x = min(r.left() for r in rects)
        min_y = min(r.top() for r in rects)
        max_x = max(r.right() for r in rects)
        max_y = max(r.bottom() for r in rects)
        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def _get_selection_handles_screen(self) -> Dict[str, QRectF]:
        if not self.selected_objects:
            return {}

        combo_r = self._get_combined_selection_screen_rect()
        hs = self.HANDLE_SIZE
        half = hs / 2.0

        handles = {
            HandleType.TOP_LEFT: QRectF(combo_r.left() - half, combo_r.top() - half, hs, hs),
            HandleType.TOP: QRectF(combo_r.center().x() - half, combo_r.top() - half, hs, hs),
            HandleType.TOP_RIGHT: QRectF(combo_r.right() - half, combo_r.top() - half, hs, hs),
            HandleType.RIGHT: QRectF(combo_r.right() - half, combo_r.center().y() - half, hs, hs),
            HandleType.BOTTOM_RIGHT: QRectF(combo_r.right() - half, combo_r.bottom() - half, hs, hs),
            HandleType.BOTTOM: QRectF(combo_r.center().x() - half, combo_r.bottom() - half, hs, hs),
            HandleType.BOTTOM_LEFT: QRectF(combo_r.left() - half, combo_r.bottom() - half, hs, hs),
            HandleType.LEFT: QRectF(combo_r.left() - half, combo_r.center().y() - half, hs, hs),
        }

        # Single object rotation handle
        if len(self.selected_objects) == 1:
            rot_y = combo_r.top() - self.ROTATION_HANDLE_OFFSET
            handles[HandleType.ROTATION] = QRectF(combo_r.center().x() - half, rot_y - half, hs, hs)

        return handles

    def _hit_test_handles(self, screen_pos: QPoint | QPointF) -> str:
        handles = self._get_selection_handles_screen()
        for h_type, h_rect in handles.items():
            if h_rect.adjusted(-3, -3, 3, 3).contains(screen_pos):
                return h_type
        return HandleType.NONE

    def _hit_test_object(self, pt_pos: QPointF) -> Optional[PDFObject]:
        page = self.current_page
        if not page:
            return None

        # Check top-to-bottom in reverse z-index order
        for obj in reversed(sorted(page.objects, key=lambda x: x.z_index)):
            if obj.rect.contains(pt_pos):
                return obj
        return None

    # --------------------------------------------------------------------------
    # MOUSE EVENTS
    # --------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        canvas_pos = self.screen_to_canvas_pt(event.position())
        self.cursor_position_changed.emit(canvas_pos.x(), canvas_pos.y())

        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint(), canvas_pos)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # 1. Mode: DRAW_SHAPE
        if self.mode == CanvasMode.DRAW_SHAPE:
            self._start_drawing_shape(canvas_pos)
            return

        # 2. Mode: DRAW_PEN or DRAW_HIGHLIGHTER
        if self.mode in (CanvasMode.DRAW_PEN, CanvasMode.DRAW_HIGHLIGHTER):
            self._current_stroke_points = [(canvas_pos.x(), canvas_pos.y())]
            self._is_dragging = True
            return

        # 3. Mode: ADD_TEXT
        if self.mode == CanvasMode.ADD_TEXT:
            self._create_new_text_at(canvas_pos)
            self.mode = CanvasMode.SELECT
            return

        # 4. Mode: CROP
        if self.mode == CanvasMode.CROP:
            # Handle crop handle drag
            return

        # 5. Mode: SELECT
        handle = self._hit_test_handles(event.position())
        if handle != HandleType.NONE:
            self._active_handle = handle
            self._is_dragging = True
            self._drag_start_canvas_pos = canvas_pos
            self._record_drag_starts()
            return

        # Hit test object
        clicked_obj = self._hit_test_object(canvas_pos)
        is_multi_key = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))

        if clicked_obj:
            if is_multi_key:
                if clicked_obj in self.selected_objects:
                    self.selected_objects.remove(clicked_obj)
                else:
                    self.selected_objects.append(clicked_obj)
            else:
                if clicked_obj not in self.selected_objects:
                    self.selected_objects = [clicked_obj]

            self.selection_changed.emit(self.selected_objects)
            self._is_dragging = True
            self._active_handle = HandleType.NONE
            self._drag_start_canvas_pos = canvas_pos
            self._record_drag_starts()
            self.update()
        else:
            if not is_multi_key:
                self.selected_objects.clear()
                self.selection_changed.emit([])

            # Start Rubber Banding
            self._is_rubber_banding = True
            self._rubber_band_rect = QRectF(event.position(), QSizeF(0, 0))
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        canvas_pos = self.screen_to_canvas_pt(event.position())
        self.cursor_position_changed.emit(canvas_pos.x(), canvas_pos.y())

        # Update cursor based on hover
        if not self._is_dragging and not self._is_rubber_banding:
            handle = self._hit_test_handles(event.position())
            self._update_cursor(handle, canvas_pos)

        # 1. Stroke drawing
        if self._is_dragging and self.mode in (CanvasMode.DRAW_PEN, CanvasMode.DRAW_HIGHLIGHTER):
            self._current_stroke_points.append((canvas_pos.x(), canvas_pos.y()))
            self.update()
            return

        # 2. Rubber banding
        if self._is_rubber_banding:
            origin_pos = self._rubber_band_rect.topLeft()
            self._rubber_band_rect = QRectF(origin_pos, event.position()).normalized()
            self._update_rubber_band_selection()
            self.update()
            return

        # 3. Dragging / Resizing / Rotating Objects
        if self._is_dragging and self.selected_objects:
            dx = canvas_pos.x() - self._drag_start_canvas_pos.x()
            dy = canvas_pos.y() - self._drag_start_canvas_pos.y()

            if self._active_handle == HandleType.NONE:
                # Moving objects
                self._move_selected_objects(dx, dy)
            elif self._active_handle == HandleType.ROTATION:
                # Rotating
                self._rotate_selected_objects(canvas_pos)
            else:
                # Resizing
                shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                self._resize_selected_objects(self._active_handle, dx, dy, shift_held)

            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # 1. Pen / Highlighter Stroke Finished
        if self.mode in (CanvasMode.DRAW_PEN, CanvasMode.DRAW_HIGHLIGHTER) and self._current_stroke_points:
            page = self.current_page
            if page and len(self._current_stroke_points) >= 2:
                # Calculate bounding rect of stroke
                xs = [p[0] for p in self._current_stroke_points]
                ys = [p[1] for p in self._current_stroke_points]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                tool_type = "pen" if self.mode == CanvasMode.DRAW_PEN else "highlighter"
                ann_obj = PDFAnnotationObject(
                    tool=tool_type,
                    color=self.active_drawing_color,
                    stroke_width_pt=self.active_drawing_width,
                    points=list(self._current_stroke_points),
                    x_pt=min_x,
                    y_pt=min_y,
                    width_pt=max(1.0, max_x - min_x),
                    height_pt=max(1.0, max_y - min_y),
                )
                cmd = AddObjectCommand(page, ann_obj)
                self.history.push(cmd)
                self.page_modified.emit()

            self._current_stroke_points.clear()
            self._is_dragging = False
            self.update()
            return

        # 2. Rubber Band Finished
        if self._is_rubber_banding:
            self._is_rubber_banding = False
            self._rubber_band_rect = QRectF()
            self.update()
            return

        # 3. Drag / Transform Finished -> Commit Command to History
        if self._is_dragging and self.selected_objects:
            self._commit_drag_command()
            self._is_dragging = False
            self._active_handle = HandleType.NONE
            self._active_snap_lines_x.clear()
            self._active_snap_lines_y.clear()
            self.page_modified.emit()
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        canvas_pos = self.screen_to_canvas_pt(event.position())
        obj = self._hit_test_object(canvas_pos)
        if obj:
            self.object_double_clicked.emit(obj)
            if isinstance(obj, PDFTextObject):
                self._start_inline_text_edit(obj)
            elif isinstance(obj, PDFImageObject):
                self.start_crop_mode(obj)

    # --------------------------------------------------------------------------
    # OBJECT TRANSFORMS & SNAPPING LOGIC
    # --------------------------------------------------------------------------

    def _record_drag_starts(self) -> None:
        self._drag_start_obj_rects.clear()
        self._drag_start_obj_rotations.clear()
        for obj in self.selected_objects:
            self._drag_start_obj_rects[obj.id] = QRectF(obj.x, obj.y, obj.width, obj.height)
            self._drag_start_obj_rotations[obj.id] = obj.rotation

    def _move_selected_objects(self, dx: float, dy: float) -> None:
        page = self.current_page
        if not page:
            return

        self._active_snap_lines_x.clear()
        self._active_snap_lines_y.clear()

        # Snapping for first object
        if self.snap_to_guides and self.selected_objects:
            primary = self.selected_objects[0]
            start_r = self._drag_start_obj_rects[primary.id]
            target_x = start_r.x() + dx
            target_y = start_r.y() + dy

            # Snap to page center & margins
            p_rect = page.get_printable_rect_pt()
            snap_dist = 6.0

            # Center X
            if abs((target_x + primary.width / 2.0) - page.width_pt / 2.0) < snap_dist:
                dx = (page.width_pt / 2.0 - primary.width / 2.0) - start_r.x()
                self._active_snap_lines_x.append(page.width_pt / 2.0)
            # Margin Left
            elif abs(target_x - p_rect.left()) < snap_dist:
                dx = p_rect.left() - start_r.x()
                self._active_snap_lines_x.append(p_rect.left())
            # Margin Right
            elif abs((target_x + primary.width) - p_rect.right()) < snap_dist:
                dx = (p_rect.right() - primary.width) - start_r.x()
                self._active_snap_lines_x.append(p_rect.right())

            # Center Y
            if abs((target_y + primary.height / 2.0) - page.height_pt / 2.0) < snap_dist:
                dy = (page.height_pt / 2.0 - primary.height / 2.0) - start_r.y()
                self._active_snap_lines_y.append(page.height_pt / 2.0)
            # Margin Top
            elif abs(target_y - p_rect.top()) < snap_dist:
                dy = p_rect.top() - start_r.y()
                self._active_snap_lines_y.append(p_rect.top())
            # Margin Bottom
            elif abs((target_y + primary.height) - p_rect.bottom()) < snap_dist:
                dy = (p_rect.bottom() - primary.height) - start_r.y()
                self._active_snap_lines_y.append(p_rect.bottom())

        for obj in self.selected_objects:
            if not obj.locked:
                orig_r = self._drag_start_obj_rects[obj.id]
                obj.x = orig_r.x() + dx
                obj.y = orig_r.y() + dy

    def _resize_selected_objects(self, handle: str, dx: float, dy: float, shift_held: bool) -> None:
        for obj in self.selected_objects:
            if obj.locked:
                continue
            orig_r = self._drag_start_obj_rects[obj.id]
            x, y, w, h = orig_r.x(), orig_r.y(), orig_r.width(), orig_r.height()
            aspect = w / max(1.0, h)
            lock_ratio = shift_held or getattr(obj, "lock_aspect_ratio", False)

            if handle == HandleType.RIGHT:
                w = max(10.0, orig_r.width() + dx)
                if lock_ratio:
                    h = w / aspect
            elif handle == HandleType.BOTTOM:
                h = max(10.0, orig_r.height() + dy)
                if lock_ratio:
                    w = h * aspect
            elif handle == HandleType.BOTTOM_RIGHT:
                w = max(10.0, orig_r.width() + dx)
                h = max(10.0, orig_r.height() + dy)
                if lock_ratio:
                    h = w / aspect
            elif handle == HandleType.LEFT:
                w = max(10.0, orig_r.width() - dx)
                x = orig_r.right() - w
                if lock_ratio:
                    h = w / aspect
            elif handle == HandleType.TOP:
                h = max(10.0, orig_r.height() - dy)
                y = orig_r.bottom() - h
                if lock_ratio:
                    w = h * aspect
            elif handle == HandleType.TOP_LEFT:
                w = max(10.0, orig_r.width() - dx)
                h = max(10.0, orig_r.height() - dy)
                if lock_ratio:
                    h = w / aspect
                x = orig_r.right() - w
                y = orig_r.bottom() - h
            elif handle == HandleType.TOP_RIGHT:
                w = max(10.0, orig_r.width() + dx)
                h = max(10.0, orig_r.height() - dy)
                if lock_ratio:
                    h = w / aspect
                y = orig_r.bottom() - h
            elif handle == HandleType.BOTTOM_LEFT:
                w = max(10.0, orig_r.width() - dx)
                h = max(10.0, orig_r.height() + dy)
                if lock_ratio:
                    h = w / aspect
                x = orig_r.right() - w

            obj.x = x
            obj.y = y
            obj.width = w
            obj.height = h

    def _rotate_selected_objects(self, canvas_pos: QPointF) -> None:
        if len(self.selected_objects) == 1:
            obj = self.selected_objects[0]
            if obj.locked:
                return
            center = QPointF(obj.x + obj.width / 2.0, obj.y + obj.height / 2.0)
            angle = math.degrees(math.atan2(canvas_pos.y() - center.y(), canvas_pos.x() - center.x()))
            # Snap to 0, 45, 90, 180, 270 if close
            angle = (angle + 90) % 360
            for snap_ang in (0, 45, 90, 135, 180, 225, 270, 315):
                if abs(angle - snap_ang) < 4.0:
                    angle = snap_ang
                    break
            obj.rotation = angle

    def _commit_drag_command(self) -> None:
        page = self.current_page
        if not page or not self.selected_objects:
            return

        commands = []
        for obj in self.selected_objects:
            old_r = self._drag_start_obj_rects.get(obj.id)
            old_rot = self._drag_start_obj_rotations.get(obj.id, 0.0)
            new_r = QRectF(obj.x, obj.y, obj.width, obj.height)
            new_rot = obj.rotation

            if old_r and (old_r != new_r or abs(old_rot - new_rot) > 1e-3):
                cmd = TransformObjectCommand(
                    page=page,
                    obj=obj,
                    old_rect=old_r,
                    new_rect=new_r,
                    old_rotation=old_rot,
                    new_rotation=new_rot,
                )
                commands.append(cmd)

        if len(commands) == 1:
            self.history.record_without_execute(commands[0])
        elif len(commands) > 1:
            batch = BatchCommand(commands, desc="Transform Multi Objects")
            self.history.record_without_execute(batch)

    def _update_rubber_band_selection(self) -> None:
        page = self.current_page
        if not page:
            return
        p1 = self.screen_to_canvas_pt(self._rubber_band_rect.topLeft())
        p2 = self.screen_to_canvas_pt(self._rubber_band_rect.bottomRight())
        canvas_sel_r = QRectF(p1, p2).normalized()

        self.selected_objects = [o for o in page.objects if canvas_sel_r.intersects(o.rect)]
        self.selection_changed.emit(self.selected_objects)

    def _update_cursor(self, handle: str, canvas_pos: QPointF) -> None:
        if self.mode == CanvasMode.PAN:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif self.mode in (CanvasMode.DRAW_PEN, CanvasMode.DRAW_HIGHLIGHTER, CanvasMode.DRAW_SHAPE):
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self.mode == CanvasMode.ADD_TEXT:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        elif handle in (HandleType.TOP_LEFT, HandleType.BOTTOM_RIGHT):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif handle in (HandleType.TOP_RIGHT, HandleType.BOTTOM_LEFT):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif handle in (HandleType.TOP, HandleType.BOTTOM):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif handle in (HandleType.LEFT, HandleType.RIGHT):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif handle == HandleType.ROTATION:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            obj = self._hit_test_object(canvas_pos)
            if obj and obj in self.selected_objects:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            elif obj:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    # --------------------------------------------------------------------------
    # INLINE TEXT EDITING
    # --------------------------------------------------------------------------

    def _start_inline_text_edit(self, text_obj: PDFTextObject) -> None:
        if self._inline_text_editor:
            self._finish_inline_text_edit()

        self._editing_text_obj = text_obj
        screen_r = self._get_object_screen_rect(text_obj)

        editor = QTextEdit(self)
        editor.setGeometry(screen_r.toRect())
        editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: #1E293B;
                color: {text_obj.font_color};
                border: 2px solid #38BDF8;
                border-radius: 4px;
                font-family: '{text_obj.font_family}';
                font-size: {int(text_obj.font_size_pt * self.zoom_factor)}pt;
            }}
        """)
        editor.setPlainText(text_obj.text)
        editor.selectAll()
        editor.show()
        editor.setFocus()
        self._inline_text_editor = editor

    def _finish_inline_text_edit(self) -> None:
        if not self._inline_text_editor or not self._editing_text_obj:
            return

        new_text = self._inline_text_editor.toPlainText().strip() or "Text"
        old_text = self._editing_text_obj.text
        page = self.current_page

        if page and new_text != old_text:
            cmd = TextEditCommand(
                page=page,
                text_obj=self._editing_text_obj,
                old_text=old_text,
                new_text=new_text,
                old_html=self._editing_text_obj.html,
                new_html="",
            )
            self.history.push(cmd)
            self.page_modified.emit()

        self._inline_text_editor.deleteLater()
        self._inline_text_editor = None
        self._editing_text_obj = None
        self.update()

    def _create_new_text_at(self, pos: QPointF) -> None:
        page = self.current_page
        if not page:
            return
        t_obj = PDFTextObject(
            text="Edit Text",
            x_pt=pos.x(),
            y_pt=pos.y(),
            width_pt=180.0,
            height_pt=40.0,
            font_size_pt=14.0,
            font_color="#0F172A",
        )
        cmd = AddObjectCommand(page, t_obj)
        self.history.push(cmd)
        self.selected_objects = [t_obj]
        self.selection_changed.emit([t_obj])
        self.page_modified.emit()
        self._start_inline_text_edit(t_obj)

    # --------------------------------------------------------------------------
    # CROP MODE
    # --------------------------------------------------------------------------

    def start_crop_mode(self, img_obj: PDFImageObject) -> None:
        self.mode = CanvasMode.CROP
        self.crop_target_image = img_obj
        self.selected_objects = [img_obj]
        self.selection_changed.emit([img_obj])
        self.update()

    def apply_crop(self) -> None:
        if not self.crop_target_image or not self.current_page:
            return
        # Crop is updated non-destructively in image object
        self.mode = CanvasMode.SELECT
        self.crop_target_image = None
        self.page_modified.emit()
        self.update()

    def cancel_crop(self) -> None:
        self.mode = CanvasMode.SELECT
        self.crop_target_image = None
        self.update()

    # --------------------------------------------------------------------------
    # CONTEXT MENU & SHORTCUTS
    # --------------------------------------------------------------------------

    def _show_context_menu(self, global_pos: QPoint, canvas_pos: QPointF) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2563EB;
            }
        """)

        if self.selected_objects:
            act_cut = menu.addAction("✂️ Cut (Ctrl+X)")
            act_copy = menu.addAction("📋 Copy (Ctrl+C)")
            act_dup = menu.addAction("📑 Duplicate (Ctrl+D)")
            act_del = menu.addAction("🗑️ Delete (Delete)")
            menu.addSeparator()

            act_front = menu.addAction("⬆️ Bring to Front")
            act_back = menu.addAction("⬇️ Send to Back")
            menu.addSeparator()

            is_locked = any(o.locked for o in self.selected_objects)
            act_lock = menu.addAction("🔓 Unlock" if is_locked else "🔒 Lock Object")

            if len(self.selected_objects) == 1 and isinstance(self.selected_objects[0], PDFImageObject):
                menu.addSeparator()
                act_crop = menu.addAction("✂️ Crop Image")
                act_crop.triggered.connect(lambda: self.start_crop_mode(self.selected_objects[0]))

            act_cut.triggered.connect(self.cut_selected)
            act_copy.triggered.connect(self.copy_selected)
            act_dup.triggered.connect(self.duplicate_selected)
            act_del.triggered.connect(self.delete_selected)
            act_front.triggered.connect(self.bring_to_front)
            act_back.triggered.connect(self.send_to_back)
            act_lock.triggered.connect(self.toggle_lock_selected)
        else:
            act_paste = menu.addAction("📋 Paste (Ctrl+V)")
            act_paste.setEnabled(len(self._clipboard_objects) > 0)
            act_paste.triggered.connect(lambda: self.paste_at(canvas_pos))

            menu.addSeparator()
            act_add_text = menu.addAction("🔤 Add Text")
            act_add_text.triggered.connect(lambda: self._create_new_text_at(canvas_pos))

        menu.exec(global_pos)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self.delete_selected()
        elif event.matches(QKeySequence.StandardKey.Undo):
            self.history.undo()
            self.update()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self.history.redo()
            self.update()
        elif event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected()
        elif event.matches(QKeySequence.StandardKey.Cut):
            self.cut_selected()
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste()
        elif event.matches(QKeySequence.StandardKey.SelectAll):
            if self.current_page:
                self.selected_objects = list(self.current_page.objects)
                self.selection_changed.emit(self.selected_objects)
                self.update()
        elif event.key() == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.duplicate_selected()
        else:
            super().keyPressEvent(event)

    # --------------------------------------------------------------------------
    # CLIPBOARD & COMMAND ACTIONS
    # --------------------------------------------------------------------------

    def copy_selected(self) -> None:
        self._clipboard_objects = [o.to_dict() for o in self.selected_objects]

    def cut_selected(self) -> None:
        self.copy_selected()
        self.delete_selected()

    def paste(self) -> None:
        self.paste_at(QPointF(50, 50))

    def paste_at(self, pos: QPointF) -> None:
        page = self.current_page
        if not page or not self._clipboard_objects:
            return

        commands = []
        new_objs = []
        for i, d in enumerate(self._clipboard_objects):
            clone_d = dict(d)
            clone_d["id"] = None
            obj = PDFObject.from_dict(clone_d)
            obj.x = pos.x() + (i * 15)
            obj.y = pos.y() + (i * 15)
            new_objs.append(obj)
            commands.append(AddObjectCommand(page, obj))

        if len(commands) == 1:
            self.history.push(commands[0])
        elif len(commands) > 1:
            self.history.push(BatchCommand(commands, desc="Paste Objects"))

        self.selected_objects = new_objs
        self.selection_changed.emit(new_objs)
        self.page_modified.emit()
        self.update()

    def duplicate_selected(self) -> None:
        if not self.selected_objects or not self.current_page:
            return
        self.copy_selected()
        self.paste_at(QPointF(self.selected_objects[0].x + 20, self.selected_objects[0].y + 20))

    def delete_selected(self) -> None:
        page = self.current_page
        if not page or not self.selected_objects:
            return
        cmd = DeleteObjectCommand(page, self.selected_objects)
        self.history.push(cmd)
        self.selected_objects.clear()
        self.selection_changed.emit([])
        self.page_modified.emit()
        self.update()

    def bring_to_front(self) -> None:
        page = self.current_page
        if not page or not self.selected_objects:
            return
        old_order = list(page.objects)
        for o in self.selected_objects:
            page.bring_to_front(o)
        cmd = LayerOrderCommand(page, old_order, list(page.objects))
        self.history.record_without_execute(cmd)
        self.page_modified.emit()
        self.update()

    def send_to_back(self) -> None:
        page = self.current_page
        if not page or not self.selected_objects:
            return
        old_order = list(page.objects)
        for o in self.selected_objects:
            page.send_to_back(o)
        cmd = LayerOrderCommand(page, old_order, list(page.objects))
        self.history.record_without_execute(cmd)
        self.page_modified.emit()
        self.update()

    def toggle_lock_selected(self) -> None:
        if not self.selected_objects:
            return
        target_locked = not any(o.locked for o in self.selected_objects)
        for o in self.selected_objects:
            o.locked = target_locked
        self.page_modified.emit()
        self.update()

