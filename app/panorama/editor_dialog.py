"""Interactive Panorama Capture & Multi-Monitor Stitching Editor Dialog with Zoom/Pan and Export."""

from pathlib import Path
import uuid
from typing import List, Optional
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.panorama.models import (
    AlignmentMode,
    BlendingMode,
    FeatureDetectorType,
    MonitorInfo,
    PanoramaCaptureMode,
    PanoramaFrame,
    StitchConfig,
    StitchResult,
)
from app.panorama.monitor_manager import MultiMonitorManager
from app.panorama.stitcher_engine import PanoramaStitchWorker, PanoramaStitcherEngine
from app.services.clipboard_service import ClipboardService
from app.services.naming_service import CaptureMetadata, SmartNamingService
from app.services.storage_service import StorageService
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.i18n import tr
from app.utils.logger import logger
from config.config_manager import ConfigManager


class PanoramaPreviewCanvas(QWidget):
    """Interactive high-resolution image preview canvas supporting smooth Zoom and Pan."""

    zoom_changed = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(460, 320)
        self._image: Optional[QImage] = None
        self._pixmap: Optional[QPixmap] = None
        self._zoom: float = 1.0
        self._pan_offset = QPointF(0.0, 0.0)
        self._is_panning: bool = False
        self._last_mouse_pos = QPoint()
        self._fit_mode: bool = True
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_image(self, image: Optional[QImage], fit_to_view: bool = True) -> None:
        """Load a new stitched panorama QImage into the canvas."""
        self._image = image
        self._pixmap = QPixmap.fromImage(image) if (image is not None and not image.isNull()) else None
        if fit_to_view:
            self.fit_to_view()
        else:
            self.update()

    @property
    def zoom_factor(self) -> float:
        return self._zoom

    def fit_to_view(self) -> None:
        """Automatically calculate zoom and center offset so the entire panorama fits inside viewport."""
        self._fit_mode = True
        if self._pixmap is None or self._pixmap.isNull():
            self._zoom = 1.0
            self._pan_offset = QPointF(0.0, 0.0)
            self.update()
            return

        vw = max(1, self.width() - 24)
        vh = max(1, self.height() - 24)
        pw = max(1, self._pixmap.width())
        ph = max(1, self._pixmap.height())

        self._zoom = max(0.05, min(4.0, min(vw / float(pw), vh / float(ph))))
        scaled_w = pw * self._zoom
        scaled_h = ph * self._zoom
        self._pan_offset = QPointF((self.width() - scaled_w) / 2.0, (self.height() - scaled_h) / 2.0)
        self.zoom_changed.emit(self._zoom)
        self.update()

    def set_zoom(self, zoom: float, anchor: Optional[QPointF] = None) -> None:
        """Set explicit zoom level [0.05 .. 8.0] anchored around a viewport point."""
        if self._pixmap is None or self._pixmap.isNull():
            return
        self._fit_mode = False
        new_zoom = max(0.05, min(8.0, float(zoom)))
        if abs(new_zoom - self._zoom) < 1e-4:
            return

        center = anchor if anchor is not None else QPointF(self.width() / 2.0, self.height() / 2.0)
        img_x = (center.x() - self._pan_offset.x()) / self._zoom
        img_y = (center.y() - self._pan_offset.y()) / self._zoom

        self._zoom = new_zoom
        self._pan_offset = QPointF(center.x() - img_x * self._zoom, center.y() - img_y * self._zoom)
        self.zoom_changed.emit(self._zoom)
        self.update()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.25)

    def zoom_100(self) -> None:
        self.set_zoom(1.0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_mode and self._pixmap is not None:
            self.fit_to_view()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.18 if delta > 0 else (1.0 / 1.18)
        self.set_zoom(self._zoom * factor, anchor=event.position())
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._is_panning = True
            self._fit_mode = False
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()
            self._pan_offset += QPointF(delta.x(), delta.y())
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._is_panning = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Dark studio background with subtle grid
        painter.fillRect(self.rect(), QColor("#0B0F17"))
        grid_pen = QPen(QColor(255, 255, 255, 10), 1)
        painter.setPen(grid_pen)
        step = 28
        for x in range(0, self.width(), step):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            painter.drawLine(0, y, self.width(), y)

        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor("#64748B"))
            font = QFont("Segoe UI", 11)
            painter.setFont(font)
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Önizleme için monitörleri yakalayın veya görüntü ekleyin.",
            )
            painter.end()
            return

        target_rect = QRectF(
            self._pan_offset.x(),
            self._pan_offset.y(),
            self._pixmap.width() * self._zoom,
            self._pixmap.height() * self._zoom,
        )
        painter.drawPixmap(target_rect, self._pixmap, QRectF(self._pixmap.rect()))

        # Subtle border around canvas image
        border_pen = QPen(QColor("#38BDF8"), 1.2)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(target_rect)
        painter.end()


