"""Pages sidebar showing real-time rendered thumbnails, drag-and-drop ordering, and page actions."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.pdf.document import PDFDocument, PDFPage
from app.pdf.render_engine import PDFRenderEngine
from app.ui.styles import get_icon


class PageThumbnailWidget(QWidget):
    """Custom item widget rendering page number and rendered thumbnail image."""

    def __init__(self, page_num: int, thumbnail: QImage, is_selected: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.page_num = page_num
        self.thumbnail = thumbnail
        self.is_selected = is_selected
        self.setFixedHeight(140)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Draw selection indicator
        if self.is_selected:
            painter.fillRect(self.rect(), QColor("#1E293B"))
            painter.setPen(QColor("#2563EB"))
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 6, 6)

        # Draw page badge
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QColor("#38BDF8" if self.is_selected else "#94A3B8"))
        painter.drawText(QRect(0, 4, self.width(), 16), Qt.AlignmentFlag.AlignCenter, f"Page {self.page_num}")

        # Draw Thumbnail
        if not self.thumbnail.isNull():
            t_w = min(self.width() - 24, self.thumbnail.width())
            t_h = min(110, self.thumbnail.height())
            aspect = self.thumbnail.width() / max(1, self.thumbnail.height())

            if aspect >= 1.0:
                draw_w = self.width() - 24
                draw_h = int(draw_w / aspect)
            else:
                draw_h = 105
                draw_w = int(draw_h * aspect)

            tx = (self.width() - draw_w) / 2.0
            ty = 24 + (105 - draw_h) / 2.0
            thumb_rect = QRect(int(tx), int(ty), draw_w, draw_h)

            # Thumbnail paper shadow
            painter.fillRect(thumb_rect.adjusted(2, 2, 2, 2), QColor(0, 0, 0, 80))
            painter.drawImage(thumb_rect, self.thumbnail)
            painter.setPen(QPen(QColor("#334155"), 1))
            painter.drawRect(thumb_rect)
        painter.end()


class PDFPagesSidebar(QWidget):
    """Left sidebar containing the page list with thumbnails, drag-and-drop reordering, and action buttons."""

    page_selected = Signal(int)
    page_add_requested = Signal()
    page_duplicate_requested = Signal(int)
    page_delete_requested = Signal(int)
    page_reordered = Signal(int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(190)
        self.setStyleSheet("""
            QWidget {
                background-color: #0F172A;
                color: #F8FAFC;
            }
            QListWidget {
                background-color: #0B0F19;
                border: 1px solid #1E293B;
                border-radius: 8px;
                outline: none;
            }
            QListWidget::item {
                border-radius: 6px;
                margin: 4px;
            }
            QListWidget::item:selected {
                background-color: #1E293B;
                border: 1px solid #2563EB;
            }
            QPushButton#actionBtn {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px;
                color: #F8FAFC;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#actionBtn:hover {
                background-color: #2563EB;
                border-color: #3B82F6;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header Title
        lbl_title = QLabel("📄 PAGES", self)
        lbl_title.setStyleSheet("font-weight: 700; color: #38BDF8; font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(lbl_title)

        # List Widget
        self.list_widget = QListWidget(self)
        self.list_widget.setIconSize(QSize(130, 100))
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.currentRowChanged.connect(self._on_current_row_changed)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.list_widget)

        # Bottom Quick Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self.btn_add = QPushButton("➕ Add", self)
        self.btn_add.setObjectName("actionBtn")
        self.btn_add.clicked.connect(self.page_add_requested.emit)
        btn_layout.addWidget(self.btn_add)

        self.btn_dup = QPushButton("📑 Duplicate", self)
        self.btn_dup.setObjectName("actionBtn")
        self.btn_dup.clicked.connect(self._on_duplicate_clicked)
        btn_layout.addWidget(self.btn_dup)

        self.btn_del = QPushButton("🗑️", self)
        self.btn_del.setObjectName("actionBtn")
        self.btn_del.setFixedWidth(32)
        self.btn_del.clicked.connect(self._on_delete_clicked)
        btn_layout.addWidget(self.btn_del)

        layout.addLayout(btn_layout)

        self._doc: Optional[PDFDocument] = None

    def set_document(self, doc: PDFDocument, active_index: int = 0) -> None:
        self._doc = doc
        self.refresh_thumbnails(active_index)

    def refresh_thumbnails(self, active_index: int = 0) -> None:
        if not self._doc:
            self.list_widget.clear()
            return

        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        for idx, page in enumerate(self._doc.pages):
            thumb_img = PDFRenderEngine.render_page_to_image(page, doc_settings=self._doc.settings, max_dim=140)
            item = QListWidgetItem()
            item.setSizeHint(QSize(160, 140))
            self.list_widget.addItem(item)

            thumb_widget = PageThumbnailWidget(
                page_num=idx + 1,
                thumbnail=thumb_img,
                is_selected=(idx == active_index),
            )
            self.list_widget.setItemWidget(item, thumb_widget)

        if 0 <= active_index < self.list_widget.count():
            self.list_widget.setCurrentRow(active_index)

        self.list_widget.blockSignals(False)

    def _on_current_row_changed(self, row: int) -> None:
        if row >= 0:
            self.page_selected.emit(row)
            # Update selection highlights
            for i in range(self.list_widget.count()):
                w = self.list_widget.itemWidget(self.list_widget.item(i))
                if isinstance(w, PageThumbnailWidget):
                    w.is_selected = (i == row)
                    w.update()

    def _on_duplicate_clicked(self) -> None:
        cur = self.list_widget.currentRow()
        if cur >= 0:
            self.page_duplicate_requested.emit(cur)

    def _on_delete_clicked(self) -> None:
        cur = self.list_widget.currentRow()
        if cur >= 0:
            self.page_delete_requested.emit(cur)

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self.list_widget.itemAt(pos)
        row = self.list_widget.row(item) if item else -1

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1E293B;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #2563EB;
            }
        """)

        act_add = menu.addAction("➕ Add New Page")
        act_add.triggered.connect(self.page_add_requested.emit)

        if row >= 0:
            act_dup = menu.addAction(f"📑 Duplicate Page {row + 1}")
            act_dup.triggered.connect(lambda: self.page_duplicate_requested.emit(row))

            act_del = menu.addAction(f"🗑️ Delete Page {row + 1}")
            act_del.triggered.connect(lambda: self.page_delete_requested.emit(row))
            if self.list_widget.count() <= 1:
                act_del.setEnabled(False)

        menu.exec(self.list_widget.mapToGlobal(pos))

