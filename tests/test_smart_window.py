"""Comprehensive unit and integration test suite for Smart Window Capture subsystem."""

import os
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from app.capture.selection_overlay import SelectionOverlay
from app.editor.history import HistoryManager
from app.editor.tools import ToolManager
from app.utils.i18n import set_language, tr
from app.window.detector import BrowserWindowDetector
from app.window.models import BrowserWindowInfo
from config.config_manager import ConfigManager


@pytest.fixture(autouse=True)
def reset_detector_cache():
    """Reset detector process cache between tests."""
    BrowserWindowDetector.clear_cache()
    yield
    BrowserWindowDetector.clear_cache()


# TEST 01: Verify all supported browser executables are recognized
def test_supported_browsers_registry():
    supported = [
        "chrome.exe",
        "msedge.exe",
        "brave.exe",
        "opera.exe",
        "opera_gx.exe",
        "vivaldi.exe",
        "chromium.exe",
        "arc.exe",
        "sidekick.exe",
        "zen.exe",
        "floorp.exe",
        "firefox.exe",
    ]
    for b in supported:
        assert BrowserWindowDetector.is_supported_browser(b) is True
        # Case insensitive test
        assert BrowserWindowDetector.is_supported_browser(b.upper()) is True
        # Without .exe extension
        assert BrowserWindowDetector.is_supported_browser(b.replace(".exe", "")) is True


# TEST 02: Negative tests: Non-browser applications MUST NOT be recognized as browsers
def test_non_browser_processes_rejected():
    non_browsers = [
        "explorer.exe",
        "code.exe",
        "discord.exe",
        "notepad.exe",
        "calc.exe",
        "systemsettings.exe",
        "Quickglint.exe",
        "python.exe",
        "cmd.exe",
        "powershell.exe",
    ]
    for nb in non_browsers:
        assert BrowserWindowDetector.is_supported_browser(nb) is False


# TEST 03: Browser display names
def test_browser_display_names():
    assert BrowserWindowDetector.get_browser_display_name("chrome.exe") == "Google Chrome"
    assert BrowserWindowDetector.get_browser_display_name("msedge.exe") == "Microsoft Edge"
    assert BrowserWindowDetector.get_browser_display_name("brave.exe") == "Brave"
    assert BrowserWindowDetector.get_browser_display_name("opera.exe") == "Opera"
    assert BrowserWindowDetector.get_browser_display_name("unknown.exe") == "Web Browser"


# TEST 04: BrowserWindowInfo data model formatting
def test_browser_window_info_formatting():
    info = BrowserWindowInfo(
        hwnd=12345,
        title="Quickglint - GitHub",
        process_name="chrome.exe",
        process_id=999,
        display_name="Google Chrome",
        bounds=QRect(100, 150, 1920, 1080),
        is_maximized=False,
    )
    assert info.formatted_dimensions == "1920 × 1080 px"
    assert "Google Chrome — Quickglint - GitHub" in info.formatted_title

    empty_info = BrowserWindowInfo(hwnd=0)
    assert empty_info.formatted_dimensions == ""
    assert empty_info.formatted_title == "Web Browser"


# TEST 05: DevTools filter test
def test_devtools_filtering():
    with patch.object(BrowserWindowDetector, "_get_process_info", return_value=("chrome.exe", "Google Chrome")), \
         patch.object(BrowserWindowDetector, "get_window_bounds", return_value=QRect(0, 0, 800, 600)):

        # Normal title should be accepted
        with patch("ctypes.windll.user32.IsWindow", return_value=1), \
             patch("ctypes.windll.user32.IsWindowVisible", return_value=1), \
             patch("ctypes.windll.user32.IsIconic", return_value=0), \
             patch.object(BrowserWindowDetector, "get_window_pid", return_value=5555), \
             patch("ctypes.windll.user32.GetWindowLongW", return_value=0), \
             patch.object(BrowserWindowDetector, "get_window_title", return_value="Google - Search"):

            res = BrowserWindowDetector.inspect_window(101)
            assert res is not None
            assert res.process_name == "chrome.exe"

        # DevTools title should be rejected
        with patch("ctypes.windll.user32.IsWindow", return_value=1), \
             patch("ctypes.windll.user32.IsWindowVisible", return_value=1), \
             patch("ctypes.windll.user32.IsIconic", return_value=0), \
             patch.object(BrowserWindowDetector, "get_window_pid", return_value=5555), \
             patch("ctypes.windll.user32.GetWindowLongW", return_value=0), \
             patch.object(BrowserWindowDetector, "get_window_title", return_value="DevTools - chrome://inspect"):

            res = BrowserWindowDetector.inspect_window(102)
            assert res is None


# TEST 06: Own process filter test (Quickglint should never capture its own overlay)
def test_own_process_filtered():
    own_pid = os.getpid()
    with patch("ctypes.windll.user32.IsWindow", return_value=1), \
         patch("ctypes.windll.user32.IsWindowVisible", return_value=1), \
         patch("ctypes.windll.user32.IsIconic", return_value=0), \
         patch.object(BrowserWindowDetector, "get_window_pid", return_value=own_pid):

        res = BrowserWindowDetector.inspect_window(999)
        assert res is None


