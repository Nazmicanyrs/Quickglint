"""Master PDF Editor & Document Builder Workspace Window."""

from __future__ import annotations

from pathlib import Path
import time
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app.pdf.autosave import PDFAutosaveManager
from app.pdf.canvas import CanvasMode
from app.pdf.commands import (
    AddObjectCommand,
    AddPageCommand,
    DeleteObjectCommand,
    DeletePageCommand,
    DuplicatePageCommand,
    ReorderPageCommand,
)
from app.pdf.document import (
    PDFDocument,
    PDFImageObject,
    PDFObject,
    PDFPage,
    PDFShapeObject,
    PDFSignatureObject,
    PDFTextObject,
    ShapeType,
)
from app.pdf.history import PDFHistoryManager
from app.pdf.pdf_importer import PDFImporter
from app.pdf.ui.export_preview_dialog import PDFExportPreviewDialog
from app.pdf.ui.header_footer_dialog import PDFHeaderFooterDialog
from app.pdf.ui.pages_sidebar import PDFPagesSidebar
from app.pdf.ui.properties_panel import PDFPropertiesPanel
from app.pdf.ui.search_bar import PDFSearchBar
from app.pdf.ui.signature_dialog import PDFSignatureDialog
from app.pdf.ui.top_toolbar import PDFTopToolbar
from app.pdf.viewport import PDFViewportWidget
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.logger import logger


