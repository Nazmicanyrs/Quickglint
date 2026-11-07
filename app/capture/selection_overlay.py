"""Interactive multi-monitor selection overlay with Smart Privacy, Scrolling, and GIF recording."""

from enum import Enum, auto
import sys
import time
from typing import List, Optional
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QLineEdit, QMessageBox, QWidget

from app.editor.canvas import AnnotationCanvas
from app.editor.history import AddObjectCommand, HistoryManager
from app.editor.objects import BlurObject, PixelateObject, RectangleObject
from app.editor.tools import ToolManager
from app.privacy.detection_result import DetectionResult, PrivacyAction
from app.privacy.privacy_dialog import PrivacyResultDialog
from app.qr.qr_panel import QRNotificationPanel
from app.qr.qr_result import QRResult
from app.qr.qr_service import QRService
from app.services.clipboard_service import ClipboardService
from app.services.storage_service import StorageService
from app.ui.toolbar import FloatingToolbar
from app.utils.constants import (
    DEFAULT_JPEG_QUALITY,
    DIM_BACKGROUND_COLOR,
    DIM_BACKGROUND_OPACITY,
    HANDLE_COLOR,
    HANDLE_SIZE,
    SELECTION_BORDER_COLOR,
    ToolType,
)
from app.utils.helpers import normalize_rect
from app.utils.i18n import tr
from app.utils.logger import logger
from config.config_manager import ConfigManager


from app.window.detector import BrowserWindowDetector
from app.window.models import BrowserWindowInfo


class HandlePosition(Enum):
    """8 resize handles plus center move."""
    NONE = auto()
    TOP_LEFT = auto()
    TOP_CENTER = auto()
    TOP_RIGHT = auto()
    RIGHT_CENTER = auto()
    BOTTOM_RIGHT = auto()
    BOTTOM_CENTER = auto()
    BOTTOM_LEFT = auto()
    LEFT_CENTER = auto()
    INSIDE = auto()


