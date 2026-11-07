"""Top toolbar ribbon for the PDF Workspace providing tool selection, shape dropdowns, color pickers, and project actions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolBar,
    QToolButton,
    QWidget,
)

from app.pdf.canvas import CanvasMode
from app.pdf.document import ShapeType
from app.ui.styles import get_icon


class PDFTopToolbar(QFrame):
    """Categorized ribbon toolbar for the PDF Editor."""

    # Project & File Signals
    new_doc_requested = Signal()
    open_doc_requested = Signal()
    save_doc_requested = Signal()
    save_as_doc_requested = Signal()
    import_pdf_requested = Signal()
    export_pdf_requested = Signal()
    print_preview_requested = Signal()

    # Edit & History Signals
    undo_requested = Signal()
    redo_requested = Signal()

    # Insert Signals
    add_image_requested = Signal()
    add_text_requested = Signal()
    add_shape_requested = Signal(ShapeType)
    add_signature_requested = Signal()
    add_page_requested = Signal()
    header_footer_requested = Signal()
    ocr_layer_requested = Signal()

    # Mode & Tool Signals
    mode_changed = Signal(str)  # CanvasMode
    zoom_in_requested = Signal()
    zoom_out_requested = Signal()
    zoom_preset_selected = Signal(float)
    fit_page_requested = Signal()
    fit_width_requested = Signal()
    search_requested = Signal()
    toggle_grid_requested = Signal()
    toggle_rulers_requested = Signal()

    color_changed = Signal(str)
    brush_size_changed = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet("""
            QFrame {
                background-color: #0F172A;
                border-bottom: 1px solid #1E293B;
            }
            QToolButton, QPushButton#toolBtn {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 4px 8px;
                color: #F8FAFC;
                font-size: 11px;
                font-weight: 500;
            }
            QToolButton:hover, QPushButton#toolBtn:hover {
                background-color: #1E293B;
                border-color: #334155;
            }
            QToolButton:checked, QPushButton#toolBtn:checked {
                background-color: #2563EB;
                border-color: #3B82F6;
                color: #FFFFFF;
            }
            QComboBox {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 3px 6px;
                color: #F8FAFC;
                font-size: 11px;
            }
            QFrame#sep {
                background-color: #334155;
                width: 1px;
                max-width: 1px;
                margin: 6px 4px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # 1. FILE & PROJECT ACTIONS
        self.btn_new = self._add_button("📄 New", self.new_doc_requested.emit)
        self.btn_open = self._add_button("📂 Open", self.open_doc_requested.emit)
        self.btn_save = self._add_button("💾 Save", self.save_doc_requested.emit)
        self.btn_import = self._add_button("📥 Import PDF", self.import_pdf_requested.emit)
        self.btn_export = self._add_button("🚀 Export PDF", self.export_pdf_requested.emit)
        self.btn_export.setStyleSheet("background-color: #2563EB; font-weight: bold; border-radius: 6px;")

        layout.addWidget(self._create_separator())

        # 2. UNDO / REDO
        self.btn_undo = self._add_button("↩️ Undo", self.undo_requested.emit)
        self.btn_redo = self._add_button("↪️ Redo", self.redo_requested.emit)

        layout.addWidget(self._create_separator())

        # 3. INTERACTIVE TOOLS (Select, Pan, Text, Pen, Highlighter)
        self.btn_select = self._add_checkable_button("👆 Select", lambda: self._set_mode(CanvasMode.SELECT), checked=True)
        self.btn_pan = self._add_checkable_button("✋ Pan", lambda: self._set_mode(CanvasMode.PAN))
        self.btn_text = self._add_checkable_button("🔤 Text", self.add_text_requested.emit)
        self.btn_pen = self._add_checkable_button("✏️ Pen", lambda: self._set_mode(CanvasMode.DRAW_PEN))
        self.btn_hl = self._add_checkable_button("🖍️ Highlighter", lambda: self._set_mode(CanvasMode.DRAW_HIGHLIGHTER))

        # Shape Dropdown Menu
        self.btn_shape = QToolButton(self)
        self.btn_shape.setText("🔷 Shapes ▾")
        self.btn_shape.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        shape_menu = QMenu(self)
        shape_menu.setStyleSheet("""
            QMenu {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item:selected {
                background-color: #2563EB;
            }
        """)
        for s_type, label in [
            (ShapeType.RECTANGLE, "⬛ Rectangle"),
            (ShapeType.ROUNDED_RECT, "🔲 Rounded Rectangle"),
            (ShapeType.CIRCLE, "⭕ Circle / Ellipse"),
            (ShapeType.LINE, "📏 Line"),
            (ShapeType.ARROW, "↗️ Arrow"),
        ]:
            act = shape_menu.addAction(label)
            act.triggered.connect(lambda _, st=s_type: self.add_shape_requested.emit(st))
        self.btn_shape.setMenu(shape_menu)
        layout.addWidget(self.btn_shape)

        self.btn_image = self._add_button("🖼️ Image", self.add_image_requested.emit)
        self.btn_signature = self._add_button("✍️ Signature", self.add_signature_requested.emit)
        self.btn_hf = self._add_button("📑 Header/Footer", self.header_footer_requested.emit)

        layout.addWidget(self._create_separator())

        # 4. COLOR & SIZE PICKER
        self.btn_color = QPushButton()
        self.btn_color.setObjectName("toolBtn")
        self.btn_color.setFixedSize(26, 26)
        self.btn_color.setStyleSheet("background-color: #EF4444; border: 1px solid #475569; border-radius: 4px;")
        self.btn_color.clicked.connect(self._pick_color)
        layout.addWidget(self.btn_color)

        layout.addStretch()

        # 5. ZOOM & VIEW CONTROLS
        self.btn_search = self._add_button("🔍", self.search_requested.emit)
        self.btn_zoom_out = self._add_button("➖", self.zoom_out_requested.emit)

        self.combo_zoom = QComboBox(self)
        self.combo_zoom.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "Fit Page", "Fit Width"])
        self.combo_zoom.setCurrentText("100%")
        self.combo_zoom.currentTextChanged.connect(self._on_zoom_text_changed)
        layout.addWidget(self.combo_zoom)

        self.btn_zoom_in = self._add_button("➕", self.zoom_in_requested.emit)

    def _add_button(self, text: str, callback: Any) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setObjectName("toolBtn")
        btn.clicked.connect(callback)
        self.layout().addWidget(btn)
        return btn

    def _add_checkable_button(self, text: str, callback: Any, checked: bool = False) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setObjectName("toolBtn")
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.clicked.connect(callback)
        self.layout().addWidget(btn)
        return btn

    def _create_separator(self) -> QFrame:
        sep = QFrame(self)
        sep.setObjectName("sep")
        sep.setFrameShape(QFrame.Shape.VLine)
        return sep

    def _set_mode(self, mode: str) -> None:
        self.btn_select.setChecked(mode == CanvasMode.SELECT)
        self.btn_pan.setChecked(mode == CanvasMode.PAN)
        self.btn_pen.setChecked(mode == CanvasMode.DRAW_PEN)
        self.btn_hl.setChecked(mode == CanvasMode.DRAW_HIGHLIGHTER)
        self.mode_changed.emit(mode)

    def set_active_mode(self, mode: str) -> None:
        self.btn_select.setChecked(mode == CanvasMode.SELECT)
        self.btn_pan.setChecked(mode == CanvasMode.PAN)
        self.btn_pen.setChecked(mode == CanvasMode.DRAW_PEN)
        self.btn_hl.setChecked(mode == CanvasMode.DRAW_HIGHLIGHTER)

    def _pick_color(self) -> None:
        col = QColorDialog.getColor(QColor("#EF4444"), self, "Select Active Drawing Color")
        if col.isValid():
            self.btn_color.setStyleSheet(f"background-color: {col.name()}; border: 1px solid #475569; border-radius: 4px;")
            self.color_changed.emit(col.name())

    def update_zoom_display(self, zoom_factor: float) -> None:
        self.combo_zoom.blockSignals(True)
        pct = int(round(zoom_factor * 100))
        self.combo_zoom.setCurrentText(f"{pct}%")
        self.combo_zoom.blockSignals(False)

    def _on_zoom_text_changed(self, text: str) -> None:
        if text == "Fit Page":
            self.fit_page_requested.emit()
        elif text == "Fit Width":
            self.fit_width_requested.emit()
        elif "%" in text:
            try:
                val = float(text.replace("%", "").strip()) / 100.0
                self.zoom_preset_selected.emit(val)
            except ValueError:
                pass