class PDFEditorWindow(QMainWindow):
    """Modern, full-featured PDF Document Builder and Editor."""

    def __init__(self, document: Optional[PDFDocument] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quickglint — Professional PDF Document Builder")
        self.resize(1280, 850)
        self.setStyleSheet(DARK_THEME_QSS)

        # Core State
        self.history_manager = PDFHistoryManager(parent=self)
        self.autosave_manager = PDFAutosaveManager(parent=self)
        self.document: PDFDocument = document or PDFDocument.create_empty("New Document")

        # Central Layout with Splitter
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Ribbon Toolbar
        self.toolbar = PDFTopToolbar(self)
        main_layout.addWidget(self.toolbar)

        # 2. Search HUD
        self.search_bar = PDFSearchBar(self)
        self.search_bar.hide()
        main_layout.addWidget(self.search_bar)

        # 3. Main Workspace Splitter (Left Sidebar | Center Canvas Viewport | Right Properties)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #1E293B;
                width: 2px;
            }
        """)

        # Left Sidebar (Pages)
        self.sidebar = PDFPagesSidebar(self)
        self.splitter.addWidget(self.sidebar)

        # Center Viewport
        self.viewport = PDFViewportWidget(history_manager=self.history_manager, parent=self)
        self.splitter.addWidget(self.viewport)

        # Right Properties Panel
        self.properties = PDFPropertiesPanel(history_manager=self.history_manager, parent=self)
        self.splitter.addWidget(self.properties)

        self.splitter.setStretchFactor(0, 0)  # Left
        self.splitter.setStretchFactor(1, 1)  # Center (expands)
        self.splitter.setStretchFactor(2, 0)  # Right
        self.splitter.setSizes([190, 820, 270])

        main_layout.addWidget(self.splitter)

        # 4. Status Bar
        self.status_bar = QStatusBar(self)
        self.status_bar.setStyleSheet("background-color: #0F172A; color: #94A3B8; font-size: 11px;")
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self._connect_signals()
        self._setup_shortcuts()

        # Initialize Document
        self.load_document(self.document)
        self.autosave_manager.start(self.document)

    def _connect_signals(self) -> None:
        # History
        self.history_manager.can_undo_changed.connect(self.toolbar.btn_undo.setEnabled)
        self.history_manager.can_redo_changed.connect(self.toolbar.btn_redo.setEnabled)
        self.history_manager.history_changed.connect(self._on_history_changed)

        # Toolbar Actions
        self.toolbar.new_doc_requested.connect(self.new_document)
        self.toolbar.open_doc_requested.connect(self.open_document)
        self.toolbar.save_doc_requested.connect(self.save_document)
        self.toolbar.import_pdf_requested.connect(self.import_pdf_file)
        self.toolbar.export_pdf_requested.connect(self.export_pdf)
        self.toolbar.undo_requested.connect(self.history_manager.undo)
        self.toolbar.redo_requested.connect(self.history_manager.redo)

        self.toolbar.mode_changed.connect(self._on_mode_changed)
        self.toolbar.add_image_requested.connect(self.add_image_dialog)
        self.toolbar.add_text_requested.connect(self._on_add_text_clicked)
        self.toolbar.add_shape_requested.connect(self._on_add_shape_requested)
        self.toolbar.add_signature_requested.connect(self.open_signature_dialog)
        self.toolbar.header_footer_requested.connect(self.open_header_footer_dialog)
        self.toolbar.search_requested.connect(self._toggle_search)

        self.toolbar.zoom_in_requested.connect(self.viewport.zoom_in)
        self.toolbar.zoom_out_requested.connect(self.viewport.zoom_out)
        self.toolbar.zoom_preset_selected.connect(self.viewport.set_zoom)
        self.toolbar.fit_page_requested.connect(self.viewport.fit_page)
        self.toolbar.fit_width_requested.connect(self.viewport.fit_width)
        self.toolbar.color_changed.connect(self._on_toolbar_color_changed)

        # Viewport & Canvas
        self.viewport.zoom_changed.connect(self.toolbar.update_zoom_display)
        self.viewport.canvas.selection_changed.connect(self.properties.set_selected_objects)
        self.viewport.canvas.page_modified.connect(self._on_page_modified)

        # Sidebar
        self.sidebar.page_selected.connect(self._on_sidebar_page_selected)
        self.sidebar.page_add_requested.connect(self.add_page)
        self.sidebar.page_duplicate_requested.connect(self.duplicate_page)
        self.sidebar.page_delete_requested.connect(self.delete_page)

        # Properties panel
        self.properties.property_changed.connect(self.viewport.canvas.update)
        self.properties.property_changed.connect(self._on_page_modified)
        self.properties.crop_requested.connect(self._on_crop_requested)
        self.properties.fit_to_page_requested.connect(self._on_fit_content)
        self.properties.center_content_requested.connect(self._on_center_content)

        # Search
        self.search_bar.match_selected.connect(self._on_search_match_selected)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, self.new_document)
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_document)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_document)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self.save_document_as)
        QShortcut(QKeySequence("Ctrl+E"), self, self.export_pdf)
        QShortcut(QKeySequence("Ctrl+F"), self, self._toggle_search)

    # --------------------------------------------------------------------------
    # DOCUMENT & PAGE LIFECYCLE
    # --------------------------------------------------------------------------

    def load_document(self, doc: PDFDocument) -> None:
        self.document = doc
        self.viewport.canvas.set_document(doc, 0)
        self.sidebar.set_document(doc, 0)
        self.search_bar.set_document(doc)
        self.properties.set_active_page(self.viewport.canvas.current_page)
        self.history_manager.clear()
        self.status_bar.showMessage(f"Loaded: {doc.settings.title} ({len(doc.pages)} pages)")

    def new_document(self) -> None:
        doc = PDFDocument.create_empty("New Document")
        self.load_document(doc)

    def open_document(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF Project", "", "Quickglint PDF Project (*.quickglintpdf *.quickglintpdf);;All Files (*.*)")
        if path:
            doc = PDFDocument.load_project(path)
            if doc:
                self.load_document(doc)
                NotificationManager.show_toast("Project Loaded 📂", f"Loaded project {Path(path).name}")

    def save_document(self) -> None:
        if self.document.file_path:
            self.document.save_project(self.document.file_path)
            NotificationManager.show_toast("Project Saved 💾", f"Saved to {self.document.file_path.name}")
        else:
            self.save_document_as()

    def save_document_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF Project As",
            f"{self.document.settings.title}.quickglintpdf",
            "Quickglint PDF Project (*.quickglintpdf);;Quickglint Legacy PDF Project (*.quickglintpdf)",
        )
        if path:
            self.document.save_project(path)
            NotificationManager.show_toast("Project Saved 💾", f"Saved to {Path(path).name}")

    def import_pdf_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import PDF Document", "", "PDF Documents (*.pdf)")
        if path:
            doc = PDFImporter.import_pdf(path)
            if doc:
                self.load_document(doc)
                NotificationManager.show_toast("PDF Imported 📥", f"Imported {len(doc.pages)} pages from {Path(path).name}")

    def export_pdf(self) -> None:
        dlg = PDFExportPreviewDialog(self.document, self)
        dlg.exec()

    # --------------------------------------------------------------------------
    # PAGE ACTIONS
    # --------------------------------------------------------------------------

    def add_page(self) -> None:
        page = PDFPage()
        cmd = AddPageCommand(self.document, page)
        self.history_manager.push(cmd)
        self.sidebar.refresh_thumbnails(len(self.document.pages) - 1)
        self.viewport.canvas.set_page_index(len(self.document.pages) - 1)
        self.properties.set_active_page(self.viewport.canvas.current_page)

    def duplicate_page(self, index: int) -> None:
        cmd = DuplicatePageCommand(self.document, index)
        self.history_manager.push(cmd)
        self.sidebar.refresh_thumbnails(index + 1)
        self.viewport.canvas.set_page_index(index + 1)
        self.properties.set_active_page(self.viewport.canvas.current_page)

    def delete_page(self, index: int) -> None:
        if len(self.document.pages) <= 1:
            QMessageBox.information(self, "Info", "Cannot delete the only remaining page.")
            return
        cmd = DeletePageCommand(self.document, index)
        self.history_manager.push(cmd)
        new_idx = max(0, min(index, len(self.document.pages) - 1))
        self.sidebar.refresh_thumbnails(new_idx)
        self.viewport.canvas.set_page_index(new_idx)
        self.properties.set_active_page(self.viewport.canvas.current_page)

    def _on_sidebar_page_selected(self, index: int) -> None:
        self.viewport.canvas.set_page_index(index)
        self.properties.set_active_page(self.viewport.canvas.current_page)

    # --------------------------------------------------------------------------
    # INSERT ACTIONS
    # --------------------------------------------------------------------------

    def add_image_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Add Image", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff)")
        if path:
            img = QImage(path)
            if not img.isNull():
                self.add_image(img, title=Path(path).stem)

    def add_image(self, img: QImage, title: str = "Image") -> None:
        page = self.viewport.canvas.current_page
        if not page:
            return
        p_rect = page.get_printable_rect_pt()
        aspect = img.width() / max(1, img.height())
        target_w = min(p_rect.width() * 0.8, 400.0)
        target_h = target_w / aspect

        img_obj = PDFImageObject(
            image=img,
            x_pt=p_rect.x() + (p_rect.width() - target_w) / 2.0,
            y_pt=p_rect.y() + (p_rect.height() - target_h) / 2.0,
            width_pt=target_w,
            height_pt=target_h,
            title=title,
        )
        cmd = AddObjectCommand(page, img_obj)
        self.history_manager.push(cmd)
        self.viewport.canvas.selected_objects = [img_obj]
        self.viewport.canvas.selection_changed.emit([img_obj])
        self.viewport.canvas.update()
        self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)

    def _on_add_text_clicked(self) -> None:
        page = self.viewport.canvas.current_page
        if not page:
            return
        p_rect = page.get_printable_rect_pt()
        t_obj = PDFTextObject(
            text="Add your text here",
            x_pt=p_rect.x() + 40,
            y_pt=p_rect.y() + 40,
            width_pt=200.0,
            height_pt=40.0,
            font_size_pt=14.0,
            font_color="#0F172A",
        )
        cmd = AddObjectCommand(page, t_obj)
        self.history_manager.push(cmd)
        self.viewport.canvas.selected_objects = [t_obj]
        self.viewport.canvas.selection_changed.emit([t_obj])
        self.viewport.canvas.update()
        self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)
        self.viewport.canvas._start_inline_text_edit(t_obj)
        self.status_bar.showMessage("Text box created. Type to edit.")

    def _on_add_shape_requested(self, shape_type: ShapeType) -> None:
        page = self.viewport.canvas.current_page
        if not page:
            return
        p_rect = page.get_printable_rect_pt()
        shape_obj = PDFShapeObject(
            shape_type=shape_type,
            x_pt=p_rect.x() + 40,
            y_pt=p_rect.y() + 40,
            width_pt=140.0,
            height_pt=90.0,
            fill_color="#3B82F6",
            border_color="#1D4ED8",
        )
        cmd = AddObjectCommand(page, shape_obj)
        self.history_manager.push(cmd)
        self.viewport.canvas.selected_objects = [shape_obj]
        self.viewport.canvas.selection_changed.emit([shape_obj])
        self.viewport.canvas.update()
        self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)

    def open_signature_dialog(self) -> None:
        page = self.viewport.canvas.current_page
        if not page:
            return
        dlg = PDFSignatureDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.created_signature_obj:
            sig = dlg.created_signature_obj
            p_rect = page.get_printable_rect_pt()
            sig.x = p_rect.right() - sig.width - 20
            sig.y = p_rect.bottom() - sig.height - 20

            cmd = AddObjectCommand(page, sig)
            self.history_manager.push(cmd)
            self.viewport.canvas.selected_objects = [sig]
            self.viewport.canvas.selection_changed.emit([sig])
            self.viewport.canvas.update()
            self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)

    def open_header_footer_dialog(self) -> None:
        dlg = PDFHeaderFooterDialog(
            header_footer=self.document.settings.header_footer,
            page_numbers=self.document.settings.page_numbers,
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.viewport.canvas.update()
            self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)

    def _toggle_search(self) -> None:
        if self.search_bar.isVisible():
            self.search_bar.hide()
        else:
            self.search_bar.set_document(self.document)
            self.search_bar.show()
            self.search_bar.edit_search.setFocus()

    def _on_search_match_selected(self, page_index: int, text_obj: PDFTextObject) -> None:
        self.sidebar.list_widget.setCurrentRow(page_index)
        self.viewport.canvas.set_page_index(page_index)
        self.viewport.canvas.selected_objects = [text_obj]
        self.viewport.canvas.selection_changed.emit([text_obj])
        self.viewport.canvas.update()

    def _on_mode_changed(self, mode: str) -> None:
        self.viewport.canvas.mode = mode
        self.status_bar.showMessage(f"Tool: {mode.replace('_', ' ').capitalize()}")

    def _on_toolbar_color_changed(self, color_hex: str) -> None:
        self.viewport.canvas.active_drawing_color = color_hex

    def _on_crop_requested(self) -> None:
        if self.viewport.canvas.selected_objects:
            obj = self.viewport.canvas.selected_objects[0]
            if isinstance(obj, PDFImageObject):
                self.viewport.canvas.start_crop_mode(obj)

    def _on_fit_content(self) -> None:
        page = self.viewport.canvas.current_page
        if page:
            page.fit_content_to_page()
            self.viewport.canvas.update()
            self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)

    def _on_center_content(self) -> None:
        page = self.viewport.canvas.current_page
        if page:
            page.center_content()
            self.viewport.canvas.update()
            self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)

    def _on_page_modified(self) -> None:
        self.document.is_modified = True
        self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)

    def _on_history_changed(self) -> None:
        self.document.is_modified = True
        self.sidebar.refresh_thumbnails(self.viewport.canvas.current_page_index)
        self.viewport.canvas.update()

