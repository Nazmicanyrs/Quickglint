"""Signature creation dialog supporting: 1) Draw freehand signature, 2) Type with cursive fonts, 3) Import signature image."""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.pdf.document import PDFSignatureObject, SignatureType
from app.ui.styles import DARK_THEME_QSS


class SignatureCanvas(QWidget):
    """Interactive drawing area for smooth handwritten digital signature."""

    def __init__(self, ink_color: str = "#0F172A", stroke_width: float = 3.0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ink_color: str = ink_color
        self.stroke_width: float = stroke_width
        self.strokes: List[List[Tuple[float, float]]] = []
        self._current_stroke: List[Tuple[float, float]] = []

        self.setMinimumSize(420, 160)
        self.setStyleSheet("background-color: #FFFFFF; border: 2px dashed #94A3B8; border-radius: 8px;")

    def clear(self) -> None:
        self.strokes.clear()
        self._current_stroke.clear()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            self._current_stroke = [(pos.x(), pos.y())]
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton and self._current_stroke:
            pos = event.position()
            self._current_stroke.append((pos.x(), pos.y()))
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and len(self._current_stroke) >= 2:
            self.strokes.append(list(self._current_stroke))
            self._current_stroke.clear()
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))

        # Guide line for signing
        painter.setPen(QPen(QColor("#E2E8F0"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(20, self.height() - 35, self.width() - 20, self.height() - 35)

        pen = QPen(QColor(self.ink_color), self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        # Draw completed strokes
        all_strokes = list(self.strokes)
        if len(self._current_stroke) >= 2:
            all_strokes.append(self._current_stroke)

        for stroke in all_strokes:
            if len(stroke) < 2:
                continue
            path = QPainterPath()
            path.moveTo(stroke[0][0], stroke[0][1])
            for pt in stroke[1:]:
                path.lineTo(pt[0], pt[1])
            painter.drawPath(path)


class PDFSignatureDialog(QDialog):
    """Modal dialog allowing user to create, customize, and insert signatures into the PDF."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Signature — Quickglint PDF Builder")
        self.resize(500, 360)
        self.setStyleSheet(DARK_THEME_QSS)

        self.created_signature_obj: Optional[PDFSignatureObject] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget(self)

        # 1. DRAW TAB
        self.tab_draw = QWidget()
        l_draw = QVBoxLayout(self.tab_draw)
        self.draw_canvas = SignatureCanvas()
        l_draw.addWidget(self.draw_canvas)

        h_ctrl = QHBoxLayout()
        btn_clear = QPushButton("🗑️ Clear", self)
        btn_clear.clicked.connect(self.draw_canvas.clear)
        h_ctrl.addWidget(btn_clear)
        h_ctrl.addStretch()
        l_draw.addLayout(h_ctrl)
        self.tabs.addTab(self.tab_draw, "✏️ Draw Signature")

        # 2. TYPE TAB
        self.tab_type = QWidget()
        l_type = QVBoxLayout(self.tab_type)
        l_type.addWidget(QLabel("Enter Full Name:"))
        self.edit_typed = QLineEdit()
        self.edit_typed.setPlaceholderText("John Doe")
        self.edit_typed.setText("John Doe")
        l_type.addWidget(self.edit_typed)

        l_type.addWidget(QLabel("Select Handwriting Font:"))
        self.combo_fonts = QComboBox()
        self.combo_fonts.addItems(["Segoe Script", "Brush Script MT", "Lucida Handwriting", "Freestyle Script", "Comic Sans MS"])
        l_type.addWidget(self.combo_fonts)
        l_type.addStretch()
        self.tabs.addTab(self.tab_type, "🔤 Type Signature")

        # 3. IMPORT IMAGE TAB
        self.tab_import = QWidget()
        l_imp = QVBoxLayout(self.tab_import)
        self.lbl_imported_info = QLabel("No signature image loaded.", self)
        self.lbl_imported_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l_imp.addWidget(self.lbl_imported_info)

        btn_browse = QPushButton("📁 Browse Image File...", self)
        btn_browse.clicked.connect(self._browse_signature_image)
        l_imp.addWidget(btn_browse)
        l_imp.addStretch()
        self.tabs.addTab(self.tab_import, "🖼️ Import Image")

        layout.addWidget(self.tabs)

        self._imported_image: Optional[QImage] = None

        # Bottom Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_insert = QPushButton("Insert Signature ✍️", self)
        btn_insert.setStyleSheet("background-color: #2563EB; font-weight: bold; color: white;")
        btn_insert.clicked.connect(self._on_insert_clicked)
        btn_row.addWidget(btn_insert)

        layout.addLayout(btn_row)

    def _browse_signature_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Signature Image", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            img = QImage(path)
            if not img.isNull():
                self._imported_image = img
                self.lbl_imported_info.setText(f"Loaded: {path}")

    def _on_insert_clicked(self) -> None:
        tab_idx = self.tabs.currentIndex()
        if tab_idx == 0:
            # Drawn
            if not self.draw_canvas.strokes:
                self.reject()
                return
            # Normalize points relative to canvas
            cw = max(1.0, float(self.draw_canvas.width()))
            ch = max(1.0, float(self.draw_canvas.height()))
            normalized_strokes = []
            for stroke in self.draw_canvas.strokes:
                normalized_strokes.append([(pt[0] / cw, pt[1] / ch) for pt in stroke])

            self.created_signature_obj = PDFSignatureObject(
                sig_type=SignatureType.DRAWN,
                points=normalized_strokes,
                width_pt=180.0,
                height_pt=70.0,
            )
        elif tab_idx == 1:
            # Typed
            text = self.edit_typed.text().strip() or "Signature"
            font_name = self.combo_fonts.currentText()
            self.created_signature_obj = PDFSignatureObject(
                sig_type=SignatureType.TYPED,
                typed_text=text,
                typed_font=font_name,
                width_pt=200.0,
                height_pt=60.0,
            )
        else:
            # Image
            if not self._imported_image or self._imported_image.isNull():
                self.reject()
                return
            aspect = self._imported_image.width() / max(1, self._imported_image.height())
            self.created_signature_obj = PDFSignatureObject(
                sig_type=SignatureType.IMAGE,
                image=self._imported_image,
                width_pt=160.0,
                height_pt=160.0 / aspect,
            )

        self.accept()

