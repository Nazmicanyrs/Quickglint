"""Central application coordinator connecting UI, capture, privacy, scrolling, GIF, and services."""

import sys
import time
from pathlib import Path
from typing import Any, Optional
from PySide6.QtCore import QObject, QRect, QTimer, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from app.capture.engine import CaptureEngine
from app.capture.screen_capture import ScreenCaptureManager
from app.capture.selection_overlay import SelectionOverlay
from app.editor.history import HistoryManager
from app.editor.tools import ToolManager
from app.recorder.frame import RecordedFrame
from app.recorder.preview_dialog import GifPreviewDialog
from app.recorder.recorder import ScreenGifRecorder
from app.scrolling.controller import ScrollingCaptureController
from app.session.session_manager import SessionManager
from app.services.autostart_service import AutostartService
from app.services.hotkey_service import HotkeyService
from app.ui.notifications import NotificationManager
from app.ui.settings_dialog import SettingsDialog
from app.ui.styles import DARK_THEME_QSS, get_icon, get_theme_qss
from app.ui.tray import TrayIconManager
from app.utils.constants import APP_NAME, APP_VERSION
from app.utils.helpers import get_app_icon
from app.utils.i18n import get_language, set_language, tr
from app.utils.logger import logger
from config.config_manager import ConfigManager


