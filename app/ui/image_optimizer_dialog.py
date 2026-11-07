"""Professional Image Optimizer Dialog with interactive Before/After preview and real-time metrics."""

import io
from pathlib import Path
from typing import Optional

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.optimizer.engine import ImageOptimizer
from app.optimizer.models import (
    ChromaSubsampling,
    OptimizationMode,
    OptimizationResult,
    OptimizerConfig,
    OutputFormat,
    QualityPreset,
    ResizePreset,
)
from app.pdf.image_loader import pil_to_qimage
from app.ui.notifications import NotificationManager
from app.utils.logger import logger

OPTIMIZER_DIALOG_QSS = """
QDialog {
    background-color: #0F172A;
    color: #F8FAFC;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

QFrame#card {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 10px;
}

QGroupBox {
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 12px;
    font-weight: 600;
    color: #38BDF8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}

QPushButton#primaryActionBtn {
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 18px;
    border: none;
}

QPushButton#primaryActionBtn:hover {
    background-color: #1D4ED8;
}

QPushButton#secondaryBtn {
    background-color: #334155;
    color: #E2E8F0;
    font-weight: 500;
    border-radius: 6px;
    padding: 6px 12px;
    border: 1px solid #475569;
}

QPushButton#secondaryBtn:hover {
    background-color: #475569;
}
"""


