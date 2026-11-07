"""Professional PDF Export & Print Dialog with real-time preview, reordering, and layout controls."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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

from app.pdf.geometry import get_paper_dimensions_mm
from app.pdf.image_loader import create_source_from_qimage, load_image_from_file
from app.pdf.models import (
    FitMode,
    HeaderFooterConfig,
    LayoutMode,
    MarginConfig,
    MetadataConfig,
    PageNumberPosition,
    PageOrientation,
    PaperSizePreset,
    PDFExportOptions,
    PDFSourceItem,
    QualityLevel,
)
from app.pdf.pdf_generator import PDFExportWorker, PDFGenerator
from app.pdf.preview_renderer import PDFPreviewRenderer
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.logger import logger

PDF_DIALOG_QSS = """
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

QListWidget {
    background-color: #0F172A;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 4px;
    color: #F8FAFC;
}

QListWidget::item {
    border-radius: 6px;
    padding: 6px;
    margin-bottom: 2px;
}

QListWidget::item:selected {
    background-color: #2563EB;
    color: #FFFFFF;
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


class PDFExportDialog(QDialog):
    """Main PDF Export configuration and preview dialog."""

    def __init__(
        self,
        items: Optional[List[PDFSourceItem]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export to PDF / Print — Quickglint")
        self.resize(1080, 720)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(PDF_DIALOG_QSS)

        self.items: List[PDFSourceItem] = items or []
        self.options = PDFExportOptions()
        self.preview_renderer = PDFPreviewRenderer(self.options)

        self.current_preview_page = 1
        self._export_worker: Optional[PDFExportWorker] = None

        self._setup_ui()
        self._populate_item_list()
        self._update_preview()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(10)

        # 3-Panel Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # -------------------------------------------------------------
        # LEFT: Item Reordering & Thumbnails
        # -------------------------------------------------------------
        left_card = QFrame(self)
        left_card.setObjectName("card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        left_title = QLabel("<b>📄 Sayfalar & Görseller</b>", left_card)
        left_title.setStyleSheet("font-size: 14px; color: #38BDF8;")
        left_layout.addWidget(left_title)

        self.list_widget = QListWidget(left_card)
        self.list_widget.setIconSize(QSize(48, 48))
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_widget.model().rowsMoved.connect(self._on_item_rows_moved)
        self.list_widget.currentRowChanged.connect(self._on_list_selection_changed)
        left_layout.addWidget(self.list_widget)

        # List Buttons Toolbar
        list_btn_layout = QHBoxLayout()
        list_btn_layout.setSpacing(6)

        self.btn_add = QPushButton("➕ Ekle", left_card)
        self.btn_add.setObjectName("secondaryBtn")
        self.btn_add.clicked.connect(self._on_add_images)
        list_btn_layout.addWidget(self.btn_add)

        self.btn_remove = QPushButton("🗑️ Sil", left_card)
        self.btn_remove.setObjectName("secondaryBtn")
        self.btn_remove.clicked.connect(self._on_remove_item)
        list_btn_layout.addWidget(self.btn_remove)

        self.btn_up = QPushButton("⬆️", left_card)
        self.btn_up.setObjectName("secondaryBtn")
        self.btn_up.clicked.connect(self._on_move_up)
        list_btn_layout.addWidget(self.btn_up)

        self.btn_down = QPushButton("⬇️", left_card)
        self.btn_down.setObjectName("secondaryBtn")
        self.btn_down.clicked.connect(self._on_move_down)
        list_btn_layout.addWidget(self.btn_down)

        left_layout.addLayout(list_btn_layout)
        splitter.addWidget(left_card)

        # -------------------------------------------------------------
        # CENTER: Interactive Preview Panel
        # -------------------------------------------------------------
        center_card = QFrame(self)
        center_card.setObjectName("card")
        center_layout = QVBoxLayout(center_card)
        center_layout.setContentsMargins(10, 10, 10, 10)
        center_layout.setSpacing(8)

        center_title = QLabel("<b>👁️ Canlı PDF Önizleme</b>", center_card)
        center_title.setStyleSheet("font-size: 14px; color: #38BDF8;")
        center_layout.addWidget(center_title)

        self.preview_scroll = QScrollArea(center_card)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setStyleSheet("background-color: #0B1120; border: 1px solid #1E293B; border-radius: 8px;")

        self.preview_label = QLabel(self.preview_scroll)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("padding: 10px;")
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setWidgetResizable(True)
        center_layout.addWidget(self.preview_scroll)

        # Preview Nav Bar
        nav_layout = QHBoxLayout()
        nav_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_prev_page = QPushButton("◀ Önceki", center_card)
        self.btn_prev_page.setObjectName("secondaryBtn")
        self.btn_prev_page.clicked.connect(self._on_prev_page)
        nav_layout.addWidget(self.btn_prev_page)

        self.page_indicator_lbl = QLabel("Sayfa 1 / 1", center_card)
        self.page_indicator_lbl.setStyleSheet("font-weight: 600; padding: 0 12px; color: #F8FAFC;")
        nav_layout.addWidget(self.page_indicator_lbl)

        self.btn_next_page = QPushButton("Sonraki ▶", center_card)
        self.btn_next_page.setObjectName("secondaryBtn")
        self.btn_next_page.clicked.connect(self._on_next_page)
        nav_layout.addWidget(self.btn_next_page)

        center_layout.addLayout(nav_layout)
        splitter.addWidget(center_card)

        # -------------------------------------------------------------
        # RIGHT: Options & Settings Tabs
        # -------------------------------------------------------------
        right_card = QFrame(self)
        right_card.setObjectName("card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(8)

        right_title = QLabel("<b>⚙️ PDF Ayarları</b>", right_card)
        right_title.setStyleSheet("font-size: 14px; color: #38BDF8;")
        right_layout.addWidget(right_title)

        self.settings_tabs = QTabWidget(right_card)

        # 1. Page & Layout Tab
        tab_layout_widget = QWidget()
        tl_layout = QVBoxLayout(tab_layout_widget)
        tl_layout.setSpacing(10)

        # Paper Size
        box_paper = QGroupBox("Kağıt Boyutu & Yön", tab_layout_widget)
        b_p_layout = QVBoxLayout(box_paper)
        self.combo_paper = QComboBox(box_paper)
        for p in PaperSizePreset:
            self.combo_paper.addItem(p.value, p)
        self.combo_paper.currentIndexChanged.connect(self._on_options_changed)
        b_p_layout.addWidget(self.combo_paper)

        self.combo_orientation = QComboBox(box_paper)
        for o in PageOrientation:
            self.combo_orientation.addItem(f"Yön: {o.value}", o)
        self.combo_orientation.currentIndexChanged.connect(self._on_options_changed)
        b_p_layout.addWidget(self.combo_orientation)
        tl_layout.addWidget(box_paper)

        # Image Fit Mode
        box_fit = QGroupBox("Görüntü Yerleşimi (Fit Mode)", tab_layout_widget)
        b_f_layout = QVBoxLayout(box_fit)
        self.combo_fit = QComboBox(box_fit)
        for f in FitMode:
            self.combo_fit.addItem(f.value, f)
        self.combo_fit.currentIndexChanged.connect(self._on_options_changed)
        b_f_layout.addWidget(self.combo_fit)

        # Layout Mode (Single, Grid, Contact Sheet)
        self.combo_layout_mode = QComboBox(box_fit)
        for lm in LayoutMode:
            self.combo_layout_mode.addItem(lm.value, lm)
        self.combo_layout_mode.currentIndexChanged.connect(self._on_options_changed)
        b_f_layout.addWidget(self.combo_layout_mode)
        tl_layout.addWidget(box_fit)

        # Margins
        box_margin = QGroupBox("Kenar Boşluğu (Margin)", tab_layout_widget)
        b_m_layout = QHBoxLayout(box_margin)
        b_m_layout.addWidget(QLabel("Boşluk (mm):", box_margin))
        self.spin_margin = QDoubleSpinBox(box_margin)
        self.spin_margin.setRange(0.0, 50.0)
        self.spin_margin.setValue(10.0)
        self.spin_margin.valueChanged.connect(self._on_options_changed)
        b_m_layout.addWidget(self.spin_margin)
        tl_layout.addWidget(box_margin)

        tl_layout.addStretch()
        self.settings_tabs.addTab(tab_layout_widget, "Sayfa & Düzen")

        # 2. Header, Footer & Numbers Tab
        tab_hf_widget = QWidget()
        thf_layout = QVBoxLayout(tab_hf_widget)
        thf_layout.setSpacing(10)

        box_hf = QGroupBox("Başlık & Altbilgi", tab_hf_widget)
        bhf_layout = QVBoxLayout(box_hf)

        bhf_layout.addWidget(QLabel("Üst Bilgi (Header):", box_hf))
        self.edit_header = QLineEdit(box_hf)
        self.edit_header.setPlaceholderText("Örn: Quickglint Screenshots")
        self.edit_header.textChanged.connect(self._on_options_changed)
        bhf_layout.addWidget(self.edit_header)

        bhf_layout.addWidget(QLabel("Alt Bilgi (Footer):", box_hf))
        self.edit_footer = QLineEdit(box_hf)
        self.edit_footer.setPlaceholderText("Örn: Gizli / Confidential")
        self.edit_footer.textChanged.connect(self._on_options_changed)
        bhf_layout.addWidget(self.edit_footer)
        thf_layout.addWidget(box_hf)

        box_num = QGroupBox("Sayfa Numarası", tab_hf_widget)
        bnum_layout = QVBoxLayout(box_num)
        self.combo_page_num_pos = QComboBox(box_num)
        for pnp in PageNumberPosition:
            self.combo_page_num_pos.addItem(pnp.value, pnp)
        self.combo_page_num_pos.setCurrentIndex(3)  # Bottom Right default
        self.combo_page_num_pos.currentIndexChanged.connect(self._on_options_changed)
        bnum_layout.addWidget(self.combo_page_num_pos)
        thf_layout.addWidget(box_num)

        thf_layout.addStretch()
        self.settings_tabs.addTab(tab_hf_widget, "Metin & Numara")

        # 3. Quality & Metadata Tab
        tab_qm_widget = QWidget()
        tqm_layout = QVBoxLayout(tab_qm_widget)
        tqm_layout.setSpacing(10)

        box_qual = QGroupBox("Baskı Kalitesi & DPI", tab_qm_widget)
        bq_layout = QVBoxLayout(box_qual)

        self.combo_quality = QComboBox(box_qual)
        for q in QualityLevel:
            self.combo_quality.addItem(q.value, q)
        self.combo_quality.currentIndexChanged.connect(self._on_options_changed)
        bq_layout.addWidget(self.combo_quality)

        self.combo_dpi = QComboBox(box_qual)
        for dpi_val in (150, 300, 600):
            self.combo_dpi.addItem(f"{dpi_val} DPI", dpi_val)
        self.combo_dpi.setCurrentIndex(1)  # 300 DPI default
        self.combo_dpi.currentIndexChanged.connect(self._on_options_changed)
        bq_layout.addWidget(self.combo_dpi)
        tqm_layout.addWidget(box_qual)

        box_meta = QGroupBox("PDF Belge Başlığı", tab_qm_widget)
        bm_layout = QVBoxLayout(box_meta)
        self.edit_title = QLineEdit(box_meta)
        self.edit_title.setText("Quickglint Export")
        self.edit_title.textChanged.connect(self._on_options_changed)
        bm_layout.addWidget(self.edit_title)
        tqm_layout.addWidget(box_meta)

        tqm_layout.addStretch()
        self.settings_tabs.addTab(tab_qm_widget, "Kalite & Bilgi")

        right_layout.addWidget(self.settings_tabs)
        splitter.addWidget(right_card)

        # Set initial splitter proportions (25% left, 45% center, 30% right)
        splitter.setSizes([260, 480, 320])
        main_layout.addWidget(splitter)

        # Progress Bar for background worker
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Bottom Actions Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self.btn_print = QPushButton("🖨️ Yazdır (Print)", self)
        self.btn_print.setObjectName("secondaryBtn")
        self.btn_print.clicked.connect(self._on_print)
        bottom_bar.addWidget(self.btn_print)

        self.btn_builder = QPushButton("🎨 PDF Düzenleyici Workspace", self)
        self.btn_builder.setObjectName("secondaryBtn")
        self.btn_builder.setStyleSheet("background-color: #1E293B; border: 1px solid #38BDF8; color: #38BDF8; font-weight: bold;")
        self.btn_builder.clicked.connect(self._on_open_builder)
        bottom_bar.addWidget(self.btn_builder)

        bottom_bar.addStretch()

        self.btn_cancel = QPushButton("İptal", self)
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        self.btn_export = QPushButton("💾 PDF Olarak Dışa Aktar", self)
        self.btn_export.setObjectName("primaryActionBtn")
        self.btn_export.clicked.connect(self._on_export_pdf)
        bottom_bar.addWidget(self.btn_export)

        main_layout.addLayout(bottom_bar)

    def _on_open_builder(self) -> None:
        """Transfers items into a new PDFDocument and opens the PDFEditorWindow."""
        from PySide6.QtWidgets import QApplication
        from app.pdf.document import PDFDocument
        from app.pdf.ui.editor_window import PDFEditorWindow

        images = []
        for item in self.items:
            img = item.get_image()
            if img and not img.isNull():
                images.append((img, item.title))

        if images:
            doc = PDFDocument.create_from_images(images)
        else:
            doc = PDFDocument.create_empty("New Document")

        app = QApplication.instance()
        if hasattr(app, "open_pdf_editor"):
            app.open_pdf_editor(doc=doc)
        else:
            editor = PDFEditorWindow(document=doc, parent=None)
            editor.show()
            editor.raise_()
            editor.activateWindow()

        self.accept()

    def _populate_item_list(self) -> None:
        self.list_widget.clear()
        for idx, item in enumerate(self.items):
            thumb = item.get_thumbnail(64)
            icon = QIcon(QPixmap.fromImage(thumb)) if thumb else QIcon()
            list_item = QListWidgetItem(icon, f"{idx+1}. {item.title}")
            self.list_widget.addItem(list_item)

    def _on_options_changed(self) -> None:
        """Reads UI controls into PDFExportOptions and refreshes live preview."""
        self.options.paper_size = self.combo_paper.currentData()
        self.options.orientation = self.combo_orientation.currentData()
        self.options.fit_mode = self.combo_fit.currentData()
        self.options.layout_mode = self.combo_layout_mode.currentData()

        margin_val = self.spin_margin.value()
        self.options.margins.set_all(margin_val)

        self.options.header_footer.header_text = self.edit_header.text()
        self.options.header_footer.footer_text = self.edit_footer.text()
        self.options.page_number_position = self.combo_page_num_pos.currentData()

        self.options.quality = self.combo_quality.currentData()
        self.options.dpi = int(self.combo_dpi.currentData() or 300)
        self.options.metadata.title = self.edit_title.text().strip() or "Quickglint Export"

        self.preview_renderer.update_options(self.options)
        self._update_preview()

    def _update_preview(self) -> None:
        if not self.items:
            self.preview_label.setText("Önizleme için en az bir görsel ekleyin.")
            self.page_indicator_lbl.setText("Sayfa 0 / 0")
            return

        total_pages = self.preview_renderer.get_total_pages(self.items)
        self.current_preview_page = max(1, min(self.current_preview_page, total_pages))

        pixmap = self.preview_renderer.render_page_pixmap(
            items=self.items,
            page_num=self.current_preview_page,
            preview_width_px=480,
        )
        self.preview_label.setPixmap(pixmap)
        self.page_indicator_lbl.setText(f"Sayfa {self.current_preview_page} / {total_pages}")

        self.btn_prev_page.setEnabled(self.current_preview_page > 1)
        self.btn_next_page.setEnabled(self.current_preview_page < total_pages)

    def _on_prev_page(self) -> None:
        if self.current_preview_page > 1:
            self.current_preview_page -= 1
            self._update_preview()

    def _on_next_page(self) -> None:
        total = self.preview_renderer.get_total_pages(self.items)
        if self.current_preview_page < total:
            self.current_preview_page += 1
            self._update_preview()

    def _on_add_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Görsel Ekle",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.gif);;All Files (*)",
        )
        if paths:
            for p in paths:
                try:
                    loaded = load_image_from_file(p)
                    self.items.extend(loaded)
                except Exception as exc:
                    QMessageBox.warning(self, "Uyarı", f"Görsel yüklenemedi: {p}\n{exc}")
            self._populate_item_list()
            self._on_options_changed()

    def _on_remove_item(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.items):
            del self.items[row]
            self._populate_item_list()
            self._on_options_changed()

    def _on_move_up(self) -> None:
        row = self.list_widget.currentRow()
        if row > 0:
            self.items[row], self.items[row - 1] = self.items[row - 1], self.items[row]
            self._populate_item_list()
            self.list_widget.setCurrentRow(row - 1)
            self._on_options_changed()

    def _on_move_down(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.items) - 1:
            self.items[row], self.items[row + 1] = self.items[row + 1], self.items[row]
            self._populate_item_list()
            self.list_widget.setCurrentRow(row + 1)
            self._on_options_changed()

    def _on_item_rows_moved(self) -> None:
        # Re-sync items order with list_widget items
        new_items = []
        for i in range(self.list_widget.count()):
            text = self.list_widget.item(i).text()
            # Match item by title
            for it in self.items:
                if it.title in text and it not in new_items:
                    new_items.append(it)
                    break
        if len(new_items) == len(self.items):
            self.items = new_items
            self._on_options_changed()

    def _on_list_selection_changed(self, row: int) -> None:
        pass

    def _on_print(self) -> None:
        """Sends document directly to System Print Dialog via QPrinter."""
        if not self.items:
            QMessageBox.warning(self, "Uyarı", "Yazdırılacak görsel bulunmuyor.")
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dlg = QPrintDialog(printer, self)
        if print_dlg.exec() == QPrintDialog.DialogCode.Accepted:
            try:
                painter = QPainter(printer)
                generator = PDFGenerator(self.options)
                total_pages = generator.calculate_total_pages(self.items)
                slots = generator.get_layout_slots_count()

                for p_idx in range(total_pages):
                    if p_idx > 0:
                        printer.newPage()
                    start_i = p_idx * slots
                    page_items = self.items[start_i : start_i + slots]
                    w_pt = printer.pageLayout().paintRectPixels(printer.resolution()).width()
                    h_pt = printer.pageLayout().paintRectPixels(printer.resolution()).height()
                    generator._render_page(painter, page_items, p_idx + 1, total_pages, w_pt, h_pt)

                painter.end()
                NotificationManager.show_toast("Yazdırma Tamamlandı 🖨️", "Belge yazıcıya başarıyla gönderildi.")
            except Exception as exc:
                QMessageBox.critical(self, "Hata", f"Yazdırma başarısız:\n{exc}")

    def _on_export_pdf(self) -> None:
        if not self.items:
            QMessageBox.warning(self, "Uyarı", "PDF oluşturmak için en az bir görsel gereklidir.")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "PDF Olarak Kaydet",
            "quickglint_export.pdf",
            "PDF Files (*.pdf)",
        )
        if not save_path:
            return

        self.btn_export.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self._export_worker = PDFExportWorker(
            items=self.items,
            output_path=save_path,
            options=self.options,
            parent=self,
        )
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.finished_success.connect(self._on_export_success)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.start()

    def _on_export_progress(self, current: int, total: int) -> None:
        pct = int((current / float(max(1, total))) * 100)
        self.progress_bar.setValue(pct)

    def _on_export_success(self, output_path: str) -> None:
        self.btn_export.setEnabled(True)
        self.progress_bar.setVisible(False)
        NotificationManager.show_toast(
            "PDF Dışa Aktarıldı 📄",
            f"PDF belgeniz başarıyla oluşturuldu:\n{Path(output_path).name}",
        )
        self.accept()

    def _on_export_failed(self, err_msg: str) -> None:
        self.btn_export.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "PDF Hatası", f"PDF oluşturulamadı:\n{err_msg}")

