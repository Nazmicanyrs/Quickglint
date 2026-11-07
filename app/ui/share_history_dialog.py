"""Modern dark-themed UI Dialog for viewing, searching, and managing Image Share History."""

from datetime import datetime
import os
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.upload.history_manager import ShareHistoryManager
from app.upload.models import ShareHistoryItem
from app.utils.helpers import open_folder_in_file_manager
from app.utils.logger import logger


def _format_size(bytes_num: Optional[int]) -> str:
    """Format bytes to human readable string (KB, MB)."""
    if not bytes_num or bytes_num <= 0:
        return ""
    if bytes_num < 1024:
        return f"{bytes_num} B"
    if bytes_num < 1024 * 1024:
        return f"{bytes_num / 1024:.1f} KB"
    return f"{bytes_num / (1024 * 1024):.1f} MB"


def _format_timestamp(ts: float) -> str:
    """Format unix timestamp to localized readable string."""
    try:
        dt = datetime.fromtimestamp(ts)
        return dt.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return "Bilinmeyen Tarih"


class ShareHistoryItemWidget(QFrame):
    """Widget displaying a single uploaded share record with action buttons."""

    def __init__(
        self,
        item: ShareHistoryItem,
        on_delete_callback,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.item = item
        self.on_delete_callback = on_delete_callback

        self.setObjectName("shareHistoryItem")
        self.setStyleSheet(
            """
            QFrame#shareHistoryItem {
                background-color: rgba(30, 41, 59, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 10px 14px;
            }
            QFrame#shareHistoryItem:hover {
                background-color: rgba(30, 41, 59, 0.95);
                border-color: rgba(56, 189, 248, 0.3);
            }
            """
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        # Icon / Badge
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(get_icon("cloud_upload", "#38BDF8", 24).pixmap(24, 24))
        icon_lbl.setFixedSize(32, 32)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_lbl)

        # Metadata Details Column
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(3)

        # Title & Provider
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title_text = self.item.title or "Ekran Görüntüsü"
        title_lbl = QLabel(title_text, self)
        title_lbl.setStyleSheet("color: #F8FAFC; font-weight: 600; font-size: 13.5px;")
        title_row.addWidget(title_lbl)

        prov_badge = QLabel(self.item.provider or "ImgBB", self)
        prov_badge.setStyleSheet(
            """
            background-color: rgba(56, 189, 248, 0.15);
            color: #38BDF8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 4px;
            padding: 1px 6px;
            font-size: 11px;
            font-weight: 600;
            """
        )
        title_row.addWidget(prov_badge)
        title_row.addStretch()
        info_col.addLayout(title_row)

        # Subtitle: Date & Size & Expiration
        sub_text_parts = [_format_timestamp(self.item.timestamp)]
        sz_str = _format_size(self.item.size_bytes)
        if sz_str:
            sub_text_parts.append(sz_str)
        if self.item.expiration:
            sub_text_parts.append(f"Süre: {self.item.expiration}s")

        sub_lbl = QLabel("  •  ".join(sub_text_parts), self)
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 11.5px;")
        info_col.addWidget(sub_lbl)

        # URL Preview
        display_url = self.item.share_url or self.item.direct_url or ""
        url_lbl = QLabel(display_url, self)
        url_lbl.setStyleSheet("color: #60A5FA; font-size: 11.5px; font-family: 'Consolas', monospace;")
        url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_col.addWidget(url_lbl)

        layout.addLayout(info_col, stretch=1)

        # Action Buttons Column
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)

        # 1. Copy Share URL
        if self.item.share_url:
            btn_copy_share = QPushButton(" Paylaşım Linki", self)
            btn_copy_share.setIcon(get_icon("copy", "#38BDF8", 14))
            btn_copy_share.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_copy_share.setStyleSheet(self._btn_secondary_qss())
            btn_copy_share.setToolTip("Paylaşım sayfasını panoya kopyala")
            btn_copy_share.clicked.connect(lambda: self._copy_to_clipboard(self.item.share_url, "Paylaşım Bağlantısı"))
            btn_layout.addWidget(btn_copy_share)

        # 2. Copy Direct URL
        if self.item.direct_url:
            btn_copy_direct = QPushButton(" Direkt Link", self)
            btn_copy_direct.setIcon(get_icon("copy", "#34D399", 14))
            btn_copy_direct.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_copy_direct.setStyleSheet(self._btn_secondary_qss())
            btn_copy_direct.setToolTip("Doğrudan görsel CDN bağlantısını kopyala")
            btn_copy_direct.clicked.connect(lambda: self._copy_to_clipboard(self.item.direct_url, "Doğrudan Resim Linki"))
            btn_layout.addWidget(btn_copy_direct)

        # 3. Open in Browser
        target_url = self.item.share_url or self.item.direct_url
        if target_url:
            btn_open = QPushButton(self)
            btn_open.setIcon(get_icon("external_link", "#CBD5E1", 16))
            btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_open.setToolTip("Tarayıcıda Aç")
            btn_open.setFixedSize(32, 32)
            btn_open.setStyleSheet(self._icon_btn_qss())
            btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(target_url)))
            btn_layout.addWidget(btn_open)

        # 4. Delete Single Item
        btn_del = QPushButton(self)
        btn_del.setIcon(get_icon("trash", "#F87171", 16))
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setToolTip("Geçmişten Sil")
        btn_del.setFixedSize(32, 32)
        btn_del.setStyleSheet(self._icon_btn_danger_qss())
        btn_del.clicked.connect(self._on_delete_clicked)
        btn_layout.addWidget(btn_del)

        layout.addLayout(btn_layout)

    def _copy_to_clipboard(self, url: str, label_type: str) -> None:
        QApplication.clipboard().setText(url)
        NotificationManager.show_toast("Panoya Kopyalandı", f"{label_type} panoya kopyalandı:\n{url}", "copy", 2500)

    def _on_delete_clicked(self) -> None:
        self.on_delete_callback(self.item)

    @staticmethod
    def _btn_secondary_qss() -> str:
        return """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
                border-color: rgba(255, 255, 255, 0.25);
                color: #FFFFFF;
            }
        """

    @staticmethod
    def _icon_btn_qss() -> str:
        return """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                border-color: rgba(255, 255, 255, 0.25);
            }
        """

    @staticmethod
    def _icon_btn_danger_qss() -> str:
        return """
            QPushButton {
                background-color: rgba(239, 68, 68, 0.1);
                border: 1px solid rgba(239, 68, 68, 0.25);
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.25);
                border-color: rgba(239, 68, 68, 0.45);
            }
        """