# TEST 07: Minimized / Invisible windows filtered
def test_minimized_window_filtered():
    with patch("ctypes.windll.user32.IsWindow", return_value=1), \
         patch("ctypes.windll.user32.IsWindowVisible", return_value=1), \
         patch("ctypes.windll.user32.IsIconic", return_value=1):  # Minimized

        res = BrowserWindowDetector.inspect_window(888)
        assert res is None


# TEST 08: Process info caching
def test_process_info_caching():
    with patch("ctypes.windll.kernel32.OpenProcess", return_value=123) as mock_open, \
         patch("ctypes.windll.kernel32.CloseHandle", return_value=1), \
         patch("ctypes.windll.kernel32.QueryFullProcessImageNameW", lambda h, f, b, s: (setattr(b, "value", r"C:\Program Files\Google\Chrome\chrome.exe"), 1)[1]):

        info1 = BrowserWindowDetector._get_process_info(4321)
        assert info1 == ("chrome.exe", "Google Chrome")
        assert mock_open.call_count == 1

        # Second lookup should hit the cache without calling OpenProcess
        info2 = BrowserWindowDetector._get_process_info(4321)
        assert info2 == ("chrome.exe", "Google Chrome")
        assert mock_open.call_count == 1  # Still 1


# TEST 09: SelectionOverlay in Smart Window Mode - Hover and Render
def test_selection_overlay_smart_window_hover(qapp):
    pix = QPixmap(1920, 1080)
    pix.fill(Qt.GlobalColor.white)
    tm = ToolManager()
    hm = HistoryManager()
    cm = ConfigManager()

    overlay = SelectionOverlay(
        full_desktop_pixmap=pix,
        virtual_geometry=QRect(0, 0, 1920, 1080),
        tool_manager=tm,
        history_manager=hm,
        config_manager=cm,
        default_save_dir="",
        smart_window_mode=True,
    )
    overlay.show()

    mock_browser = BrowserWindowInfo(
        hwnd=777,
        title="Google Chrome",
        process_name="chrome.exe",
        process_id=333,
        display_name="Google Chrome",
        bounds=QRect(50, 50, 1200, 800),
    )

    with patch.object(BrowserWindowDetector, "detect_browser_at_point", return_value=mock_browser):
        # Simulate mouse move over overlay
        move_event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPoint(200, 200),
            QPoint(200, 200),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move_event)

        assert overlay._hovered_browser is not None
        assert overlay._hovered_browser.hwnd == 777
        assert overlay._hovered_browser.bounds == QRect(50, 50, 1200, 800)

        # Trigger paint to ensure no exception occurs
        overlay.repaint()

    overlay.close()


# TEST 10: SelectionOverlay in Smart Window Mode - Click to Capture
def test_selection_overlay_smart_window_click_to_capture(qapp):
    pix = QPixmap(1920, 1080)
    pix.fill(Qt.GlobalColor.white)
    tm = ToolManager()
    hm = HistoryManager()
    cm = ConfigManager()

    overlay = SelectionOverlay(
        full_desktop_pixmap=pix,
        virtual_geometry=QRect(0, 0, 1920, 1080),
        tool_manager=tm,
        history_manager=hm,
        config_manager=cm,
        default_save_dir="",
        smart_window_mode=True,
    )
    overlay.show()

    mock_browser = BrowserWindowInfo(
        hwnd=888,
        title="Microsoft Edge",
        process_name="msedge.exe",
        process_id=444,
        display_name="Microsoft Edge",
        bounds=QRect(100, 100, 1000, 700),
    )
    overlay._hovered_browser = mock_browser

    # Simulate left click
    click_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(300, 300),
        QPoint(300, 300),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(click_event)

    assert overlay._has_selection is True
    assert overlay.selected_rect == QRect(100, 100, 1000, 700)
    assert overlay.smart_window_mode is False
    assert overlay.toolbar.isVisible() is True

    overlay.close()


# TEST 11: Keyboard Shortcut Configuration
def test_smart_window_shortcut_configuration(tmp_path):
    cfg_file = tmp_path / "sw_settings.json"
    cm = ConfigManager(custom_path=cfg_file)
    sw_shortcut = cm.get("hotkeys", "action_smart_window", "Alt+PrintScreen")
    assert sw_shortcut == "Alt+PrintScreen"

    cm.set("hotkeys", "action_smart_window", "Ctrl+Alt+W")
    cm.save()

    cm2 = ConfigManager(custom_path=cfg_file)
    assert cm2.get("hotkeys", "action_smart_window") == "Ctrl+Alt+W"


# TEST 12: Localization keys
def test_smart_window_localization():
    set_language("tr")
    assert "Akıllı Tarayıcı" in tr("tray_smart_window")
    assert "Tıklayarak Yakala" in tr("smart_window_click_to_capture")

    set_language("en")
    assert "Smart Browser" in tr("tray_smart_window")
    assert "Click to Capture" in tr("smart_window_click_to_capture")

