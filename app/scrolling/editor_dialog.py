"""Dedicated scrollable and zoomable full-canvas editor for tall stitched scrolling screenshots."""

from pathlib import Path
from typing import Optional
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.editor.canvas import AnnotationCanvas
from app.editor.history import HistoryManager
from app.editor.tools import ToolManager
from app.privacy.privacy_dialog import PrivacyResultDialog
from app.services.clipboard_service import ClipboardService
from app.services.storage_service import StorageService
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.constants import ToolType
from app.utils.i18n import tr
from app.utils.logger import logger


class ScrollingEditorDialog(QDialog):
    """Full-featured editor dialog specifically designed for reviewing and annotating long screenshots."""

    copied_to_clipboard = Signal()
    saved_to_file = Signal(str)

    def __init__(
        self,
        stitched_image: QImage,
        tool_manager: Optional[ToolManager] = None,
        history_manager: Optional[HistoryManager] = None,
        default_save_dir: str = "",
        default_format: str = "PNG",
        jpeg_quality: int = 95,
        config_manager=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.stitched_image = stitched_image
        self.tool_manager = tool_manager or ToolManager()
        self.history_manager = history_manager or HistoryManager()
        self.default_save_dir = default_save_dir
        self.default_format = default_format
        self.jpeg_quality = jpeg_quality
        self.config_manager = config_manager

        self.zoom_factor = 1.0

        # Enable full standard window capabilities (Maximize, Minimize, Resize)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle(
            f"Quickglint — Kaydırmalı Ekran Görüntüsü ({stitched_image.width()} × {stitched_image.height()} px)"
        )
        self.setMinimumSize(800, 600)
        self.resize(1200, 850)
        self.setStyleSheet(DARK_THEME_QSS)

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 1. Top Toolbar Bar
        top_bar = QFrame(self)
        top_bar.setStyleSheet(
            "background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 4px;"
        )
        bar_layout = QHBoxLayout(top_bar)
        bar_layout.setContentsMargins(6, 4, 6, 4)
        bar_layout.setSpacing(6)

        # Primary Action Buttons
        self.copy_btn = QPushButton("Kopyala", top_bar)
        self.copy_btn.setIcon(get_icon("copy", "#FFFFFF", 16))
        self.copy_btn.setIconSize(QSize(15, 15))
        self.copy_btn.setFixedHeight(32)
        self.copy_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0284C7, stop:1 #0369A1); "
            "color: #FFFFFF; font-weight: 600; font-size: 12.5px; border: 1px solid #38BDF8; border-radius: 6px; padding: 0 14px; } "
            "QPushButton:hover { background: #0284C7; }"
        )
        self.copy_btn.clicked.connect(self._on_copy)
        bar_layout.addWidget(self.copy_btn)

        self.save_btn = QPushButton("Kaydet", top_bar)
        self.save_btn.setIcon(get_icon("save", "#FFFFFF", 16))
        self.save_btn.setIconSize(QSize(15, 15))
        self.save_btn.setFixedHeight(32)
        self.save_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1D4ED8); "
            "color: #FFFFFF; font-weight: 600; font-size: 12.5px; border: 1px solid #60A5FA; border-radius: 6px; padding: 0 14px; } "
            "QPushButton:hover { background: #3B82F6; }"
        )
        self.save_btn.clicked.connect(self._on_save)
        bar_layout.addWidget(self.save_btn)

        self.ocr_btn = QPushButton("Metin Çıkar", top_bar)
        self.ocr_btn.setIcon(get_icon("ocr", "#38BDF8", 16))
        self.ocr_btn.setIconSize(QSize(15, 15))
        self.ocr_btn.setFixedHeight(32)
        self.ocr_btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #38BDF8; font-weight: 600; font-size: 12px; "
            "border: 1px solid rgba(56, 189, 248, 0.4); border-radius: 6px; padding: 0 12px; } "
            "QPushButton:hover { background-color: rgba(56, 189, 248, 0.2); color: #FFFFFF; }"
        )
        self.ocr_btn.setToolTip("Kaydırmalı Görseldeki Metinleri Çıkar ve Kopyala (Extract Text)")
        self.ocr_btn.clicked.connect(self._on_extract_text)
        bar_layout.addWidget(self.ocr_btn)

        self.privacy_btn = QPushButton("Smart Privacy", top_bar)
        self.privacy_btn.setIcon(get_icon("privacy", "#F59E0B", 16))
        self.privacy_btn.setIconSize(QSize(15, 15))
        self.privacy_btn.setFixedHeight(32)
        self.privacy_btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F59E0B; font-weight: 600; font-size: 12px; "
            "border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 6px; padding: 0 12px; } "
            "QPushButton:hover { background-color: rgba(245, 158, 11, 0.2); color: #FFFFFF; }"
        )
        self.privacy_btn.clicked.connect(self._on_smart_privacy)
        bar_layout.addWidget(self.privacy_btn)

        # Separator
        sep1 = QFrame(top_bar)
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("background-color: rgba(255, 255, 255, 0.12); max-width: 1px; margin: 2px 4px;")
        bar_layout.addWidget(sep1)

        # Drawing Tool Buttons
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        tools_data = [
            ("pen", ToolType.PEN, "Kalem (P)"),
            ("arrow", ToolType.ARROW, "Ok (A)"),
            ("rect", ToolType.RECTANGLE, "Dikdörtgen (R)"),
            ("text", ToolType.TEXT, "Metin (T)"),
            ("magnifier", ToolType.MAGNIFIER, tr("tool_magnifier")),
            ("blur", ToolType.BLUR, "Bulanıklaştır (B)"),
            ("pixelate", ToolType.PIXELATE, "Pikselle (X)"),
        ]

        for icon_name, tool_enum, tooltip in tools_data:
            btn = QToolButton(top_bar)
            btn.setIcon(get_icon(icon_name, "#E2E8F0", 18))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setFixedSize(32, 32)
            btn.setStyleSheet(
                "QToolButton { background-color: rgba(30, 41, 59, 0.85); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; } "
                "QToolButton:checked { background-color: #2563EB; border-color: #60A5FA; color: #FFFFFF; } "
                "QToolButton:hover:!checked { background-color: rgba(51, 65, 85, 0.95); border-color: rgba(255, 255, 255, 0.2); }"
            )
            btn.clicked.connect(lambda checked, t=tool_enum: self._on_tool_selected(t))
            self.tool_group.addButton(btn)
            bar_layout.addWidget(btn)

        # History Buttons (Undo / Redo)
        self.undo_btn = QToolButton(top_bar)
        self.undo_btn.setIcon(get_icon("undo", "#E2E8F0", 18))
        self.undo_btn.setIconSize(QSize(18, 18))
        self.undo_btn.setFixedSize(32, 32)
        self.undo_btn.setToolTip("Geri Al (Ctrl+Z)")
        self.undo_btn.setStyleSheet(
            "QToolButton { background-color: rgba(30, 41, 59, 0.85); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; } "
            "QToolButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: rgba(255, 255, 255, 0.2); }"
        )
        self.undo_btn.clicked.connect(self._on_undo)
        bar_layout.addWidget(self.undo_btn)

        self.redo_btn = QToolButton(top_bar)
        self.redo_btn.setIcon(get_icon("redo", "#E2E8F0", 18))
        self.redo_btn.setIconSize(QSize(18, 18))
        self.redo_btn.setFixedSize(32, 32)
        self.redo_btn.setToolTip("İleri Al (Ctrl+Y)")
        self.redo_btn.setStyleSheet(
            "QToolButton { background-color: rgba(30, 41, 59, 0.85); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 6px; } "
            "QToolButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: rgba(255, 255, 255, 0.2); }"
        )
        self.redo_btn.clicked.connect(self._on_redo)
        bar_layout.addWidget(self.redo_btn)

        bar_layout.addStretch()

        # Image Dimensions Badge
        dim_lbl = QLabel(f"{self.stitched_image.width()} × {self.stitched_image.height()} px", top_bar)
        dim_lbl.setStyleSheet("background-color: rgba(30, 41, 59, 0.8); color: #CBD5E1; padding: 4px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 600;")
        bar_layout.addWidget(dim_lbl)

        # Maximize / Restore Toggle Button
        self.max_btn = QPushButton("🗖", top_bar)
        self.max_btn.setFixedSize(28, 28)
        self.max_btn.setToolTip("Tam Ekran / Normal Boyut")
        self.max_btn.setStyleSheet(
            "QPushButton { background-color: #334155; color: #FFFFFF; font-weight: bold; border-radius: 4px; } "
            "QPushButton:hover { background-color: #475569; }"
        )
        self.max_btn.clicked.connect(self._toggle_maximize)
        bar_layout.addWidget(self.max_btn)

        # Close Button
        close_btn = QPushButton("✕", top_bar)
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton { background-color: #475569; color: #FFFFFF; font-weight: bold; border-radius: 4px; } "
            "QPushButton:hover { background-color: #EF4444; }"
        )
        close_btn.clicked.connect(self.close)
        bar_layout.addWidget(close_btn)

        main_layout.addWidget(top_bar)

        # 2. Central Scroll Area containing the Canvas
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background-color: #0F172A; border: 1px solid #334155; border-radius: 6px; } "
            "QScrollBar:vertical { background: #1E293B; width: 12px; } "
            "QScrollBar::handle:vertical { background: #475569; border-radius: 6px; } "
            "QScrollBar::handle:vertical:hover { background: #64748B; }"
        )
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        # Canvas Widget with direct QImage
        self.canvas = AnnotationCanvas(
            base_image=self.stitched_image,
            tool_manager=self.tool_manager,
            history_manager=self.history_manager,
            parent=self.scroll_area,
        )
        self.canvas.setFixedSize(self.stitched_image.size())

        self.scroll_area.setWidget(self.canvas)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # Connect Shortcuts
        QShortcut(QKeySequence.StandardKey.Undo, self, self._on_undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, self._on_redo)
        QShortcut(QKeySequence.StandardKey.Copy, self, self._on_copy)
        QShortcut(QKeySequence.StandardKey.Save, self, self._on_save)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _on_tool_selected(self, tool_type: ToolType) -> None:
        self.tool_manager.active_tool = tool_type

    def _on_undo(self) -> None:
        self.history_manager.undo()
        self.canvas.update()

    def _on_redo(self) -> None:
        self.history_manager.redo()
        self.canvas.update()

    def _get_output_image(self, action: str = "save") -> QImage:
        rendered = self.canvas.get_annotated_image()
        if rendered.isNull():
            return rendered

        from app.privacy.auto_redactor import AutoRedactor
        from app.services.info_banner_service import InfoBannerService
        from app.services.naming_service import CaptureMetadata
        from app.services.watermark_service import WatermarkService

        if AutoRedactor.is_enabled(self.config_manager):
            res = AutoRedactor.redact(rendered, self.config_manager)
            if res.count:
                NotificationManager.show_toast(
                    "Hassas veri gizlendi",
                    f"{res.count} bölge otomatik olarak gizlendi.",
                    "shield",
                    2500,
                )
            rendered = res.image

        meta = getattr(self, "_capture_metadata", None) or CaptureMetadata(mode="kaydirmali")
        meta.resolution = f"{rendered.width()} × {rendered.height()} px"

        if WatermarkService.should_apply(self.config_manager, action=action):
            rendered = WatermarkService.apply_watermark(rendered, config_manager=self.config_manager)

        if InfoBannerService.should_apply(self.config_manager, action=action):
            rendered = InfoBannerService.apply_info_banner(
                rendered,
                config_manager=self.config_manager,
                metadata=meta,
            )

        return rendered

    def _on_copy(self) -> None:
        rendered = self._get_output_image(action="copy")
        success, _ = ClipboardService.copy_image(rendered)
        if success:
            NotificationManager.show_toast(tr("toast_copied_title"), tr("toast_copied_msg"), "copy", 2500)
            self.copied_to_clipboard.emit()

    def _on_save(self) -> None:
        from app.services.naming_service import CaptureMetadata

        rendered = self._get_output_image(action="save")
        meta = getattr(self, "_capture_metadata", None) or CaptureMetadata(mode="kaydirmali")
        default_path = StorageService.get_quick_save_path(
            self.default_save_dir,
            self.default_format,
            config_manager=self.config_manager,
            metadata=meta,
        )

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Ekran Görüntüsünü Kaydet",
            str(default_path),
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;WebP Image (*.webp)",
        )

        if not filepath:
            return

        success, _ = StorageService.save_image(
            image=rendered,
            destination_path=Path(filepath),
            quality=self.jpeg_quality,
        )

        if success:
            NotificationManager.show_toast(
                tr("toast_saved_title"),
                tr("toast_saved_msg", filename=Path(filepath).name),
                "save",
                3000,
            )
            self.saved_to_file.emit(filepath)

    def _on_extract_text(self) -> None:
        from app.ocr.dialog import TextExtractionDialog
        from app.ocr.provider import AutoOCRProvider

        rendered = self.canvas.get_annotated_image()
        dialog = TextExtractionDialog(
            image=rendered,
            provider=AutoOCRProvider(),
            parent=self,
        )
        dialog.exec()
        if getattr(dialog, "ocr_result", None) is not None and getattr(dialog.ocr_result, "full_text", ""):
            from app.services.naming_service import CaptureMetadata

            if not hasattr(self, "_capture_metadata") or self._capture_metadata is None:
                self._capture_metadata = CaptureMetadata(mode="kaydirmali")
            self._capture_metadata.ocr_text = dialog.ocr_result.full_text

    def _on_smart_privacy(self) -> None:
        rendered = self.canvas.get_annotated_image()
        dialog = PrivacyResultDialog(
            image=rendered,
            parent=self,
        )
        dialog.apply_privacy.connect(self._on_privacy_masks_applied)
        dialog.exec()

    def _on_privacy_masks_applied(self, detections) -> None:
        if not detections or self.canvas is None:
            return
        from app.editor.history import AddObjectCommand
        from app.editor.objects import BlurObject, PixelateObject, RectangleObject
        from app.privacy.detection_result import PrivacyAction

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
                )
            else:
                obj = PixelateObject(
                    rect=box,
                    pixel_size=self.tool_manager.pixel_size,
                    tint_color=self.tool_manager.blur_tint,
                )

            cmd = AddObjectCommand(self.canvas.objects, obj)
            self.history_manager.execute_command(cmd)

        self.canvas.update()


