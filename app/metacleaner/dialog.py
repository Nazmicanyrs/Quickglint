"""Interactive dialog for inspecting, selecting, and scrubbing image metadata with Before/After views."""

from pathlib import Path
from typing import List, Optional, Union
from PIL import Image
from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.metacleaner.cleaner import MetadataCleaner
from app.metacleaner.models import (
    CleanConfig,
    CleaningPreset,
    CleanResult,
    MetadataCategory,
    MetadataField,
    MetadataRiskLevel,
    MetadataScanReport,
)
from app.metacleaner.report import MetadataReportGenerator
from app.metacleaner.scanner import MetadataScanner
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.logger import logger


class MetadataCleanerDialog(QDialog):
    """Full-featured modern Dark Glass dialog for scanning and removing sensitive image metadata."""

    metadata_cleaned = Signal(object)  # CleanResult

    def __init__(
        self,
        image_source: Union[str, Path, QImage, Image.Image],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.image_source = image_source
        self.file_path: Optional[Path] = Path(image_source) if isinstance(image_source, (str, Path)) else None
        self.scan_report: Optional[MetadataScanReport] = None
        self.clean_result: Optional[CleanResult] = None
        self._reveal_sensitive: bool = False

        self.setWindowTitle("Quickglint — Görsel Metadata ve Gizlilik Temizleyicisi (Metadata Cleaner)")
        self.setMinimumSize(1000, 680)
        self.resize(1150, 740)
        self.setStyleSheet(DARK_THEME_QSS)

        self._setup_ui()
        self._load_and_scan()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. TOP HEADER BAR
        top_bar = QFrame(self)
        top_bar.setStyleSheet(
            "QFrame { background-color: rgba(15, 23, 42, 0.95); border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 10px; padding: 8px 14px; }"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(12)

        icon_lbl = QLabel(top_bar)
        icon_lbl.setPixmap(get_icon("privacy", "#38BDF8", 24).pixmap(24, 24))
        top_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        self.title_lbl = QLabel("Görsel Metadata & Gizlilik Analizi", top_bar)
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 14.5px;")
        title_vbox.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel("EXIF, GPS, XMP, IPTC ve PNG text chunk'larını yerel olarak temizleyin.", top_bar)
        self.subtitle_lbl.setStyleSheet("color: #94A3B8; font-size: 11.5px;")
        title_vbox.addWidget(self.subtitle_lbl)
        top_layout.addLayout(title_vbox)

        top_layout.addStretch()

        # Format & Metadata Count Pills
        self.format_pill = QLabel("Format: -", top_bar)
        self.format_pill.setStyleSheet(
            "background-color: rgba(30, 41, 59, 0.85); color: #CBD5E1; border: 1px solid rgba(255, 255, 255, 0.08); "
            "padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;"
        )
        top_layout.addWidget(self.format_pill)

        self.count_pill = QLabel("0 Metadata Alanı", top_bar)
        self.count_pill.setStyleSheet(
            "background-color: rgba(30, 41, 59, 0.85); color: #38BDF8; border: 1px solid rgba(56, 189, 248, 0.3); "
            "padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;"
        )
        top_layout.addWidget(self.count_pill)

        main_layout.addWidget(top_bar)

        # 2. MAIN SPLITTER (Left: Preview & Summary Cards, Right: Categorized Tree & Presets)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)

        # --- LEFT PANEL ---
        left_panel = QFrame(self.splitter)
        left_panel.setStyleSheet("QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(12)

        # Preview Thumbnail
        preview_header = QLabel("Görsel Önizleme", left_panel)
        preview_header.setStyleSheet("color: #F8FAFC; font-weight: 600; font-size: 13px;")
        left_layout.addWidget(preview_header)

        self.preview_lbl = QLabel(left_panel)
        self.preview_lbl.setFixedHeight(180)
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet("background-color: #070D17; border: 1px solid #1E293B; border-radius: 6px;")
        left_layout.addWidget(self.preview_lbl)

        # Before / After Comparison Cards
        cards_grid = QGridLayout()
        cards_grid.setSpacing(10)

        # Before Card
        self.before_card = QFrame(left_panel)
        self.before_card.setStyleSheet("background-color: #131D31; border: 1px solid #1E293B; border-radius: 6px; padding: 8px;")
        before_vbox = QVBoxLayout(self.before_card)
        before_vbox.setContentsMargins(6, 6, 6, 6)
        before_vbox.setSpacing(4)
        before_title = QLabel("🔴 MEVCUT METADATA", self.before_card)
        before_title.setStyleSheet("color: #F87171; font-weight: 700; font-size: 11.5px;")
        before_vbox.addWidget(before_title)
        self.lbl_before_total = QLabel("Toplam: 0 alan", self.before_card)
        self.lbl_before_total.setStyleSheet("color: #F1F5F9; font-weight: 600; font-size: 12px;")
        before_vbox.addWidget(self.lbl_before_total)
        self.lbl_before_risks = QLabel("0 Yüksek  •  0 Orta", self.before_card)
        self.lbl_before_risks.setStyleSheet("color: #94A3B8; font-size: 11px;")
        before_vbox.addWidget(self.lbl_before_risks)
        cards_grid.addWidget(self.before_card, 0, 0)

        # After Card (Projected/Cleaned)
        self.after_card = QFrame(left_panel)
        self.after_card.setStyleSheet("background-color: #131D31; border: 1px solid #1E293B; border-radius: 6px; padding: 8px;")
        after_vbox = QVBoxLayout(self.after_card)
        after_vbox.setContentsMargins(6, 6, 6, 6)
        after_vbox.setSpacing(4)
        after_title = QLabel("🟢 TEMİZLİK SONRASI", self.after_card)
        after_title.setStyleSheet("color: #34D399; font-weight: 700; font-size: 11.5px;")
        after_vbox.addWidget(after_title)
        self.lbl_after_total = QLabel("Kalan: 0 alan (ICC hariç)", self.after_card)
        self.lbl_after_total.setStyleSheet("color: #F1F5F9; font-weight: 600; font-size: 12px;")
        after_vbox.addWidget(self.lbl_after_total)
        self.lbl_after_status = QLabel("🛡️ Gizlilik Korunuyor", self.after_card)
        self.lbl_after_status.setStyleSheet("color: #38BDF8; font-size: 11px;")
        after_vbox.addWidget(self.lbl_after_status)
        cards_grid.addWidget(self.after_card, 0, 1)

        left_layout.addLayout(cards_grid)

        # Privacy Controls Box
        priv_ctrl_box = QFrame(left_panel)
        priv_ctrl_box.setStyleSheet("background-color: rgba(30, 41, 59, 0.5); border: 1px solid #1E293B; border-radius: 6px; padding: 6px 10px;")
        priv_ctrl_layout = QHBoxLayout(priv_ctrl_box)
        priv_ctrl_layout.setContentsMargins(4, 4, 4, 4)

        self.btn_toggle_reveal = QPushButton("👁️ Hassas Bilgileri Göster", priv_ctrl_box)
        self.btn_toggle_reveal.setFixedHeight(28)
        self.btn_toggle_reveal.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 5px; font-size: 11.5px; font-weight: 600; padding: 2px 10px; } "
            "QPushButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: #38BDF8; color: #FFFFFF; }"
        )
        self.btn_toggle_reveal.clicked.connect(self._on_toggle_reveal)
        priv_ctrl_layout.addWidget(self.btn_toggle_reveal)
        left_layout.addWidget(priv_ctrl_box)

        left_layout.addStretch()
        self.splitter.addWidget(left_panel)

        # --- RIGHT PANEL ---
        right_panel = QFrame(self.splitter)
        right_panel.setStyleSheet("QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; }")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        # Presets Bar
        preset_row = QHBoxLayout()
        preset_lbl = QLabel("Temizleme Modu (Preset):", right_panel)
        preset_lbl.setStyleSheet("color: #F8FAFC; font-weight: 600; font-size: 12.5px;")
        preset_row.addWidget(preset_lbl)

        self.preset_combo = QComboBox(right_panel)
        self.preset_combo.addItem("🛡️ Privacy Clean (Önerilen - GPS, EXIF, XMP, IPTC Temizle)", CleaningPreset.PRIVACY_CLEAN.value)
        self.preset_combo.addItem("⚡ Quick Clean (GPS, Kamera, Yazar ve Yorumları Temizle)", CleaningPreset.QUICK_CLEAN.value)
        self.preset_combo.addItem("🔥 Maximum Privacy (Tüm Alanları Temizle)", CleaningPreset.MAXIMUM_PRIVACY.value)
        self.preset_combo.addItem("🎨 Preserve ICC (Sadece Renk Profilini Koru)", CleaningPreset.PRESERVE_ICC.value)
        self.preset_combo.addItem("⚙️ Özel (Kategorileri Manuel Seç)", CleaningPreset.CUSTOM.value)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self.preset_combo, stretch=1)
        right_layout.addLayout(preset_row)

        # Quick Option Checkboxes
        opt_row = QHBoxLayout()
        self.cb_preserve_icc = QCheckBox("🎨 ICC Renk Profilini Koru (Önerilen)", right_panel)
        self.cb_preserve_icc.setChecked(True)
        self.cb_preserve_icc.stateChanged.connect(self._on_icc_cb_changed)
        opt_row.addWidget(self.cb_preserve_icc)

        self.cb_anonymize_name = QCheckBox("🔏 Çıktı Dosya Adını Anonimleştir", right_panel)
        self.cb_anonymize_name.setChecked(False)
        opt_row.addWidget(self.cb_anonymize_name)
        right_layout.addLayout(opt_row)

        # Tree View of Metadata Categories
        self.tree = QTreeWidget(right_panel)
        self.tree.setHeaderLabels(["Alan / Kategori", "Değer", "Risk Seviyesi"])
        self.tree.header().resizeSection(0, 240)
        self.tree.header().resizeSection(1, 250)
        self.tree.header().resizeSection(2, 90)
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: #070D17; border: 1px solid #1E293B; border-radius: 6px; color: #F1F5F9; font-size: 12px; } "
            "QTreeWidget::item { padding: 4px 6px; } "
            "QTreeWidget::item:selected { background-color: #2563EB; color: #FFFFFF; }"
        )
        self.tree.itemChanged.connect(self._on_tree_item_changed)
        right_layout.addWidget(self.tree, stretch=1)

        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([420, 580])
        main_layout.addWidget(self.splitter, stretch=1)

        # 3. BOTTOM ACTION BAR
        bottom_bar = QFrame(self)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(8)

        # Report Button
        self.btn_save_report = QPushButton("Rapor Oluştur (Markdown/TXT)", bottom_bar)
        self.btn_save_report.setIcon(get_icon("file_text", "#38BDF8", 15))
        self.btn_save_report.setIconSize(QSize(14, 14))
        self.btn_save_report.setFixedHeight(34)
        self.btn_save_report.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.85); color: #F1F5F9; font-weight: 600; font-size: 12px; "
            "border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 0 12px; } "
            "QPushButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: rgba(255, 255, 255, 0.25); color: #FFFFFF; }"
        )
        self.btn_save_report.clicked.connect(self._on_save_report)
        bottom_layout.addWidget(self.btn_save_report)

        bottom_layout.addStretch()

        # Replace Original Button (Optional)
        self.btn_replace = QPushButton("Orijinalin Üzerine Yaz", bottom_bar)
        self.btn_replace.setIcon(get_icon("save", "#FBBF24", 15))
        self.btn_replace.setIconSize(QSize(14, 14))
        self.btn_replace.setFixedHeight(34)
        self.btn_replace.setStyleSheet(
            "QPushButton { background-color: rgba(217, 119, 6, 0.2); color: #FBBF24; font-weight: 600; font-size: 12px; "
            "border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 6px; padding: 0 14px; } "
            "QPushButton:hover { background-color: rgba(217, 119, 6, 0.4); color: #FFFFFF; }"
        )
        self.btn_replace.clicked.connect(self._on_clean_replace)
        bottom_layout.addWidget(self.btn_replace)

        # Primary Clean & Save As Button
        self.btn_clean_save_as = QPushButton("Temizle & Farklı Kaydet", bottom_bar)
        self.btn_clean_save_as.setIcon(get_icon("check", "#FFFFFF", 16))
        self.btn_clean_save_as.setIconSize(QSize(15, 15))
        self.btn_clean_save_as.setFixedHeight(34)
        self.btn_clean_save_as.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1D4ED8); "
            "color: #FFFFFF; font-weight: 700; font-size: 12.5px; border: 1px solid #60A5FA; border-radius: 6px; padding: 0 18px; } "
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3B82F6, stop:1 #2563EB); border-color: #93C5FD; }"
        )
        self.btn_clean_save_as.clicked.connect(self._on_clean_save_as)
        bottom_layout.addWidget(self.btn_clean_save_as)

        # Close
        close_btn = QPushButton("Kapat", bottom_bar)
        close_btn.setIcon(get_icon("close", "#FDA4AF", 15))
        close_btn.setIconSize(QSize(14, 14))
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.85); color: #F1F5F9; font-weight: 600; font-size: 12px; "
            "border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 0 14px; } "
            "QPushButton:hover { background-color: #E11D48; border-color: #F43F5E; color: #FFFFFF; }"
        )
        close_btn.clicked.connect(self.close)
        bottom_layout.addWidget(close_btn)

        main_layout.addWidget(bottom_bar)

    def _load_and_scan(self) -> None:
        """Scan the image metadata and populate UI tree and preview."""
        self.scan_report = MetadataScanner.scan_image(self.image_source)

        # Update preview
        self._update_preview()

        # Update Header pills
        self.format_pill.setText(f"Format: {self.scan_report.format_name} ({self.scan_report.image_size[0]}×{self.scan_report.image_size[1]})")
        total_img_fields = self.scan_report.total_image_fields_count
        self.count_pill.setText(f"{total_img_fields} Metadata Alanı")

        # Update Before Card
        self.lbl_before_total.setText(f"Toplam: {total_img_fields} alan")
        self.lbl_before_risks.setText(
            f"🔴 {self.scan_report.high_risk_count} Yüksek  •  🟡 {self.scan_report.medium_risk_count} Orta  •  🔵 {self.scan_report.low_risk_count} Düşük"
        )

        # Populate Tree
        self._populate_tree()
        self._update_projected_after()

    def _update_preview(self) -> None:
        """Render scaled preview pixmap."""
        pixmap: Optional[QPixmap] = None
        if isinstance(self.image_source, (str, Path)):
            pixmap = QPixmap(str(self.image_source))
        elif isinstance(self.image_source, QImage):
            pixmap = QPixmap.fromImage(self.image_source)
        elif isinstance(self.image_source, Image.Image):
            import io
            buf = io.BytesIO()
            self.image_source.save(buf, format="PNG")
            qimg = QImage()
            qimg.loadFromData(buf.getvalue(), "PNG")
            pixmap = QPixmap.fromImage(qimg)

        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                380, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.preview_lbl.setPixmap(scaled)
        else:
            self.preview_lbl.setText("🖼️ [Önizleme Yok]")

    def _populate_tree(self) -> None:
        """Populate tree widget with Image Metadata and File System Metadata separated."""
        self.tree.blockSignals(True)
        self.tree.clear()

        if not self.scan_report:
            self.tree.blockSignals(False)
            return

        # 1. Image Metadata Root
        img_root = QTreeWidgetItem(self.tree)
        img_root.setText(0, f"🖼️ Görüntü Metadata'sı ({self.scan_report.total_image_fields_count} alan)")
        img_root.setExpanded(True)

        categories = [
            MetadataCategory.GPS,
            MetadataCategory.EXIF,
            MetadataCategory.XMP,
            MetadataCategory.IPTC,
            MetadataCategory.PNG_CHUNKS,
            MetadataCategory.TIFF,
            MetadataCategory.ICC,
        ]

        for cat in categories:
            cat_fields = self.scan_report.get_fields_by_category(cat)
            if not cat_fields:
                continue

            cat_item = QTreeWidgetItem(img_root)
            cat_item.setText(0, f"{cat.value} ({len(cat_fields)})")
            cat_item.setExpanded(True)
            cat_item.setFlags(cat_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            cat_item.setCheckState(0, Qt.CheckState.Checked if cat != MetadataCategory.ICC else (Qt.CheckState.Checked if not self.cb_preserve_icc.isChecked() else Qt.CheckState.Unchecked))

            for f in cat_fields:
                field_item = QTreeWidgetItem(cat_item)
                field_item.setText(0, f.human_name)

                # Value & Masking
                val_text = f.display_value
                if f.is_sensitive and not self._reveal_sensitive:
                    val_text = f"🔒 [Gizli / Maskelenmiş: {f.display_value.split('(')[-1].replace(')', '') if '(' in f.display_value else 'Konum'}]"
                field_item.setText(1, val_text)

                # Risk badge
                risk_text = "🔴 YÜKSEK" if f.risk_level == MetadataRiskLevel.HIGH else ("🟡 ORTA" if f.risk_level == MetadataRiskLevel.MEDIUM else "🔵 DÜŞÜK")
                field_item.setText(2, risk_text)

                field_item.setFlags(field_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                field_item.setCheckState(0, Qt.CheckState.Checked if f.is_selected_for_removal else Qt.CheckState.Unchecked)
                field_item.setData(0, Qt.ItemDataRole.UserRole, f)

        # 2. File System Metadata Root (Informational)
        fs_fields = self.scan_report.file_system_fields
        if fs_fields:
            fs_root = QTreeWidgetItem(self.tree)
            fs_root.setText(0, "📁 Dosya Sistemi Metadata'sı (Sistem Düzeyi)")
            fs_root.setExpanded(False)

            for f in fs_fields:
                fs_item = QTreeWidgetItem(fs_root)
                fs_item.setText(0, f.human_name)
                fs_item.setText(1, f.display_value)
                fs_item.setText(2, "Dosya Sistemi")

        self.tree.blockSignals(False)

    def _on_toggle_reveal(self) -> None:
        """Toggle reveal of masked sensitive fields."""
        self._reveal_sensitive = not self._reveal_sensitive
        self.btn_toggle_reveal.setText("🔒 Hassas Bilgileri Maskele" if self._reveal_sensitive else "👁️ Hassas Bilgileri Göster")
        self._populate_tree()

    def _on_preset_changed(self, idx: int) -> None:
        """Handle preset selection changes."""
        preset_val = self.preset_combo.currentData()
        if not self.scan_report:
            return

        self.tree.blockSignals(True)

        if preset_val == CleaningPreset.QUICK_CLEAN.value:
            self.cb_preserve_icc.setChecked(True)
            for f in self.scan_report.image_metadata_fields:
                f.is_selected_for_removal = (f.risk_level in (MetadataRiskLevel.HIGH, MetadataRiskLevel.MEDIUM) and f.category != MetadataCategory.ICC)
        elif preset_val == CleaningPreset.PRIVACY_CLEAN.value:
            self.cb_preserve_icc.setChecked(True)
            for f in self.scan_report.image_metadata_fields:
                f.is_selected_for_removal = (f.category != MetadataCategory.ICC)
        elif preset_val == CleaningPreset.MAXIMUM_PRIVACY.value:
            self.cb_preserve_icc.setChecked(False)
            for f in self.scan_report.image_metadata_fields:
                f.is_selected_for_removal = True
            QMessageBox.information(
                self,
                "Maximum Privacy Uyarısı",
                "Maximum Privacy modu ICC Renk Profillerini de kaldırır. Bu işlem bazı cihazlarda renk yönetimini ve renk doğruluğunu etkileyebilir.",
            )
        elif preset_val == CleaningPreset.PRESERVE_ICC.value:
            self.cb_preserve_icc.setChecked(True)
            for f in self.scan_report.image_metadata_fields:
                f.is_selected_for_removal = (f.category != MetadataCategory.ICC)

        self.tree.blockSignals(False)
        self._populate_tree()
        self._update_projected_after()

    def _on_icc_cb_changed(self, state: int) -> None:
        preserve = (state == Qt.CheckState.Checked.value or state == 2)
        if self.scan_report:
            for f in self.scan_report.get_fields_by_category(MetadataCategory.ICC):
                f.is_selected_for_removal = not preserve
        self._populate_tree()
        self._update_projected_after()

    def _on_tree_item_changed(self, item: QTreeWidgetItem, col: int) -> None:
        """Synchronize check states between categories and fields."""
        if col != 0:
            return

        is_checked = (item.checkState(0) == Qt.CheckState.Checked)
        field_data: Optional[MetadataField] = item.data(0, Qt.ItemDataRole.UserRole)

        if field_data:
            field_data.is_selected_for_removal = is_checked
        else:
            # Category level check toggled
            for i in range(item.childCount()):
                child = item.child(i)
                child.setCheckState(0, item.checkState(0))
                c_data = child.data(0, Qt.ItemDataRole.UserRole)
                if c_data:
                    c_data.is_selected_for_removal = is_checked

        self._update_projected_after()

    def _update_projected_after(self) -> None:
        """Update the projected After card metrics."""
        if not self.scan_report:
            return

        total_removable = sum(1 for f in self.scan_report.image_metadata_fields if f.is_selected_for_removal)
        remaining = self.scan_report.total_image_fields_count - total_removable

        self.lbl_after_total.setText(f"Kalan: {remaining} alan  •  -{total_removable} silinecek")
        if remaining == 0:
            self.lbl_after_status.setText("🛡️ %100 Temiz (Tam Gizlilik)")
            self.lbl_after_status.setStyleSheet("color: #34D399; font-size: 11px; font-weight: 600;")
        elif self.cb_preserve_icc.isChecked() and remaining == len(self.scan_report.get_fields_by_category(MetadataCategory.ICC)):
            self.lbl_after_status.setText("🎨 Yalnızca ICC Profili Korunuyor")
            self.lbl_after_status.setStyleSheet("color: #38BDF8; font-size: 11px; font-weight: 600;")
        else:
            self.lbl_after_status.setText(f"⚠️ {remaining} metadata alanı korunacak")
            self.lbl_after_status.setStyleSheet("color: #FBBF24; font-size: 11px; font-weight: 500;")

    def _build_clean_config(self, replace_original: bool = False) -> CleanConfig:
        """Construct CleanConfig from current UI state."""
        categories = set()
        if self.scan_report:
            for f in self.scan_report.image_metadata_fields:
                if f.is_selected_for_removal:
                    categories.add(f.category)

        return CleanConfig(
            preset=CleaningPreset(self.preset_combo.currentData()),
            categories_to_remove=categories,
            preserve_icc=self.cb_preserve_icc.isChecked(),
            auto_orient=True,
            anonymize_filename=self.cb_anonymize_name.isChecked(),
            replace_original=replace_original,
        )

    def _on_clean_save_as(self) -> None:
        """Perform metadata cleaning and prompt user for save destination."""
        if not self.file_path:
            QMessageBox.warning(self, "Uyarı", "Temizlenecek geçerli bir görsel dosyası bulunamadı.")
            return

        cfg = self._build_clean_config(replace_original=False)
        suggested_path = MetadataCleaner.generate_output_path(
            self.file_path,
            anonymize=cfg.anonymize_filename,
        )

        filter_str = "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;WebP Image (*.webp);;TIFF Image (*.tiff)"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Temizlenmiş Görseli Kaydet",
            str(suggested_path),
            filter_str,
        )

        if not save_path:
            return

        res = MetadataCleaner.clean_file(self.file_path, config=cfg, output_path=save_path)
        self._handle_cleaning_result(res)

    def _on_clean_replace(self) -> None:
        """Clean metadata and overwrite original file after confirmation."""
        if not self.file_path:
            return

        reply = QMessageBox.question(
            self,
            "Orijinal Dosyanın Üzerine Yaz",
            f"'{self.file_path.name}' dosyasındaki seçili metadata alanları kalıcı olarak temizlenecek.\n\nDevam etmek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        cfg = self._build_clean_config(replace_original=True)
        res = MetadataCleaner.clean_file(self.file_path, config=cfg)
        self._handle_cleaning_result(res)

    def _handle_cleaning_result(self, res: CleanResult) -> None:
        """Display toast and update state after cleaning."""
        self.clean_result = res
        if res.success:
            NotificationManager.show_toast(
                "Metadata Temizlendi 🛡️",
                f"{res.removed_fields_count} metadata alanı başarıyla kaldırıldı.",
                "privacy",
                3000,
            )
            self.metadata_cleaned.emit(res)
            # Re-scan cleaned image to show new status
            if res.output_path and res.output_path.exists():
                self.image_source = res.output_path
                self.file_path = res.output_path
                self._load_and_scan()
        else:
            QMessageBox.critical(self, "Hata", f"Metadata temizleme işlemi başarısız:\n{res.error_msg}")

    def _on_save_report(self) -> None:
        """Export before/after cleaning report as Markdown or TXT."""
        if not self.clean_result:
            # Create a mock CleanResult from current scan report
            self.clean_result = CleanResult(
                success=True,
                input_path=self.file_path,
                before_report=self.scan_report,
                after_report=self.scan_report,
            )

        report_md = MetadataReportGenerator.generate_markdown(self.clean_result)

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Metadata Raporunu Kaydet",
            "metadata_cleaning_report.md",
            "Markdown File (*.md);;Text File (*.txt);;All Files (*.*)",
        )
        if path:
            Path(path).write_text(report_md, encoding="utf-8")
            NotificationManager.show_toast("Rapor Kaydedildi 📄", f"Rapor: {Path(path).name}", "save", 3000)