class ImageOptimizerDialog(QDialog):
    """Interactive GUI dialog for optimizing screenshots and images with live Before/After preview."""

    def __init__(
        self,
        source_image: Image.Image | QImage,
        file_path: Optional[Path | str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Görsel Optimize Edici (Image Optimizer) — Quickglint")
        self.resize(1060, 680)
        self.setMinimumSize(920, 580)
        self.setStyleSheet(OPTIMIZER_DIALOG_QSS)

        self.optimizer = ImageOptimizer()
        self.pil_orig = self.optimizer.load_pil_image(source_image)
        self.file_path = Path(file_path) if file_path else None

        self.config = OptimizerConfig()
        self.last_result: Optional[OptimizationResult] = None

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(150)
        self._debounce_timer.timeout.connect(self._run_optimization)

        self._setup_ui()
        self._apply_preset(QualityPreset.SCREENSHOT_LOSSLESS)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 1. TOP PRESET BAR
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("<b>⚡ Hızlı Profiller:</b>", self))

        self.combo_presets = QComboBox(self)
        for p in QualityPreset:
            self.combo_presets.addItem(p.value, p)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        top_bar.addWidget(self.combo_presets)
        top_bar.addStretch()

        main_layout.addLayout(top_bar)

        # 2. MAIN SPLITTER (Preview left, Controls right)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # LEFT CARD: BEFORE / AFTER PREVIEWS
        preview_card = QFrame(self)
        preview_card.setObjectName("card")
        p_layout = QVBoxLayout(preview_card)
        p_layout.setContentsMargins(12, 12, 12, 12)
        p_layout.setSpacing(8)

        # Preview header
        p_hdr = QLabel("<b>👁️ Karşılaştırmalı Önizleme (Before / After)</b>", preview_card)
        p_hdr.setStyleSheet("color: #38BDF8; font-size: 14px;")
        p_layout.addWidget(p_hdr)

        # Side-by-side containers
        imgs_layout = QHBoxLayout()
        imgs_layout.setSpacing(10)

        # Original Box
        orig_box = QVBoxLayout()
        self.orig_lbl_title = QLabel("Orijinal Görsel", preview_card)
        self.orig_lbl_title.setStyleSheet("font-weight: 600; color: #94A3B8;")
        orig_box.addWidget(self.orig_lbl_title)

        self.orig_img_label = QLabel(preview_card)
        self.orig_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orig_img_label.setStyleSheet("background-color: #0B1120; border: 1px solid #334155; border-radius: 8px;")
        self.orig_img_label.setMinimumSize(220, 220)
        orig_box.addWidget(self.orig_img_label)
        imgs_layout.addLayout(orig_box)

        # Optimized Box
        opt_box = QVBoxLayout()
        self.opt_lbl_title = QLabel("Optimize Edilmiş", preview_card)
        self.opt_lbl_title.setStyleSheet("font-weight: 600; color: #38BDF8;")
        opt_box.addWidget(self.opt_lbl_title)

        self.opt_img_label = QLabel(preview_card)
        self.opt_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.opt_img_label.setStyleSheet("background-color: #0B1120; border: 1px solid #0284C7; border-radius: 8px;")
        self.opt_img_label.setMinimumSize(220, 220)
        opt_box.addWidget(self.opt_img_label)
        imgs_layout.addLayout(opt_box)

        p_layout.addLayout(imgs_layout)

        # Stats Badge Card
        self.stats_frame = QFrame(preview_card)
        self.stats_frame.setStyleSheet("background-color: #0F172A; border: 1px solid #334155; border-radius: 8px; padding: 8px;")
        stats_layout = QVBoxLayout(self.stats_frame)

        self.lbl_stats_size = QLabel("Boyut: Hesaplanıyor...", self.stats_frame)
        self.lbl_stats_size.setStyleSheet("font-size: 13px; font-weight: 600; color: #10B981;")
        stats_layout.addWidget(self.lbl_stats_size)

        self.lbl_stats_quality = QLabel("Görsel Kalitesi: Hesaplanıyor...", self.stats_frame)
        self.lbl_stats_quality.setStyleSheet("font-size: 12px; color: #94A3B8;")
        stats_layout.addWidget(self.lbl_stats_quality)

        p_layout.addWidget(self.stats_frame)
        splitter.addWidget(preview_card)

        # RIGHT CARD: CONTROLS
        ctrl_card = QFrame(self)
        ctrl_card.setObjectName("card")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(12, 12, 12, 12)
        ctrl_layout.setSpacing(10)

        c_hdr = QLabel("<b>⚙️ Optimizasyon Parametreleri</b>", ctrl_card)
        c_hdr.setStyleSheet("color: #38BDF8; font-size: 14px;")
        ctrl_layout.addWidget(c_hdr)

        # Format Box
        box_fmt = QGroupBox("Çıktı Formatı (Output Format)", ctrl_card)
        bf_layout = QVBoxLayout(box_fmt)
        self.combo_format = QComboBox(box_fmt)
        for fmt in OutputFormat:
            self.combo_format.addItem(fmt.value, fmt)
        self.combo_format.currentIndexChanged.connect(self._on_control_changed)
        bf_layout.addWidget(self.combo_format)
        ctrl_layout.addWidget(box_fmt)

        # Quality Slider Box
        box_qual = QGroupBox("Kalite Seviyesi (Quality 1-100)", ctrl_card)
        bq_layout = QVBoxLayout(box_qual)

        q_slider_row = QHBoxLayout()
        self.slider_quality = QSlider(Qt.Orientation.Horizontal, box_qual)
        self.slider_quality.setRange(10, 100)
        self.slider_quality.setValue(88)
        self.slider_quality.valueChanged.connect(self._on_quality_slider_moved)
        q_slider_row.addWidget(self.slider_quality)

        self.lbl_qual_val = QLabel("88", box_qual)
        self.lbl_qual_val.setStyleSheet("font-weight: 700; color: #38BDF8; min-width: 30px;")
        q_slider_row.addWidget(self.lbl_qual_val)
        bq_layout.addLayout(q_slider_row)

        self.cb_lossless = QCheckBox("Kayıpsız Sıkıştırma (Lossless)", box_qual)
        self.cb_lossless.toggled.connect(self._on_lossless_toggled)
        bq_layout.addWidget(self.cb_lossless)
        ctrl_layout.addWidget(box_qual)

        # Resolution / Resize Box
        box_res = QGroupBox("Çözünürlük & Yeniden Boyutlandırma", ctrl_card)
        br_layout = QVBoxLayout(box_res)
        self.combo_resize = QComboBox(box_res)
        for r in ResizePreset:
            self.combo_resize.addItem(r.value, r)
        self.combo_resize.currentIndexChanged.connect(self._on_control_changed)
        br_layout.addWidget(self.combo_resize)

        self.cb_strip_meta = QCheckBox("Gereksiz Metadata & EXIF Bilgilerini Temizle", box_res)
        self.cb_strip_meta.setChecked(True)
        self.cb_strip_meta.toggled.connect(self._on_control_changed)
        br_layout.addWidget(self.cb_strip_meta)
        ctrl_layout.addWidget(box_res)

        # Advanced JPEG Subsampling Box
        box_sub = QGroupBox("JPEG Renk Örneklemesi (Chroma)", ctrl_card)
        bs_layout = QVBoxLayout(box_sub)
        self.combo_chroma = QComboBox(box_sub)
        for c in ChromaSubsampling:
            self.combo_chroma.addItem(c.value, c)
        self.combo_chroma.currentIndexChanged.connect(self._on_control_changed)
        bs_layout.addWidget(self.combo_chroma)
        ctrl_layout.addWidget(box_sub)

        ctrl_layout.addStretch()
        splitter.addWidget(ctrl_card)

        splitter.setSizes([600, 420])
        main_layout.addWidget(splitter)

        # 3. BOTTOM ACTION BUTTONS
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self.btn_replace = QPushButton("🔄 Orijinalin Üzerine Yaz", self)
        self.btn_replace.setObjectName("secondaryBtn")
        self.btn_replace.setEnabled(bool(self.file_path))
        self.btn_replace.clicked.connect(self._on_replace_original)
        bottom_bar.addWidget(self.btn_replace)

        bottom_bar.addStretch()

        self.btn_cancel = QPushButton("İptal", self)
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_save_as = QPushButton("💾 Yeni Dosya Olarak Kaydet", self)
        self.btn_save_as.setObjectName("primaryActionBtn")
        self.btn_save_as.clicked.connect(self._on_save_as)
        bottom_bar.addWidget(self.btn_save_as)

        main_layout.addLayout(bottom_bar)

    def _apply_preset(self, preset: QualityPreset) -> None:
        if preset == QualityPreset.SCREENSHOT_LOSSLESS:
            self.combo_format.setCurrentIndex(1)  # PNG
            self.cb_lossless.setChecked(True)
            self.slider_quality.setValue(100)
            self.combo_resize.setCurrentIndex(0)  # Original
        elif preset == QualityPreset.WEB_SHARE:
            self.combo_format.setCurrentIndex(3)  # WebP
            self.cb_lossless.setChecked(False)
            self.slider_quality.setValue(88)
            self.combo_resize.setCurrentIndex(3)  # 1920px
        elif preset == QualityPreset.EMAIL:
            self.combo_format.setCurrentIndex(2)  # JPEG
            self.cb_lossless.setChecked(False)
            self.slider_quality.setValue(80)
            self.combo_resize.setCurrentIndex(4)  # 1280px
        elif preset == QualityPreset.SOCIAL_MEDIA:
            self.combo_format.setCurrentIndex(3)  # WebP
            self.cb_lossless.setChecked(False)
            self.slider_quality.setValue(90)
            self.combo_resize.setCurrentIndex(2)  # 2560px
        elif preset == QualityPreset.MAX_COMPRESSION:
            self.combo_format.setCurrentIndex(3)  # WebP
            self.cb_lossless.setChecked(False)
            self.slider_quality.setValue(70)
            self.combo_resize.setCurrentIndex(3)  # 1920px
        self._on_control_changed()

    def _on_preset_selected(self) -> None:
        preset = self.combo_presets.currentData()
        if preset and preset != QualityPreset.CUSTOM:
            self._apply_preset(preset)

    def _on_quality_slider_moved(self, val: int) -> None:
        self.lbl_qual_val.setText(str(val))
        self._on_control_changed()

    def _on_lossless_toggled(self, checked: bool) -> None:
        self.slider_quality.setEnabled(not checked)
        self._on_control_changed()

    def _on_control_changed(self) -> None:
        self._debounce_timer.start()

    def _run_optimization(self) -> None:
        """Executes optimization in background and refreshes side-by-side preview."""
        self.config.format = self.combo_format.currentData()
        self.config.quality = self.slider_quality.value()
        self.config.is_lossless = self.cb_lossless.isChecked()
        self.config.resize_preset = self.combo_resize.currentData()
        self.config.strip_metadata = self.cb_strip_meta.isChecked()
        self.config.chroma_subsampling = self.combo_chroma.currentData()

        self.last_result = self.optimizer.optimize(self.pil_orig, self.config)

        # Update Original Preview
        orig_qimg = pil_to_qimage(self.pil_orig)
        scaled_orig = orig_qimg.scaled(
            260, 260,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        )
        self.orig_img_label.setPixmap(QPixmap.fromImage(scaled_orig))
        self.orig_lbl_title.setText(f"Orijinal: {self.pil_orig.width}x{self.pil_orig.height} ({self.last_result.orig_size_kb:.1f} KB)")

        # Update Optimized Preview
        opt_qimg = pil_to_qimage(self.last_result.optimized_image)
        scaled_opt = opt_qimg.scaled(
            260, 260,
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        )
        self.opt_img_label.setPixmap(QPixmap.fromImage(scaled_opt))
        self.opt_lbl_title.setText(f"Optimize: {self.last_result.optimized_dimensions[0]}x{self.last_result.optimized_dimensions[1]} ({self.last_result.opt_size_kb:.1f} KB)")

        # Update Stats Badge
        self.lbl_stats_size.setText(
            f"🎉 Boyut: {self.last_result.orig_size_kb:.1f} KB ➔ {self.last_result.opt_size_kb:.1f} KB (Tasarruf: {self.last_result.reduction_str}) — [{self.last_result.format_name}]"
        )
        self.lbl_stats_quality.setText(
            f"Görsel Kalite: <b>{self.last_result.quality_label}</b> | SSIM: {self.last_result.ssim_score:.3f} | İşlem: {self.last_result.elapsed_ms:.1f} ms"
        )

    def _on_save_as(self) -> None:
        if not self.last_result:
            return

        ext = f".{self.last_result.format_name.lower()}"
        if ext == ".jpeg":
            ext = ".jpg"

        def_name = f"{self.file_path.stem if self.file_path else 'screenshot'}_optimized{ext}"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Optimize Edilmiş Görseli Kaydet",
            def_name,
            f"{self.last_result.format_name} (*{ext});;All Files (*)",
        )
        if save_path:
            with open(save_path, "wb") as f:
                f.write(self.last_result.optimized_bytes)
            NotificationManager.show_toast(
                "Görsel Optimize Edildi ⚡",
                f"Görsel %{self.last_result.reduction_pct:.1f} tasarrufla kaydedildi:\n{Path(save_path).name}",
            )
            self.accept()

    def _on_replace_original(self) -> None:
        if not self.file_path or not self.last_result:
            return

        reply = QMessageBox.question(
            self,
            "Onay",
            f"Orijinal dosyanın ({self.file_path.name}) üzerine yazılacak.\nEmin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            tmp = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
            with open(tmp, "wb") as f:
                f.write(self.last_result.optimized_bytes)
            tmp.replace(self.file_path)

            NotificationManager.show_toast(
                "Orijinal Dosya Güncellendi ⚡",
                f"Görsel optimize edildi (%{self.last_result.reduction_pct:.1f} küçüldü).",
            )
            self.accept()

