"""Interactive on-image highlight and selection overlay for OCR text bounding boxes."""

from typing import List, Optional, Set
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from app.ocr.models import OCRStructuredResult, OCRWord


class OCRHighlightOverlay(QWidget):
    """Interactive visual layer displaying OCR bounding boxes over the image with selection support."""

    selection_changed = Signal(set)  # Set of word IDs
    word_clicked = Signal(str)

    def __init__(
        self,
        base_pixmap: QPixmap,
        ocr_result: OCRStructuredResult,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.base_pixmap = base_pixmap
        self.ocr_result = ocr_result
        self.selected_word_ids: Set[str] = set()
        self.hovered_word_id: Optional[str] = None

        self.setFixedSize(base_pixmap.size())
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Select all words by default initially
        all_words = ocr_result.get_all_words()
        self.selected_word_ids = {w.id for w in all_words}

    def set_ocr_result(self, result: OCRStructuredResult) -> None:
        self.ocr_result = result
        self.selected_word_ids = {w.id for w in result.get_all_words()}
        self.update()
        self.selection_changed.emit(self.selected_word_ids)

    def select_all(self) -> None:
        self.selected_word_ids = {w.id for w in self.ocr_result.get_all_words()}
        self.update()
        self.selection_changed.emit(self.selected_word_ids)

    def clear_selection(self) -> None:
        self.selected_word_ids.clear()
        self.update()
        self.selection_changed.emit(self.selected_word_ids)

    def _get_word_at_pos(self, pos: QPoint) -> Optional[OCRWord]:
        words = self.ocr_result.get_all_words()
        for w in words:
            if w.bounding_box.contains(pos):
                return w
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        w = self._get_word_at_pos(event.pos())
        if not w:
            if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self.clear_selection()
            return

        is_ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

        if is_ctrl:
            if w.id in self.selected_word_ids:
                self.selected_word_ids.remove(w.id)
            else:
                self.selected_word_ids.add(w.id)
        else:
            self.selected_word_ids = {w.id}

        self.update()
        self.selection_changed.emit(self.selected_word_ids)
        self.word_clicked.emit(w.id)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        w = self._get_word_at_pos(event.pos())
        new_hover = w.id if w else None
        if new_hover != self.hovered_word_id:
            self.hovered_word_id = new_hover
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Draw base image
        painter.drawPixmap(0, 0, self.base_pixmap)

        # 2. Dim background slightly if there are selections
        words = self.ocr_result.get_all_words()

        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)

        for w in words:
            box = w.bounding_box
            is_selected = w.id in self.selected_word_ids
            is_hovered = w.id == self.hovered_word_id
            is_low_conf = w.confidence < 0.70

            # Determine colors
            if is_selected:
                if is_low_conf:
                    fill_color = QColor(217, 119, 6, 95)  # Amber
                    border_color = QColor("#F59E0B")
                else:
                    fill_color = QColor(37, 99, 235, 95)  # Royal Blue
                    border_color = QColor("#38BDF8")
            elif is_hovered:
                fill_color = QColor(56, 189, 248, 60)
                border_color = QColor("#67E8F9")
            else:
                fill_color = QColor(15, 23, 42, 40)
                border_color = QColor(148, 163, 184, 80)

            # Draw highlight box with subtle rounded corners
            painter.setBrush(QBrush(fill_color))
            painter.setPen(QPen(border_color, 2.0 if is_selected else (1.5 if is_hovered else 1.0)))
            painter.drawRoundedRect(box, 3, 3)

            # Low confidence warning badge
            if is_low_conf and (is_selected or is_hovered):
                badge_rect = QRect(box.left(), max(0, box.top() - 15), 18, 14)
                painter.setBrush(QBrush(QColor("#D97706")))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(badge_rect, 3, 3)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "⚠")

        painter.end()

