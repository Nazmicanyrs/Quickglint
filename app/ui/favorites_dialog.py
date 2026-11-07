"""Modern, dark-themed UI Dialog for viewing, searching, and managing Favorited Screenshots."""

import os
from pathlib import Path
import subprocess
import sys
import time
from typing import List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.favorites.manager import FavoritesManager
from app.favorites.models import FavoriteItem
from app.services.clipboard_service import ClipboardService
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.helpers import get_default_screenshots_dir
from app.utils.i18n import tr
from app.utils.logger import logger


class FavoriteItemWidget(QFrame):
    """Custom rich widget representation for a Favorite item in List View."""

    remove_requested = Signal(str)

    def __init__(self, item: FavoriteItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setObjectName("favoriteItemWidget")
        self.setStyleSheet(
            """
            QFrame#favoriteItemWidget {
                background-color: rgba(30, 41, 59, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 4px 8px;
            }
            QFrame#favoriteItemWidget:hover {
                background-color: rgba(51, 65, 85, 0.85);
                border-color: rgba(56, 189, 248, 0.4);
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        # 1. Thumbnail
        self.thumb_label = QLabel(self)
        self.thumb_label.setFixedSize(64, 44)
        self.thumb_label.setStyleSheet("background-color: #0F172A; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1);")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        thumb = FavoritesManager.get_thumbnail(item.file_path, QSize(64, 44))
        if thumb and not thumb.isNull():
            self.thumb_label.setPixmap(thumb.scaled(64, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.thumb_label.setPixmap(get_icon("camera" if item.exists else "info", "#64748B" if item.exists else "#EF4444", 22).pixmap(22, 22))
        layout.addWidget(self.thumb_label)

        # 2. Information Column
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        star_icon = QLabel(self)
        star_icon.setPixmap(get_icon("star_filled", "#FBBF24", 14).pixmap(14, 14))
        title_row.addWidget(star_icon)

        filename_lbl = QLabel(item.filename, self)
        filename_lbl.setStyleSheet("color: #F8FAFC; font-weight: 600; font-size: 13px;")
        title_row.addWidget(filename_lbl)

        if not item.exists:
            missing_tag = QLabel("⚠️ Dosya Bulunamadı (Missing)", self)
            missing_tag.setStyleSheet("color: #EF4444; font-size: 11px; font-weight: 700; background: rgba(239, 68, 68, 0.15); padding: 2px 6px; border-radius: 4px;")
            title_row.addWidget(missing_tag)

        title_row.addStretch()
        info_col.addLayout(title_row)

        # Sub details row
        time_str = time.strftime("%d.%m.%Y %H:%M", time.localtime(item.favorited_at))
        meta_parts = [f"Favorilendi: {time_str}"]
        if item.formatted_dimensions:
            meta_parts.append(item.formatted_dimensions)
        if item.formatted_size != "0 KB":
            meta_parts.append(item.formatted_size)

        sub_lbl = QLabel(" • ".join(meta_parts), self)
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 11.5px;")
        info_col.addWidget(sub_lbl)

        layout.addLayout(info_col, stretch=1)

        # 3. Actions (Remove from favorite)
        btn_unfav = QToolButton(self)
        btn_unfav.setIcon(get_icon("trash", "#94A3B8", 16))
        btn_unfav.setToolTip("Favorilerden Çıkar")
        btn_unfav.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_unfav.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 6px; border-radius: 6px; } "
            "QToolButton:hover { background-color: rgba(239, 68, 68, 0.2); color: #EF4444; }"
        )
        btn_unfav.clicked.connect(lambda: self.remove_requested.emit(item.file_path))
        layout.addWidget(btn_unfav)


class FavoritesDialog(QDialog):
    """Professional Standalone Dialog for searching, managing, and viewing favorite screenshots."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Quickglint — Favoriler (Favorites)")
        self.setWindowIcon(get_icon("star_filled", "#FBBF24", 24))
        self.resize(880, 640)
        self.setMinimumSize(680, 480)
        self.setStyleSheet(DARK_THEME_QSS)

        self._all_items: List[FavoriteItem] = []
        self._filtered_items: List[FavoriteItem] = []
        self._is_grid_view: bool = True

        self._setup_ui()
        self._setup_shortcuts()
        self._connect_signals()
        self._load_favorites()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(14)

        # 1. Header Bar
        header = QHBoxLayout()
        header.setSpacing(10)

        star_brand = QLabel(self)
        star_brand.setPixmap(get_icon("star_filled", "#FBBF24", 26).pixmap(26, 26))
        header.addWidget(star_brand)

        title_label = QLabel("Favori Ekran Görüntüleri", self)
        title_label.setStyleSheet("color: #FFFFFF; font-size: 17px; font-weight: 700;")
        header.addWidget(title_label)

        self.count_badge = QLabel("0", self)
        self.count_badge.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; font-size: 11.5px; font-weight: 700; "
            "border-radius: 10px; padding: 2px 9px; min-width: 14px; text-align: center;"
        )
        header.addWidget(self.count_badge)

        header.addStretch()

        # Open Screenshots Directory button
        btn_open_folder = QPushButton(" Klasörü Aç", self)
        btn_open_folder.setIcon(get_icon("folder", "#38BDF8", 16))
        btn_open_folder.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.14); "
            "border-radius: 7px; padding: 6px 12px; font-size: 12.5px; font-weight: 500; } "
            "QPushButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: #38BDF8; color: #FFFFFF; }"
        )
        btn_open_folder.setToolTip("Ekran Görüntüleri Kayıt Klasörünü Aç")
        btn_open_folder.clicked.connect(self._on_open_screenshots_folder)
        header.addWidget(btn_open_folder)

        # Clean missing files button
        self.btn_clean_missing = QPushButton(" Eksikleri Temizle", self)
        self.btn_clean_missing.setIcon(get_icon("reset", "#F59E0B", 16))
        self.btn_clean_missing.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.14); "
            "border-radius: 7px; padding: 6px 12px; font-size: 12.5px; font-weight: 500; } "
            "QPushButton:hover { background-color: rgba(245, 158, 11, 0.2); border-color: #F59E0B; color: #FCD34D; }"
        )
        self.btn_clean_missing.setToolTip("Diskte bulunamayan silinmiş favorileri listeden kaldır")
        self.btn_clean_missing.clicked.connect(self._on_clean_missing_files)
        header.addWidget(self.btn_clean_missing)

        main_layout.addLayout(header)

        # 2. Control Ribbon (Search Bar, Sort Combo, View Mode Toggle)
        controls_frame = QFrame(self)
        controls_frame.setStyleSheet(
            "QFrame { background-color: #131D31; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 4px; }"
        )
        controls_layout = QHBoxLayout(controls_frame)
        controls_layout.setContentsMargins(8, 6, 8, 6)
        controls_layout.setSpacing(10)

        # Search box
        search_icon = QLabel(controls_frame)
        search_icon.setPixmap(get_icon("search", "#94A3B8", 16).pixmap(16, 16))
        controls_layout.addWidget(search_icon)

        self.search_edit = QLineEdit(controls_frame)
        self.search_edit.setPlaceholderText("Favorilerde ara (dosya adı, tarih, not)...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: #FFFFFF; font-size: 13px; padding: 4px; } "
            "QLineEdit:focus { border: none; }"
        )
        self.search_edit.textChanged.connect(self._apply_filter_and_sort)
        controls_layout.addWidget(self.search_edit, stretch=1)

        # Sort Dropdown
        lbl_sort = QLabel("Sırala:", controls_frame)
        lbl_sort.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        controls_layout.addWidget(lbl_sort)

        self.sort_combo = QComboBox(controls_frame)
        self.sort_combo.addItem("En Son Eklenen (Newest)", "newest")
        self.sort_combo.addItem("En Eski Eklenen (Oldest)", "oldest")
        self.sort_combo.addItem("İsim: A - Z (Name A-Z)", "name_asc")
        self.sort_combo.addItem("İsim: Z - A (Name Z-A)", "name_desc")
        self.sort_combo.addItem("Boyut: Büyükten Küçüğe (Size)", "size_desc")
        self.sort_combo.addItem("Boyut: Küçükten Büyüğe", "size_asc")
        self.sort_combo.setStyleSheet(
            "QComboBox { background-color: #0F172A; color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.14); "
            "border-radius: 6px; padding: 4px 10px; font-size: 12px; min-width: 170px; } "
            "QComboBox::drop-down { border: none; } "
            "QComboBox QAbstractItemView { background-color: #0F172A; color: #F1F5F9; border: 1px solid #334155; "
            "selection-background-color: #2563EB; selection-color: #FFFFFF; padding: 4px; }"
        )
        self.sort_combo.currentIndexChanged.connect(self._apply_filter_and_sort)
        controls_layout.addWidget(self.sort_combo)

        # View Mode Toggle (Grid vs List)
        self.btn_grid_mode = QToolButton(controls_frame)
        self.btn_grid_mode.setIcon(get_icon("monitor", "#38BDF8", 16))
        self.btn_grid_mode.setCheckable(True)
        self.btn_grid_mode.setChecked(True)
        self.btn_grid_mode.setToolTip("Thumbnail Izgara Görünümü")
        self.btn_grid_mode.setStyleSheet(self._view_btn_qss())
        self.btn_grid_mode.clicked.connect(lambda: self._set_view_mode(True))
        controls_layout.addWidget(self.btn_grid_mode)

        self.btn_list_mode = QToolButton(controls_frame)
        self.btn_list_mode.setIcon(get_icon("file_text", "#94A3B8", 16))
        self.btn_list_mode.setCheckable(True)
        self.btn_list_mode.setChecked(False)
        self.btn_list_mode.setToolTip("Liste Görünümü")
        self.btn_list_mode.setStyleSheet(self._view_btn_qss())
        self.btn_list_mode.clicked.connect(lambda: self._set_view_mode(False))
        controls_layout.addWidget(self.btn_list_mode)

        main_layout.addWidget(controls_frame)

        # 3. Main Central List / Grid View
        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setStyleSheet(
            """
            QListWidget {
                background-color: #0B0F19;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 10px;
            }
            QListWidget::item {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                margin: 4px;
                padding: 4px;
                color: #F8FAFC;
            }
            QListWidget::item:hover {
                background-color: rgba(30, 41, 59, 0.8);
                border-color: rgba(56, 189, 248, 0.3);
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E3A8A, stop:1 #1E293B);
                border: 1px solid #38BDF8;
                color: #FFFFFF;
            }
            """
        )
        self._configure_list_view_mode()
        main_layout.addWidget(self.list_widget, stretch=1)

        # 4. Empty State Container (Overlay widget shown when list is empty)
        self.empty_state_frame = QFrame(self.list_widget)
        self.empty_state_frame.setStyleSheet("background: transparent; border: none;")
        empty_layout = QVBoxLayout(self.empty_state_frame)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(10)

        empty_icon = QLabel(self.empty_state_frame)
        empty_icon.setPixmap(get_icon("star", "#475569", 56).pixmap(56, 56))
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon)

        empty_title = QLabel("Henüz Favori Ekran Görüntüsü Yok", self.empty_state_frame)
        empty_title.setStyleSheet("color: #E2E8F0; font-size: 16px; font-weight: 700;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)

        empty_desc = QLabel(
            "Ekran görüntüsü alırken veya önizlemede yıldız (★) butonuna basarak\n"
            "sık kullandığınız görselleri buraya ekleyebilirsiniz.",
            self.empty_state_frame,
        )
        empty_desc.setStyleSheet("color: #94A3B8; font-size: 13px; line-height: 1.4;")
        empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_desc)

        empty_btn = QPushButton("📁 Ekran Görüntüleri Klasörünü Aç", self.empty_state_frame)
        empty_btn.setStyleSheet(
            "QPushButton { background-color: #2563EB; color: #FFFFFF; font-weight: 600; font-size: 13px; "
            "border-radius: 8px; padding: 8px 18px; margin-top: 8px; } "
            "QPushButton:hover { background-color: #1D4ED8; }"
        )
        empty_btn.clicked.connect(self._on_open_screenshots_folder)
        empty_layout.addWidget(empty_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # 5. Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self.lbl_selection_info = QLabel("", self)
        self.lbl_selection_info.setStyleSheet("color: #94A3B8; font-size: 12px;")
        bottom_bar.addWidget(self.lbl_selection_info)

        bottom_bar.addStretch()

        btn_copy_image = QPushButton("Görseli Kopyala", self)
        btn_copy_image.setIcon(get_icon("copy", "#F1F5F9", 16))
        btn_copy_image.clicked.connect(self._on_copy_selected_image)
        bottom_bar.addWidget(btn_copy_image)

        btn_open = QPushButton("Aç", self)
        btn_open.setIcon(get_icon("external_link", "#F1F5F9", 16))
        btn_open.clicked.connect(self._on_open_selected)
        bottom_bar.addWidget(btn_open)

        btn_remove_fav = QPushButton("Favorilerden Çıkar", self)
        btn_remove_fav.setIcon(get_icon("trash", "#EF4444", 16))
        btn_remove_fav.setStyleSheet(
            "QPushButton { background-color: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.35); "
            "border-radius: 7px; color: #FCA5A5; font-size: 12.5px; font-weight: 600; padding: 7px 14px; } "
            "QPushButton:hover { background-color: rgba(239, 68, 68, 0.3); border-color: #EF4444; color: #FFFFFF; }"
        )
        btn_remove_fav.clicked.connect(self._on_remove_selected_favorites)
        bottom_bar.addWidget(btn_remove_fav)

        main_layout.addLayout(bottom_bar)

    def _view_btn_qss(self) -> str:
        return (
            "QToolButton { background-color: #0F172A; border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 6px; padding: 4px; } "
            "QToolButton:checked { background-color: #2563EB; border-color: #60A5FA; } "
            "QToolButton:hover { background-color: rgba(255, 255, 255, 0.1); }"
        )

    def _setup_shortcuts(self) -> None:
        # Ctrl+A to select all items
        shortcut_select_all = QShortcut(QKeySequence.StandardKey.SelectAll, self)
        shortcut_select_all.activated.connect(self.list_widget.selectAll)

        # Delete key to remove from favorites
        shortcut_delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        shortcut_delete.activated.connect(self._on_remove_selected_favorites)

    def _connect_signals(self) -> None:
        FavoritesManager.get_signal_bus().favorites_changed.connect(self._load_favorites)
        self.list_widget.itemSelectionChanged.connect(self._update_selection_info)

    def _load_favorites(self) -> None:
        """Loads and updates favorites list from storage."""
        self._all_items = FavoritesManager.get_items()
        self._apply_filter_and_sort()

    def _apply_filter_and_sort(self) -> None:
        """Filters and sorts favorite items according to search text and sort combo."""
        query = self.search_edit.text().strip().lower()
        items = list(self._all_items)

        # Filter
        if query:
            items = [
                it for it in items
                if query in it.filename.lower() or query in it.file_path.lower() or query in it.note.lower() or any(query in t.lower() for t in it.tags)
            ]

        # Sort
        sort_mode = self.sort_combo.currentData() or "newest"
        if sort_mode == "newest":
            items.sort(key=lambda x: x.favorited_at, reverse=True)
        elif sort_mode == "oldest":
            items.sort(key=lambda x: x.favorited_at)
        elif sort_mode == "name_asc":
            items.sort(key=lambda x: x.filename.lower())
        elif sort_mode == "name_desc":
            items.sort(key=lambda x: x.filename.lower(), reverse=True)
        elif sort_mode == "size_desc":
            items.sort(key=lambda x: x.file_size, reverse=True)
        elif sort_mode == "size_asc":
            items.sort(key=lambda x: x.file_size)

        self._filtered_items = items
        self._populate_list()

    def _configure_list_view_mode(self) -> None:
        """Configures QListWidget for Grid or List presentation."""
        if self._is_grid_view:
            self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
            self.list_widget.setIconSize(QSize(160, 110))
            self.list_widget.setGridSize(QSize(184, 160))
            self.list_widget.setSpacing(8)
            self.list_widget.setMovement(QListWidget.Movement.Static)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.list_widget.setWrapping(True)
        else:
            self.list_widget.setViewMode(QListWidget.ViewMode.ListMode)
            self.list_widget.setGridSize(QSize())
            self.list_widget.setSpacing(4)
            self.list_widget.setMovement(QListWidget.Movement.Static)
            self.list_widget.setResizeMode(QListWidget.ResizeMode.Fixed)
            self.list_widget.setWrapping(False)

    def _set_view_mode(self, is_grid: bool) -> None:
        self._is_grid_view = is_grid
        self.btn_grid_mode.setChecked(is_grid)
        self.btn_list_mode.setChecked(not is_grid)
        self._configure_list_view_mode()
        self._populate_list()

    def _populate_list(self) -> None:
        """Renders filtered items onto the list widget."""
        self.list_widget.clear()
        total_count = len(self._all_items)
        filtered_count = len(self._filtered_items)

        self.count_badge.setText(str(total_count))
        self.empty_state_frame.setVisible(filtered_count == 0)

        for item in self._filtered_items:
            list_item = QListWidgetItem()
            list_item.setData(Qt.ItemDataRole.UserRole, item)

            if self._is_grid_view:
                # Grid View Item with Thumbnail
                thumb = FavoritesManager.get_thumbnail(item.file_path, QSize(160, 110))
                if thumb and not thumb.isNull():
                    list_item.setIcon(QIcon(thumb))
                else:
                    fallback_pix = get_icon("camera" if item.exists else "info", "#64748B" if item.exists else "#EF4444", 64).pixmap(64, 64)
                    list_item.setIcon(QIcon(fallback_pix))

                display_title = item.filename
                if not item.exists:
                    display_title = f"⚠️ {item.filename}"
                list_item.setText(display_title)
                list_item.setToolTip(f"Dosya: {item.file_path}\nBoyut: {item.formatted_size}\nÇözünürlük: {item.formatted_dimensions}")
                list_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
                self.list_widget.addItem(list_item)
            else:
                # List View Item with Custom Widget
                list_item.setSizeHint(QSize(self.list_widget.width() - 30, 68))
                self.list_widget.addItem(list_item)
                widget = FavoriteItemWidget(item)
                widget.remove_requested.connect(self._remove_single_favorite)
                self.list_widget.setItemWidget(list_item, widget)

        self._update_selection_info()

    def _update_selection_info(self) -> None:
        selected_count = len(self.list_widget.selectedItems())
        total = len(self._filtered_items)
        if selected_count > 0:
            self.lbl_selection_info.setText(f"{selected_count} / {total} öğe seçildi")
        else:
            self.lbl_selection_info.setText(f"Toplam {total} favori öğe")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.empty_state_frame.setGeometry(self.list_widget.rect())

    def _get_selected_items(self) -> List[FavoriteItem]:
        items: List[FavoriteItem] = []
        for list_item in self.list_widget.selectedItems():
            it = list_item.data(Qt.ItemDataRole.UserRole)
            if isinstance(it, FavoriteItem):
                items.append(it)
        return items

    # --- Actions & Context Menu ---

    def _show_context_menu(self, pos: QPoint) -> None:
        selected_items = self._get_selected_items()
        if not selected_items:
            item_under_cursor = self.list_widget.itemAt(pos)
            if item_under_cursor:
                it = item_under_cursor.data(Qt.ItemDataRole.UserRole)
                if it:
                    selected_items = [it]

        if not selected_items:
            return

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #0F172A; color: #F8FAFC; border: 1px solid rgba(255, 255, 255, 0.15); "
            "border-radius: 10px; padding: 6px; font-size: 13px; } "
            "QMenu::item { padding: 8px 24px 8px 12px; margin: 2px 4px; border-radius: 6px; } "
            "QMenu::item:selected { background-color: #2563EB; color: #FFFFFF; font-weight: 600; } "
            "QMenu::separator { height: 1px; background-color: rgba(255, 255, 255, 0.12); margin: 4px 6px; }"
        )

        first_item = selected_items[0]

        # 1. Open File
        act_open = menu.addAction(get_icon("external_link", "#38BDF8", 16), "Görseli Aç (Varsayılan Görüntüleyici)")
        act_open.triggered.connect(lambda: self._open_file(first_item.file_path))

        # 2. Open in Folder
        act_folder = menu.addAction(get_icon("folder", "#A5B4FC", 16), "Klasörde Göster (Explorer)")
        act_folder.triggered.connect(lambda: self._open_folder_and_select(first_item.file_path))

        menu.addSeparator()

        # 3. Copy Image
        act_copy_img = menu.addAction(get_icon("copy", "#34D399", 16), "Görseli Panoya Kopyala")
        act_copy_img.triggered.connect(lambda: self._copy_image_to_clipboard(first_item.file_path))

        # 4. Copy Path
        act_copy_path = menu.addAction(get_icon("file_text", "#CBD5E1", 16), "Dosya Yolunu Kopyala")
        act_copy_path.triggered.connect(lambda: self._copy_path_to_clipboard(first_item.file_path))

        menu.addSeparator()

        # 5. Remove from Favorites (Safe)
        remove_label = f"Seçili Favorilerden Çıkar ({len(selected_items)})" if len(selected_items) > 1 else "Favorilerden Çıkar"
        act_unfav = menu.addAction(get_icon("star", "#FBBF24", 16), remove_label)
        act_unfav.triggered.connect(lambda: self._remove_multiple_favorites(selected_items))

        # 6. Delete File from Disk (Destructive, with confirmation)
        act_delete = menu.addAction(get_icon("trash", "#EF4444", 16), "Dosyayı Diskten Sil...")
        act_delete.triggered.connect(lambda: self._delete_files_from_disk(selected_items))

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _on_item_double_clicked(self, list_item: QListWidgetItem) -> None:
        item = list_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(item, FavoriteItem):
            self._open_file(item.file_path)

    def _open_file(self, file_path: str) -> None:
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Dosya Bulunamadı", f"Görsel dosyası diskte bulunamadı:\n{file_path}")
            return

        try:
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", file_path])
            else:
                subprocess.Popen(["xdg-open", file_path])
        except Exception as exc:
            logger.error("Failed to open file %s: %s", file_path, exc)

    def _open_folder_and_select(self, file_path: str) -> None:
        if not file_path:
            return

        if not os.path.exists(file_path):
            # Try opening parent dir
            parent = str(Path(file_path).parent)
            if os.path.exists(parent):
                os.startfile(parent)
            return

        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", os.path.normpath(file_path)])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", file_path])
            else:
                subprocess.run(["xdg-open", str(Path(file_path).parent)])
        except Exception as exc:
            logger.error("Failed to open folder for %s: %s", file_path, exc)

    def _copy_image_to_clipboard(self, file_path: str) -> None:
        if not file_path or not os.path.exists(file_path):
            return
        try:
            img = QImage(file_path)
            if not img.isNull():
                ClipboardService.copy_image(img)
                NotificationManager.show_toast("Panoya Kopyalandı", "Favori görsel panoya kopyalandı.", icon_name="check")
        except Exception as exc:
            logger.error("Failed to copy image to clipboard: %s", exc)

    def _copy_path_to_clipboard(self, file_path: str) -> None:
        if file_path:
            ClipboardService.copy_text(file_path)
            NotificationManager.show_toast("Kopyalandı", "Dosya yolu panoya kopyalandı.", icon_name="check")

    def _remove_single_favorite(self, file_path: str) -> None:
        FavoritesManager.remove_favorite(file_path)
        NotificationManager.show_toast("Favorilerden Çıkarıldı", Path(file_path).name, icon_name="star")

    def _remove_multiple_favorites(self, items: List[FavoriteItem]) -> None:
        for it in items:
            FavoritesManager.remove_favorite(it.file_path)
        NotificationManager.show_toast("Favorilerden Çıkarıldı", f"{len(items)} öğe favorilerden kaldırıldı.", icon_name="star")

    def _delete_files_from_disk(self, items: List[FavoriteItem]) -> None:
        """Prompts the user with a clear confirmation dialog before permanently deleting file(s)."""
        count = len(items)
        reply = QMessageBox.question(
            self,
            "Dosyaları Kalıcı Olarak Sil",
            f"Seçilen {count} adet görsel dosyasını diskten KALICI olarak silmek istediğinizden emin misiniz?\n\nBu işlem geri alınamaz.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            for it in items:
                # Remove from favorites first
                FavoritesManager.remove_favorite(it.file_path)
                if it.file_path and os.path.exists(it.file_path):
                    try:
                        os.remove(it.file_path)
                        deleted_count += 1
                    except Exception as exc:
                        logger.error("Failed to delete file %s: %s", it.file_path, exc)

            NotificationManager.show_toast("Dosyalar Silindi", f"{deleted_count} görsel diskten silindi.", icon_name="trash")

    def _on_clean_missing_files(self) -> None:
        cleaned = FavoritesManager.clean_missing_files()
        if cleaned > 0:
            NotificationManager.show_toast("Temizlendi", f"{cleaned} adet eksik favori kaydı temizlendi.", icon_name="check")
        else:
            NotificationManager.show_toast("Eksik Dosya Yok", "Tüm favori dosyaları diskte mevcut.", icon_name="check")

    def _on_open_screenshots_folder(self) -> None:
        default_dir = get_default_screenshots_dir()
        if sys.platform == "win32":
            os.startfile(str(default_dir))
        else:
            subprocess.Popen(["xdg-open", str(default_dir)])

    def _on_open_selected(self) -> None:
        selected = self._get_selected_items()
        if selected:
            self._open_file(selected[0].file_path)

    def _on_copy_selected_image(self) -> None:
        selected = self._get_selected_items()
        if selected:
            self._copy_image_to_clipboard(selected[0].file_path)

    def _on_remove_selected_favorites(self) -> None:
        selected = self._get_selected_items()
        if selected:
            self._remove_multiple_favorites(selected)