class PanoramaEditorDialog(QDialog):
    """
    Production-ready Multi-Monitor & Panorama Capture Editor Dialog.
    Supports:
    - Full Desktop Panorama, Selected Monitor, Custom Monitor Layout, and Manual Image Stitching.
    - Reordering frames, enabling/disabling monitors, adding external images.
    - OpenCV ORB/SIFT feature matching, Multi-Band & Feather blending, exposure compensation, and auto-crop.
    - Real-time background preview with Zoom/Pan and export to PNG/JPEG/WebP, Smart Naming, and Image Optimizer.
    """

    open_in_editor_requested = Signal(QImage)

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        initial_frames: Optional[List[PanoramaFrame]] = None,
        initial_mode: PanoramaCaptureMode = PanoramaCaptureMode.FULL_DESKTOP,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager or ConfigManager()
        self.setWindowTitle(tr("panorama_window_title"))
        self.resize(1180, 760)
        self.setStyleSheet(DARK_THEME_QSS)

        self.monitors: List[MonitorInfo] = MultiMonitorManager.detect_monitors()
        self.frames: List[PanoramaFrame] = list(initial_frames) if initial_frames else []
        self.current_result: Optional[StitchResult] = None
        self._worker: Optional[PanoramaStitchWorker] = None

        self._build_ui(initial_mode)

        if not self.frames:
            self.capture_from_monitors()
        else:
            self._refresh_frame_list()
            self.start_stitching()

    def _build_ui(self, initial_mode: PanoramaCaptureMode) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(10)

        # Top Header Bar
        header_frame = QFrame(self)
        header_frame.setStyleSheet(
            "QFrame { background-color: #131D31; border: 1px solid #1E293B; border-radius: 10px; padding: 8px 12px; }"
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 4, 8, 4)

        title_lbl = QLabel("🖥️ Panorama Capture & Çoklu Ekran Birleştirme Stüdyosu")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #38BDF8; border: none;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        mon_summary = f"Algılanan Monitör: {len(self.monitors)}"
        self.mon_badge_lbl = QLabel(mon_summary)
        self.mon_badge_lbl.setStyleSheet(
            "background-color: #1E293B; color: #E2E8F0; border-radius: 6px; padding: 4px 10px; font-weight: 600;"
        )
        header_layout.addWidget(self.mon_badge_lbl)
        root_layout.addWidget(header_frame)

        # Main Splitter: Left Control Panel + Right Interactive Preview
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        left_panel = QWidget(splitter)
        left_panel.setMinimumWidth(370)
        left_panel.setMaximumWidth(450)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(10)

        # 1. Capture Mode & Monitor Action Group
        mode_group = QGroupBox("1. Yakalama Modu ve Kaynaklar", left_panel)
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setSpacing(8)

        form_mode = QFormLayout()
        self.mode_combo = QComboBox(mode_group)
        self.mode_combo.addItem("Tam Masaüstü Panoraması (Tüm Ekranlar)", PanoramaCaptureMode.FULL_DESKTOP.value)
        self.mode_combo.addItem("Seçili Monitör Yakalama", PanoramaCaptureMode.SELECTED_MONITOR.value)
        self.mode_combo.addItem("Özel Monitör Düzeni (Seçilenleri Birleştir)", PanoramaCaptureMode.CUSTOM_LAYOUT.value)
        self.mode_combo.addItem("Manuel Panorama Birleştirme (OpenCV)", PanoramaCaptureMode.MANUAL_STITCHING.value)

        idx_m = self.mode_combo.findData(initial_mode.value)
        if idx_m >= 0:
            self.mode_combo.setCurrentIndex(idx_m)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form_mode.addRow("Mod:", self.mode_combo)

        self.single_mon_combo = QComboBox(mode_group)
        for m in self.monitors:
            self.single_mon_combo.addItem(m.display_label, m.index)
        self.single_mon_combo.currentIndexChanged.connect(self._on_single_monitor_selected)
        form_mode.addRow("Hedef Ekran:", self.single_mon_combo)
        mode_layout.addLayout(form_mode)

        # Source Frame List (Checkable + Reorderable)
        list_header_lbl = QLabel("Görüntü Katmanları ve Sıralama (İşaretliler Birleştirilir):")
        list_header_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        mode_layout.addWidget(list_header_lbl)

        self.frame_list = QListWidget(mode_group)
        self.frame_list.setIconSize(QSize(64, 40))
        self.frame_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.frame_list.setStyleSheet(
            "QListWidget { background-color: #0B0F17; border: 1px solid #334155; border-radius: 6px; padding: 4px; }"
            "QListWidget::item { padding: 6px; border-bottom: 1px solid #1E293B; border-radius: 4px; }"
            "QListWidget::item:selected { background-color: #1E3A8A; color: #FFFFFF; }"
        )
        self.frame_list.itemChanged.connect(self._on_frame_item_changed)
        mode_layout.addWidget(self.frame_list, 1)

        # Frame Reorder & Add/Capture Buttons
        btn_row1 = QHBoxLayout()
        self.btn_up = QPushButton("▲ Yukarı", mode_group)
        self.btn_up.setObjectName("secondaryActionBtn")
        self.btn_up.clicked.connect(self.move_selected_frame_up)
        btn_row1.addWidget(self.btn_up)

        self.btn_down = QPushButton("▼ Aşağı", mode_group)
        self.btn_down.setObjectName("secondaryActionBtn")
        self.btn_down.clicked.connect(self.move_selected_frame_down)
        btn_row1.addWidget(self.btn_down)

        self.btn_add_files = QPushButton("➕ Görsel Ekle", mode_group)
        self.btn_add_files.setObjectName("secondaryActionBtn")
        self.btn_add_files.clicked.connect(self.add_images_from_disk)
        btn_row1.addWidget(self.btn_add_files)

        self.btn_remove = QPushButton("🗑️ Sil", mode_group)
        self.btn_remove.setObjectName("secondaryActionBtn")
        self.btn_remove.clicked.connect(self.remove_selected_frame)
        btn_row1.addWidget(self.btn_remove)
        mode_layout.addLayout(btn_row1)

        self.btn_recapture = QPushButton("🔄 Monitörleri Yeniden Yakala", mode_group)
        self.btn_recapture.setObjectName("secondaryActionBtn")
        self.btn_recapture.clicked.connect(self.capture_from_monitors)
        mode_layout.addWidget(self.btn_recapture)

        left_layout.addWidget(mode_group, 1)

        # 2. Stitching & Alignment Settings Group
        stitch_group = QGroupBox("2. Hizalama, Harmanlama ve Kırpma Ayarları", left_panel)
        stitch_form = QFormLayout(stitch_group)
        stitch_form.setSpacing(8)

        self.layout_combo = QComboBox(stitch_group)
        self.layout_combo.addItem("Gerçek Masaüstü Koordinatları (Fiziksel)", "physical")
        self.layout_combo.addItem("Yatay Şerit (Yan Yana)", "horizontal")
        self.layout_combo.addItem("Dikey Yığın (Alt Alta)", "vertical")
        self.layout_combo.currentIndexChanged.connect(self.start_stitching)
        stitch_form.addRow("Yerleşim Düzeni:", self.layout_combo)

        self.detector_combo = QComboBox(stitch_group)
        self.detector_combo.addItem("Otomatik (SIFT / ORB)", FeatureDetectorType.AUTO.value)
        self.detector_combo.addItem("ORB (Hızlı Özellik Eşleştirme)", FeatureDetectorType.ORB.value)
        self.detector_combo.addItem("SIFT (Yüksek Hassasiyetli Eşleştirme)", FeatureDetectorType.SIFT.value)
        self.detector_combo.currentIndexChanged.connect(self.start_stitching)
        stitch_form.addRow("Özellik Algoritması:", self.detector_combo)

        self.alignment_combo = QComboBox(stitch_group)
        self.alignment_combo.addItem("Perspektif & Homografi (8-DOF)", AlignmentMode.HOMOGRAPHY.value)
        self.alignment_combo.addItem("Afin Hizalama (Ölçek + Döndürme)", AlignmentMode.AFFINE.value)
        self.alignment_combo.addItem("2B Kaydırma (Ekran Görüntüsü Optimize)", AlignmentMode.TRANSLATION.value)
        self.alignment_combo.addItem("Doğrudan Koordinat Yerleşimi", AlignmentMode.DESKTOP_COORDS.value)
        self.alignment_combo.currentIndexChanged.connect(self.start_stitching)
        stitch_form.addRow("Hizalama Modeli:", self.alignment_combo)

        self.blending_combo = QComboBox(stitch_group)
        self.blending_combo.addItem("Multi-Band (Laplacian Piramit Dikişsiz)", BlendingMode.MULTIBAND.value)
        self.blending_combo.addItem("Feather (Yumuşak Geçişli Harmanlama)", BlendingMode.FEATHER.value)
        self.blending_combo.addItem("Kapalı (Keskin Birleştirme)", BlendingMode.NONE.value)
        self.blending_combo.currentIndexChanged.connect(self.start_stitching)
        stitch_form.addRow("Dikiş Harmanlama:", self.blending_combo)

        self.chk_exposure = QCheckBox("Renk ve Parlaklık Farklarını Dengele", stitch_group)
        self.chk_exposure.setChecked(bool(self.config_manager.get("panorama", "exposure_compensation", True)))
        self.chk_exposure.toggled.connect(self.start_stitching)
        stitch_form.addRow(self.chk_exposure)

        self.chk_dpi = QCheckBox("Farklı DPI / Ölçeklendirme Oranlarını Eşitle", stitch_group)
        self.chk_dpi.setChecked(bool(self.config_manager.get("panorama", "normalize_dpi", True)))
        self.chk_dpi.toggled.connect(self.start_stitching)
        stitch_form.addRow(self.chk_dpi)

        self.chk_autocrop = QCheckBox("Otomatik Kırpma ve Boş Alan Temizleme", stitch_group)
        self.chk_autocrop.setChecked(bool(self.config_manager.get("panorama", "auto_crop", True)))
        self.chk_autocrop.toggled.connect(self.start_stitching)
        stitch_form.addRow(self.chk_autocrop)

        left_layout.addWidget(stitch_group)

        # 3. Export Format & Quality Group
        export_group = QGroupBox("3. Dışa Aktarma Ayarları", left_panel)
        export_form = QFormLayout(export_group)

        self.format_combo = QComboBox(export_group)
        self.format_combo.addItem("PNG (Kayıpsız Orijinal Çözünürlük)", "PNG")
        self.format_combo.addItem("JPEG (Sıkıştırılmış Fotoğraf)", "JPEG")
        self.format_combo.addItem("WebP (Modern Yüksek Verimli)", "WEBP")
        default_fmt = self.config_manager.get("panorama", "default_format", "PNG")
        f_idx = self.format_combo.findData(default_fmt.upper())
        if f_idx >= 0:
            self.format_combo.setCurrentIndex(f_idx)
        export_form.addRow("Dosya Formatı:", self.format_combo)

        qual_row = QHBoxLayout()
        self.quality_slider = QSlider(Qt.Orientation.Horizontal, export_group)
        self.quality_slider.setRange(10, 100)
        self.quality_slider.setValue(int(self.config_manager.get("panorama", "jpeg_quality", 95)))
        self.quality_lbl = QLabel(f"%{self.quality_slider.value()}", export_group)
        self.quality_slider.valueChanged.connect(lambda v: self.quality_lbl.setText(f"%{v}"))
        qual_row.addWidget(self.quality_slider, 1)
        qual_row.addWidget(self.quality_lbl)
        export_form.addRow("JPEG/WebP Kalite:", qual_row)

        left_layout.addWidget(export_group)

        # Right Preview Panel
        right_panel = QWidget(splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 0, 0, 0)
        right_layout.setSpacing(8)

        # Zoom & Pan Toolbar
        preview_bar = QHBoxLayout()
        preview_title = QLabel("Canlı Panorama Önizleme (Fare Tekerleği: Zoom | Sürükle: Kaydır)")
        preview_title.setStyleSheet("color: #94A3B8; font-weight: 600;")
        preview_bar.addWidget(preview_title)
        preview_bar.addStretch()

        self.btn_zoom_out = QPushButton("➖", right_panel)
        self.btn_zoom_out.setFixedWidth(36)
        self.btn_zoom_out.setObjectName("secondaryActionBtn")
        self.btn_zoom_out.clicked.connect(lambda: self.preview_canvas.zoom_out())
        preview_bar.addWidget(self.btn_zoom_out)

        self.lbl_zoom = QLabel("%100", right_panel)
        self.lbl_zoom.setMinimumWidth(52)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_bar.addWidget(self.lbl_zoom)

        self.btn_zoom_in = QPushButton("➕", right_panel)
        self.btn_zoom_in.setFixedWidth(36)
        self.btn_zoom_in.setObjectName("secondaryActionBtn")
        self.btn_zoom_in.clicked.connect(lambda: self.preview_canvas.zoom_in())
        preview_bar.addWidget(self.btn_zoom_in)

        self.btn_zoom_fit = QPushButton("Ekrana Sığdır", right_panel)
        self.btn_zoom_fit.setObjectName("secondaryActionBtn")
        self.btn_zoom_fit.clicked.connect(lambda: self.preview_canvas.fit_to_view())
        preview_bar.addWidget(self.btn_zoom_fit)

        self.btn_zoom_100 = QPushButton("1:1 (%100)", right_panel)
        self.btn_zoom_100.setObjectName("secondaryActionBtn")
        self.btn_zoom_100.clicked.connect(lambda: self.preview_canvas.zoom_100())
        preview_bar.addWidget(self.btn_zoom_100)

        right_layout.addLayout(preview_bar)

        self.preview_canvas = PanoramaPreviewCanvas(right_panel)
        self.preview_canvas.zoom_changed.connect(lambda z: self.lbl_zoom.setText(f"%{int(round(z * 100))}"))
        right_layout.addWidget(self.preview_canvas, 1)

        # Progress Bar & Status Info Row
        status_row = QHBoxLayout()
        self.progress_bar = QProgressBar(right_panel)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(True)
        status_row.addWidget(self.progress_bar, 1)

        self.status_lbl = QLabel("Hazır", right_panel)
        self.status_lbl.setStyleSheet("color: #38BDF8; font-weight: 600;")
        status_row.addWidget(self.status_lbl)

        self.btn_cancel_job = QPushButton("⏹️ İptal Et", right_panel)
        self.btn_cancel_job.setObjectName("cancelActionBtn")
        self.btn_cancel_job.setEnabled(False)
        self.btn_cancel_job.clicked.connect(self.cancel_stitching)
        status_row.addWidget(self.btn_cancel_job)

        self.btn_restart_job = QPushButton("▶️ Yeniden Birleştir", right_panel)
        self.btn_restart_job.setObjectName("secondaryActionBtn")
        self.btn_restart_job.clicked.connect(self.start_stitching)
        status_row.addWidget(self.btn_restart_job)

        right_layout.addLayout(status_row)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)

        # Bottom Action Footer
        footer = QHBoxLayout()
        self.resolution_lbl = QLabel("Çıktı Çözünürlüğü: -", self)
        self.resolution_lbl.setStyleSheet("color: #94A3B8; font-weight: 600;")
        footer.addWidget(self.resolution_lbl)
        footer.addStretch()

        self.btn_optimize = QPushButton("⚡ Image Optimizer", self)
        self.btn_optimize.setIcon(get_icon("optimize", "#F59E0B", 16))
        self.btn_optimize.setObjectName("secondaryActionBtn")
        self.btn_optimize.clicked.connect(self.open_in_optimizer)
        footer.addWidget(self.btn_optimize)

        self.btn_open_editor = QPushButton("✏️ Editörde Düzenle", self)
        self.btn_open_editor.setIcon(get_icon("pen", "#38BDF8", 16))
        self.btn_open_editor.setObjectName("secondaryActionBtn")
        self.btn_open_editor.clicked.connect(self.send_to_annotation_editor)
        footer.addWidget(self.btn_open_editor)

        self.btn_copy = QPushButton("📋 Panoya Kopyala", self)
        self.btn_copy.setIcon(get_icon("copy", "#FFFFFF", 16))
        self.btn_copy.setObjectName("primaryActionBtn")
        self.btn_copy.clicked.connect(self.copy_result_to_clipboard)
        footer.addWidget(self.btn_copy)

        self.btn_save = QPushButton("💾 Kaydet (Dışa Aktar)", self)
        self.btn_save.setIcon(get_icon("save", "#FFFFFF", 16))
        self.btn_save.setObjectName("primaryActionBtn")
        self.btn_save.clicked.connect(self.export_result_to_file)
        footer.addWidget(self.btn_save)

        self.btn_close = QPushButton("Kapat", self)
        self.btn_close.setObjectName("cancelActionBtn")
        self.btn_close.clicked.connect(self.reject)
        footer.addWidget(self.btn_close)

        root_layout.addLayout(footer)
        self._update_mode_controls_visibility()

    def _current_mode(self) -> PanoramaCaptureMode:
        val = self.mode_combo.currentData()
        try:
            return PanoramaCaptureMode(val)
        except Exception:
            return PanoramaCaptureMode.FULL_DESKTOP

    def _update_mode_controls_visibility(self) -> None:
        mode = self._current_mode()
        self.single_mon_combo.setEnabled(mode == PanoramaCaptureMode.SELECTED_MONITOR)

    def _on_mode_changed(self) -> None:
        self._update_mode_controls_visibility()
        mode = self._current_mode()
        if mode == PanoramaCaptureMode.SELECTED_MONITOR:
            self._on_single_monitor_selected()
        elif mode == PanoramaCaptureMode.FULL_DESKTOP:
            for f in self.frames:
                if f.monitor_info is not None:
                    f.enabled = True
            self._refresh_frame_list()
            self.start_stitching()
        else:
            self.start_stitching()

    def _on_single_monitor_selected(self) -> None:
        if self._current_mode() != PanoramaCaptureMode.SELECTED_MONITOR:
            return
        selected_mon_idx = self.single_mon_combo.currentData()
        for f in self.frames:
            if f.monitor_info is not None:
                f.enabled = (f.monitor_info.index == selected_mon_idx)
        self._refresh_frame_list()
        self.start_stitching()

    def capture_from_monitors(self) -> None:
        """Capture all connected monitors into frame list."""
        self.monitors = MultiMonitorManager.detect_monitors()
        self.mon_badge_lbl.setText(f"Algılanan Monitör: {len(self.monitors)}")
        include_cursor = bool(self.config_manager.get("image", "include_cursor", False))
        self.frames = MultiMonitorManager.capture_monitors(include_cursor=include_cursor)

        if self._current_mode() == PanoramaCaptureMode.SELECTED_MONITOR:
            sel_idx = self.single_mon_combo.currentData()
            for f in self.frames:
                if f.monitor_info is not None:
                    f.enabled = (f.monitor_info.index == sel_idx)

        self._refresh_frame_list()
        self.start_stitching()

    def _refresh_frame_list(self) -> None:
        self.frame_list.blockSignals(True)
        self.frame_list.clear()
        for idx, frame in enumerate(self.frames):
            frame.order_index = idx
            item = QListWidgetItem(f"{idx + 1}. {frame.title} [{frame.width}×{frame.height}]")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Checked if frame.enabled else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, frame.frame_id)
            if not frame.image.isNull():
                thumb = QPixmap.fromImage(frame.image).scaled(
                    64, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                item.setIcon(QIcon(thumb))
            self.frame_list.addItem(item)
        self.frame_list.blockSignals(False)

    def _on_frame_item_changed(self, item: QListWidgetItem) -> None:
        fid = item.data(Qt.ItemDataRole.UserRole)
        checked = item.checkState() == Qt.CheckState.Checked
        for f in self.frames:
            if f.frame_id == fid:
                f.enabled = checked
                break
        self.start_stitching()

    def move_selected_frame_up(self) -> None:
        row = self.frame_list.currentRow()
        if row <= 0 or row >= len(self.frames):
            return
        self.frames[row - 1], self.frames[row] = self.frames[row], self.frames[row - 1]
        self._refresh_frame_list()
        self.frame_list.setCurrentRow(row - 1)
        self.start_stitching()

    def move_selected_frame_down(self) -> None:
        row = self.frame_list.currentRow()
        if row < 0 or row >= len(self.frames) - 1:
            return
        self.frames[row + 1], self.frames[row] = self.frames[row], self.frames[row + 1]
        self._refresh_frame_list()
        self.frame_list.setCurrentRow(row + 1)
        self.start_stitching()

    def remove_selected_frame(self) -> None:
        row = self.frame_list.currentRow()
        if row < 0 or row >= len(self.frames):
            return
        del self.frames[row]
        self._refresh_frame_list()
        if self.frames:
            self.frame_list.setCurrentRow(min(row, len(self.frames) - 1))
        self.start_stitching()

    def add_images_from_disk(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Panoramaya Eklenecek Görselleri Seçin",
            self.config_manager.get("general", "default_save_dir", ""),
            "Görüntüler (*.png *.jpg *.jpeg *.webp *.bmp);;Tüm Dosyalar (*.*)",
        )
        if not paths:
            return

        added = 0
        for p_str in paths:
            qimg = QImage(p_str)
            if qimg.isNull():
                continue
            qimg = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
            p_obj = Path(p_str)
            self.frames.append(
                PanoramaFrame(
                    frame_id=f"file_{uuid.uuid4().hex[:6]}",
                    title=p_obj.name,
                    image=qimg,
                    monitor_info=None,
                    logical_rect=None,
                    enabled=True,
                    order_index=len(self.frames),
                    source_path=p_str,
                )
            )
            added += 1

        if added > 0:
            # Automatically switch to Manual Stitching when external image files are added
            idx_man = self.mode_combo.findData(PanoramaCaptureMode.MANUAL_STITCHING.value)
            if idx_man >= 0 and self._current_mode() != PanoramaCaptureMode.MANUAL_STITCHING:
                self.mode_combo.blockSignals(True)
                self.mode_combo.setCurrentIndex(idx_man)
                self.mode_combo.blockSignals(False)
                self._update_mode_controls_visibility()

            self._refresh_frame_list()
            self.start_stitching()

    def build_stitch_config(self) -> StitchConfig:
        return StitchConfig(
            mode=self._current_mode(),
            detector=FeatureDetectorType(self.detector_combo.currentData()),
            alignment=AlignmentMode(self.alignment_combo.currentData()),
            blending=BlendingMode(self.blending_combo.currentData()),
            exposure_compensation=self.chk_exposure.isChecked(),
            auto_crop=self.chk_autocrop.isChecked(),
            normalize_dpi=self.chk_dpi.isChecked(),
            layout_arrangement=str(self.layout_combo.currentData()),
        )

    def start_stitching(self) -> None:
        """Start or restart panorama stitching in background worker."""
        self.cancel_stitching()

        active = [f for f in self.frames if f.enabled and not f.image.isNull()]
        if not active:
            self.preview_canvas.set_image(None)
            self.status_lbl.setText("En az 1 görüntü seçin")
            self.resolution_lbl.setText("Çıktı Çözünürlüğü: -")
            self.progress_bar.setValue(0)
            return

        cfg = self.build_stitch_config()
        self.btn_cancel_job.setEnabled(True)
        self.progress_bar.setValue(5)
        self.status_lbl.setText("Birleştiriliyor...")

        worker = PanoramaStitchWorker(self.frames, cfg, self)
        worker.progress_changed.connect(self._on_worker_progress)
        worker.stitch_finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def cancel_stitching(self) -> None:
        """Cancel any active background stitch worker cleanly."""
        if self._worker is not None:
            if self._worker.isRunning():
                self._worker.cancel()
                self._worker.wait(1500)
            self._worker.deleteLater()
            self._worker = None
        self.btn_cancel_job.setEnabled(False)

    def _on_worker_progress(self, pct: int, msg: str) -> None:
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)

    def _on_worker_finished(self, result: StitchResult) -> None:
        self.btn_cancel_job.setEnabled(False)
        self.current_result = result

        if not result.success or result.image is None or result.image.isNull():
            self.progress_bar.setValue(0)
            self.status_lbl.setText(result.error_message or "Birleştirme başarısız.")
            return

        self.progress_bar.setValue(100)
        self.preview_canvas.set_image(result.image, fit_to_view=True)
        w, h = result.width, result.height
        mp = (w * h) / 1_000_000.0
        self.resolution_lbl.setText(
            f"Çıktı Çözünürlüğü: {w} × {h} px ({mp:.2f} MP) | Süre: {result.execution_time_ms:.0f} ms | "
            f"Kare: {result.frames_count}"
        )
        if result.warnings:
            self.status_lbl.setText(f"Tamamlandı ({result.warnings[0]})")
        else:
            self.status_lbl.setText("Panorama hazır ✓")

    def _get_export_image(self) -> Optional[QImage]:
        if self.current_result and self.current_result.image and not self.current_result.image.isNull():
            return self.current_result.image
        return None

    def copy_result_to_clipboard(self) -> None:
        img = self._get_export_image()
        if img is None:
            QMessageBox.information(self, "Bilgi", "Kopyalanacak panorama görüntüsü henüz hazır değil.")
            return
        ok, _ = ClipboardService.copy_image(img)
        if ok:
            NotificationManager.show_toast("Panoya Kopyalandı", f"Panorama ({img.width()}×{img.height()} px) panoya kopyalandı.", "copy", 2500)

    def export_result_to_file(self) -> None:
        img = self._get_export_image()
        if img is None:
            QMessageBox.information(self, "Bilgi", "Kaydedilecek panorama görüntüsü henüz hazır değil.")
            return

        fmt = str(self.format_combo.currentData() or "PNG").upper()
        quality = int(self.quality_slider.value())
        save_dir = self.config_manager.get("general", "default_save_dir", "")

        # Smart File Naming integration
        meta = CaptureMetadata(
            window_title="Panorama",
            app_name="Quickglint",
            mode="panorama",
        )
        ext_map = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
        default_path = StorageService.get_quick_save_path(
            save_dir=save_dir,
            format_ext=ext_map.get(fmt, "png"),
            config_manager=self.config_manager,
            metadata=meta,
        )

        filter_str = "PNG (*.png);;JPEG (*.jpg *.jpeg);;WebP (*.webp)"
        if fmt == "JPEG":
            filter_str = "JPEG (*.jpg *.jpeg);;PNG (*.png);;WebP (*.webp)"
        elif fmt == "WEBP":
            filter_str = "WebP (*.webp);;PNG (*.png);;JPEG (*.jpg *.jpeg)"

        chosen_path, _ = QFileDialog.getSaveFileName(
            self,
            "Panoramayı Kaydet",
            str(default_path),
            filter_str,
        )
        if not chosen_path:
            return

        ok, err = StorageService.save_image(img, Path(chosen_path), quality=quality)
        if ok:
            NotificationManager.show_toast(
                "Panorama Kaydedildi",
                f"{Path(chosen_path).name} ({img.width()}×{img.height()} px) başarıyla kaydedildi.",
                "save",
                3000,
            )
        else:
            QMessageBox.critical(self, "Kaydetme Hatası", f"Dosya kaydedilemedi:\n{err or chosen_path}")

    def open_in_optimizer(self) -> None:
        img = self._get_export_image()
        if img is None:
            QMessageBox.information(self, "Bilgi", "Optimize edilecek panorama görüntüsü henüz hazır değil.")
            return
        from app.ui.image_optimizer_dialog import ImageOptimizerDialog

        dlg = ImageOptimizerDialog(source_image=img, parent=self)
        dlg.exec()

    def send_to_annotation_editor(self) -> None:
        img = self._get_export_image()
        if img is None:
            return
        self.open_in_editor_requested.emit(img.copy())
        self.accept()

    def closeEvent(self, event) -> None:
        self.cancel_stitching()
        super().closeEvent(event)

