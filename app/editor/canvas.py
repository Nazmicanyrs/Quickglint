"""Annotation canvas widget handling vector drawing, text input, and live filter previews."""

from typing import Any, List, Optional
from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeyEvent, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QTextEdit, QWidget

from app.editor.history import AddObjectCommand, HistoryManager
from app.editor.objects import (
    ArrowObject,
    BlurObject,
    CanvasObject,
    EllipseObject,
    HighlighterObject,
    LineObject,
    MagnifierObject,
    PenObject,
    PixelateObject,
    RectangleObject,
    RulerObject,
    TextObject,
)
from app.editor.tools import ToolManager
from app.utils.constants import ToolType
from app.utils.helpers import normalize_rect
from app.utils.logger import logger


class AnnotationCanvas(QWidget):
    """Widget for rendering screenshot base and interactive annotation overlay."""

    drawing_completed = Signal()

    def __init__(
        self,
        base_image: QImage | QPixmap,
        tool_manager: ToolManager,
        history_manager: HistoryManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if isinstance(base_image, QPixmap):
            self.base_image: QImage = base_image.toImage()
        else:
            self.base_image: QImage = base_image

        self.tool_manager = tool_manager
        self.history_manager = history_manager
        self.objects: List[CanvasObject] = []

        # Drawing interaction state
        self._is_drawing = False
        self._start_point: QPoint = QPoint()
        self._current_point: QPoint = QPoint()
        self._active_preview_object: Optional[CanvasObject] = None

        # Interactive Magnifier move/resize state
        self._moving_magnifier: Optional[MagnifierObject] = None
        self._magnifier_drag_mode: Optional[str] = None
        self._magnifier_drag_offset: QPoint = QPoint()
        self._magnifier_initial_rect: QRect = QRect()

        # Inline text editor widget
        self._inline_text_editor: Optional[QTextEdit] = None
        self._text_pos: QPoint = QPoint()

        # Non-destructive live watermark preview state
        self._watermark_preview_settings: Optional[Any] = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(self.base_image.size())

        self.tool_manager.font_size_changed.connect(self._on_font_size_changed)
        self.tool_manager.color_changed.connect(self._on_color_changed)

    def set_base_image(self, image: QImage | QPixmap) -> None:
        """Update base screenshot image."""
        if isinstance(image, QPixmap):
            self.base_image = image.toImage()
        else:
            self.base_image = image
        self.setFixedSize(self.base_image.size())
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw base image, vector objects, and active drawing preview."""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            # 1. Draw base image
            painter.drawImage(0, 0, self.base_image)

            # 2. Draw committed objects
            for obj in self.objects:
                obj.render(painter, self.base_image)

            # 3. Draw active preview object
            if self._active_preview_object is not None:
                self._active_preview_object.render(painter, self.base_image)

            # 4. Draw non-destructive live watermark preview (on-screen only)
            if self._watermark_preview_settings is not None and getattr(self._watermark_preview_settings, "enabled", False):
                from app.services.watermark_service import WatermarkService

                WatermarkService.render_on_painter(
                    painter,
                    QRectF(self.rect()),
                    self._watermark_preview_settings,
                )
        finally:
            painter.end()

    def set_watermark_preview(self, settings: Optional[Any]) -> None:
        """Update non-destructive live watermark preview settings and refresh display."""
        self._watermark_preview_settings = settings
        self.update()

    def add_object(self, obj: CanvasObject) -> None:
        """Add object to canvas through command history."""
        cmd = AddObjectCommand(self.objects, obj)
        self.history_manager.execute_command(cmd)
        self.update()

    def clear_objects(self) -> None:
        """Remove all committed objects from canvas."""
        self.objects.clear()
        self.update()

    def get_annotated_image(self) -> QImage:
        """Render base image plus all annotations to an exportable QImage."""
        result = self.base_image.copy()
        painter = QPainter(result)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            for obj in self.objects:
                obj.render(painter, self.base_image)
        finally:
            painter.end()
        return result

    # Alias for API compatibility
    render_final_image = get_annotated_image

    # --- Mouse Event Handlers ---

    def _hit_test_magnifier(self, pos: QPoint) -> tuple[Optional[MagnifierObject], Optional[str]]:
        """Check if pos hits an existing MagnifierObject's resize edge/corner or interior body."""
        margin = 8
        for obj in reversed(self.objects):
            if not isinstance(obj, MagnifierObject):
                continue
            r = normalize_rect(obj.rect)
            if r.isEmpty():
                continue
            expanded = r.adjusted(-margin, -margin, margin, margin)
            if not expanded.contains(pos):
                continue

            near_left = abs(pos.x() - r.left()) <= margin
            near_right = abs(pos.x() - r.right()) <= margin
            near_top = abs(pos.y() - r.top()) <= margin
            near_bottom = abs(pos.y() - r.bottom()) <= margin

            if near_top and near_left:
                return obj, "tl"
            if near_top and near_right:
                return obj, "tr"
            if near_bottom and near_left:
                return obj, "bl"
            if near_bottom and near_right:
                return obj, "br"
            if near_left:
                return obj, "l"
            if near_right:
                return obj, "r"
            if near_top:
                return obj, "t"
            if near_bottom:
                return obj, "b"
            if r.contains(pos):
                return obj, "move"
        return None, None

    def _clamp_magnifier_rect(self, rect: QRect) -> QRect:
        """Keep a moved magnifier rectangle within the canvas bounds."""
        img_w = self.base_image.width()
        img_h = self.base_image.height()
        w = min(rect.width(), img_w)
        h = min(rect.height(), img_h)
        x = max(0, min(rect.x(), max(0, img_w - w)))
        y = max(0, min(rect.y(), max(0, img_h - h)))
        return QRect(x, y, w, h)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._inline_text_editor is not None:
            self._commit_text()
            return

        pos = event.position().toPoint()
        tool = self.tool_manager.active_tool
        color = self.tool_manager.color
        stroke_width = self.tool_manager.stroke_width

        # Allow grabbing, moving, or resizing an existing Magnifier box with the mouse
        if tool in (ToolType.MAGNIFIER, ToolType.SELECT):
            hit_mag, hit_mode = self._hit_test_magnifier(pos)
            if hit_mag is not None and hit_mode is not None:
                self._moving_magnifier = hit_mag
                self._magnifier_drag_mode = hit_mode
                self._magnifier_initial_rect = normalize_rect(hit_mag.rect)
                self._magnifier_drag_offset = pos - self._magnifier_initial_rect.topLeft()
                self._start_point = pos
                self.update()
                return

        if tool == ToolType.SELECT:
            return

        self._is_drawing = True
        self._start_point = pos
        self._current_point = pos

        if tool == ToolType.PEN:
            self._active_preview_object = PenObject(
                points=[pos],
                color=color,
                stroke_width=stroke_width,
            )
        elif tool == ToolType.HIGHLIGHTER:
            self._active_preview_object = HighlighterObject(
                points=[pos],
                color=color,
                stroke_width=max(14, stroke_width * 4),
            )
        elif tool == ToolType.LINE:
            self._active_preview_object = LineObject(pos, pos, color=color, stroke_width=stroke_width)
        elif tool == ToolType.RULER:
            self._active_preview_object = RulerObject(pos, pos, color=color, stroke_width=max(2, stroke_width))
        elif tool == ToolType.MAGNIFIER:
            self._active_preview_object = MagnifierObject(
                QRect(pos, pos),
                zoom_factor=self.tool_manager.magnifier_zoom,
                color=color,
                stroke_width=max(2, stroke_width),
            )
        elif tool == ToolType.ARROW:
            self._active_preview_object = ArrowObject(pos, pos, color=color, stroke_width=stroke_width)
        elif tool == ToolType.RECTANGLE:
            self._active_preview_object = RectangleObject(QRect(pos, pos), color=color, stroke_width=stroke_width)
        elif tool == ToolType.ELLIPSE:
            self._active_preview_object = EllipseObject(QRect(pos, pos), color=color, stroke_width=stroke_width)
        elif tool == ToolType.BLUR:
            self._active_preview_object = BlurObject(
                QRect(pos, pos),
                radius=self.tool_manager.blur_radius,
                tint_color=self.tool_manager.blur_tint,
                tint_opacity=self.tool_manager.blur_tint_opacity,
            )
        elif tool == ToolType.PIXELATE:
            self._active_preview_object = PixelateObject(
                QRect(pos, pos),
                pixel_size=self.tool_manager.pixel_size,
                tint_color=self.tool_manager.blur_tint,
                tint_opacity=self.tool_manager.blur_tint_opacity,
            )
        elif tool == ToolType.TEXT:
            self._open_text_editor(pos)
            self._is_drawing = False
            return

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        tool = self.tool_manager.active_tool

        if self._moving_magnifier is not None and self._magnifier_drag_mode is not None:
            mode = self._magnifier_drag_mode
            if mode == "move":
                new_tl = pos - self._magnifier_drag_offset
                moved = QRect(new_tl, self._magnifier_initial_rect.size())
                self._moving_magnifier.rect = self._clamp_magnifier_rect(moved)
            else:
                r = QRect(self._magnifier_initial_rect)
                if "l" in mode:
                    r.setLeft(min(pos.x(), r.right() - 24))
                if "r" in mode:
                    r.setRight(max(pos.x(), r.left() + 24))
                if "t" in mode:
                    r.setTop(min(pos.y(), r.bottom() - 24))
                if "b" in mode:
                    r.setBottom(max(pos.y(), r.top() + 24))
                self._moving_magnifier.rect = self._clamp_magnifier_rect(normalize_rect(r))
            self.update()
            return

        if not self._is_drawing or self._active_preview_object is None:
            if tool in (ToolType.MAGNIFIER, ToolType.SELECT):
                _, hit_mode = self._hit_test_magnifier(pos)
                if hit_mode == "move":
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                elif hit_mode in ("tl", "br"):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                elif hit_mode in ("tr", "bl"):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif hit_mode in ("l", "r"):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                elif hit_mode in ("t", "b"):
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                else:
                    self.unsetCursor()
            return

        self._current_point = pos

        if tool == ToolType.PEN and isinstance(self._active_preview_object, PenObject):
            self._active_preview_object.add_point(pos)
        elif tool == ToolType.HIGHLIGHTER and isinstance(self._active_preview_object, HighlighterObject):
            self._active_preview_object.add_point(pos)
        elif tool == ToolType.LINE and isinstance(self._active_preview_object, LineObject):
            self._active_preview_object.end_point = pos
        elif tool == ToolType.RULER and isinstance(self._active_preview_object, RulerObject):
            self._active_preview_object.end_point = pos
        elif tool == ToolType.MAGNIFIER and isinstance(self._active_preview_object, MagnifierObject):
            self._active_preview_object.rect = normalize_rect(QRect(self._start_point, pos))
        elif tool == ToolType.ARROW and isinstance(self._active_preview_object, ArrowObject):
            self._active_preview_object.end_point = pos
        elif tool == ToolType.RECTANGLE and isinstance(self._active_preview_object, RectangleObject):
            self._active_preview_object.rect = normalize_rect(QRect(self._start_point, pos))
        elif tool == ToolType.ELLIPSE and isinstance(self._active_preview_object, EllipseObject):
            self._active_preview_object.rect = normalize_rect(QRect(self._start_point, pos))
        elif tool == ToolType.BLUR and isinstance(self._active_preview_object, BlurObject):
            self._active_preview_object.rect = normalize_rect(QRect(self._start_point, pos))
        elif tool == ToolType.PIXELATE and isinstance(self._active_preview_object, PixelateObject):
            self._active_preview_object.rect = normalize_rect(QRect(self._start_point, pos))

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._moving_magnifier is not None:
            self._moving_magnifier = None
            self._magnifier_drag_mode = None
            self.update()
            return

        if not self._is_drawing:
            return

        self._is_drawing = False

        if self._active_preview_object is not None:
            if isinstance(self._active_preview_object, MagnifierObject):
                norm_r = normalize_rect(self._active_preview_object.rect)
                if norm_r.width() < 12 or norm_r.height() < 12:
                    default_side = 150
                    default_rect = QRect(
                        self._start_point.x() - default_side // 2,
                        self._start_point.y() - default_side // 2,
                        default_side,
                        default_side,
                    )
                    self._active_preview_object.rect = self._clamp_magnifier_rect(default_rect)
            cmd = AddObjectCommand(self.objects, self._active_preview_object)
            self.history_manager.execute_command(cmd)
            self._active_preview_object = None
            self.drawing_completed.emit()

        self.update()

    # --- Text Editing Support ---

    def _open_text_editor(self, pos: QPoint) -> None:
        """Create and focus an inline text editor at pos."""
        self._text_pos = pos
        editor = QTextEdit(self)
        editor.setStyleSheet(
            f"background: transparent; color: {self.tool_manager.color}; "
            f"border: 1px dashed {self.tool_manager.color}; border-radius: 3px; padding: 2px;"
        )
        font = QFont(self.tool_manager.font_family, max(8, self.tool_manager.font_size))
        font.setBold(self.tool_manager.bold)
        editor.setFont(font)
        editor.move(pos)
        editor.resize(220, 80)
        editor.show()
        editor.setFocus()
        editor.installEventFilter(self)
        self._inline_text_editor = editor

    def eventFilter(self, watched, event) -> bool:
        if watched == self._inline_text_editor:
            if event.type() == QEvent.Type.KeyPress:
                key_event: QKeyEvent = event
                if key_event.key() == Qt.Key.Key_Escape:
                    self._cancel_text()
                    return True
                if (key_event.key() == Qt.Key.Key_Return or key_event.key() == Qt.Key.Key_Enter) and not (
                    key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                ):
                    self._commit_text()
                    return True
        return super().eventFilter(watched, event)

    def _commit_text(self) -> None:
        if self._inline_text_editor is None:
            return

        text = self._inline_text_editor.toPlainText().strip()
        if text:
            text_obj = TextObject(
                position=self._text_pos,
                text=text,
                color=self.tool_manager.color,
                font_size=self.tool_manager.font_size,
                font_family=self.tool_manager.font_family,
                bold=self.tool_manager.bold,
            )
            cmd = AddObjectCommand(self.objects, text_obj)
            self.history_manager.execute_command(cmd)

        self._inline_text_editor.deleteLater()
        self._inline_text_editor = None
        self.update()

    def _cancel_text(self) -> None:
        if self._inline_text_editor is not None:
            self._inline_text_editor.deleteLater()
            self._inline_text_editor = None
            self.update()

    def _on_font_size_changed(self, size: int) -> None:
        if self._inline_text_editor is not None:
            font = self._inline_text_editor.font()
            font.setPointSize(max(8, size))
            self._inline_text_editor.setFont(font)

    def _on_color_changed(self, color_hex: str) -> None:
        if self._inline_text_editor is not None:
            self._inline_text_editor.setStyleSheet(
                f"background: transparent; color: {color_hex}; "
                f"border: 1px dashed {color_hex}; border-radius: 3px; padding: 2px;"
            )


