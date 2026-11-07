"""Header, Footer, and Page Numbering configuration modal with live macro substitution."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.pdf.document import PageNumberConfig
from app.pdf.models import HeaderFooterConfig, PageNumberPosition
from app.ui.styles import DARK_THEME_QSS


class PDFHeaderFooterDialog(QDialog):
    """Configuration dialog for document headers, footers, and page numbers."""

    def __init__(
        self,
        header_footer: HeaderFooterConfig,
        page_numbers: PageNumberConfig,
        parent: Optional[QDialog] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Header, Footer & Page Numbers — Quickglint PDF")
        self.resize(520, 480)
        self.setStyleSheet(DARK_THEME_QSS)

        self.hf_config = header_footer
        self.pn_config = page_numbers

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # 1. HEADER BOX
        box_header = QGroupBox("Header Settings", self)
        l_h = QVBoxLayout(box_header)

        l_h.addWidget(QLabel("Header Text:"))
        self.edit_header = QLineEdit(self.hf_config.header_text)
        self.edit_header.setPlaceholderText("e.g. {title} — Confidential")
        l_h.addWidget(self.edit_header)

        row_h_align = QHBoxLayout()
        row_h_align.addWidget(QLabel("Alignment:"))
        self.combo_h_align = QComboBox()
        self.combo_h_align.addItems(["Left", "Center", "Right"])
        self.combo_h_align.setCurrentText(self.hf_config.header_alignment.capitalize())
        row_h_align.addWidget(self.combo_h_align)
        l_h.addLayout(row_h_align)
        layout.addWidget(box_header)

        # 2. FOOTER BOX
        box_footer = QGroupBox("Footer Settings", self)
        l_f = QVBoxLayout(box_footer)

        l_f.addWidget(QLabel("Footer Text:"))
        self.edit_footer = QLineEdit(self.hf_config.footer_text)
        self.edit_footer.setPlaceholderText("e.g. Generated on {date} — Page {page} of {pages}")
        l_f.addWidget(self.edit_footer)

        row_f_align = QHBoxLayout()
        row_f_align.addWidget(QLabel("Alignment:"))
        self.combo_f_align = QComboBox()
        self.combo_f_align.addItems(["Left", "Center", "Right"])
        self.combo_f_align.setCurrentText(self.hf_config.footer_alignment.capitalize())
        row_f_align.addWidget(self.combo_f_align)
        l_f.addLayout(row_f_align)

        # Macro insertion helper buttons
        row_macros = QHBoxLayout()
        row_macros.addWidget(QLabel("Insert Macro:"))
        for macro in ["{page}", "{pages}", "{date}", "{time}", "{title}"]:
            btn_m = QPushButton(macro)
            btn_m.setStyleSheet("background-color: #1E293B; border: 1px solid #334155; font-size: 10px; padding: 2px 6px;")
            btn_m.clicked.connect(lambda _, m=macro: self._insert_macro(m))
            row_macros.addWidget(btn_m)
        l_f.addLayout(row_macros)

        layout.addWidget(box_footer)

        # 3. PAGE NUMBERS BOX
        box_pn = QGroupBox("Automatic Page Numbering", self)
        l_pn = QVBoxLayout(box_pn)

        self.chk_pn = QCheckBox("Enable Page Numbers")
        self.chk_pn.setChecked(self.pn_config.enabled and self.pn_config.position != PageNumberPosition.NONE)
        l_pn.addWidget(self.chk_pn)

        row_pn_pos = QHBoxLayout()
        row_pn_pos.addWidget(QLabel("Position:"))
        self.combo_pn_pos = QComboBox()
        for pos in PageNumberPosition:
            self.combo_pn_pos.addItem(pos.value, pos)
        self.combo_pn_pos.setCurrentText(self.pn_config.position.value)
        row_pn_pos.addWidget(self.combo_pn_pos)

        row_pn_pos.addWidget(QLabel("Format:"))
        self.combo_pn_fmt = QComboBox()
        self.combo_pn_fmt.addItems([
            "{page}",
            "Page {page}",
            "{page} / {pages}",
            "Page {page} of {pages}",
        ])
        self.combo_pn_fmt.setEditable(True)
        self.combo_pn_fmt.setCurrentText(self.pn_config.format_template)
        row_pn_pos.addWidget(self.combo_pn_fmt)
        l_pn.addLayout(row_pn_pos)

        row_pn_start = QHBoxLayout()
        row_pn_start.addWidget(QLabel("Start Numbering At:"))
        self.spin_start_num = QSpinBox()
        self.spin_start_num.setRange(1, 1000)
        self.spin_start_num.setValue(self.pn_config.start_number)
        row_pn_start.addWidget(self.spin_start_num)
        row_pn_start.addStretch()
        l_pn.addLayout(row_pn_start)

        layout.addWidget(box_pn)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Apply Settings", self)
        btn_save.setStyleSheet("background-color: #2563EB; font-weight: bold; color: white;")
        btn_save.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _insert_macro(self, macro: str) -> None:
        if self.edit_footer.hasFocus():
            self.edit_footer.insert(macro)
        else:
            self.edit_header.insert(macro)

    def _on_save_clicked(self) -> None:
        self.hf_config.header_text = self.edit_header.text().strip()
        self.hf_config.header_alignment = self.combo_h_align.currentText()
        self.hf_config.footer_text = self.edit_footer.text().strip()
        self.hf_config.footer_alignment = self.combo_f_align.currentText()

        self.pn_config.enabled = self.chk_pn.isChecked()
        self.pn_config.position = self.combo_pn_pos.currentData() if self.chk_pn.isChecked() else PageNumberPosition.NONE
        self.pn_config.format_template = self.combo_pn_fmt.currentText()
        self.pn_config.start_number = self.spin_start_num.value()

        self.accept()