class SelectionOverlay(QWidget):
    """Full-screen interactive overlay for region selection, drawing, and capture."""

    capture_copied = Signal()
    capture_saved = Signal(str)
    capture_cancelled = Signal()
    stitched_capture_ready = Signal(QImage)
    session_image_captured = Signal(QImage)
    new_session_from_image = Signal(QImage)
    open_session_requested = Signal()

    def __init__(
        self,
        full_desktop_pixmap: QPixmap,
        virtual_geometry: QRect,
        tool_manager: ToolManager,
        history_manager: HistoryManager,
        config_manager: ConfigManager,
        default_save_dir: str = "",
        default_format: str = "PNG",
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        session_capture_mode: bool = False,
        smart_window_mode: bool = False,
        initial_window_title: str = "",
        initial_app_name: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.full_desktop_pixmap = full_desktop_pixmap
        self.virtual_geometry = virtual_geometry
        self.tool_manager = tool_manager
        self.history_manager = history_manager
        self.config_manager = config_manager
        self.default_save_dir = default_save_dir
        self.default_format = default_format
        self.jpeg_quality = jpeg_quality
        self.session_capture_mode = session_capture_mode
        self.smart_window_mode = smart_window_mode

        from app.services.naming_service import CaptureMetadata

        self.capture_metadata = CaptureMetadata(
            window_title=initial_window_title,
            app_name=initial_app_name,
            mode="pencere" if smart_window_mode else "bolge",
        )

        self.selected_rect = QRect()
        self._start_pos = QPoint()
        self._active_handle = HandlePosition.NONE
        self._drag_start_rect = QRect()
        self._is_selecting = False
        self._has_selection = False

        # Smart Window State
        self._hovered_browser: Optional[BrowserWindowInfo] = None
        self._is_capturing: bool = False

        # Reset active tool to SELECT on every new capture
        self.tool_manager.active_tool = ToolType.SELECT

        # Eyedropper state
        self._is_eyedropping = False
        self._eyedropper_pos = QPoint()
        self._eyedropper_color = ""

        # Embedded Annotation Canvas
        self.canvas: Optional[AnnotationCanvas] = None

        # QR Code Detection State
        self._detected_qr_results: List[QRResult] = []
        self._qr_panel: Optional[QRNotificationPanel] = None
        self._highlighted_qr: Optional[QRResult] = None

        # Floating Toolbar
        self.toolbar = FloatingToolbar(self.tool_manager, self.history_manager, self)
        self.toolbar.hide()
        self._connect_toolbar()

        # Window setup across all screens
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setGeometry(virtual_geometry)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _connect_toolbar(self) -> None:
        self.tool_manager.tool_changed.connect(self._on_tool_changed)
        self.toolbar.copy_requested.connect(self.copy_to_clipboard)
        self.toolbar.save_requested.connect(self.save_to_file)
        self.toolbar.cancel_requested.connect(self.cancel_capture)
        self.toolbar.undo_requested.connect(self._on_undo)
        self.toolbar.redo_requested.connect(self._on_redo)
        self.toolbar.eyedropper_requested.connect(self._start_eyedropper)

        # Advanced features
        self.toolbar.new_session_requested.connect(self._on_new_session)
        self.toolbar.add_to_session_requested.connect(self._on_add_to_session)
        self.toolbar.open_session_requested.connect(self._on_open_session)
        self.toolbar.extract_text_requested.connect(self.extract_text)
        self.toolbar.privacy_requested.connect(self.open_smart_privacy)
        self.toolbar.scrolling_requested.connect(self.start_scrolling_capture)
        self.toolbar.record_gif_requested.connect(self.start_gif_recording)
        self.toolbar.save_to_vault_requested.connect(self._on_save_to_vault)
        self.toolbar.export_pdf_requested.connect(self._on_export_pdf)
        self.toolbar.optimize_requested.connect(self._on_optimize_image)
        self.toolbar.upload_requested.connect(self._on_upload_share)
        self.toolbar.open_share_history_requested.connect(self._on_open_share_history)
        self.toolbar.measure_requested.connect(self._on_measure_studio)
        self.toolbar.favorite_toggled.connect(self._on_toggle_favorite)
        self.toolbar.open_favorites_gallery_requested.connect(self._on_open_favorites_gallery)
        self.toolbar.qr_scan_requested.connect(lambda: self.scan_qr_codes(force_show=True))
        self.toolbar.panorama_requested.connect(self.open_panorama_capture)
        self.toolbar.watermark_toggled.connect(self._on_watermark_toggled)
        self.toolbar.info_banner_toggled.connect(self._on_info_banner_toggled)
        self.toolbar.set_output_toggles(
            bool(self.config_manager.get("watermark", "enabled", False)),
            bool(self.config_manager.get("info_banner", "enabled", False)),
        )

        self._last_saved_path: Optional[str] = None

    def _start_eyedropper(self) -> None:
        self._is_eyedropping = True
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def _on_tool_changed(self, tool: ToolType) -> None:
        if self.canvas is not None:
            self.canvas.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                tool == ToolType.SELECT,
            )
        if tool == ToolType.SELECT:
            self.setCursor(Qt.CursorShape.SizeAllCursor if self._has_selection else Qt.CursorShape.CrossCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def _on_undo(self) -> None:
        if self.history_manager.undo():
            if self.canvas:
                self.canvas.update()

    def _on_redo(self) -> None:
        if self.history_manager.redo():
            if self.canvas:
                self.canvas.update()

    def _get_handles_map(self) -> dict[HandlePosition, QRect]:
        if not self._has_selection:
            return {}

        r = self.selected_rect
        hs = HANDLE_SIZE
        half = hs // 2

        return {
            HandlePosition.TOP_LEFT: QRect(r.left() - half, r.top() - half, hs, hs),
            HandlePosition.TOP_CENTER: QRect(r.center().x() - half, r.top() - half, hs, hs),
            HandlePosition.TOP_RIGHT: QRect(r.right() - half, r.top() - half, hs, hs),
            HandlePosition.RIGHT_CENTER: QRect(r.right() - half, r.center().y() - half, hs, hs),
            HandlePosition.BOTTOM_RIGHT: QRect(r.right() - half, r.bottom() - half, hs, hs),
            HandlePosition.BOTTOM_CENTER: QRect(r.center().x() - half, r.bottom() - half, hs, hs),
            HandlePosition.BOTTOM_LEFT: QRect(r.left() - half, r.bottom() - half, hs, hs),
            HandlePosition.LEFT_CENTER: QRect(r.left() - half, r.center().y() - half, hs, hs),
        }

    def _hit_test(self, pos: QPoint) -> HandlePosition:
        if not self._has_selection:
            return HandlePosition.NONE

        handles = self._get_handles_map()
        for handle, rect in handles.items():
            expanded = rect.adjusted(-3, -3, 3, 3)
            if expanded.contains(pos):
                return handle

        if self.selected_rect.contains(pos):
            return HandlePosition.INSIDE

        return HandlePosition.NONE

    def _update_cursor(self, handle: HandlePosition) -> None:
        if self._is_eyedropping:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        if self.tool_manager.active_tool != ToolType.SELECT and self._has_selection:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        cursor_map = {
            HandlePosition.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
            HandlePosition.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
            HandlePosition.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
            HandlePosition.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
            HandlePosition.TOP_CENTER: Qt.CursorShape.SizeVerCursor,
            HandlePosition.BOTTOM_CENTER: Qt.CursorShape.SizeVerCursor,
            HandlePosition.LEFT_CENTER: Qt.CursorShape.SizeHorCursor,
            HandlePosition.RIGHT_CENTER: Qt.CursorShape.SizeHorCursor,
            HandlePosition.INSIDE: Qt.CursorShape.SizeAllCursor,
            HandlePosition.NONE: Qt.CursorShape.CrossCursor,
        }
        self.setCursor(cursor_map.get(handle, Qt.CursorShape.CrossCursor))

    def _init_canvas(self) -> None:
        try:
            if self.canvas is not None:
                self.canvas.deleteLater()
                self.canvas = None

            valid_rect = self.selected_rect.intersected(self.rect())
            if valid_rect.width() <= 2 or valid_rect.height() <= 2:
                return

            self.selected_rect = valid_rect
            sub_pixmap = self.full_desktop_pixmap.copy(self.selected_rect)
            if sub_pixmap.isNull():
                return

            sub_image = sub_pixmap.toImage()
            if sub_image.isNull():
                return

            self.canvas = AnnotationCanvas(
                base_image=sub_image,
                tool_manager=self.tool_manager,
                history_manager=self.history_manager,
                parent=self,
            )
            self.canvas.move(self.selected_rect.topLeft())
            self.canvas.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                self.tool_manager.active_tool == ToolType.SELECT,
            )
            from app.services.watermark_service import WatermarkSettings

            self.canvas.set_watermark_preview(WatermarkSettings.from_config(self.config_manager))
            self.canvas.show()
            self.canvas.raise_()
            if hasattr(self, "toolbar") and self.toolbar is not None:
                self.toolbar.raise_()
        except Exception as exc:
            logger.error("Error initializing canvas: %s", exc)

    # --- Mouse Events ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            if event.button() == Qt.MouseButton.RightButton:
                if self._is_eyedropping:
                    self._is_eyedropping = False
                    self._eyedropper_color = ""
                    self.update()
                    return
                self.cancel_capture()
            return

        pos = event.position().toPoint()

        # 0. Smart Window Capture click
        if self.smart_window_mode and not self._has_selection and not self._is_selecting:
            if self._is_capturing:
                return
            if self._hovered_browser is not None and self._hovered_browser.bounds.isValid():
                from pathlib import Path as _Path

                self._is_capturing = True
                if self._hovered_browser.title:
                    self.capture_metadata.window_title = self._hovered_browser.title
                if self._hovered_browser.process_name:
                    self.capture_metadata.app_name = _Path(self._hovered_browser.process_name).stem
                self.capture_metadata.mode = "pencere"
                selected = QRect(self._hovered_browser.bounds)
                self._hovered_browser = None
                self.selected_rect = selected
                self._has_selection = True
                self.smart_window_mode = False
                self._init_canvas()
                self.toolbar.position_near_selection(self.selected_rect, self.rect())
                if self.config_manager.get("qr", "enabled", True) and not self.session_capture_mode:
                    self.scan_qr_codes(force_show=False)
                if self.session_capture_mode:
                    self._complete_session_capture()
                    return
                self.update()
                return

        if self._is_eyedropping:
            img = self.full_desktop_pixmap.toImage()
            if 0 <= pos.x() < img.width() and 0 <= pos.y() < img.height():
                c = img.pixelColor(pos.x(), pos.y())
                self.tool_manager.color = c.name().upper()
            self._is_eyedropping = False
            self._eyedropper_color = ""
            self._update_cursor(self._hit_test(pos))
            self.update()
            return

        handle = self._hit_test(pos)

        if self._has_selection and self.tool_manager.active_tool != ToolType.SELECT:
            if handle == HandlePosition.NONE or handle == HandlePosition.INSIDE:
                return

        self._start_pos = pos
        self._drag_start_rect = QRect(self.selected_rect)

        if handle == HandlePosition.NONE:
            self._is_selecting = True
            self._has_selection = False
            self.selected_rect = QRect(pos, pos)
            self.toolbar.hide()
            if self._qr_panel:
                self._qr_panel.hide()
            self._detected_qr_results.clear()
            if self.canvas:
                self.canvas.deleteLater()
                self.canvas = None
        else:
            self._active_handle = handle
            self.toolbar.hide()
            if self._qr_panel:
                self._qr_panel.hide()
            self._detected_qr_results.clear()
            if self.canvas:
                self.canvas.hide()

        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()

        # Handle Smart Window Hover Detection
        if self.smart_window_mode and not self._has_selection and not self._is_selecting:
            global_pos = pos + self.virtual_geometry.topLeft()
            detected = BrowserWindowDetector.detect_browser_at_point(global_pos)
            if detected is not None:
                # Map to overlay coordinate space
                local_bounds = detected.bounds.translated(-self.virtual_geometry.topLeft()).intersected(self.rect())
                detected.bounds = local_bounds
                if (
                    self._hovered_browser is None
                    or self._hovered_browser.hwnd != detected.hwnd
                    or self._hovered_browser.bounds != detected.bounds
                ):
                    self._hovered_browser = detected
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                    self.update()
            else:
                if self._hovered_browser is not None:
                    self._hovered_browser = None
                    self.setCursor(Qt.CursorShape.CrossCursor)
                    self.update()
            return

        if self._is_eyedropping:
            self._eyedropper_pos = pos
            img = self.full_desktop_pixmap.toImage()
            if 0 <= pos.x() < img.width() and 0 <= pos.y() < img.height():
                self._eyedropper_color = img.pixelColor(pos.x(), pos.y()).name().upper()
            self.update()
            return

        if self._is_selecting:
            self.selected_rect = normalize_rect(QRect(self._start_pos, pos)).intersected(self.rect())
            self.update()
            return

        if self._active_handle != HandlePosition.NONE:
            dx = pos.x() - self._start_pos.x()
            dy = pos.y() - self._start_pos.y()
            r = QRect(self._drag_start_rect)

            if self._active_handle == HandlePosition.INSIDE:
                r.translate(dx, dy)
                if r.left() < 0:
                    r.moveLeft(0)
                if r.top() < 0:
                    r.moveTop(0)
                if r.right() > self.rect().right():
                    r.moveRight(self.rect().right())
                if r.bottom() > self.rect().bottom():
                    r.moveBottom(self.rect().bottom())
            elif self._active_handle == HandlePosition.TOP_LEFT:
                r.setTopLeft(r.topLeft() + QPoint(dx, dy))
            elif self._active_handle == HandlePosition.TOP_CENTER:
                r.setTop(r.top() + dy)
            elif self._active_handle == HandlePosition.TOP_RIGHT:
                r.setTopRight(r.topRight() + QPoint(dx, dy))
            elif self._active_handle == HandlePosition.RIGHT_CENTER:
                r.setRight(r.right() + dx)
            elif self._active_handle == HandlePosition.BOTTOM_RIGHT:
                r.setBottomRight(r.bottomRight() + QPoint(dx, dy))
            elif self._active_handle == HandlePosition.BOTTOM_CENTER:
                r.setBottom(r.bottom() + dy)
            elif self._active_handle == HandlePosition.BOTTOM_LEFT:
                r.setBottomLeft(r.bottomLeft() + QPoint(dx, dy))
            elif self._active_handle == HandlePosition.LEFT_CENTER:
                r.setLeft(r.left() + dx)

            self.selected_rect = normalize_rect(r).intersected(self.rect())
            self.update()
            return

        hover_handle = self._hit_test(pos)
        self._update_cursor(hover_handle)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._is_selecting:
            self._is_selecting = False
            self.selected_rect = normalize_rect(self.selected_rect)
            if self.selected_rect.width() > 10 and self.selected_rect.height() > 10:
                self._has_selection = True
                self._init_canvas()
                self.toolbar.position_near_selection(self.selected_rect, self.rect())
                if self.config_manager.get("qr", "enabled", True) and not self.session_capture_mode:
                    self.scan_qr_codes(force_show=False)
                if self.session_capture_mode:
                    self._complete_session_capture()
                    return
            else:
                self._has_selection = False
                self.selected_rect = QRect()
                self._detected_qr_results.clear()
                if self._qr_panel:
                    self._qr_panel.hide()

        elif self._active_handle != HandlePosition.NONE:
            self._active_handle = HandlePosition.NONE
            if self.selected_rect.width() > 10 and self.selected_rect.height() > 10:
                self._init_canvas()
                self.toolbar.position_near_selection(self.selected_rect, self.rect())
                if self.config_manager.get("qr", "enabled", True):
                    self.scan_qr_codes(force_show=False)

        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._has_selection and self.selected_rect.contains(event.pos()):
            if self.session_capture_mode:
                self._complete_session_capture()
                return
            self.copy_to_clipboard()

    # --- Keyboard Shortcuts ---

    def _event_matches_hotkey(self, event: QKeyEvent, hotkey_str: str) -> bool:
        if not hotkey_str:
            return False

        parts = [p.strip().upper() for p in hotkey_str.split("+")]
        target_key = parts[-1]
        req_ctrl = "CTRL" in parts
        req_alt = "ALT" in parts
        req_shift = "SHIFT" in parts
        req_win = "WIN" in parts

        modifiers = event.modifiers()
        has_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        has_alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        has_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        has_win = bool(modifiers & Qt.KeyboardModifier.MetaModifier)

        if (req_ctrl != has_ctrl) or (req_alt != has_alt) or (req_shift != has_shift) or (req_win != has_win):
            return False

        key = event.key()
        special_keys = {
            "PRINTSCREEN": [Qt.Key.Key_Print, Qt.Key.Key_SysReq],
            "ENTER": [Qt.Key.Key_Return, Qt.Key.Key_Enter],
            "ESC": [Qt.Key.Key_Escape],
            "ESCAPE": [Qt.Key.Key_Escape],
            "SPACE": [Qt.Key.Key_Space],
            "TAB": [Qt.Key.Key_Tab],
            "F1": [Qt.Key.Key_F1], "F2": [Qt.Key.Key_F2], "F3": [Qt.Key.Key_F3], "F4": [Qt.Key.Key_F4],
            "F5": [Qt.Key.Key_F5], "F6": [Qt.Key.Key_F6], "F7": [Qt.Key.Key_F7], "F8": [Qt.Key.Key_F8],
            "F9": [Qt.Key.Key_F9], "F10": [Qt.Key.Key_F10], "F11": [Qt.Key.Key_F11], "F12": [Qt.Key.Key_F12],
        }

        if target_key in special_keys:
            return key in special_keys[target_key]

        text = event.text().upper()
        if text and text == target_key:
            return True

        if len(target_key) == 1 and ord(target_key) == key:
            return True

        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Escape:
            if self.tool_manager.active_tool != ToolType.SELECT:
                self.tool_manager.active_tool = ToolType.SELECT
                return
            self.cancel_capture()
            return


        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (modifiers & Qt.KeyboardModifier.ShiftModifier):
            if self.session_capture_mode:
                self._complete_session_capture()
                return
            self.copy_to_clipboard()
            return

        # Advanced feature hotkeys
        if (modifiers & Qt.KeyboardModifier.ControlModifier) and (modifiers & Qt.KeyboardModifier.ShiftModifier):
            if key == Qt.Key.Key_O:
                self.extract_text()
                return
            elif key == Qt.Key.Key_P:
                self.open_smart_privacy()
                return
            elif key == Qt.Key.Key_L:
                self.start_scrolling_capture()
                return
            elif key == Qt.Key.Key_G:
                self.start_gif_recording()
                return
            elif key == Qt.Key.Key_M:
                self.open_panorama_capture()
                return

        hk = self.config_manager.get_section("hotkeys")

        if self._event_matches_hotkey(event, hk.get("action_ocr", "Ctrl+Shift+O")):
            self.extract_text()
            return

        if self._event_matches_hotkey(event, hk.get("action_copy", "Ctrl+C")):
            self.copy_to_clipboard()
            return
        if self._event_matches_hotkey(event, hk.get("action_save", "Ctrl+S")):
            self.save_to_file()
            return
        if self._event_matches_hotkey(event, hk.get("action_favorite", "Ctrl+Shift+F")):
            self._on_toggle_favorite()
            return
        if self._event_matches_hotkey(event, hk.get("action_undo", "Ctrl+Z")):
            self._on_undo()
            return
        if self._event_matches_hotkey(event, hk.get("action_redo", "Ctrl+Y")):
            self._on_redo()
            return

        # Tool shortcut triggers
        tool_map = [
            ("tool_pen", ToolType.PEN),
            ("tool_highlighter", ToolType.HIGHLIGHTER),
            ("tool_line", ToolType.LINE),
            ("tool_arrow", ToolType.ARROW),
            ("tool_rectangle", ToolType.RECTANGLE),
            ("tool_ellipse", ToolType.ELLIPSE),
            ("tool_text", ToolType.TEXT),
            ("tool_blur", ToolType.BLUR),
            ("tool_pixelate", ToolType.PIXELATE),
            ("tool_magnifier", ToolType.MAGNIFIER),
        ]

        for conf_key, tool_type in tool_map:
            assigned_hotkey = hk.get(conf_key, "")
            if self._event_matches_hotkey(event, assigned_hotkey):
                self.tool_manager.active_tool = tool_type
                return

    # --- Paint Event ---

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

            # 1. 1:1 hardware pixel blit across the screen
            painter.drawPixmap(0, 0, self.full_desktop_pixmap)

            # 2. Draw dimmed overlay outside selected_rect
            dim_color = QColor(DIM_BACKGROUND_COLOR)
            dim_color.setAlpha(DIM_BACKGROUND_OPACITY)

            if self._has_selection or self._is_selecting:
                full_region = QRegion(self.rect())
                cutout_region = QRegion(self.selected_rect)
                dim_region = full_region.subtracted(cutout_region)

                painter.setClipRegion(dim_region)
                painter.fillRect(self.rect(), dim_color)
                painter.setClipping(False)

                # 3. Draw selection border & handles
                painter.setPen(QPen(QColor(SELECTION_BORDER_COLOR), 1, Qt.PenStyle.SolidLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(self.selected_rect)

                # 4. Rich Measurement HUD & Edge Dimension Guides
                self._render_selection_measurement_hud(painter)

                # Draw Resize handles
                if self._has_selection:
                    painter.setBrush(QBrush(QColor(HANDLE_COLOR)))
                    painter.setPen(QPen(QColor("#FFFFFF"), 1))
                    for rect in self._get_handles_map().values():
                        painter.drawRect(rect)
            elif self.smart_window_mode:
                if self._hovered_browser is not None and self._hovered_browser.bounds.isValid():
                    full_region = QRegion(self.rect())
                    cutout_region = QRegion(self._hovered_browser.bounds)
                    dim_region = full_region.subtracted(cutout_region)

                    painter.setClipRegion(dim_region)
                    painter.fillRect(self.rect(), dim_color)
                    painter.setClipping(False)

                    # Draw glowing highlight border
                    painter.setPen(QPen(QColor("#38BDF8"), 2, Qt.PenStyle.SolidLine))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(self._hovered_browser.bounds)

                    # Draw Smart Window Badge HUD
                    self._render_smart_window_hud(painter, self._hovered_browser)
                else:
                    painter.fillRect(self.rect(), dim_color)
                    self._render_smart_window_hint(painter)
            else:
                painter.fillRect(self.rect(), dim_color)

            # Draw Eyedropper Live Preview Loupe
            if self._is_eyedropping and self._eyedropper_color:
                ep = self._eyedropper_pos
                c = QColor(self._eyedropper_color)

                # Circular Loupe Swatch
                swatch_rect = QRect(ep.x() + 14, ep.y() + 14, 22, 22)
                painter.setBrush(QBrush(c))
                painter.setPen(QPen(QColor("#FFFFFF"), 2))
                painter.drawEllipse(swatch_rect)

                # Hex Label Badge
                font = QFont("Segoe UI", 9, QFont.Weight.Bold)
                painter.setFont(font)
                metrics = QFontMetrics(font)
                lbl_w = metrics.horizontalAdvance(self._eyedropper_color) + 12
                lbl_h = metrics.height() + 6
                lbl_rect = QRect(ep.x() + 40, ep.y() + 15, lbl_w, lbl_h)
                painter.fillRect(lbl_rect, QColor(15, 23, 42, 235))
                painter.setPen(QPen(QColor("#38BDF8"), 1))
                painter.drawRect(lbl_rect)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(lbl_rect, Qt.AlignmentFlag.AlignCenter, self._eyedropper_color)

            # Draw Detected QR Code Highlights (Non-destructive overlay)
            if self._has_selection and self._detected_qr_results and self.config_manager.get("qr", "highlight_detected", True):
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                top_left = self.selected_rect.topLeft()

                for qr_res in self._detected_qr_results:
                    box = qr_res.bounding_box.translated(top_left)
                    is_focused = (qr_res == self._highlighted_qr)

                    # Glow fill
                    fill_color = QColor(56, 189, 248, 55 if is_focused else 20)
                    painter.fillRect(box, fill_color)

                    # Neon border
                    pen_color = QColor("#38BDF8" if not is_focused else "#60A5FA")
                    pen = QPen(pen_color, 2 if not is_focused else 3, Qt.PenStyle.DashLine if not is_focused else Qt.PenStyle.SolidLine)
                    painter.setPen(pen)
                    painter.drawRoundedRect(box, 4, 4)

                    # Small index badge
                    badge_text = f"#{qr_res.index} QR"
                    font = QFont("Segoe UI", 8, QFont.Weight.Bold)
                    painter.setFont(font)
                    badge_top = box.top() - 18
                    if badge_top < self.selected_rect.top():
                        badge_top = box.top() + 4
                    b_rect = QRect(box.left(), badge_top, 46, 16)
                    painter.fillRect(b_rect, QColor(15, 23, 42, 230))
                    painter.setPen(QPen(QColor("#38BDF8"), 1))
                    painter.drawRect(b_rect)
                    painter.setPen(QColor("#FFFFFF"))
                    painter.drawText(b_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

                painter.restore()
        except Exception as exc:
            logger.error("Error in SelectionOverlay paintEvent: %s", exc)
        finally:
            painter.end()

    # --- Actions ---

    def _render_selection_measurement_hud(self, painter: QPainter) -> None:
        """Renders rich real-time measurement HUD, edge dimension brackets and center guides."""
        rect = self.selected_rect
        w = rect.width()
        h = rect.height()
        if w <= 0 or h <= 0:
            return

        import math

        x = rect.x()
        y = rect.y()
        diag = math.hypot(w, h)
        area = w * h

        # Calculate Aspect Ratio
        ratio = w / h if h > 0 else 1.0
        if abs(ratio - 16 / 9) < 0.03:
            aspect = "16:9"
        elif abs(ratio - 16 / 10) < 0.03:
            aspect = "16:10"
        elif abs(ratio - 4 / 3) < 0.03:
            aspect = "4:3"
        elif abs(ratio - 1.0) < 0.02:
            aspect = "1:1"
        elif abs(ratio - 21 / 9) < 0.04:
            aspect = "21:9"
        else:
            gcd_val = math.gcd(w, h)
            rw, rh = w // gcd_val, h // gcd_val
            if rw < 25 and rh < 25:
                aspect = f"{rw}:{rh}"
            else:
                aspect = f"{ratio:.2f}:1"

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Subtle Center Crosshair Guide
        if w >= 90 and h >= 90:
            cx = x + w / 2.0
            cy = y + h / 2.0
            guide_pen = QPen(QColor(56, 189, 248, 70), 1, Qt.PenStyle.DashLine)
            painter.setPen(guide_pen)
            painter.drawLine(QPointF(x, cy), QPointF(x + w, cy))
            painter.drawLine(QPointF(cx, y), QPointF(cx, y + h))

            # Center Dot
            painter.setBrush(QBrush(QColor(56, 189, 248, 180)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), 3, 3)

        # 2. Top Edge Dimension Line & Badge
        if w >= 80:
            top_line_y = y - 8
            if top_line_y < 12:
                top_line_y = y + 16

            dim_pen = QPen(QColor(56, 189, 248, 180), 1)
            painter.setPen(dim_pen)
            painter.drawLine(QPointF(x, top_line_y), QPointF(x + w, top_line_y))
            # Ticks
            painter.drawLine(QPointF(x, top_line_y - 3), QPointF(x, top_line_y + 3))
            painter.drawLine(QPointF(x + w, top_line_y - 3), QPointF(x + w, top_line_y + 3))

            # Centered Width Pill
            w_badge_txt = f"↔ {w} px"
            badge_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(badge_font)
            fm = QFontMetrics(badge_font)
            bw = fm.horizontalAdvance(w_badge_txt) + 10
            bh = fm.height() + 4
            bx = x + (w - bw) / 2.0
            by = top_line_y - bh / 2.0

            painter.setBrush(QBrush(QColor(15, 23, 42, 230)))
            painter.setPen(QPen(QColor(56, 189, 248, 120), 1))
            painter.drawRoundedRect(QRectF(bx, by, bw, bh), 4, 4)
            painter.setPen(QColor("#38BDF8"))
            painter.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, w_badge_txt)

        # 3. Left Edge Dimension Line & Badge
        if h >= 60:
            left_line_x = x - 8
            if left_line_x < 12:
                left_line_x = x + 16

            dim_pen = QPen(QColor(96, 165, 250, 180), 1)
            painter.setPen(dim_pen)
            painter.drawLine(QPointF(left_line_x, y), QPointF(left_line_x, y + h))
            # Ticks
            painter.drawLine(QPointF(left_line_x - 3, y), QPointF(left_line_x + 3, y))
            painter.drawLine(QPointF(left_line_x - 3, y + h), QPointF(left_line_x + 3, y + h))

            # Centered Height Pill
            h_badge_txt = f"↕ {h} px"
            badge_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(badge_font)
            fm = QFontMetrics(badge_font)
            bw = fm.horizontalAdvance(h_badge_txt) + 10
            bh = fm.height() + 4
            bx = left_line_x - bw / 2.0
            by = y + (h - bh) / 2.0

            painter.setBrush(QBrush(QColor(15, 23, 42, 230)))
            painter.setPen(QPen(QColor(96, 165, 250, 120), 1))
            painter.drawRoundedRect(QRectF(bx, by, bw, bh), 4, 4)
            painter.setPen(QColor("#60A5FA"))
            painter.drawText(QRectF(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, h_badge_txt)

        # 4. Main Top Floating Measurement HUD Card
        title_txt = f"{w} × {h} px  •  📐 {diag:.1f} px"
        meta_txt = f"X: {x}  Y: {y}  |  {aspect}  |  {area:,} px²"

        title_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        meta_font = QFont("Segoe UI", 8, QFont.Weight.Normal)

        painter.setFont(title_font)
        fm_title = QFontMetrics(title_font)
        painter.setFont(meta_font)
        fm_meta = QFontMetrics(meta_font)

        card_w = max(fm_title.horizontalAdvance(title_txt), fm_meta.horizontalAdvance(meta_txt)) + 20
        card_h = fm_title.height() + fm_meta.height() + 10

        card_x = x
        card_y = y - card_h - 18
        if card_y < 10:
            card_y = y + 10
        if card_x + card_w > self.width() - 10:
            card_x = self.width() - card_w - 10
        if card_x < 10:
            card_x = 10

        card_rect = QRectF(card_x, card_y, card_w, card_h)

        # Glassmorphic Card Container
        painter.setBrush(QBrush(QColor(15, 23, 42, 235)))
        painter.setPen(QPen(QColor(56, 189, 248, 140), 1.2))
        painter.drawRoundedRect(card_rect, 6, 6)

        # Line 1: Dimensions & Diagonal
        painter.setFont(title_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(
            QRectF(card_x + 10, card_y + 4, card_w - 20, fm_title.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title_txt,
        )

        # Line 2: Coordinates, Aspect & Area
        painter.setFont(meta_font)
        painter.setPen(QColor("#94A3B8"))
        painter.drawText(
            QRectF(card_x + 10, card_y + 4 + fm_title.height(), card_w - 20, fm_meta.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            meta_txt,
        )

        painter.restore()

    def _render_smart_window_hud(self, painter: QPainter, browser: BrowserWindowInfo) -> None:
        """Render modern, informative floating badge at top-left of the hovered browser window."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        badge_text = f"🌐 {browser.display_name}"
        if browser.formatted_dimensions:
            badge_text += f" • {browser.formatted_dimensions}"
        badge_text += "  [Sol Tık: Yakala]"

        text_w = metrics.horizontalAdvance(badge_text)
        badge_w = text_w + 24
        badge_h = 30

        bx = browser.bounds.left() + 10
        by = browser.bounds.top() + 10
        if by + badge_h > self.rect().bottom() - 10:
            by = browser.bounds.bottom() - badge_h - 10
        if bx + badge_w > self.rect().right() - 10:
            bx = self.rect().right() - badge_w - 10

        badge_rect = QRectF(bx, by, badge_w, badge_h)

        # Glassmorphic Card Container
        painter.setBrush(QBrush(QColor(15, 23, 42, 235)))
        painter.setPen(QPen(QColor(56, 189, 248, 220), 1.5))
        painter.drawRoundedRect(badge_rect, 6, 6)

        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        painter.restore()

    def _render_smart_window_hint(self, painter: QPainter) -> None:
        """Render non-intrusive guidance hint at the top center of the screen."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        hint_text = "🌐 Akıllı Tarayıcı Yakalama: İmleci bir web tarayıcısı üzerine getirin • İptal için ESC"
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        text_w = metrics.horizontalAdvance(hint_text)
        pill_w = text_w + 32
        pill_h = 36
        pill_x = (self.width() - pill_w) // 2
        pill_y = 28

        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)

        painter.setBrush(QBrush(QColor(15, 23, 42, 220)))
        painter.setPen(QPen(QColor(56, 189, 248, 160), 1.2))
        painter.drawRoundedRect(pill_rect, 8, 8)

        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, hint_text)
        painter.restore()

    def _on_watermark_toggled(self, checked: bool) -> None:
        self.config_manager.set("watermark", "enabled", bool(checked))
        if self.canvas is not None:
            from app.services.watermark_service import WatermarkSettings

            self.canvas.set_watermark_preview(WatermarkSettings.from_config(self.config_manager))
        self.update()

    def _on_info_banner_toggled(self, checked: bool) -> None:
        self.config_manager.set("info_banner", "enabled", bool(checked))
        self.update()

    def get_final_image(self) -> QImage:
        """Get 1:1 hardware pixel annotated or raw cropped image."""
        if self.canvas is not None and len(self.canvas.objects) > 0:
            return self.canvas.get_annotated_image()
        elif self._has_selection:
            return self.full_desktop_pixmap.copy(self.selected_rect).toImage()
        else:
            return self.full_desktop_pixmap.toImage()

    def get_output_image(self, action: str = "save") -> QImage:
        """Final image for saving/copying/exporting, with auto-redaction, watermark, and info banner.

        The on-canvas editing state is left untouched; effects are burned into a copy.
        """
        img = self.get_final_image()
        if img.isNull():
            return img

        from app.privacy.auto_redactor import AutoRedactor
        from app.services.info_banner_service import InfoBannerService
        from app.services.watermark_service import WatermarkService

        if AutoRedactor.is_enabled(self.config_manager):
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                result = AutoRedactor.redact(img, self.config_manager)
            finally:
                QApplication.restoreOverrideCursor()

            if result.error:
                logger.warning("Auto redaction failed, output is NOT redacted: %s", result.error)
                try:
                    from app.ui.notifications import NotificationManager

                    NotificationManager.show_toast(
                        "Otomatik gizleme yapılamadı",
                        "Hassas veri taraması başarısız oldu; görüntü gizlenmeden işlendi.",
                        "info",
                        3500,
                    )
                except Exception:
                    pass
            elif result.count:
                logger.info("Auto redaction masked %d region(s).", result.count)
                try:
                    from app.ui.notifications import NotificationManager

                    NotificationManager.show_toast(
                        "Hassas veri gizlendi",
                        f"{result.count} bölge otomatik olarak gizlendi.",
                        "shield",
                        2500,
                    )
                except Exception:
                    pass
            img = result.image

        self.capture_metadata.resolution = f"{img.width()} × {img.height()} px"

        if WatermarkService.should_apply(self.config_manager, action=action):
            img = WatermarkService.apply_watermark(img, config_manager=self.config_manager)

        if InfoBannerService.should_apply(self.config_manager, action=action):
            img = InfoBannerService.apply_info_banner(
                img,
                config_manager=self.config_manager,
                metadata=self.capture_metadata,
            )

        return img

    def _complete_session_capture(self) -> None:
        """Hand the valid in-memory capture to the active session and close."""
        image = self.get_final_image()
        if not image.isNull():
            self.session_image_captured.emit(image.copy())
        self.close()

    def _on_new_session(self) -> None:
        """Start a new session from the current capture."""
        image = self.get_final_image()
        if not image.isNull():
            self.new_session_from_image.emit(image.copy())
        self.close()

    def _on_add_to_session(self) -> None:
        """Add current capture to the active session."""
        self._complete_session_capture()

    def _on_open_session(self) -> None:
        """Open the session gallery window."""
        self.open_session_requested.emit()

    def extract_text(self) -> None:
        """Open OCR Text Extraction dialog on current cropped / annotated image."""
        try:
            from app.ocr.dialog import TextExtractionDialog
            from app.ocr.provider import AutoOCRProvider

            current_img = self.get_final_image()
            langs = self.config_manager.get("ocr", "languages", ["tr", "en"])
            dlg = TextExtractionDialog(
                image=current_img,
                provider=AutoOCRProvider(),
                languages=langs,
                parent=self,
            )
            dlg.exec()
            if getattr(dlg, "ocr_result", None) is not None and getattr(dlg.ocr_result, "full_text", ""):
                self.capture_metadata.ocr_text = dlg.ocr_result.full_text
        except Exception as exc:
            logger.error("Error opening OCR extraction dialog: %s", exc, exc_info=True)

    def open_smart_privacy(self) -> None:
        """Open Smart Privacy detection dialog on current crop."""
        try:
            current_img = self.get_final_image()
            dlg = PrivacyResultDialog(current_img, parent=self)
            dlg.apply_privacy.connect(self._on_privacy_masks_applied)
            dlg.exec()
        except Exception as exc:
            logger.error("Error opening Smart Privacy dialog: %s", exc, exc_info=True)

    def open_panorama_capture(self) -> None:
        """Open Multi-Monitor & Panorama Capture Studio."""
        try:
            from app.panorama.editor_dialog import PanoramaEditorDialog

            self.hide()
            dlg = PanoramaEditorDialog(config_manager=self.config_manager, parent=None)
            dlg.open_in_editor_requested.connect(self._on_scrolling_complete)
            dlg.exec()
            self.close()
        except Exception as exc:
            logger.error("Error opening Panorama Capture dialog: %s", exc, exc_info=True)
            self.close()

    def _on_privacy_masks_applied(self, detections: List[DetectionResult]) -> None:
        """Apply selected sensitive privacy masks as non-destructive canvas objects."""
        if not detections:
            return

        if self.canvas is None:
            if not self._has_selection:
                self.selected_rect = self.rect()
                self._has_selection = True
            self._init_canvas()
            if self.toolbar:
                self.toolbar.position_near_selection(self.selected_rect, self.rect())

        for det in detections:
            box = det.bounding_box
            if det.action == PrivacyAction.BLUR:
                obj = BlurObject(
                    rect=box,
                    radius=self.tool_manager.blur_radius,
                    tint_color=self.tool_manager.blur_tint,
                )
            elif det.action == PrivacyAction.BLACKOUT:
                obj = RectangleObject(
                    rect=box,
                    color="#000000",
                    stroke_width=1,
                    opacity=1.0,
                    fill=True,
                )
            else:  # PIXELATE default
                obj = PixelateObject(
                    rect=box,
                    pixel_size=self.tool_manager.pixel_size,
                    tint_color=self.tool_manager.blur_tint,
                )

            if self.canvas:
                self.canvas.add_object(obj)

        if self.canvas:
            self.canvas.update()
        self.update()

    def start_scrolling_capture(self) -> None:
        """Start scrolling screenshot on the current selection or window."""
        from app.scrolling.controller import ScrollingCaptureController
        target_rect = self.selected_rect if self._has_selection else self.rect()
        self.toolbar.hide()
        self.hide()

        controller = ScrollingCaptureController(
            region=target_rect,
            on_complete_callback=self._on_scrolling_complete,
            on_cancel_callback=self._on_scrolling_cancelled,
        )
        controller.start()
        self._active_scroll_controller = controller

    def _on_scrolling_complete(self, stitched_image: QImage) -> None:
        self.close()
        self.stitched_capture_ready.emit(stitched_image)

    def _on_scrolling_cancelled(self) -> None:
        self.cancel_capture()

    def start_gif_recording(self) -> None:
        """Start GIF recording on the active selection."""
        from app.recorder.recorder import ScreenGifRecorder
        target_rect = self.selected_rect if self._has_selection else self.rect()
        self.toolbar.hide()
        self.hide()

        recorder = ScreenGifRecorder(
            region=target_rect,
            fps=self.config_manager.get("recorder", "fps", 15),
            max_duration_sec=self.config_manager.get("recorder", "max_duration", 60.0),
            on_finished_callback=self._on_gif_frames_recorded,
            on_cancel_callback=self.cancel_capture,
        )
        recorder.start_with_countdown()
        self._active_gif_recorder = recorder

    def _on_gif_frames_recorded(self, frames: list) -> None:
        if not frames:
            self.cancel_capture()
            return

        from app.recorder.preview_dialog import GifPreviewDialog
        preview = GifPreviewDialog(
            frames=frames,
            initial_fps=self.config_manager.get("recorder", "fps", 15),
            default_save_dir=self.default_save_dir,
        )
        preview.gif_saved.connect(lambda path: self.capture_saved.emit(path))
        preview.exec()
        self.close()

    def copy_to_clipboard(self) -> None:
        """Copy the selected and annotated image to the clipboard and close."""
        img = self.get_output_image(action="copy")
        success, err = ClipboardService.copy_image(img)
        if success:
            self.capture_copied.emit()
        else:
            logger.error("Clipboard copy failed: %s", err)
        self.close()

    def save_to_file(self) -> None:
        """Open Save File dialog and persist screenshot."""
        default_path = StorageService.get_quick_save_path(
            self.default_save_dir,
            self.default_format,
            config_manager=self.config_manager,
            metadata=self.capture_metadata,
        )
        filters = "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;WEBP Image (*.webp);;All Files (*.*)"

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog_save_screenshot"),
            str(default_path),
            filters,
        )

        if filepath:
            img = self.get_output_image(action="save")
            success, err = StorageService.save_image(img, filepath, self.jpeg_quality)
            if success:
                self._last_saved_path = filepath
                self.capture_saved.emit(filepath)
                self.close()
            else:
                logger.error("Save failed: %s", err)

    def _on_toggle_favorite(self) -> None:
        """Toggles the favorite state of current screenshot."""
        import os
        from app.favorites.manager import FavoritesManager
        from app.services.storage_service import StorageService
        from app.ui.notifications import NotificationManager

        img = self.get_output_image(action="save")
        if img.isNull():
            return

        # If not saved yet, quick save to screenshots dir
        if not self._last_saved_path or not os.path.exists(self._last_saved_path):
            quick_path = StorageService.get_quick_save_path(
                self.default_save_dir,
                self.default_format,
                config_manager=self.config_manager,
                metadata=self.capture_metadata,
            )
            success, err = StorageService.save_image(img, quick_path, self.jpeg_quality)
            if success:
                self._last_saved_path = str(quick_path)
            else:
                logger.error("Failed to quick-save screenshot for favorite: %s", err)
                return

        is_now_fav, success = FavoritesManager.toggle_favorite(self._last_saved_path)
        self.toolbar.set_is_favorite(is_now_fav)

        if is_now_fav:
            NotificationManager.show_toast(
                tr("toast_fav_added_title"),
                tr("toast_fav_added_msg"),
                icon_name="star_filled",
            )
        else:
            NotificationManager.show_toast(
                tr("toast_fav_removed_title"),
                tr("toast_fav_removed_msg"),
                icon_name="star",
            )

    def _on_open_share_history(self) -> None:
        """Open upload/share history dialog."""
        from app.ui.share_history_dialog import ShareHistoryDialog
        dlg = ShareHistoryDialog(parent=self)
        dlg.exec()

    def _on_open_favorites_gallery(self) -> None:
        """Open favorites management gallery dialog."""
        from app.ui.favorites_dialog import FavoritesDialog
        dlg = FavoritesDialog(parent=self)
        dlg.exec()

    def _on_save_to_vault(self) -> None:
        """Encrypt and save current screenshot directly into the Secure Vault (zero plaintext leak)."""
        from PySide6.QtWidgets import QDialog, QInputDialog, QLineEdit, QMessageBox
        from app.security.encryption import AuthenticationError
        from app.security.vault import SecureVault
        from app.ui.notifications import NotificationManager
        from app.ui.vault_window import CreateVaultDialog

        img = self.get_final_image()
        custom_loc = self.config_manager.get("general", "vault_location", "")
        vault = SecureVault(custom_loc if custom_loc else None)

        if not vault.is_initialized:
            dlg = CreateVaultDialog(default_dir=vault.storage.root, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.master_password:
                return
            try:
                vault = SecureVault(dlg.selected_dir)
                vault.create_vault(dlg.master_password)
                self.config_manager.set("general", "vault_location", str(dlg.selected_dir))
                self.config_manager.save()
            except Exception as exc:
                QMessageBox.critical(self, "Hata", f"Kasa oluşturulamadı:\n{exc}")
                return
        elif not vault.is_unlocked:
            from app.ui.styles import DARK_THEME_QSS
            input_dlg = QInputDialog(self)
            input_dlg.setStyleSheet(DARK_THEME_QSS)
            input_dlg.setWindowTitle("Güvenli Kasa Parolası")
            input_dlg.setLabelText("Fotoğrafı şifrelemek için Ana Parolanızı (Master Password) girin:")
            input_dlg.setTextEchoMode(QLineEdit.EchoMode.Password)
            input_dlg.setOkButtonText("Kasaya Kaydet")
            input_dlg.setCancelButtonText("İptal")

            if input_dlg.exec() != QDialog.DialogCode.Accepted:
                return
            pwd = input_dlg.textValue()
            if not pwd:
                return
            try:
                vault.unlock(pwd)
            except AuthenticationError:
                QMessageBox.critical(self, "Hata", "Hatalı ana parola! Görsel kasaya kaydedilemedi.")
                return
            except Exception as exc:
                QMessageBox.critical(self, "Hata", f"Kasa açılamadı:\n{exc}")
                return

        # Save encrypted image to vault
        try:
            vault.add_image(img, title=f"Screenshot {time.strftime('%Y-%m-%d %H:%M:%S')}")
            NotificationManager.show_toast(
                "Kasaya Kaydedildi 🔐",
                "Görsel doğrudan şifreli kasaya kaydedildi (başka hiçbir yere kaydedilmedi).",
            )
            self.close()
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Görsel kasaya kaydedilemedi:\n{exc}")

    def _on_export_pdf(self) -> None:
        """Open PDF Export & Document Builder Dialog with current final edited image canvas."""
        from app.pdf.image_loader import create_source_from_qimage
        from app.ui.pdf_export_dialog import PDFExportDialog

        img = self.get_output_image(action="export")
        item = create_source_from_qimage(img, title=f"Screenshot_{time.strftime('%Y%m%d_%H%M%S')}")
        self.hide()
        dlg = PDFExportDialog(items=[item], parent=None)
        dlg.exec()
        self.close()

    def _on_optimize_image(self) -> None:
        """Open Professional Image Optimizer Dialog with current final edited image canvas."""
        from app.ui.image_optimizer_dialog import ImageOptimizerDialog

        img = self.get_output_image(action="export")
        dlg = ImageOptimizerDialog(source_image=img, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.close()

    def _on_measure_studio(self) -> None:
        """Open Professional Measurement Studio with current final captured/edited image."""
        from app.measurement.studio_dialog import MeasurementStudioWindow

        img = self.get_final_image()
        self.hide()
        dlg = MeasurementStudioWindow(image=img, parent=None)
        dlg.exec()
        self.close()

    def _on_upload_share(self) -> None:
        """Uploads screenshot to ImgBB using user API key and presents result dialog."""
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QEventLoop
        from PySide6.QtWidgets import QProgressDialog
        from app.privacy.detector import SensitiveDataDetector
        from app.privacy.providers import AutoOCRProvider
        from app.security.credential_store import CredentialStore
        from app.ui.notifications import NotificationManager
        from app.ui.upload_dialog import ApiKeyPromptDialog, SmartPrivacyUploadWarningDialog, UploadResultDialog
        from app.upload.history_manager import ShareHistoryManager
        from app.upload.imgbb import ImgBBProvider
        from app.upload.models import ShareHistoryItem
        from app.upload.worker import UploadWorker

        api_key = CredentialStore.get_credential("imgbb", "user") or ""
        if not api_key.strip():
            key_dlg = ApiKeyPromptDialog(parent=self)
            if key_dlg.exec() != QDialog.DialogCode.Accepted or not key_dlg.entered_key.strip():
                return
            api_key = key_dlg.entered_key.strip()

        final_img = self.get_final_image()

        # 1. Smart Privacy Pre-Upload Scan
        if self.config_manager.get("upload", "privacy_check", True):
            try:
                ocr = AutoOCRProvider()
                tokens = ocr.detect_text(final_img)
                detector = SensitiveDataDetector()
                findings = detector.scan(tokens)

                if findings:
                    dlg = SmartPrivacyUploadWarningDialog(findings, parent=self)
                    dlg.exec()
                    if dlg.selected_action == SmartPrivacyUploadWarningDialog.ACTION_CANCEL:
                        return
                    elif dlg.selected_action == SmartPrivacyUploadWarningDialog.ACTION_REVIEW:
                        self.open_smart_privacy()
                        return
                    elif dlg.selected_action == SmartPrivacyUploadWarningDialog.ACTION_AUTO_REDACT:
                        for f in findings:
                            rect = f.bounding_box
                            obj = BlurObject(
                                rect=rect,
                                radius=15,
                            )
                            if self.canvas:
                                self.canvas.add_object(obj)
                        if self.canvas:
                            self.canvas.update()
                        final_img = self.get_final_image()
            except Exception as exc:
                logger.warning("Privacy pre-scan skipped: %s", exc)

        # 2. Convert QImage to optimized JPEG bytes (Quality 85, ~300KB for instant upload)
        qba = QByteArray()
        buf = QBuffer(qba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        final_img.save(buf, "JPEG", quality=85)
        img_bytes = bytes(qba.data())

        # 3. Create Progress Dialog
        prog = QProgressDialog("Görsel ImgBB'ye yükleniyor, lütfen bekleyin...", "İptal", 0, 100, None)
        prog.setWindowTitle("Yükleniyor...")
        prog.setWindowModality(Qt.WindowModality.NonModal)
        prog.setWindowFlags(prog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        prog.setValue(10)
        prog.show()

        # 4. Hide full-screen selection overlay right away so desktop is clear
        self.hide()

        provider = ImgBBProvider()
        exp_setting = self.config_manager.get("upload", "expiration", None)
        worker = UploadWorker(
            image_bytes=img_bytes,
            file_name=f"Screenshot_{time.strftime('%Y%m%d_%H%M%S')}.jpg",
            provider=provider,
            api_key=api_key,
            expiration=exp_setting,
        )
        self._upload_worker = worker

        loop = QEventLoop()
        result_holder = []

        def on_progress(val: int) -> None:
            prog.setValue(val)

        def on_finished(res) -> None:
            result_holder.append(res)
            loop.quit()

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        prog.canceled.connect(worker.cancel)

        worker.start()
        loop.exec()
        worker.wait()
        self._upload_worker = None

        prog.setValue(100)
        prog.close()

        if not result_holder:
            self.close()
            return

        res = result_holder[0]
        if res.success:
            # Save to local share history
            if self.config_manager.get("upload", "save_history", True):
                ShareHistoryManager.add_item(
                    ShareHistoryItem(
                        timestamp=time.time(),
                        provider=provider.name,
                        direct_url=res.direct_url,
                        share_url=res.share_url,
                        delete_url=res.delete_url,
                        title=res.file_name,
                        size_bytes=res.size_bytes,
                    )
                )

            # Auto copy URL to clipboard
            clip_url = res.share_url or res.direct_url
            if clip_url:
                QApplication.clipboard().setText(clip_url)
                NotificationManager.show_toast("Link Panoya Kopyalandı 🌐", f"Paylaşım adresi panoya kopyalandı:\n{clip_url}")

            # Present Result Dialog on top
            res_dlg = UploadResultDialog(res, parent=None)
            res_dlg.exec()
        else:
            QMessageBox.critical(None, "Yükleme Başarısız", f"Görsel ImgBB'ye yüklenemedi:\n\n{res.error_msg}")

        self.close()

    def scan_qr_codes(self, force_show: bool = False) -> None:
        """Scan current screenshot for QR codes in background."""
        img = self.get_final_image()
        QRService.get_instance().detect_async(
            img,
            on_finished=lambda res: self._on_qr_detected(res, force_show=force_show),
        )

    def _on_qr_detected(self, results: List[QRResult], force_show: bool = False) -> None:
        self._detected_qr_results = results
        if not results:
            if self._qr_panel:
                self._qr_panel.hide()
            self.update()
            return

        if self.config_manager.get("qr", "show_panel_automatically", True) or force_show:
            if self._qr_panel:
                self._qr_panel.deleteLater()
                self._qr_panel = None

            self._qr_panel = QRNotificationPanel(results, parent=self)
            self._qr_panel.locate_requested.connect(self._on_locate_qr)
            self._qr_panel.closed.connect(self._on_qr_panel_closed)
            target_r = self.selected_rect if self._has_selection else self.rect()
            self._qr_panel.position_smart(target_r, self.rect())

        self.update()

    def _on_locate_qr(self, qr_res: QRResult) -> None:
        self._highlighted_qr = qr_res
        self.update()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2500, self._clear_qr_highlight)

    def _clear_qr_highlight(self) -> None:
        self._highlighted_qr = None
        self.update()

    def _on_qr_panel_closed(self) -> None:
        self._qr_panel = None

    def cancel_capture(self) -> None:
        """Cancel and close overlay."""
        if self._qr_panel:
            self._qr_panel.hide()
            self._qr_panel.deleteLater()
            self._qr_panel = None
        self.capture_cancelled.emit()
        self.close()

    def closeEvent(self, event) -> None:
        if self._qr_panel:
            self._qr_panel.hide()
            self._qr_panel.deleteLater()
            self._qr_panel = None
        super().closeEvent(event)

