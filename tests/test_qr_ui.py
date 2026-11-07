"""Unit and integration tests for QR Notification Panel, Editor Overlays, and Settings."""

from unittest.mock import MagicMock, patch
from PIL import Image
import pytest
import qrcode
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import QApplication

from app.capture.selection_overlay import SelectionOverlay
from app.editor.history import HistoryManager
from app.editor.tools import ToolManager
from app.qr.qr_panel import QRItemWidget, QRNotificationPanel
from app.qr.qr_result import QRDataType, QRResult
from config.config_manager import ConfigManager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def config_manager(tmp_path):
    cfg_file = tmp_path / "test_settings.json"
    return ConfigManager(custom_path=cfg_file)


def generate_qr_pixmap(text: str) -> QPixmap:
    qr = qrcode.QRCode(version=1, box_size=6, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    pil_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    
    # Convert PIL to QPixmap
    from PySide6.QtGui import QImage
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.size[0], pil_img.size[1], QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


# Single QR Panel UI test
def test_single_qr_notification_panel(qapp):
    res = QRResult.create("https://example.com/single", QRect(10, 10, 80, 80), index=1)
    panel = QRNotificationPanel([res])
    assert len(panel.results) == 1

    # Check that open link button exists
    item = panel.findChild(QRItemWidget)
    assert item is not None
    assert hasattr(item, "open_btn")
    assert item.open_btn.isEnabled()

    # Test open link invocation with mock
    with patch.object(QDesktopServices, "openUrl") as mock_open:
        item.open_btn.click()
        mock_open.assert_called_once()
        assert mock_open.call_args[0][0].toString() == "https://example.com/single"


# Multi QR Panel UI test
def test_multiple_qr_notification_panel(qapp):
    res1 = QRResult.create("https://example.com/first", QRect(10, 10, 80, 80), index=1)
    res2 = QRResult.create("WIFI:T:WPA;S:OfficeNet;P:Secret;;", QRect(100, 10, 80, 80), index=2)
    res3 = QRResult.create("Plain text item", QRect(200, 10, 80, 80), index=3)

    panel = QRNotificationPanel([res1, res2, res3])
    items = panel.findChildren(QRItemWidget)
    assert len(items) == 3

    # Item 1 has open link, Item 2 and 3 do not
    assert hasattr(items[0], "open_btn")
    assert not hasattr(items[1], "open_btn")
    assert not hasattr(items[2], "open_btn")


# Copy button and visual feedback test
def test_qr_item_copy_feedback(qapp):
    res = QRResult.create("https://example.com/copy-test", QRect(10, 10, 80, 80))
    item = QRItemWidget(res)
    item.copy_btn.click()
    from app.services.clipboard_service import ClipboardService
    assert (QApplication.clipboard().text() or ClipboardService._last_copied_text) == "https://example.com/copy-test"
    assert "✓" in item.copy_btn.text()


# 23. QR panel disabled setting
def test_qr_panel_disabled_setting(qapp, config_manager):
    config_manager.set("qr", "enabled", True)
    config_manager.set("qr", "show_panel_automatically", False)

    tool_mgr = ToolManager()
    hist_mgr = HistoryManager()
    dummy_pixmap = QPixmap(800, 600)
    dummy_pixmap.fill(Qt.GlobalColor.white)

    overlay = SelectionOverlay(
        full_desktop_pixmap=dummy_pixmap,
        virtual_geometry=QRect(0, 0, 800, 600),
        tool_manager=tool_mgr,
        history_manager=hist_mgr,
        config_manager=config_manager,
        default_save_dir="",
    )

    fake_qr = [QRResult.create("https://example.com", QRect(20, 20, 50, 50))]
    overlay._on_qr_detected(fake_qr, force_show=False)

    # Panel should NOT be created or shown automatically
    assert overlay._qr_panel is None
    overlay.close()


# 24. QR auto-detection disabled setting
def test_qr_auto_detection_disabled_setting(qapp, config_manager):
    config_manager.set("qr", "enabled", False)

    tool_mgr = ToolManager()
    hist_mgr = HistoryManager()
    dummy_pixmap = QPixmap(800, 600)
    dummy_pixmap.fill(Qt.GlobalColor.white)

    overlay = SelectionOverlay(
        full_desktop_pixmap=dummy_pixmap,
        virtual_geometry=QRect(0, 0, 800, 600),
        tool_manager=tool_mgr,
        history_manager=hist_mgr,
        config_manager=config_manager,
        default_save_dir="",
    )

    with patch.object(overlay, "scan_qr_codes") as mock_scan:
        # Simulate mouse selection finish
        overlay._is_selecting = True
        overlay.selected_rect = QRect(10, 10, 200, 200)
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QPointF
        event = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(210, 210), QPointF(210, 210), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        overlay.mouseReleaseEvent(event)

        # scan_qr_codes should not be called automatically because qr.enabled is False
        mock_scan.assert_not_called()

    overlay.close()


# Drag and move QR panel test
def test_qr_panel_drag_and_move(qapp):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    res = QRResult.create("https://example.com/drag-test", QRect(10, 10, 80, 80))
    panel = QRNotificationPanel([res])
    panel.move(100, 100)

    # Simulate mouse press on header
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(50, 15),
        QPointF(150, 115),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.mousePressEvent(press_event)
    assert panel._is_dragging is True

    # Simulate mouse move to (250, 215)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(150, 115),
        QPointF(250, 215),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.mouseMoveEvent(move_event)
    assert panel.pos().x() == 200
    assert panel.pos().y() == 200

    # Simulate mouse release
    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(150, 115),
        QPointF(250, 215),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    panel.mouseReleaseEvent(release_event)
    assert panel._is_dragging is False
    panel.close()

