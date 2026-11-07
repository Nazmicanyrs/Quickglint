"""Comprehensive Export Preview, Print, Metadata, and PDF Security Dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.pdf.document import PDFDocument, QualityLevel
from app.pdf.pdf_generator import PDFExportWorker, PDFGenerator
from app.pdf.render_engine import PDFRenderEngine
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS


class PDFExportPreviewDialog(QDialog):
    """Dialog showing real-time multi-page preview, security encryption, quality controls, metadata, and printing."""

    def __init__(self, doc: PDFDocument, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export PDF Document — Quickglint")
        self.resize(850, 620)
        self.setStyleSheet(DARK_THEME_QSS)

        self.document = doc
        self.current_preview_page_idx = 0
        self._export_worker: Optional[PDFExportWorker] = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # LEFT: Live Preview Canvas Area
        left_card = QFrame(self)
        left_card.setStyleSheet("background-color: #1E293B; border-radius: 8px;")
        l_left = QVBoxLayout(left_card)

        # Nav Header
        nav_row = QHBoxLayout()
        self.btn_prev_p = QPushButton("◀ Prev", self)
        self.btn_prev_p.clicked.connect(self._prev_page)
        nav_row.addWidget(self.btn_prev_p)

        self.lbl_page_info = QLabel("Page 1 of 1", self)
        self.lbl_page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page_info.setStyleSheet("font-weight: bold; color: #38BDF8;")
        nav_row.addWidget(self.lbl_page_info)

        self.btn_next_p = QPushButton("Next ▶", self)
        self.btn_next_p.clicked.connect(self._next_page)
        nav_row.addWidget(self.btn_next_p)
        l_left.addLayout(nav_row)

        # Preview Image Container
        self.scroll_preview = QScrollArea(self)
        self.scroll_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_preview.setStyleSheet("border: none; background-color: #0B0F19;")

        self.lbl_preview_img = QLabel(self)
        self.lbl_preview_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_preview.setWidget(self.lbl_preview_img)
        l_left.addWidget(self.scroll_preview)

        main_layout.addWidget(left_card, stretch=6)

        # RIGHT: Settings Tabs
        right_card = QFrame(self)
        right_card.setFixedWidth(340)
        right_card.setStyleSheet("background-color: #1E293B; border-radius: 8px;")
        l_right = QVBoxLayout(right_card)

        self.tabs = QTabWidget(self)

        # Tab 1: Quality & Compression
        tab_qual = QWidget()
        l_q = QVBoxLayout(tab_qual)

        l_q.addWidget(QLabel("Quality Preset:"))
        self.combo_quality = QComboBox()
        for q in QualityLevel:
            self.combo_quality.addItem(q.value, q)
        self.combo_quality.setCurrentText(self.document.settings.quality.value)
        l_q.addWidget(self.combo_quality)

        l_q.addWidget(QLabel("JPEG Quality (%):"))
        self.spin_jpeg_q = QSpinBox()
        self.spin_jpeg_q.setRange(40, 100)
        self.spin_jpeg_q.setValue(self.document.settings.jpeg_quality_pct)
        l_q.addWidget(self.spin_jpeg_q)

        l_q.addWidget(QLabel("Resolution DPI:"))
        self.combo_dpi = QComboBox()
        self.combo_dpi.addItems(["150 DPI (Screen/Web)", "300 DPI (High Quality Print)", "600 DPI (Ultra Fine)"])
        self.combo_dpi.setCurrentIndex(1)
        l_q.addWidget(self.combo_dpi)

        self.chk_ocr_searchable = QCheckBox("Generate Searchable OCR Text Layer")
        self.chk_ocr_searchable.setChecked(self.document.settings.include_ocr_layer)
        l_q.addWidget(self.chk_ocr_searchable)

        l_q.addStretch()
        self.tabs.addTab(tab_qual, "⚡ Quality")

        # Tab 2: Document Metadata
        tab_meta = QWidget()
        l_m = QVBoxLayout(tab_meta)

        l_m.addWidget(QLabel("Document Title:"))
        self.edit_title = QLineEdit(self.document.settings.title)
        l_m.addWidget(self.edit_title)

        l_m.addWidget(QLabel("Author:"))
        self.edit_author = QLineEdit(self.document.settings.author)
        l_m.addWidget(self.edit_author)

        l_m.addWidget(QLabel("Subject:"))
        self.edit_subject = QLineEdit(self.document.settings.subject)
        l_m.addWidget(self.edit_subject)

        l_m.addWidget(QLabel("Keywords:"))
        self.edit_keywords = QLineEdit(self.document.settings.keywords)
        l_m.addWidget(self.edit_keywords)

        l_m.addStretch()
        self.tabs.addTab(tab_meta, "📋 Metadata")

        # Tab 3: Security & Encryption
        tab_sec = QWidget()
        l_s = QVBoxLayout(tab_sec)

        self.chk_enable_sec = QCheckBox("Enable Password Protection")
        self.chk_enable_sec.setChecked(self.document.settings.security.enabled)
        l_s.addWidget(self.chk_enable_sec)

        l_s.addWidget(QLabel("Open Password:"))
        self.edit_pass = QLineEdit(self.document.settings.security.user_password)
        self.edit_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pass.setPlaceholderText("Password required to view")
        l_s.addWidget(self.edit_pass)

        self.chk_allow_print = QCheckBox("Allow Document Printing")
        self.chk_allow_print.setChecked(self.document.settings.security.allow_printing)
        l_s.addWidget(self.chk_allow_print)

        self.chk_allow_copy = QCheckBox("Allow Content Copying")
        self.chk_allow_copy.setChecked(self.document.settings.security.allow_copying)
        l_s.addWidget(self.chk_allow_copy)

        l_s.addStretch()
        self.tabs.addTab(tab_sec, "🔒 Security")

        l_right.addWidget(self.tabs)

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        l_right.addWidget(self.progress_bar)

        # Action Buttons
        btn_print = QPushButton("🖨️ Print Document...", self)
        btn_print.clicked.connect(self._on_print_clicked)
        l_right.addWidget(btn_print)

        btn_export = QPushButton("💾 Save PDF File", self)
        btn_export.setStyleSheet("background-color: #2563EB; font-weight: bold; padding: 10px; color: white; border-radius: 6px;")
        btn_export.clicked.connect(self._on_export_clicked)
        l_right.addWidget(btn_export)

        main_layout.addWidget(right_card)

        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not self.document.pages:
            return
        self.current_preview_page_idx = max(0, min(self.current_preview_page_idx, len(self.document.pages) - 1))
        page = self.document.pages[self.current_preview_page_idx]

        total = len(self.document.pages)
        self.lbl_page_info.setText(f"Page {self.current_preview_page_idx + 1} of {total}")
        self.btn_prev_p.setEnabled(self.current_preview_page_idx > 0)
        self.btn_next_p.setEnabled(self.current_preview_page_idx < total - 1)

        # Render high quality preview image
        preview_img = PDFRenderEngine.render_page_to_image(page, doc_settings=self.document.settings, max_dim=500)
        self.lbl_preview_img.setPixmap(QPixmap.fromImage(preview_img))
        self.lbl_preview_img.adjustSize()

    def _prev_page(self) -> None:
        if self.current_preview_page_idx > 0:
            self.current_preview_page_idx -= 1
            self._refresh_preview()

    def _next_page(self) -> None:
        if self.current_preview_page_idx < len(self.document.pages) - 1:
            self.current_preview_page_idx += 1
            self._refresh_preview()

    def _apply_settings_from_ui(self) -> None:
        self.document.settings.title = self.edit_title.text().strip() or "Quickglint Document"
        self.document.settings.author = self.edit_author.text().strip()
        self.document.settings.subject = self.edit_subject.text().strip()
        self.document.settings.keywords = self.edit_keywords.text().strip()

        self.document.settings.quality = self.combo_quality.currentData()
        self.document.settings.jpeg_quality_pct = self.spin_jpeg_q.value()
        dpi_str = self.combo_dpi.currentText()
        if "150" in dpi_str:
            self.document.settings.dpi = 150
        elif "600" in dpi_str:
            self.document.settings.dpi = 600
        else:
            self.document.settings.dpi = 300

        self.document.settings.include_ocr_layer = self.chk_ocr_searchable.isChecked()

        self.document.settings.security.enabled = self.chk_enable_sec.isChecked()
        self.document.settings.security.user_password = self.edit_pass.text()
        self.document.settings.security.allow_printing = self.chk_allow_print.isChecked()
        self.document.settings.security.allow_copying = self.chk_allow_copy.isChecked()

    def _on_export_clicked(self) -> None:
        self._apply_settings_from_ui()
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF File", f"{self.document.settings.title}.pdf", "PDF Documents (*.pdf)")
        if not path:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self._export_worker = PDFExportWorker(
            output_path=path,
            document=self.document,
        )
        self._export_worker.progress.connect(lambda cur, tot: self.progress_bar.setValue(int(cur / max(1, tot) * 100)))
        self._export_worker.finished_success.connect(self._on_export_success)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.start()

    def _on_export_success(self, output_path: str) -> None:
        self.progress_bar.setVisible(False)
        NotificationManager.show_toast(
            "PDF Exported 📄",
            f"Successfully generated PDF:\n{Path(output_path).name}",
        )
        self.accept()

    def _on_export_failed(self, err_msg: str) -> None:
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "PDF Export Error", f"Failed to generate PDF:\n\n{err_msg}")

    def _on_print_clicked(self) -> None:
        self._apply_settings_from_ui()
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() == QPrintDialog.DialogCode.Accepted:
            painter = QPainter(printer)
            total = len(self.document.pages)
            for idx, page in enumerate(self.document.pages):
                if idx > 0:
                    printer.newPage()
                PDFRenderEngine.render_page(painter, page, doc_settings=self.document.settings, page_index=idx + 1, total_pages=total)
            painter.end()
            NotificationManager.show_toast("Print Sent 🖨️", "Document successfully sent to printer.")

