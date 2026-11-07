"""Dialog for batch cleaning metadata across multiple images concurrently."""

from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.metacleaner.batch import BatchMetadataCleanerWorker
from app.metacleaner.models import CleanConfig, CleaningPreset, CleanResult
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.logger import logger


class BatchMetadataCleanerDialog(QDialog):
    """Dialog managing multi-file batch metadata cleaning with real-time progress and reporting."""

    def __init__(
        self,
        file_paths: Optional[List[Path]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.file_paths: List[Path] = [Path(p) for p in (file_paths or [])]
        self.worker: Optional[BatchMetadataCleanerWorker] = None
        self.results: List[CleanResult] = []

        self.setWindowTitle("Quickglint — Toplu Metadata Temizleyici (Batch Cleaner)")
        self.setMinimumSize(850, 560)
        self.resize(920, 620)
        self.setStyleSheet(DARK_THEME_QSS)

        self._setup_ui()
        self._update_table()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header Bar
        top_bar = QFrame(self)
        top_bar.setStyleSheet(
            "QFrame { background-color: rgba(15, 23, 42, 0.95); border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 10px; padding: 8px 14px; }"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(12)

        icon_lbl = QLabel(top_bar)
        icon_lbl.setPixmap(get_icon("privacy", "#38BDF8", 22).pixmap(22, 22))
        top_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_lbl = QLabel("Toplu Görsel Metadata Temizliği", top_bar)
        title_lbl.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 14px;")
        title_vbox.addWidget(title_lbl)

        self.subtitle_lbl = QLabel("Birden fazla görseli tek işlemde güvenle temizleyin.", top_bar)
        self.subtitle_lbl.setStyleSheet("color: #94A3B8; font-size: 11.5px;")
        title_vbox.addWidget(self.subtitle_lbl)
        top_layout.addLayout(title_vbox)

        top_layout.addStretch()

        self.count_badge = QLabel(f"{len(self.file_paths)} Görsel", top_bar)
        self.count_badge.setStyleSheet(
            "background-color: rgba(30, 41, 59, 0.85); color: #38BDF8; border: 1px solid rgba(56, 189, 248, 0.3); "
            "padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;"
        )
        top_layout.addWidget(self.count_badge)

        main_layout.addWidget(top_bar)

        # Options & Preset Bar
        opt_bar = QFrame(self)
        opt_bar.setStyleSheet("background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 8px;")
        opt_layout = QHBoxLayout(opt_bar)
        opt_layout.setSpacing(12)

        opt_layout.addWidget(QLabel("Temizleme Modu:", opt_bar))
        self.preset_combo = QComboBox(opt_bar)
        self.preset_combo.addItem("🛡️ Privacy Clean (Önerilen)", CleaningPreset.PRIVACY_CLEAN.value)
        self.preset_combo.addItem("⚡ Quick Clean", CleaningPreset.QUICK_CLEAN.value)
        self.preset_combo.addItem("🔥 Maximum Privacy", CleaningPreset.MAXIMUM_PRIVACY.value)
        self.preset_combo.addItem("🎨 Preserve ICC", CleaningPreset.PRESERVE_ICC.value)
        opt_layout.addWidget(self.preset_combo)

        self.cb_preserve_icc = QCheckBox("🎨 ICC Profilini Koru", opt_bar)
        self.cb_preserve_icc.setChecked(True)
        opt_layout.addWidget(self.cb_preserve_icc)

        self.cb_anonymize = QCheckBox("🔏 İsimleri Anonimleştir", opt_bar)
        self.cb_anonymize.setChecked(False)
        opt_layout.addWidget(self.cb_anonymize)

        opt_layout.addStretch()

        self.btn_add_files = QPushButton("➕ Dosya Ekle", opt_bar)
        self.btn_add_files.setFixedHeight(30)
        self.btn_add_files.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 5px; font-size: 11.5px; font-weight: 600; padding: 2px 10px; } "
            "QPushButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: #38BDF8; color: #FFFFFF; }"
        )
        self.btn_add_files.clicked.connect(self._on_add_files)
        opt_layout.addWidget(self.btn_add_files)

        self.btn_clear_list = QPushButton("🗑️ Listeyi Temizle", opt_bar)
        self.btn_clear_list.setFixedHeight(30)
        self.btn_clear_list.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F87171; border: 1px solid rgba(248, 113, 113, 0.3); "
            "border-radius: 5px; font-size: 11.5px; font-weight: 600; padding: 2px 10px; } "
            "QPushButton:hover { background-color: rgba(248, 113, 113, 0.2); color: #FFFFFF; }"
        )
        self.btn_clear_list.clicked.connect(self._on_clear_list)
        opt_layout.addWidget(self.btn_clear_list)

        main_layout.addWidget(opt_bar)

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #0F172A; border: none; border-radius: 3px; } "
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:1 #2563EB); border-radius: 3px; }"
        )
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # Table of files
        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Dosya Adı", "Boyut", "Durum", "Temizlenen Alan"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; color: #F1F5F9; font-size: 12px; } "
            "QHeaderView::section { background-color: #1E293B; color: #38BDF8; font-weight: 600; border: none; padding: 6px; }"
        )
        main_layout.addWidget(self.table, stretch=1)

        # Bottom Action Bar
        bottom_bar = QFrame(self)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(8)

        bottom_layout.addStretch()

        self.btn_start_batch = QPushButton("Tümünü Temizle (Start Batch Clean)", bottom_bar)
        self.btn_start_batch.setIcon(get_icon("check", "#FFFFFF", 16))
        self.btn_start_batch.setIconSize(QSize(15, 15))
        self.btn_start_batch.setFixedHeight(34)
        self.btn_start_batch.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1D4ED8); "
            "color: #FFFFFF; font-weight: 700; font-size: 12.5px; border: 1px solid #60A5FA; border-radius: 6px; padding: 0 18px; } "
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3B82F6, stop:1 #2563EB); border-color: #93C5FD; }"
        )
        self.btn_start_batch.clicked.connect(self._on_start_batch)
        bottom_layout.addWidget(self.btn_start_batch)

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

    def _update_table(self) -> None:
        """Refresh table items from file_paths list."""
        self.table.setRowCount(len(self.file_paths))
        for row, path in enumerate(self.file_paths):
            self.table.setItem(row, 0, QTableWidgetItem(path.name))
            size_str = f"{path.stat().st_size / 1024.0:.1f} KB" if path.exists() else "-"
            self.table.setItem(row, 1, QTableWidgetItem(size_str))
            self.table.setItem(row, 2, QTableWidgetItem("Bekliyor"))
            self.table.setItem(row, 3, QTableWidgetItem("-"))
        self.count_badge.setText(f"{len(self.file_paths)} Görsel")

    def _on_add_files(self) -> None:
        """Prompt user to add image files to batch queue."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Temizlenecek Görselleri Seçin",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.tiff *.bmp *.gif);;All Files (*.*)",
        )
        if paths:
            for p in paths:
                p_obj = Path(p)
                if p_obj not in self.file_paths:
                    self.file_paths.append(p_obj)
            self._update_table()

    def _on_clear_list(self) -> None:
        self.file_paths.clear()
        self._update_table()

    def _on_start_batch(self) -> None:
        """Start asynchronous batch processing worker."""
        if not self.file_paths:
            QMessageBox.warning(self, "Uyarı", "Lütfen önce temizlenecek görselleri ekleyin.")
            return

        cfg = CleanConfig(
            preset=CleaningPreset(self.preset_combo.currentData()),
            preserve_icc=self.cb_preserve_icc.isChecked(),
            anonymize_filename=self.cb_anonymize.isChecked(),
        )

        self.btn_start_batch.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self.worker = BatchMetadataCleanerWorker(self.file_paths, config=cfg, parent=self)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.item_cleaned.connect(self._on_item_cleaned)
        self.worker.finished.connect(self._on_batch_finished)
        self.worker.start()

    def _on_worker_progress(self, current: int, total: int, filename: str) -> None:
        pct = int((current / max(1, total)) * 100)
        self.progress_bar.setValue(pct)
        self.subtitle_lbl.setText(f"İşleniyor: ({current}/{total}) — {filename}")

    def _on_item_cleaned(self, res: CleanResult) -> None:
        if not res.input_path:
            return
        try:
            row = self.file_paths.index(res.input_path)
            status_item = QTableWidgetItem("✅ Temizlendi" if res.success else "❌ Hata")
            status_item.setForeground(QColor("#34D399") if res.success else QColor("#F87171"))
            self.table.setItem(row, 2, status_item)
            self.table.setItem(row, 3, QTableWidgetItem(f"-{res.removed_fields_count} alan"))
        except ValueError:
            pass

    def _on_batch_finished(self, results: List[CleanResult]) -> None:
        self.progress_bar.hide()
        self.btn_start_batch.setEnabled(True)
        self.results = results
        success_cnt = sum(1 for r in results if r.success)
        total_removed = sum(r.removed_fields_count for r in results)

        self.subtitle_lbl.setText(f"Tamamlandı: {success_cnt}/{len(results)} görsel başarıyla temizlendi.")
        NotificationManager.show_toast(
            "Toplu Temizlik Tamamlandı 🛡️",
            f"{success_cnt} görsel temizlendi, toplam {total_removed} metadata alanı kaldırıldı.",
            "privacy",
            3500,
        )

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)
        super().closeEvent(event)

