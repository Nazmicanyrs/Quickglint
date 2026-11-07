"""System Tray Icon and context menu manager with advanced capture options."""

from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.constants import APP_NAME, APP_VERSION
from app.utils.helpers import get_app_icon, open_folder_in_file_manager
from app.utils.i18n import tr
from app.utils.logger import logger


class TrayIconManager(QObject):
    """Manages the system tray icon, context menu, and tray actions."""

    take_screenshot_requested = Signal()
    smart_window_requested = Signal()
    panorama_capture_requested = Signal()
    new_session_requested = Signal()
    open_session_requested = Signal()
    scrolling_screenshot_requested = Signal()
    record_gif_requested = Signal()
    open_vault_requested = Signal()
    open_pdf_editor_requested = Signal()
    open_metacleaner_requested = Signal()
    open_share_history_requested = Signal()
    open_measurement_studio_requested = Signal()
    open_favorites_requested = Signal()
    open_settings_requested = Signal()
    exit_requested = Signal()

    def __init__(
        self,
        default_save_dir_func: Callable[[], str],
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.default_save_dir_func = default_save_dir_func

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(get_app_icon())
        self.tray_icon.setToolTip(f"{APP_NAME} v{APP_VERSION}")

        self._create_menu()
        self.tray_icon.activated.connect(self._on_tray_activated)

    def _create_menu(self) -> None:
        """Create styled context menu with dark high-contrast readable items and SVG icons."""
        self.menu = QMenu()
        self.menu.setStyleSheet(
            "QMenu { background-color: #0F172A; color: #F8FAFC; border: 1px solid rgba(255, 255, 255, 0.15); "
            "border-radius: 10px; padding: 6px; font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; "
            "font-weight: 500; font-size: 13px; } "
            "QMenu::item { background-color: transparent; color: #F1F5F9; padding: 7px 28px 7px 12px; margin: 2px 4px; border-radius: 6px; } "
            "QMenu::item:selected { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1D4ED8); color: #FFFFFF; font-weight: 600; } "
            "QMenu::separator { height: 1px; background-color: rgba(255, 255, 255, 0.12); margin: 5px 8px; }"
        )

        # 1. Take Screenshot
        self.action_capture = QAction(get_icon("camera", "#38BDF8", 16), tr("tray_take_screenshot"), self)
        self.action_capture.triggered.connect(self.take_screenshot_requested.emit)
        self.menu.addAction(self.action_capture)

        # 1b. Smart Window Capture
        self.action_smart_window = QAction(get_icon("globe", "#38BDF8", 16), tr("tray_smart_window"), self)
        self.action_smart_window.triggered.connect(self.smart_window_requested.emit)
        self.menu.addAction(self.action_smart_window)

        # 1c. Panorama Capture (Multi-Monitor Stitcher)
        self.action_panorama = QAction(get_icon("panorama", "#34D399", 16), tr("tray_panorama"), self)
        self.action_panorama.triggered.connect(self.panorama_capture_requested.emit)
        self.menu.addAction(self.action_panorama)

        self.action_new_session = QAction(
            get_icon("camera", "#34D399", 16), "Yeni Seri Ekran Görüntüsü", self
        )
        self.action_new_session.triggered.connect(self.new_session_requested.emit)
        self.menu.addAction(self.action_new_session)

        self.action_open_session = QAction(
            get_icon("folder", "#A5B4FC", 16), "Aktif Seri Ekran Görüntüsünü Aç", self
        )
        self.action_open_session.triggered.connect(self.open_session_requested.emit)
        self.menu.addAction(self.action_open_session)

        # 2. Scrolling Screenshot
        self.action_scrolling = QAction(get_icon("scroll", "#A5B4FC", 16), "Kaydırmalı Ekran Görüntüsü (Scrolling)", self)
        self.action_scrolling.triggered.connect(self.scrolling_screenshot_requested.emit)
        self.menu.addAction(self.action_scrolling)

        # 3. Record GIF
        self.action_gif = QAction(get_icon("gif", "#F472B6", 16), "Ekran GIF'i Kaydet (Record GIF)", self)
        self.action_gif.triggered.connect(self.record_gif_requested.emit)
        self.menu.addAction(self.action_gif)

        self.menu.addSeparator()

        # 4. Secure Vault
        self.action_vault = QAction(get_icon("vault", "#FBBF24", 16), "Güvenli Kasa (Secure Vault)", self)
        self.action_vault.triggered.connect(self.open_vault_requested.emit)
        self.menu.addAction(self.action_vault)

        # 4b. PDF Editor
        self.action_pdf_editor = QAction(get_icon("pdf", "#38BDF8", 16), "PDF Düzenleyici (PDF Document Builder)", self)
        self.action_pdf_editor.triggered.connect(self.open_pdf_editor_requested.emit)
        self.menu.addAction(self.action_pdf_editor)

        # 5. Metadata Cleaner
        self.action_metacleaner = QAction(get_icon("privacy", "#38BDF8", 16), "Metadata & Gizlilik Temizleyici", self)
        self.action_metacleaner.triggered.connect(self.open_metacleaner_requested.emit)
        self.menu.addAction(self.action_metacleaner)

        # 6. Share History
        self.action_share_history = QAction(get_icon("cloud_upload", "#38BDF8", 16), "Paylaşım Geçmişi (Upload History)", self)
        self.action_share_history.triggered.connect(self.open_share_history_requested.emit)
        self.menu.addAction(self.action_share_history)

        # 7. Measurement Studio
        self.action_measurement = QAction(get_icon("line", "#38BDF8", 16), "Ölçüm Stüdyosu (Measurement Studio)", self)
        self.action_measurement.triggered.connect(self.open_measurement_studio_requested.emit)
        self.menu.addAction(self.action_measurement)

        # 8. Favorites
        self.action_favorites = QAction(get_icon("star_filled", "#FBBF24", 16), tr("tray_favorites"), self)
        self.action_favorites.triggered.connect(self.open_favorites_requested.emit)
        self.menu.addAction(self.action_favorites)

        # 9. Open screenshots folder
        self.action_open_folder = QAction(get_icon("folder", "#38BDF8", 16), tr("tray_open_folder"), self)
        self.action_open_folder.triggered.connect(self._on_open_folder)
        self.menu.addAction(self.action_open_folder)

        # 10. Settings
        self.action_settings = QAction(get_icon("settings", "#CBD5E1", 16), tr("tray_settings"), self)
        self.action_settings.triggered.connect(self.open_settings_requested.emit)
        self.menu.addAction(self.action_settings)

        self.menu.addSeparator()

        # 7. Exit
        self.action_exit = QAction(get_icon("close", "#FDA4AF", 16), tr("tray_exit"), self)
        self.action_exit.triggered.connect(self.exit_requested.emit)
        self.menu.addAction(self.action_exit)

        self.tray_icon.setContextMenu(self.menu)

    def retranslate_menu(self) -> None:
        """Update context menu texts when application language changes."""
        self.action_capture.setText(tr("tray_take_screenshot"))
        self.action_smart_window.setText(tr("tray_smart_window"))
        self.action_panorama.setText(tr("tray_panorama"))
        self.action_open_folder.setText(tr("tray_open_folder"))
        self.action_settings.setText(tr("tray_settings"))
        self.action_exit.setText(tr("tray_exit"))

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # Single click
            self.take_screenshot_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_settings_requested.emit()

    def _on_open_folder(self) -> None:
        save_dir = self.default_save_dir_func()
        if save_dir:
            open_folder_in_file_manager(save_dir)

    def show(self) -> None:
        self.tray_icon.show()

    def hide(self) -> None:
        self.tray_icon.hide()

