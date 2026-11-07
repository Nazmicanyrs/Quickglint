"""Context-aware Properties Panel inspecting and updating Page, Image, Text, Shape, Signature, and Multi-selection attributes."""

from __future__ import annotations

from typing import Any, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.pdf.commands import PageSettingsCommand, TextEditCommand, TransformObjectCommand
from app.pdf.document import (
    BackgroundType,
    PageBackground,
    PDFAnnotationObject,
    PDFDocument,
    PDFImageObject,
    PDFLinkObject,
    PDFObject,
    PDFPage,
    PDFShapeObject,
    PDFSignatureObject,
    PDFTextObject,
    ShapeType,
)
from app.pdf.history import PDFHistoryManager
from app.pdf.models import (
    MarginConfig,
    PageOrientation,
    PaperSizePreset,
)


class PDFPropertiesPanel(QWidget):
    """Right inspector panel that dynamically adapts its controls to the active selection."""

    property_changed = Signal()
    crop_requested = Signal()
    fit_to_page_requested = Signal()
    fit_to_width_requested = Signal()
    original_size_requested = Signal()
    center_content_requested = Signal()

    def __init__(self, history_manager: Optional[PDFHistoryManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(270)
        self.history = history_manager

        self._active_page: Optional[PDFPage] = None
        self._selected_objects: List[PDFObject] = []
        self._is_updating_ui = False

        self.setStyleSheet("""
            QWidget {
                background-color: #0F172A;
                color: #F8FAFC;
                font-family: 'Segoe UI', sans-serif;
            }
            QGroupBox {
                border: 1px solid #1E293B;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 12px;
                font-weight: 600;
                font-size: 11px;
                color: #38BDF8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel {
                font-size: 11px;
                color: #94A3B8;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px 8px;
                color: #F8FAFC;
                font-size: 11px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #38BDF8;
            }
            QPushButton#btnSmall {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px 8px;
                color: #F8FAFC;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#btnSmall:hover {
                background-color: #2563EB;
                border-color: #3B82F6;
            }
            QPushButton#colorBtn {
                border: 1px solid #475569;
                border-radius: 4px;
                min-width: 24px;
                min-height: 24px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Header Title
        self.lbl_panel_title = QLabel("⚙️ PROPERTIES", self)
        self.lbl_panel_title.setStyleSheet("font-weight: 700; color: #38BDF8; font-size: 11px; letter-spacing: 1px;")
        main_layout.addWidget(self.lbl_panel_title)

        # Scroll Area for property controls
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(10)
        scroll.setWidget(self.container)

        main_layout.addWidget(scroll)

        # Build sub-sections
        self._build_transform_box()
        self._build_page_box()
        self._build_image_box()
        self._build_text_box()
        self._build_shape_box()
        self._build_alignment_box()

        self.container_layout.addStretch()

        self.show_page_properties()

    # --------------------------------------------------------------------------
    # SUB-SECTIONS CREATION
    # --------------------------------------------------------------------------

    def _build_transform_box(self) -> None:
        self.box_transform = QGroupBox("Transform & Position", self.container)
        l = QVBoxLayout(self.box_transform)

        # X, Y
        row_pos = QHBoxLayout()
        row_pos.addWidget(QLabel("X:"))
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-2000, 5000)
        self.spin_x.valueChanged.connect(self._on_transform_changed)
        row_pos.addWidget(self.spin_x)

        row_pos.addWidget(QLabel("Y:"))
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-2000, 5000)
        self.spin_y.valueChanged.connect(self._on_transform_changed)
        row_pos.addWidget(self.spin_y)
        l.addLayout(row_pos)

        # W, H
        row_size = QHBoxLayout()
        row_size.addWidget(QLabel("W:"))
        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(1, 5000)
        self.spin_w.valueChanged.connect(self._on_transform_changed)
        row_size.addWidget(self.spin_w)

        row_size.addWidget(QLabel("H:"))
        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(1, 5000)
        self.spin_h.valueChanged.connect(self._on_transform_changed)
        row_size.addWidget(self.spin_h)
        l.addLayout(row_size)

        # Rotation & Opacity
        row_rot_op = QHBoxLayout()
        row_rot_op.addWidget(QLabel("Rot:"))
        self.spin_rot = QDoubleSpinBox()
        self.spin_rot.setRange(0, 360)
        self.spin_rot.setSuffix("°")
        self.spin_rot.valueChanged.connect(self._on_transform_changed)
        row_rot_op.addWidget(self.spin_rot)

        row_rot_op.addWidget(QLabel("Opac:"))
        self.spin_opacity = QSpinBox()
        self.spin_opacity.setRange(0, 100)
        self.spin_opacity.setSuffix("%")
        self.spin_opacity.valueChanged.connect(self._on_transform_changed)
        row_rot_op.addWidget(self.spin_opacity)
        l.addLayout(row_rot_op)

        # Lock Checkbox
        self.chk_locked = QCheckBox("🔒 Lock Object")
        self.chk_locked.toggled.connect(self._on_lock_toggled)
        l.addWidget(self.chk_locked)

        self.container_layout.addWidget(self.box_transform)

    def _build_page_box(self) -> None:
        self.box_page = QGroupBox("Page Settings", self.container)
        l = QVBoxLayout(self.box_page)

        # Preset
        l.addWidget(QLabel("Paper Size:"))
        self.combo_paper = QComboBox()
        for p in PaperSizePreset:
            self.combo_paper.addItem(p.value, p)
        self.combo_paper.currentIndexChanged.connect(self._on_page_setting_changed)
        l.addWidget(self.combo_paper)

        # Orientation
        row_ori = QHBoxLayout()
        row_ori.addWidget(QLabel("Orientation:"))
        self.combo_ori = QComboBox()
        self.combo_ori.addItem("Portrait", PageOrientation.PORTRAIT)
        self.combo_ori.addItem("Landscape", PageOrientation.LANDSCAPE)
        self.combo_ori.currentIndexChanged.connect(self._on_page_setting_changed)
        row_ori.addWidget(self.combo_ori)
        l.addLayout(row_ori)

        # Margins (mm)
        l.addWidget(QLabel("Margins (mm):"))
        m_row1 = QHBoxLayout()
        m_row1.addWidget(QLabel("T:"))
        self.spin_m_top = QDoubleSpinBox()
        self.spin_m_top.setRange(0, 100)
        self.spin_m_top.valueChanged.connect(self._on_page_setting_changed)
        m_row1.addWidget(self.spin_m_top)

        m_row1.addWidget(QLabel("B:"))
        self.spin_m_bottom = QDoubleSpinBox()
        self.spin_m_bottom.setRange(0, 100)
        self.spin_m_bottom.valueChanged.connect(self._on_page_setting_changed)
        m_row1.addWidget(self.spin_m_bottom)
        l.addLayout(m_row1)

        m_row2 = QHBoxLayout()
        m_row2.addWidget(QLabel("L:"))
        self.spin_m_left = QDoubleSpinBox()
        self.spin_m_left.setRange(0, 100)
        self.spin_m_left.valueChanged.connect(self._on_page_setting_changed)
        m_row2.addWidget(self.spin_m_left)

        m_row2.addWidget(QLabel("R:"))
        self.spin_m_right = QDoubleSpinBox()
        self.spin_m_right.setRange(0, 100)
        self.spin_m_right.valueChanged.connect(self._on_page_setting_changed)
        m_row2.addWidget(self.spin_m_right)
        l.addLayout(m_row2)

        # Background Color
        row_bg = QHBoxLayout()
        row_bg.addWidget(QLabel("Background:"))
        self.btn_bg_color = QPushButton()
        self.btn_bg_color.setObjectName("colorBtn")
        self.btn_bg_color.setStyleSheet("background-color: #FFFFFF;")
        self.btn_bg_color.clicked.connect(self._pick_bg_color)
        row_bg.addWidget(self.btn_bg_color)
        l.addLayout(row_bg)

        # Content Actions
        btn_fit_c = QPushButton("📐 Fit Content to Page")
        btn_fit_c.setObjectName("btnSmall")
        btn_fit_c.clicked.connect(self.fit_to_page_requested.emit)
        l.addWidget(btn_fit_c)

        btn_center_c = QPushButton("🎯 Center Content")
        btn_center_c.setObjectName("btnSmall")
        btn_center_c.clicked.connect(self.center_content_requested.emit)
        l.addWidget(btn_center_c)

        self.container_layout.addWidget(self.box_page)

    def _build_image_box(self) -> None:
        self.box_image = QGroupBox("Image Controls", self.container)
        l = QVBoxLayout(self.box_image)

        self.chk_aspect_lock = QCheckBox("🔒 Lock Aspect Ratio")
        self.chk_aspect_lock.setChecked(True)
        self.chk_aspect_lock.toggled.connect(self._on_aspect_lock_toggled)
        l.addWidget(self.chk_aspect_lock)

        self.btn_crop = QPushButton("✂️ Crop Image")
        self.btn_crop.setObjectName("btnSmall")
        self.btn_crop.clicked.connect(self.crop_requested.emit)
        l.addWidget(self.btn_crop)

        row_fit = QHBoxLayout()
        b_fit_w = QPushButton("Fit Width")
        b_fit_w.setObjectName("btnSmall")
        b_fit_w.clicked.connect(self.fit_to_width_requested.emit)
        row_fit.addWidget(b_fit_w)

        b_orig = QPushButton("1:1 Original")
        b_orig.setObjectName("btnSmall")
        b_orig.clicked.connect(self.original_size_requested.emit)
        row_fit.addWidget(b_orig)
        l.addLayout(row_fit)

        self.container_layout.addWidget(self.box_image)

    def _build_text_box(self) -> None:
        self.box_text = QGroupBox("Typography & Text", self.container)
        l = QVBoxLayout(self.box_text)

        # Font & Size
        self.combo_font = QComboBox()
        self.combo_font.addItems(["Segoe UI", "Arial", "Roboto", "Times New Roman", "Courier New", "Consolas", "Georgia", "Segoe Script"])
        self.combo_font.currentTextChanged.connect(self._on_text_style_changed)
        l.addWidget(self.combo_font)

        row_sz_col = QHBoxLayout()
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 120)
        self.spin_font_size.setValue(14)
        self.spin_font_size.valueChanged.connect(self._on_text_style_changed)
        row_sz_col.addWidget(self.spin_font_size)

        self.btn_text_color = QPushButton()
        self.btn_text_color.setObjectName("colorBtn")
        self.btn_text_color.setStyleSheet("background-color: #0F172A;")
        self.btn_text_color.clicked.connect(self._pick_text_color)
        row_sz_col.addWidget(self.btn_text_color)
        l.addLayout(row_sz_col)

        # Style buttons: B, I, U, S
        row_styles = QHBoxLayout()
        self.btn_bold = QPushButton("B")
        self.btn_bold.setCheckable(True)
        self.btn_bold.setStyleSheet("font-weight: bold; min-width: 28px;")
        self.btn_bold.toggled.connect(self._on_text_style_changed)
        row_styles.addWidget(self.btn_bold)

        self.btn_italic = QPushButton("I")
        self.btn_italic.setCheckable(True)
        self.btn_italic.setStyleSheet("font-style: italic; min-width: 28px;")
        self.btn_italic.toggled.connect(self._on_text_style_changed)
        row_styles.addWidget(self.btn_italic)

        self.btn_underline = QPushButton("U")
        self.btn_underline.setCheckable(True)
        self.btn_underline.setStyleSheet("text-decoration: underline; min-width: 28px;")
        self.btn_underline.toggled.connect(self._on_text_style_changed)
        row_styles.addWidget(self.btn_underline)
        l.addLayout(row_styles)

        # Alignment
        row_align = QHBoxLayout()
        self.combo_align = QComboBox()
        self.combo_align.addItems(["Left", "Center", "Right", "Justify"])
        self.combo_align.currentTextChanged.connect(self._on_text_style_changed)
        row_align.addWidget(self.combo_align)
        l.addLayout(row_align)

        # Hyperlink
        l.addWidget(QLabel("Hyperlink URL:"))
        self.edit_link = QLineEdit()
        self.edit_link.setPlaceholderText("https://example.com")
        self.edit_link.editingFinished.connect(self._on_link_changed)
        l.addWidget(self.edit_link)

        self.chk_ocr_layer = QCheckBox("Invisible Searchable OCR")
        self.chk_ocr_layer.toggled.connect(self._on_ocr_flag_changed)
        l.addWidget(self.chk_ocr_layer)

        self.container_layout.addWidget(self.box_text)

    def _build_shape_box(self) -> None:
        self.box_shape = QGroupBox("Shape Styles", self.container)
        l = QVBoxLayout(self.box_shape)

        # Fill & Border Color
        row_colors = QHBoxLayout()
        row_colors.addWidget(QLabel("Fill:"))
        self.btn_shape_fill = QPushButton()
        self.btn_shape_fill.setObjectName("colorBtn")
        self.btn_shape_fill.setStyleSheet("background-color: #3B82F6;")
        self.btn_shape_fill.clicked.connect(self._pick_shape_fill)
        row_colors.addWidget(self.btn_shape_fill)

        row_colors.addWidget(QLabel("Border:"))
        self.btn_shape_border = QPushButton()
        self.btn_shape_border.setObjectName("colorBtn")
        self.btn_shape_border.setStyleSheet("background-color: #1D4ED8;")
        self.btn_shape_border.clicked.connect(self._pick_shape_border)
        row_colors.addWidget(self.btn_shape_border)
        l.addLayout(row_colors)

        # Border Width & Radius
        row_b_w = QHBoxLayout()
        row_b_w.addWidget(QLabel("Border W:"))
        self.spin_border_w = QDoubleSpinBox()
        self.spin_border_w.setRange(0, 50)
        self.spin_border_w.setValue(2.0)
        self.spin_border_w.valueChanged.connect(self._on_shape_style_changed)
        row_b_w.addWidget(self.spin_border_w)

        row_b_w.addWidget(QLabel("Radius:"))
        self.spin_radius = QDoubleSpinBox()
        self.spin_radius.setRange(0, 100)
        self.spin_radius.setValue(6.0)
        self.spin_radius.valueChanged.connect(self._on_shape_style_changed)
        row_b_w.addWidget(self.spin_radius)
        l.addLayout(row_b_w)

        self.container_layout.addWidget(self.box_shape)

    def _build_alignment_box(self) -> None:
        self.box_align = QGroupBox("Arrange & Align", self.container)
        l = QVBoxLayout(self.box_align)

        row1 = QHBoxLayout()
        btn_al_l = QPushButton("Left")
        btn_al_l.setObjectName("btnSmall")
        btn_al_l.clicked.connect(lambda: self._align_objects("left"))
        row1.addWidget(btn_al_l)

        btn_al_c = QPushButton("Center")
        btn_al_c.setObjectName("btnSmall")
        btn_al_c.clicked.connect(lambda: self._align_objects("center"))
        row1.addWidget(btn_al_c)

        btn_al_r = QPushButton("Right")
        btn_al_r.setObjectName("btnSmall")
        btn_al_r.clicked.connect(lambda: self._align_objects("right"))
        row1.addWidget(btn_al_r)
        l.addLayout(row1)

        row2 = QHBoxLayout()
        btn_al_t = QPushButton("Top")
        btn_al_t.setObjectName("btnSmall")
        btn_al_t.clicked.connect(lambda: self._align_objects("top"))
        row2.addWidget(btn_al_t)

        btn_al_m = QPushButton("Middle")
        btn_al_m.setObjectName("btnSmall")
        btn_al_m.clicked.connect(lambda: self._align_objects("middle"))
        row2.addWidget(btn_al_m)

        btn_al_b = QPushButton("Bottom")
        btn_al_b.setObjectName("btnSmall")
        btn_al_b.clicked.connect(lambda: self._align_objects("bottom"))
        row2.addWidget(btn_al_b)
        l.addLayout(row2)

        self.container_layout.addWidget(self.box_align)

    # --------------------------------------------------------------------------
    # CONTEXT SWITCHING
    # --------------------------------------------------------------------------

    def set_active_page(self, page: Optional[PDFPage]) -> None:
        self._active_page = page
        if not self._selected_objects:
            self.show_page_properties()

    def set_selected_objects(self, objects: List[PDFObject]) -> None:
        self._selected_objects = list(objects)
        if not objects:
            self.show_page_properties()
        elif len(objects) == 1:
            obj = objects[0]
            if isinstance(obj, PDFImageObject):
                self.show_image_properties(obj)
            elif isinstance(obj, PDFTextObject):
                self.show_text_properties(obj)
            elif isinstance(obj, PDFShapeObject):
                self.show_shape_properties(obj)
            else:
                self.show_transform_only(obj)
        else:
            self.show_multi_selection_properties(objects)

    def show_page_properties(self) -> None:
        self.lbl_panel_title.setText("⚙️ PAGE SETTINGS")
        self.box_page.show()
        self.box_transform.hide()
        self.box_image.hide()
        self.box_text.hide()
        self.box_shape.hide()
        self.box_align.hide()

        if self._active_page:
            self._is_updating_ui = True
            self.combo_paper.setCurrentText(self._active_page.paper_size.value)
            self.combo_ori.setCurrentIndex(0 if self._active_page.orientation == PageOrientation.PORTRAIT else 1)
            self.spin_m_top.setValue(self._active_page.margins.top_mm)
            self.spin_m_bottom.setValue(self._active_page.margins.bottom_mm)
            self.spin_m_left.setValue(self._active_page.margins.left_mm)
            self.spin_m_right.setValue(self._active_page.margins.right_mm)
            self.btn_bg_color.setStyleSheet(f"background-color: {self._active_page.background.color_hex};")
            self._is_updating_ui = False

    def show_image_properties(self, obj: PDFImageObject) -> None:
        self.lbl_panel_title.setText("🖼️ IMAGE PROPERTIES")
        self.box_page.hide()
        self.box_transform.show()
        self.box_image.show()
        self.box_text.hide()
        self.box_shape.hide()
        self.box_align.show()

        self._populate_transform(obj)
        self.chk_aspect_lock.setChecked(obj.lock_aspect_ratio)

    def show_text_properties(self, obj: PDFTextObject) -> None:
        self.lbl_panel_title.setText("🔤 TEXT PROPERTIES")
        self.box_page.hide()
        self.box_transform.show()
        self.box_image.hide()
        self.box_text.show()
        self.box_shape.hide()
        self.box_align.show()

        self._populate_transform(obj)
        self._is_updating_ui = True
        self.combo_font.setCurrentText(obj.font_family)
        self.spin_font_size.setValue(int(obj.font_size_pt))
        self.btn_text_color.setStyleSheet(f"background-color: {obj.font_color};")
        self.btn_bold.setChecked(obj.is_bold)
        self.btn_italic.setChecked(obj.is_italic)
        self.btn_underline.setChecked(obj.is_underline)
        self.combo_align.setCurrentText(obj.alignment.capitalize())
        self.edit_link.setText(obj.hyperlink_url or "")
        self.chk_ocr_layer.setChecked(obj.is_ocr_layer)
        self._is_updating_ui = False

    def show_shape_properties(self, obj: PDFShapeObject) -> None:
        self.lbl_panel_title.setText("🔷 SHAPE PROPERTIES")
        self.box_page.hide()
        self.box_transform.show()
        self.box_image.hide()
        self.box_text.hide()
        self.box_shape.show()
        self.box_align.show()

        self._populate_transform(obj)
        self._is_updating_ui = True
        self.btn_shape_fill.setStyleSheet(f"background-color: {obj.fill_color};")
        self.btn_shape_border.setStyleSheet(f"background-color: {obj.border_color};")
        self.spin_border_w.setValue(obj.border_width_pt)
        self.spin_radius.setValue(obj.corner_radius_pt)
        self._is_updating_ui = False

    def show_transform_only(self, obj: PDFObject) -> None:
        self.lbl_panel_title.setText("📦 OBJECT PROPERTIES")
        self.box_page.hide()
        self.box_transform.show()
        self.box_image.hide()
        self.box_text.hide()
        self.box_shape.hide()
        self.box_align.show()
        self._populate_transform(obj)

    def show_multi_selection_properties(self, objects: List[PDFObject]) -> None:
        self.lbl_panel_title.setText(f"📑 {len(objects)} OBJECTS SELECTED")
        self.box_page.hide()
        self.box_transform.show()
        self.box_image.hide()
        self.box_text.hide()
        self.box_shape.hide()
        self.box_align.show()

    def _populate_transform(self, obj: PDFObject) -> None:
        self._is_updating_ui = True
        self.spin_x.setValue(obj.x)
        self.spin_y.setValue(obj.y)
        self.spin_w.setValue(obj.width)
        self.spin_h.setValue(obj.height)
        self.spin_rot.setValue(obj.rotation)
        self.spin_opacity.setValue(int(obj.opacity * 100))
        self.chk_locked.setChecked(obj.locked)
        self._is_updating_ui = False

    # --------------------------------------------------------------------------
    # VALUE CHANGE HANDLERS
    # --------------------------------------------------------------------------

    def _on_transform_changed(self) -> None:
        if self._is_updating_ui or not self._selected_objects:
            return
        obj = self._selected_objects[0]
        obj.x = self.spin_x.value()
        obj.y = self.spin_y.value()
        obj.width = self.spin_w.value()
        obj.height = self.spin_h.value()
        obj.rotation = self.spin_rot.value()
        obj.opacity = self.spin_opacity.value() / 100.0
        self.property_changed.emit()

    def _on_lock_toggled(self, locked: bool) -> None:
        if self._is_updating_ui:
            return
        for o in self._selected_objects:
            o.locked = locked
        self.property_changed.emit()

    def _on_page_setting_changed(self) -> None:
        if self._is_updating_ui or not self._active_page:
            return
        self._active_page.paper_size = self.combo_paper.currentData()
        self._active_page.orientation = self.combo_ori.currentData()
        self._active_page.margins.top_mm = self.spin_m_top.value()
        self._active_page.margins.bottom_mm = self.spin_m_bottom.value()
        self._active_page.margins.left_mm = self.spin_m_left.value()
        self._active_page.margins.right_mm = self.spin_m_right.value()
        self.property_changed.emit()

    def _pick_bg_color(self) -> None:
        if not self._active_page:
            return
        col = QColorDialog.getColor(QColor(self._active_page.background.color_hex), self, "Select Page Background")
        if col.isValid():
            self._active_page.background.color_hex = col.name()
            self._active_page.background.bg_type = BackgroundType.COLOR
            self.btn_bg_color.setStyleSheet(f"background-color: {col.name()};")
            self.property_changed.emit()

    def _on_aspect_lock_toggled(self, locked: bool) -> None:
        for o in self._selected_objects:
            if isinstance(o, PDFImageObject):
                o.lock_aspect_ratio = locked

    def _on_text_style_changed(self) -> None:
        if self._is_updating_ui or not self._selected_objects:
            return
        for o in self._selected_objects:
            if isinstance(o, PDFTextObject):
                o.font_family = self.combo_font.currentText()
                o.font_size_pt = float(self.spin_font_size.value())
                o.is_bold = self.btn_bold.isChecked()
                o.is_italic = self.btn_italic.isChecked()
                o.is_underline = self.btn_underline.isChecked()
                o.alignment = self.combo_align.currentText().lower()
        self.property_changed.emit()

    def _pick_text_color(self) -> None:
        if not self._selected_objects:
            return
        obj = self._selected_objects[0]
        cur = QColor(getattr(obj, "font_color", "#000000"))
        col = QColorDialog.getColor(cur, self, "Select Text Color")
        if col.isValid():
            for o in self._selected_objects:
                if isinstance(o, PDFTextObject):
                    o.font_color = col.name()
            self.btn_text_color.setStyleSheet(f"background-color: {col.name()};")
            self.property_changed.emit()

    def _on_link_changed(self) -> None:
        url = self.edit_link.text().strip()
        for o in self._selected_objects:
            o.hyperlink_url = url or None
        self.property_changed.emit()

    def _on_ocr_flag_changed(self, is_ocr: bool) -> None:
        for o in self._selected_objects:
            if isinstance(o, PDFTextObject):
                o.is_ocr_layer = is_ocr
        self.property_changed.emit()

    def _pick_shape_fill(self) -> None:
        if not self._selected_objects:
            return
        obj = self._selected_objects[0]
        cur = QColor(getattr(obj, "fill_color", "#3B82F6"))
        col = QColorDialog.getColor(cur, self, "Select Fill Color")
        if col.isValid():
            for o in self._selected_objects:
                if isinstance(o, PDFShapeObject):
                    o.fill_color = col.name()
            self.btn_shape_fill.setStyleSheet(f"background-color: {col.name()};")
            self.property_changed.emit()

    def _pick_shape_border(self) -> None:
        if not self._selected_objects:
            return
        obj = self._selected_objects[0]
        cur = QColor(getattr(obj, "border_color", "#1D4ED8"))
        col = QColorDialog.getColor(cur, self, "Select Border Color")
        if col.isValid():
            for o in self._selected_objects:
                if isinstance(o, PDFShapeObject):
                    o.border_color = col.name()
            self.btn_shape_border.setStyleSheet(f"background-color: {col.name()};")
            self.property_changed.emit()

    def _on_shape_style_changed(self) -> None:
        if self._is_updating_ui or not self._selected_objects:
            return
        for o in self._selected_objects:
            if isinstance(o, PDFShapeObject):
                o.border_width_pt = self.spin_border_w.value()
                o.corner_radius_pt = self.spin_radius.value()
        self.property_changed.emit()

    def _align_objects(self, align_type: str) -> None:
        if not self._selected_objects or not self._active_page:
            return
        p_rect = self._active_page.get_printable_rect_pt()

        if len(self._selected_objects) == 1:
            # Align single object relative to page margins
            o = self._selected_objects[0]
            if align_type == "left":
                o.x = p_rect.left()
            elif align_type == "center":
                o.x = p_rect.left() + (p_rect.width() - o.width) / 2.0
            elif align_type == "right":
                o.x = p_rect.right() - o.width
            elif align_type == "top":
                o.y = p_rect.top()
            elif align_type == "middle":
                o.y = p_rect.top() + (p_rect.height() - o.height) / 2.0
            elif align_type == "bottom":
                o.y = p_rect.bottom() - o.height
        else:
            # Align objects relative to their mutual bounding box
            min_x = min(o.x for o in self._selected_objects)
            max_x = max(o.x + o.width for o in self._selected_objects)
            min_y = min(o.y for o in self._selected_objects)
            max_y = max(o.y + o.height for o in self._selected_objects)

            for o in self._selected_objects:
                if align_type == "left":
                    o.x = min_x
                elif align_type == "center":
                    o.x = min_x + (max_x - min_x - o.width) / 2.0
                elif align_type == "right":
                    o.x = max_x - o.width
                elif align_type == "top":
                    o.y = min_y
                elif align_type == "middle":
                    o.y = min_y + (max_y - min_y - o.height) / 2.0
                elif align_type == "bottom":
                    o.y = max_y - o.height

        self.property_changed.emit()