class ShareHistoryDialog(QDialog):
    """Full-featured standalone dialog for inspecting and managing local share history."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quickglint — Paylaşım ve Yükleme Geçmişi")
        self.resize(780, 580)
        self.setMinimumSize(640, 420)
        self.setStyleSheet(DARK_THEME_QSS)

        self._all_items: List[ShareHistoryItem] = []
        self._filtered_items: List[ShareHistoryItem] = []

        self._setup_ui()
        self._load_items()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(14)

        # 1. Header (Title, Subtitle, Counter Badge)
        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(12)

        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(get_icon("cloud_upload", "#38BDF8", 28).pixmap(28, 28))
        hdr_layout.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        title_lbl = QLabel("Görsel Paylaşım Geçmişi", self)
        title_lbl.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: 700;")
        title_box.addWidget(title_lbl)

        sub_lbl = QLabel("Daha önce buluta yüklediğiniz ve paylaştığınız görsellerin yerel kayıtları.", self)
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 12.5px;")
        title_box.addWidget(sub_lbl)
        hdr_layout.addLayout(title_box)

        hdr_layout.addStretch()

        self.count_badge = QLabel("0 Görsel", self)
        self.count_badge.setStyleSheet(
            """
            background-color: rgba(99, 102, 241, 0.2);
            color: #A5B4FC;
            border: 1px solid rgba(99, 102, 241, 0.4);
            border-radius: 12px;
            padding: 4px 14px;
            font-size: 12px;
            font-weight: 600;
            """
        )
        hdr_layout.addWidget(self.count_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        main_layout.addLayout(hdr_layout)

        # 2. File Path Bar (Shows exact storage file and button to open in Explorer)
        path_card = QFrame(self)
        path_card.setStyleSheet(
            """
            QFrame {
                background-color: rgba(15, 23, 42, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 6px 12px;
            }
            """
        )
        path_layout = QHBoxLayout(path_card)
        path_layout.setContentsMargins(10, 6, 10, 6)
        path_layout.setSpacing(10)

        folder_icon = QLabel(path_card)
        folder_icon.setPixmap(get_icon("folder", "#FCD34D", 18).pixmap(18, 18))
        path_layout.addWidget(folder_icon)

        file_path = ShareHistoryManager.get_history_file_path()
        self.lbl_path = QLabel(str(file_path), path_card)
        self.lbl_path.setStyleSheet("color: #CBD5E1; font-size: 12px; font-family: 'Consolas', monospace;")
        self.lbl_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_layout.addWidget(self.lbl_path, stretch=1)

        btn_open_folder = QPushButton(" Klasörde Göster", path_card)
        btn_open_folder.setIcon(get_icon("folder", "#FCD34D", 14))
        btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_folder.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                color: #F1F5F9;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11.5px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border-color: rgba(255, 255, 255, 0.22);
            }
            """
        )
        btn_open_folder.clicked.connect(self._on_open_storage_folder)
        path_layout.addWidget(btn_open_folder)

        main_layout.addWidget(path_card)

        # 3. Search Bar
        search_box = QHBoxLayout()
        search_box.setContentsMargins(0, 0, 0, 0)
        search_box.setSpacing(8)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("🔍 Görsel adı veya bağlantı ile geçmişte ara...")
        self.search_edit.setStyleSheet(
            """
            QLineEdit {
                background-color: rgba(15, 23, 42, 0.9);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #38BDF8;
            }
            """
        )
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_box.addWidget(self.search_edit)

        main_layout.addLayout(search_box)

        # 4. Scroll Area for Items
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 4, 0, 4)
        self.list_layout.setSpacing(8)

        self.scroll_area.setWidget(self.list_container)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # 5. Empty State Message
        self.empty_widget = QWidget(self)
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setContentsMargins(20, 40, 20, 40)
        empty_layout.setSpacing(10)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = QLabel(self.empty_widget)
        empty_icon.setPixmap(get_icon("inbox", "#64748B", 48).pixmap(48, 48))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_title = QLabel("Kayıtlı Paylaşım Geçmişi Bulunmuyor", self.empty_widget)
        empty_title.setStyleSheet("color: #94A3B8; font-size: 15px; font-weight: 600;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)

        empty_desc = QLabel("Ekran görüntüsü alıp ImgBB'ye yüklediğinizde bağlantılar burada listelenecektir.", self.empty_widget)
        empty_desc.setStyleSheet("color: #64748B; font-size: 12px;")
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_desc)

        main_layout.addWidget(self.empty_widget)

        # 6. Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 4, 0, 0)
        bottom_bar.setSpacing(12)

        self.btn_clear_all = QPushButton("  Tüm Geçmişi Temizle", self)
        self.btn_clear_all.setIcon(get_icon("trash", "#F87171", 14))
        self.btn_clear_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_all.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(239, 68, 68, 0.12);
                color: #FCA5A5;
                border: 1px solid rgba(239, 68, 68, 0.28);
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12.5px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.25);
                border-color: rgba(239, 68, 68, 0.5);
                color: #FFFFFF;
            }
            """
        )
        self.btn_clear_all.clicked.connect(self._on_clear_all_clicked)
        bottom_bar.addWidget(self.btn_clear_all)

        bottom_bar.addStretch()

        btn_refresh = QPushButton(" Yenile", self)
        btn_refresh.setIcon(get_icon("reset", "#CBD5E1", 14))
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                padding: 8px 18px;
                font-weight: 600;
                font-size: 12.5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
            """
        )
        btn_refresh.clicked.connect(self._load_items)
        bottom_bar.addWidget(btn_refresh)

        btn_close = QPushButton("Kapat", self)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                padding: 8px 24px;
                font-weight: 600;
                font-size: 12.5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
            """
        )
        btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(btn_close)

        main_layout.addLayout(bottom_bar)

    def _load_items(self) -> None:
        """Loads all records from ShareHistoryManager and updates the UI."""
        self._all_items = ShareHistoryManager.get_items()
        self._apply_filter()

    def _on_search_changed(self, query: str) -> None:
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search_edit.text().strip().lower()
        if query:
            self._filtered_items = [
                it for it in self._all_items
                if (it.title and query in it.title.lower())
                or (it.share_url and query in it.share_url.lower())
                or (it.direct_url and query in it.direct_url.lower())
                or (it.provider and query in it.provider.lower())
            ]
        else:
            self._filtered_items = list(self._all_items)

        self._render_list()

    def _render_list(self) -> None:
        # Clear layout items
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        count = len(self._all_items)
        filtered_count = len(self._filtered_items)
        if count == filtered_count:
            self.count_badge.setText(f"{count} Görsel")
        else:
            self.count_badge.setText(f"{filtered_count} / {count} Görsel")

        if not self._filtered_items:
            self.scroll_area.hide()
            self.empty_widget.show()
            self.btn_clear_all.setEnabled(count > 0)
            return

        self.empty_widget.hide()
        self.scroll_area.show()
        self.btn_clear_all.setEnabled(True)

        for item in self._filtered_items:
            w = ShareHistoryItemWidget(item, on_delete_callback=self._on_delete_single_item, parent=self.list_container)
            self.list_layout.addWidget(w)

        self.list_layout.addStretch()

    def _on_delete_single_item(self, item: ShareHistoryItem) -> None:
        target_url = item.share_url or item.direct_url or ""
        if ShareHistoryManager.delete_item(target_url):
            self._load_items()
            NotificationManager.show_toast("Kayıt Silindi", "Görsel paylaşım kaydı geçmişten silindi.", "trash", 2000)

    def _on_clear_all_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Geçmişi Temizle",
            "Tüm yerel paylaşım geçmişi kayıtları silinecektir.\n\nBu işlem geri alınamaz. Devam etmek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ShareHistoryManager.clear_history()
            self._load_items()
            NotificationManager.show_toast("Geçmiş Temizlendi", "Tüm paylaşım geçmişi silindi.", "trash", 2500)

    def _on_open_storage_folder(self) -> None:
        path = ShareHistoryManager.get_history_file_path()
        open_folder_in_file_manager(str(path.parent))