class QuickglintApp(QObject):
    """Main application lifecycle controller for Quickglint."""

    def __init__(self, argv: list[str]) -> None:
        super().__init__()
        self.qt_app = QApplication.instance() or QApplication(argv)
        self.qt_app.setApplicationName(APP_NAME)
        self.qt_app.setApplicationVersion(APP_VERSION)
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.setStyleSheet(DARK_THEME_QSS)

        self.qt_app.setWindowIcon(get_app_icon())

        # Config
        self.config_manager = ConfigManager()

        # Initialize language from config
        initial_lang = self.config_manager.get("general", "language", "tr")
        set_language(initial_lang)

        # Tool & History state
        self.tool_manager = ToolManager(
            initial_color=self.config_manager.get("editor", "default_color", "#FF0000"),
            initial_stroke=self.config_manager.get("editor", "default_brush_size", 3),
            initial_font_size=self.config_manager.get("editor", "default_font_size", 18),
            blur_radius=self.config_manager.get("editor", "blur_radius", 15),
            pixel_size=self.config_manager.get("editor", "pixel_size", 12),
            blur_tint=self.config_manager.get("editor", "blur_tint", ""),
            blur_tint_opacity=self.config_manager.get("editor", "blur_tint_opacity", 0.2),
        )
        self.history_manager = HistoryManager()

        # Services & UI
        self.hotkey_service = HotkeyService(
            hotkey_str=self.config_manager.get("hotkeys", "capture_hotkey", "PrintScreen")
        )
        self.tray_manager = TrayIconManager(
            default_save_dir_func=lambda: self.config_manager.get("general", "default_save_dir", "")
        )

        self._active_overlay: Optional[SelectionOverlay] = None
        self._settings_dialog: Optional[SettingsDialog] = None
        self.session_manager = SessionManager(self)
        self._session_window = None
        self._pdf_editor = None
        self._restore_session_window_after_capture = False

        self._connect_signals()

    def _connect_signals(self) -> None:
        # Hotkey triggers (Thread-safe queued connection to guarantee execution on main GUI thread)
        self.hotkey_service.triggered.connect(self._on_hotkey_triggered, Qt.ConnectionType.QueuedConnection)
        self.hotkey_service.error_occurred.connect(self._on_hotkey_error, Qt.ConnectionType.QueuedConnection)

        # Tray triggers
        self.tray_manager.take_screenshot_requested.connect(self.trigger_capture)
        self.tray_manager.smart_window_requested.connect(self.trigger_smart_window_capture)
        self.tray_manager.panorama_capture_requested.connect(self.open_panorama_capture)
        self.tray_manager.new_session_requested.connect(self.start_screenshot_session)
        self.tray_manager.open_session_requested.connect(self.open_screenshot_session)
        self.tray_manager.scrolling_screenshot_requested.connect(self.trigger_scrolling_capture)
        self.tray_manager.record_gif_requested.connect(self.trigger_gif_recording)
        self.tray_manager.open_vault_requested.connect(self.open_secure_vault)
        self.tray_manager.open_pdf_editor_requested.connect(self.open_pdf_editor)
        self.tray_manager.open_metacleaner_requested.connect(self.open_metadata_cleaner)
        self.tray_manager.open_share_history_requested.connect(self.open_share_history)
        self.tray_manager.open_measurement_studio_requested.connect(self.open_measurement_studio)
        self.tray_manager.open_favorites_requested.connect(self.open_favorites)
        self.tray_manager.open_settings_requested.connect(self.open_settings)
        self.tray_manager.exit_requested.connect(self.quit)

    def _on_hotkey_triggered(self) -> None:
        """Handle global hotkey trigger with a slight delay to allow OS modifier keys to release."""
        QTimer.singleShot(60, self.trigger_capture)

    def _on_hotkey_error(self, err_msg: str) -> None:
        logger.warning("Hotkey notification: %s", err_msg)
        if self.config_manager.get("general", "show_notifications", True):
            NotificationManager.show_toast(tr("toast_hotkey_warning_title"), err_msg, icon_name="info", duration_ms=4000)

    def trigger_smart_window_capture(self) -> None:
        """Start Smart Window Capture mode to detect and capture browser windows automatically."""
        self.trigger_capture(smart_window_mode=True)

    def trigger_capture(
        self,
        session_capture_mode: Optional[bool] = None,
        smart_window_mode: bool = False,
    ) -> None:
        """Start standard or smart window screenshot capture workflow across all connected displays."""
        if self._active_overlay is not None and self._active_overlay.isVisible():
            self._active_overlay.raise_()
            self._active_overlay.activateWindow()
            return

        use_session_capture = (
            self.session_manager.active_session is not None
            if session_capture_mode is None
            else session_capture_mode
        )
        logger.info("Triggering screen capture (smart_window=%s)...", smart_window_mode)
        self._restore_session_window_after_capture = bool(
            use_session_capture
            and self._session_window is not None
            and self._session_window.isVisible()
        )
        if self._restore_session_window_after_capture:
            # Do not capture the gallery itself when the user starts a capture
            # from the tray while reviewing an active session.
            self._session_window.hide()
        include_cursor = self.config_manager.get("image", "include_cursor", False)
        from app.services.naming_service import capture_foreground_window_info

        fg_title, fg_app = capture_foreground_window_info()
        try:
            full_pixmap, virtual_geometry = ScreenCaptureManager.capture_all_screens(include_cursor)
        except Exception as exc:
            logger.error("Screen capture failed: %s", exc, exc_info=True)
            self._active_overlay = None
            self._restore_session_window_if_needed()
            return

        self.history_manager.clear()

        overlay = SelectionOverlay(
            full_desktop_pixmap=full_pixmap,
            virtual_geometry=virtual_geometry,
            tool_manager=self.tool_manager,
            history_manager=self.history_manager,
            config_manager=self.config_manager,
            default_save_dir=self.config_manager.get("general", "default_save_dir", ""),
            default_format=self.config_manager.get("image", "default_format", "PNG"),
            jpeg_quality=self.config_manager.get("image", "jpeg_quality", 95),
            session_capture_mode=use_session_capture,
            smart_window_mode=smart_window_mode,
            initial_window_title=fg_title,
            initial_app_name=fg_app,
        )

        overlay.capture_copied.connect(self._on_capture_copied)
        overlay.capture_saved.connect(self._on_capture_saved)
        overlay.capture_cancelled.connect(self._on_capture_cancelled)
        overlay.stitched_capture_ready.connect(self._on_stitched_ready)
        overlay.session_image_captured.connect(self._on_session_image_captured)
        overlay.new_session_from_image.connect(self._on_new_session_from_image)
        overlay.open_session_requested.connect(self.open_screenshot_session)

        self._active_overlay = overlay
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()

    def start_screenshot_session(self) -> None:
        """Start a transient session and immediately capture its first image."""
        self.session_manager.create_session()
        self.trigger_capture()

    def open_screenshot_session(self) -> None:
        """Show the gallery for the active session without interrupting capture."""
        session = self.session_manager.active_session
        if session is None:
            NotificationManager.show_toast(
                "Screenshot Session",
                "Açık bir session yok. Önce Yeni Screenshot Session başlatın.",
                "info",
                3000,
            )
            return
        if self._session_window is not None and self._session_window.isVisible():
            self._session_window.raise_()
            self._session_window.activateWindow()
            return

        from app.ui.session_window import ScreenshotSessionWindow

        self._session_window = ScreenshotSessionWindow(session, self.session_manager)
        self._session_window.open_editor_requested.connect(self._on_stitched_ready)
        self._session_window.show()
        self._session_window.raise_()
        self._session_window.activateWindow()

    def _on_new_session_from_image(self, image: QImage) -> None:
        """Create a new session seeded with this captured image and open the gallery."""
        session = self.session_manager.create_session()
        session.add_image(image)
        self.open_screenshot_session()

    def _on_session_image_captured(self, image: QImage) -> None:
        """Receive an in-memory completed overlay capture only for an active session."""
        if self.session_manager.add_screenshot(image):
            session = self.session_manager.active_session
            count = len(session.items) if session else 0
            NotificationManager.show_toast(
                "Screenshot Session",
                f"Screenshot #{count} session'a eklendi.",
                "camera",
                1800,
            )
        self._active_overlay = None
        self._restore_session_window_if_needed()

    def _restore_session_window_if_needed(self) -> None:
        if self._restore_session_window_after_capture and self._session_window is not None:
            self._session_window.show()
            self._session_window.raise_()
            self._session_window.activateWindow()
        self._restore_session_window_after_capture = False

    def trigger_scrolling_capture(self) -> None:
        """Trigger scrolling screenshot directly."""
        # The overlay offers scrolling capture (Ctrl+Shift+L) after region selection.
        self.trigger_capture(session_capture_mode=False)

    def trigger_gif_recording(self) -> None:
        """Trigger GIF recording directly (available in the overlay via Ctrl+Shift+G)."""
        self.trigger_capture(session_capture_mode=False)

    def _on_stitched_ready(self, stitched_image: QImage) -> None:
        """Open the long stitched image inside a dedicated scrollable editor window."""
        from app.scrolling.editor_dialog import ScrollingEditorDialog

        logger.info("Stitched screenshot ready (%dx%d px), opening editor window...", stitched_image.width(), stitched_image.height())
        editor = ScrollingEditorDialog(
            stitched_image=stitched_image,
            tool_manager=self.tool_manager,
            history_manager=self.history_manager,
            default_save_dir=self.config_manager.get("general", "default_save_dir", ""),
            default_format=self.config_manager.get("image", "default_format", "PNG"),
            jpeg_quality=self.config_manager.get("image", "jpeg_quality", 95),
            config_manager=self.config_manager,
        )
        editor.exec()

    def _on_capture_copied(self) -> None:
        logger.info("Screenshot successfully copied to clipboard.")
        if self.config_manager.get("general", "show_notifications", True):
            NotificationManager.show_toast(tr("toast_copied_title"), tr("toast_copied_msg"), "copy", 2500)
        self._active_overlay = None

    def _on_capture_saved(self, filepath: str) -> None:
        logger.info("Screenshot successfully saved to: %s", filepath)
        if self.config_manager.get("general", "show_notifications", True):
            p = Path(filepath)
            NotificationManager.show_toast(tr("toast_saved_title"), tr("toast_saved_msg", filename=p.name), "save", 3000)
        self._active_overlay = None

    def _on_capture_cancelled(self) -> None:
        logger.info("Capture cancelled by user.")
        self._active_overlay = None
        self._restore_session_window_if_needed()

    def open_secure_vault(self) -> None:
        """Open Secure Vault management window."""
        from app.ui.vault_window import SecureVaultWindow
        vault_win = SecureVaultWindow(config_manager=self.config_manager)
        vault_win.open_in_editor.connect(self._on_stitched_ready)
        vault_win.exec()

    def open_pdf_editor(self, doc: Optional[Any] = None, image: Optional[QImage] = None) -> None:
        """Open Professional PDF Document Builder & Workspace."""
        from app.pdf.document import PDFDocument
        from app.pdf.ui.editor_window import PDFEditorWindow

        if doc is None:
            if image is not None and not image.isNull():
                doc = PDFDocument.create_from_image(image, title=f"Screenshot_{time.strftime('%Y%m%d_%H%M%S')}")
            else:
                doc = PDFDocument.create_empty("New Document")

        if self._pdf_editor is not None:
            try:
                self._pdf_editor.load_document(doc)
                self._pdf_editor.show()
                self._pdf_editor.raise_()
                self._pdf_editor.activateWindow()
                return
            except RuntimeError:
                # Underlying Qt window was destroyed; create a fresh one.
                self._pdf_editor = None

        self._pdf_editor = PDFEditorWindow(document=doc, parent=None)
        self._pdf_editor.show()
        self._pdf_editor.raise_()
        self._pdf_editor.activateWindow()

    def open_metadata_cleaner(self) -> None:
        """Open Image Metadata Cleaner dialog with file selection."""
        from PySide6.QtWidgets import QFileDialog
        from app.metacleaner.dialog import MetadataCleanerDialog
        from app.metacleaner.batch_dialog import BatchMetadataCleanerDialog

        paths, _ = QFileDialog.getOpenFileNames(
            None,
            "Metadata Temizlenecek Görselleri Seçin",
            self.config_manager.get("general", "default_save_dir", ""),
            "Images (*.png *.jpg *.jpeg *.webp *.tiff *.bmp *.gif);;All Files (*.*)",
        )
        if not paths:
            return

        if len(paths) == 1:
            dlg = MetadataCleanerDialog(image_source=paths[0])
            dlg.exec()
        else:
            batch_dlg = BatchMetadataCleanerDialog(file_paths=[Path(p) for p in paths])
            batch_dlg.exec()

    def open_share_history(self) -> None:
        """Open Image Share History management dialog."""
        from app.ui.share_history_dialog import ShareHistoryDialog
        dlg = ShareHistoryDialog()
        dlg.exec()

    def open_measurement_studio(self, image: Optional[QImage] = None) -> None:
        """Open Professional Measurement Studio Window with current screen or passed image."""
        from app.measurement.studio_dialog import MeasurementStudioWindow

        if image is None:
            include_cursor = self.config_manager.get("image", "include_cursor", False)
            full_pixmap, _ = ScreenCaptureManager.capture_all_screens(include_cursor)
            image = full_pixmap.toImage()

        dlg = MeasurementStudioWindow(image=image)
        dlg.exec()

    def open_panorama_capture(self) -> None:
        """Open Multi-Monitor & Panorama Capture Studio."""
        from app.panorama.editor_dialog import PanoramaEditorDialog

        dlg = PanoramaEditorDialog(config_manager=self.config_manager)
        dlg.open_in_editor_requested.connect(self._on_stitched_ready)
        dlg.exec()

    def open_favorites(self) -> None:
        """Open Favorites gallery and management dialog."""
        from app.ui.favorites_dialog import FavoritesDialog
        dlg = FavoritesDialog()
        dlg.exec()

    def open_settings(self) -> None:
        """Open settings dialog."""
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        self._settings_dialog = SettingsDialog(self.config_manager)
        self._settings_dialog.settings_saved.connect(self._apply_updated_settings)
        self._settings_dialog.show()

    def _apply_updated_settings(self) -> None:
        """Apply newly updated configuration settings."""
        logger.info("Applying updated settings...")
        self.tray_manager.retranslate_menu()

        new_hotkey = self.config_manager.get("hotkeys", "capture_hotkey", "PrintScreen")
        if not self.hotkey_service.start(new_hotkey):
            logger.warning("New hotkey '%s' could not be registered.", new_hotkey)

        self.tool_manager.color = self.config_manager.get("editor", "default_color", "#FF0000")
        self.tool_manager.stroke_width = self.config_manager.get("editor", "default_brush_size", 3)
        self.tool_manager.font_size = self.config_manager.get("editor", "default_font_size", 18)
        self.tool_manager.blur_radius = self.config_manager.get("editor", "blur_radius", 15)
        self.tool_manager.pixel_size = self.config_manager.get("editor", "pixel_size", 12)
        self.tool_manager.blur_tint = self.config_manager.get("editor", "blur_tint", "")
        self.tool_manager.blur_tint_opacity = self.config_manager.get("editor", "blur_tint_opacity", 0.2)
        dark_mode = bool(self.config_manager.get("editor", "dark_mode", True))
        self.qt_app.setStyleSheet(get_theme_qss(dark_mode))

    def run(self) -> int:
        """Start application services, system tray, and main event loop."""
        logger.info("Starting Quickglint v%s (Language: %s)...", APP_VERSION, get_language())

        self.tray_manager.show()

        hotkey = self.config_manager.get("hotkeys", "capture_hotkey", "PrintScreen")
        self.hotkey_service.start(hotkey)

        if self.config_manager.get("general", "show_notifications", True):
            NotificationManager.show_toast(
                tr("toast_running_title"),
                tr("toast_running_msg", hotkey=hotkey),
                "camera",
                3000,
            )

        return self.qt_app.exec()

    def quit(self) -> None:
        """Clean shutdown."""
        logger.info("Shutting down Quickglint...")
        self.hotkey_service.stop()
        self.tray_manager.hide()
        self.qt_app.quit()


# Backward-compatible alias for existing tests or imports


