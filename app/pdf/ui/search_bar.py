"""Search and Find HUD bar for searching vector text and OCR layers across all document pages."""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from app.pdf.document import PDFDocument, PDFTextObject


class PDFSearchBar(QFrame):
    """Floating HUD bar for in-document search across selectable and OCR text layers."""

    match_selected = Signal(int, object)  # (page_index, PDFTextObject)
    closed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 4px;
            }
            QLineEdit {
                background-color: #0F172A;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 4px 8px;
                color: #F8FAFC;
                font-size: 11px;
                min-width: 180px;
            }
            QPushButton {
                background-color: #334155;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                color: #F8FAFC;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
            QLabel {
                color: #94A3B8;
                font-size: 11px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        layout.addWidget(QLabel("🔍 Find:"))

        self.edit_search = QLineEdit(self)
        self.edit_search.setPlaceholderText("Search text or OCR...")
        self.edit_search.textChanged.connect(self._on_search_text_changed)
        self.edit_search.returnPressed.connect(self.find_next)
        layout.addWidget(self.edit_search)

        self.lbl_count = QLabel("0 / 0", self)
        layout.addWidget(self.lbl_count)

        self.btn_prev = QPushButton("◀", self)
        self.btn_prev.clicked.connect(self.find_prev)
        layout.addWidget(self.btn_prev)

        self.btn_next = QPushButton("▶", self)
        self.btn_next.clicked.connect(self.find_next)
        layout.addWidget(self.btn_next)

        self.btn_close = QPushButton("✕", self)
        self.btn_close.setFixedWidth(24)
        self.btn_close.clicked.connect(self.hide)
        layout.addWidget(self.btn_close)

        self._doc: Optional[PDFDocument] = None
        self._matches: List[Tuple[int, PDFTextObject]] = []
        self._current_match_idx: int = -1

    def set_document(self, doc: PDFDocument) -> None:
        self._doc = doc
        self._on_search_text_changed(self.edit_search.text())

    def _on_search_text_changed(self, text: str) -> None:
        text = text.strip().lower()
        self._matches.clear()
        self._current_match_idx = -1

        if not text or not self._doc:
            self.lbl_count.setText("0 / 0")
            return

        for p_idx, page in enumerate(self._doc.pages):
            for obj in page.objects:
                if isinstance(obj, PDFTextObject):
                    if text in obj.text.lower():
                        self._matches.append((p_idx, obj))

        total = len(self._matches)
        if total > 0:
            self._current_match_idx = 0
            self.lbl_count.setText(f"1 / {total}")
            self._jump_to_current_match()
        else:
            self.lbl_count.setText("0 / 0")

    def find_next(self) -> None:
        if not self._matches:
            return
        self._current_match_idx = (self._current_match_idx + 1) % len(self._matches)
        self.lbl_count.setText(f"{self._current_match_idx + 1} / {len(self._matches)}")
        self._jump_to_current_match()

    def find_prev(self) -> None:
        if not self._matches:
            return
        self._current_match_idx = (self._current_match_idx - 1 + len(self._matches)) % len(self._matches)
        self.lbl_count.setText(f"{self._current_match_idx + 1} / {len(self._matches)}")
        self._jump_to_current_match()

    def _jump_to_current_match(self) -> None:
        if 0 <= self._current_match_idx < len(self._matches):
            p_idx, obj = self._matches[self._current_match_idx]
            self.match_selected.emit(p_idx, obj)

