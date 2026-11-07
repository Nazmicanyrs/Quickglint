"""Dedicated Text Extraction (OCR) Dialog with interactive selection, editing, and exports."""

from pathlib import Path
from typing import Optional, Set
from PIL import Image
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ocr.formatter import TextFormatter
from app.ocr.models import OCRStructuredResult
from app.ocr.overlay_widget import OCRHighlightOverlay
from app.ocr.preprocessing import ImagePreprocessor, qimage_to_pil
from app.ocr.provider import AutoOCRProvider, OCRProvider
from app.ocr.worker import OCRWorker
from app.services.clipboard_service import ClipboardService
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.logger import logger


class TextExtractionDialog(QDialog):
    """Full-featured OCR extraction panel with interactive image highlight, editable text, and multi-format exports."""

    text_copied = Signal(str)

    def __init__(
        self,
        image: QImage | Image.Image,
        initial_result: Optional[OCRStructuredResult] = None,
        provider: Optional[OCRProvider] = None,
        languages: Optional[list[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.image = image
        self.provider = provider or AutoOCRProvider()
        self.languages = languages or ["tr", "en"]
        self.ocr_result: Optional[OCRStructuredResult] = initial_result
        self._worker: Optional[OCRWorker] = None

        if isinstance(image, QImage):
            self.base_pixmap = QPixmap.fromImage(image)
        else:
            from app.ocr.preprocessing import pil_to_qimage
            self.base_pixmap = QPixmap.fromImage(pil_to_qimage(image))

        self.setWindowTitle("Quickglint — Görselden Metin Çıkar (OCR / Extract Text)")
        self.setMinimumSize(950, 620)
        self.resize(1100, 700)
        self.setStyleSheet(DARK_THEME_QSS)

        self._setup_ui()
        self._setup_shortcuts()

        if self.ocr_result is None:
            enhance_cfg = False
            try:
                from config.config_manager import ConfigManager
                enhance_cfg = bool(ConfigManager().get("ocr", "enhance_contrast", False))
            except Exception:
                enhance_cfg = False
            self._start_ocr_worker(enhance=enhance_cfg)
        else:
            self._display_results(self.ocr_result)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Top Header Bar with Metrics & Glass Card
        top_bar = QFrame(self)
        top_bar.setStyleSheet(
            "QFrame { background-color: rgba(15, 23, 42, 0.95); border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 10px; padding: 6px 12px; }"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 6, 8, 6)
        top_layout.setSpacing(12)

        self.title_icon_lbl = QLabel(top_bar)
        self.title_icon_lbl.setPixmap(get_icon("ocr", "#38BDF8", 22).pixmap(22, 22))
        top_layout.addWidget(self.title_icon_lbl)

        self.title_lbl = QLabel("Görsel Metin Analizi (OCR)", top_bar)
        self.title_lbl.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 14px;")
        top_layout.addWidget(self.title_lbl)

        self.engine_badge = QLabel("Motor: Yerel Analiz", top_bar)
        self.engine_badge.setStyleSheet(
            "background-color: rgba(30, 41, 59, 0.8); color: #94A3B8; border: 1px solid rgba(255, 255, 255, 0.08); "
            "padding: 3px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 500;"
        )
        top_layout.addWidget(self.engine_badge)

        top_layout.addStretch()

        # Stats badges
        self.stats_lbl = QLabel("0 Karakter  •  0 Kelime", top_bar)
        self.stats_lbl.setStyleSheet(
            "background-color: rgba(30, 41, 59, 0.8); color: #CBD5E1; border: 1px solid rgba(255, 255, 255, 0.08); "
            "padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;"
        )
        top_layout.addWidget(self.stats_lbl)

        self.conf_badge = QLabel("Güvenilirlik: -", top_bar)
        self.conf_badge.setStyleSheet(
            "background-color: rgba(30, 41, 59, 0.8); color: #E2E8F0; padding: 3px 12px; "
            "border-radius: 12px; font-size: 12px; font-weight: 600;"
        )
        top_layout.addWidget(self.conf_badge)

        main_layout.addWidget(top_bar)

        # Progress Bar (for async OCR runs)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #0F172A; border: none; border-radius: 2px; } "
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:1 #2563EB); border-radius: 2px; }"
        )
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)

        # 2. Main Central Splitter (Left: Interactive Image, Right: Text Editor)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)

        # Left: Image Scroll Area
        self.scroll_area = QScrollArea(self.splitter)
        self.scroll_area.setStyleSheet(
            "QScrollArea { background-color: #070D17; border: 1px solid #1E293B; border-radius: 8px; }"
        )
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.overlay_widget: Optional[OCRHighlightOverlay] = None
        self.splitter.addWidget(self.scroll_area)

        # Right: Text Editor & Actions
        right_panel = QFrame(self.splitter)
        right_panel.setStyleSheet(
            "QFrame { background-color: #0F172A; border: 1px solid #1E293B; border-radius: 8px; }"
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        editor_header_layout = QHBoxLayout()
        editor_title = QLabel("Düzenlenebilir Metin", right_panel)
        editor_title.setStyleSheet("color: #F8FAFC; font-weight: 600; font-size: 13px;")
        editor_header_layout.addWidget(editor_title)

        editor_header_layout.addStretch()

        self.select_all_btn = QPushButton("Tümünü Seç", right_panel)
        self.select_all_btn.setIcon(get_icon("check", "#38BDF8", 14))
        self.select_all_btn.setIconSize(QSize(13, 13))
        self.select_all_btn.setFixedHeight(28)
        self.select_all_btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 5px; font-size: 11.5px; font-weight: 600; padding: 2px 10px; } "
            "QPushButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: #38BDF8; color: #FFFFFF; }"
        )
        self.select_all_btn.clicked.connect(self._select_all_words)
        editor_header_layout.addWidget(self.select_all_btn)

        self.normalize_btn = QPushButton("Metni Düzelt", right_panel)
        self.normalize_btn.setIcon(get_icon("sparkles", "#F59E0B", 14))
        self.normalize_btn.setIconSize(QSize(13, 13))
        self.normalize_btn.setFixedHeight(28)
        self.normalize_btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 5px; font-size: 11.5px; font-weight: 600; padding: 2px 10px; } "
            "QPushButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: #F59E0B; color: #FFFFFF; }"
        )
        self.normalize_btn.clicked.connect(self._on_normalize_text)
        editor_header_layout.addWidget(self.normalize_btn)

        right_layout.addLayout(editor_header_layout)

        self.text_editor = QTextEdit(right_panel)
        self.text_editor.setStyleSheet(
            "QTextEdit { background-color: #070D17; color: #F8FAFC; border: 1px solid #1E293B; "
            "border-radius: 6px; font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'Consolas', monospace; "
            "font-size: 13.5px; line-height: 1.5; padding: 10px; selection-background-color: #2563EB; selection-color: #FFFFFF; }"
        )
        self.text_editor.textChanged.connect(self._on_text_edited)
        right_layout.addWidget(self.text_editor, stretch=1)

        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([480, 520])
        main_layout.addWidget(self.splitter, stretch=1)

        # 3. Bottom Action Bar
        bottom_bar = QFrame(self)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(8)

        # Enhanced Retry Button
        self.retry_enhanced_btn = QPushButton("Gelişmiş OCR", bottom_bar)
        self.retry_enhanced_btn.setIcon(get_icon("optimize", "#C084FC", 16))
        self.retry_enhanced_btn.setIconSize(QSize(15, 15))
        self.retry_enhanced_btn.setFixedHeight(34)
        self.retry_enhanced_btn.setStyleSheet(
            "QPushButton { background-color: rgba(99, 102, 241, 0.18); color: #C084FC; font-weight: 600; font-size: 12.5px; "
            "border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 6px; padding: 0 12px; } "
            "QPushButton:hover { background-color: rgba(99, 102, 241, 0.32); border-color: #C084FC; color: #FFFFFF; }"
        )
        self.retry_enhanced_btn.setToolTip("Bulanık veya küçük yazılar için 2x/3x kontrast artırıcı gelişmiş OCR çalıştırır.")
        self.retry_enhanced_btn.clicked.connect(self._on_retry_enhanced)
        bottom_layout.addWidget(self.retry_enhanced_btn)

        bottom_layout.addStretch()

        btn_style_export = (
            "QPushButton { background-color: rgba(30, 41, 59, 0.85); color: #F1F5F9; font-weight: 600; font-size: 12px; "
            "border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 0 10px; } "
            "QPushButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: rgba(255, 255, 255, 0.25); color: #FFFFFF; }"
        )

        # Save TXT / MD / JSON
        self.save_txt_btn = QPushButton("TXT", bottom_bar)
        self.save_txt_btn.setIcon(get_icon("file_text", "#38BDF8", 15))
        self.save_txt_btn.setIconSize(QSize(14, 14))
        self.save_txt_btn.setFixedHeight(34)
        self.save_txt_btn.setStyleSheet(btn_style_export)
        self.save_txt_btn.clicked.connect(self._save_txt)
        bottom_layout.addWidget(self.save_txt_btn)

        self.save_md_btn = QPushButton("Markdown", bottom_bar)
        self.save_md_btn.setIcon(get_icon("code", "#A78BFA", 15))
        self.save_md_btn.setIconSize(QSize(14, 14))
        self.save_md_btn.setFixedHeight(34)
        self.save_md_btn.setStyleSheet(btn_style_export)
        self.save_md_btn.clicked.connect(self._save_markdown)
        bottom_layout.addWidget(self.save_md_btn)

        self.save_json_btn = QPushButton("JSON", bottom_bar)
        self.save_json_btn.setIcon(get_icon("code", "#FBBF24", 15))
        self.save_json_btn.setIconSize(QSize(14, 14))
        self.save_json_btn.setFixedHeight(34)
        self.save_json_btn.setStyleSheet(btn_style_export)
        self.save_json_btn.clicked.connect(self._save_json)
        bottom_layout.addWidget(self.save_json_btn)

        # Copy Selected
        self.copy_selected_btn = QPushButton("Seçilenleri Kopyala", bottom_bar)
        self.copy_selected_btn.setIcon(get_icon("copy", "#38BDF8", 16))
        self.copy_selected_btn.setIconSize(QSize(15, 15))
        self.copy_selected_btn.setFixedHeight(34)
        self.copy_selected_btn.setStyleSheet(
            "QPushButton { background-color: rgba(2, 132, 199, 0.2); color: #38BDF8; font-weight: 600; font-size: 12.5px; "
            "border: 1px solid #0284C7; border-radius: 6px; padding: 0 12px; } "
            "QPushButton:hover { background-color: #0284C7; color: #FFFFFF; }"
        )
        self.copy_selected_btn.clicked.connect(self._copy_selected)
        bottom_layout.addWidget(self.copy_selected_btn)

        # Copy All (Primary)
        self.copy_all_btn = QPushButton("Tümünü Kopyala (Ctrl+Shift+C)", bottom_bar)
        self.copy_all_btn.setIcon(get_icon("copy", "#FFFFFF", 16))
        self.copy_all_btn.setIconSize(QSize(15, 15))
        self.copy_all_btn.setFixedHeight(34)
        self.copy_all_btn.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1D4ED8); "
            "color: #FFFFFF; font-weight: 700; font-size: 12.5px; border: 1px solid #60A5FA; border-radius: 6px; padding: 0 16px; } "
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3B82F6, stop:1 #2563EB); border-color: #93C5FD; }"
        )
        self.copy_all_btn.clicked.connect(self._copy_all)
        bottom_layout.addWidget(self.copy_all_btn)

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

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Shift+C"), self, self._copy_all)
        QShortcut(QKeySequence("Ctrl+S"), self, self._save_txt)

    def _start_ocr_worker(self, enhance: bool = False) -> None:
        self._current_enhanced = enhance
        self.progress_bar.setValue(10)
        self.progress_bar.show()
        self.retry_enhanced_btn.setEnabled(False)
        if enhance:
            self.retry_enhanced_btn.setText("Normal Kontrast")
            self.retry_enhanced_btn.setToolTip("Normal kontrast modunda yeniden tara.")
        else:
            self.retry_enhanced_btn.setText("Gelişmiş Kontrast")
            self.retry_enhanced_btn.setToolTip("Bulanık veya küçük yazılar için 2x/3x kontrast artırıcı gelişmiş OCR çalıştırır.")

        self._worker = OCRWorker(
            image=self.image,
            provider=self.provider,
            languages=self.languages,
            enhance=enhance,
            use_cache=not enhance,
            parent=self,
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_worker_progress(self, val: int, msg: str) -> None:
        self.progress_bar.setValue(val)
        self.engine_badge.setText(f"Durum: {msg}")

    def _on_worker_finished(self, result: OCRStructuredResult) -> None:
        self.progress_bar.hide()
        self.retry_enhanced_btn.setEnabled(True)
        self._display_results(result)

    def _on_worker_error(self, err_msg: str) -> None:
        self.progress_bar.hide()
        self.retry_enhanced_btn.setEnabled(True)
        QMessageBox.warning(self, "OCR Hatası", err_msg)

    def _display_results(self, result: OCRStructuredResult) -> None:
        self.ocr_result = result
        self.engine_badge.setText(f"🟢 {result.provider_name} • {result.execution_time_ms:.0f} ms")
        self.engine_badge.setStyleSheet(
            "background-color: rgba(30, 41, 59, 0.85); color: #E2E8F0; border: 1px solid rgba(56, 189, 248, 0.3); "
            "padding: 3px 10px; border-radius: 12px; font-size: 11.5px; font-weight: 600;"
        )

        # Update text editor
        self.text_editor.setPlainText(result.full_text)

        # Update overlay widget
        if self.overlay_widget is None:
            self.overlay_widget = OCRHighlightOverlay(
                base_pixmap=self.base_pixmap,
                ocr_result=result,
                parent=self.scroll_area,
            )
            self.overlay_widget.selection_changed.connect(self._on_overlay_selection_changed)
            self.scroll_area.setWidget(self.overlay_widget)
        else:
            self.overlay_widget.set_ocr_result(result)

        self._update_metrics()

    def _on_overlay_selection_changed(self, selected_ids: Set[str]) -> None:
        if self.ocr_result:
            if not selected_ids:
                self.text_editor.setPlainText("")
            elif len(selected_ids) == len(self.ocr_result.get_all_words()):
                self.text_editor.setPlainText(self.ocr_result.full_text)
            else:
                sel_text = self.ocr_result.get_selected_text(selected_ids)
                self.text_editor.setPlainText(sel_text)
        self._update_metrics()

    def _on_text_edited(self) -> None:
        self._update_metrics()

    def _update_metrics(self) -> None:
        text = self.text_editor.toPlainText()
        char_count = len(text)
        word_count = len(text.split()) if text.strip() else 0
        self.stats_lbl.setText(f"📊 {char_count} Karakter  •  {word_count} Kelime")

        if self.ocr_result:
            conf = self.ocr_result.average_confidence
            if conf >= 0.85:
                self.conf_badge.setText(f"🛡️ %{int(conf*100)} Yüksek Doğruluk")
                self.conf_badge.setStyleSheet(
                    "background-color: rgba(5, 150, 105, 0.2); color: #34D399; border: 1px solid rgba(52, 211, 153, 0.4); "
                    "padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;"
                )
            elif conf >= 0.70:
                self.conf_badge.setText(f"🔹 %{int(conf*100)} Orta Doğruluk")
                self.conf_badge.setStyleSheet(
                    "background-color: rgba(37, 99, 235, 0.2); color: #60A5FA; border: 1px solid rgba(96, 165, 250, 0.4); "
                    "padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;"
                )
            else:
                self.conf_badge.setText(f"⚠ %{int(conf*100)} Düşük Doğruluk")
                self.conf_badge.setStyleSheet(
                    "background-color: rgba(217, 119, 6, 0.2); color: #FBBF24; border: 1px solid rgba(251, 191, 36, 0.4); "
                    "padding: 3px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;"
                )

    def _select_all_words(self) -> None:
        if self.overlay_widget and self.ocr_result:
            self.overlay_widget.select_all()
            self.text_editor.setPlainText(self.ocr_result.full_text)

    def _on_normalize_text(self) -> None:
        current_text = self.text_editor.toPlainText()
        normalized = TextFormatter.normalize_turkish_text(current_text)
        self.text_editor.setPlainText(normalized)

    def _on_retry_enhanced(self) -> None:
        is_enhanced = getattr(self, "_current_enhanced", False)
        self._start_ocr_worker(enhance=not is_enhanced)

    def _copy_all(self) -> None:
        """Copy all text to clipboard directly without saving to clipboard history."""
        text = self.text_editor.toPlainText().strip()
        if not text and self.ocr_result:
            text = self.ocr_result.full_text.strip()
        
        if text:
            self._last_copied_text = text
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
                QApplication.processEvents()
            NotificationManager.show_toast("Metin Kopyalandı 📋", f"{len(text.split())} kelime panoya kopyalandı.", "copy", 2500)
            self.text_copied.emit(text)

    def _copy_selected(self) -> None:
        """Copy selected text from editor or overlay."""
        cursor = self.text_editor.textCursor()
        if cursor.hasSelection():
            text = cursor.selectedText()
        else:
            text = self.text_editor.toPlainText().strip()

        if text:
            self._last_copied_text = text
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
                QApplication.processEvents()
            NotificationManager.show_toast("Seçili Metin Kopyalandı 📋", f"{len(text.split())} kelime panoya kopyalandı.", "copy", 2500)
            self.text_copied.emit(text)

    def _save_txt(self) -> None:
        if not self.ocr_result:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Metni Kaydet (TXT)",
            "ocr_extracted_text.txt",
            "Text File (*.txt);;All Files (*.*)",
        )
        if filepath:
            text = TextFormatter.to_plaintext(self.ocr_result, self.text_editor.toPlainText())
            Path(filepath).write_text(text, encoding="utf-8")
            NotificationManager.show_toast("TXT Kaydedildi 💾", f"Dosya: {Path(filepath).name}", "save", 3000)

    def _save_markdown(self) -> None:
        if not self.ocr_result:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Markdown Olarak Kaydet",
            "ocr_extracted_text.md",
            "Markdown File (*.md);;All Files (*.*)",
        )
        if filepath:
            md = TextFormatter.to_markdown(self.ocr_result, self.text_editor.toPlainText())
            Path(filepath).write_text(md, encoding="utf-8")
            NotificationManager.show_toast("Markdown Kaydedildi 💾", f"Dosya: {Path(filepath).name}", "save", 3000)

    def _save_json(self) -> None:
        if not self.ocr_result:
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "JSON Olarak Kaydet",
            "ocr_extracted_blocks.json",
            "JSON File (*.json);;All Files (*.*)",
        )
        if filepath:
            json_str = TextFormatter.to_json_string(self.ocr_result, self.text_editor.toPlainText())
            Path(filepath).write_text(json_str, encoding="utf-8")
            NotificationManager.show_toast("JSON Kaydedildi 💾", f"Dosya: {Path(filepath).name}", "save", 3000)

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1000)
        super().closeEvent(event)

