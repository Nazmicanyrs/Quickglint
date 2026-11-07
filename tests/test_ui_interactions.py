import pytest
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication

from app.capture.selection_overlay import HandlePosition, SelectionOverlay
from app.editor.history import HistoryManager
from app.editor.tools import ToolManager
from app.ui.settings_dialog import SettingsDialog
from config.config_manager import ConfigManager


def test_settings_dialog_opens_and_loads(qapp):
    config_manager = ConfigManager()
    dlg = SettingsDialog(config_manager)
    assert dlg is not None
    dlg.show()
    assert dlg.isVisible()
    # Test switching tabs
    dlg._switch_tab(1)  # Hotkeys
    dlg._switch_tab(2)  # Privacy
    dlg._switch_tab(3)  # OCR
    dlg._switch_tab(4)  # QR
    dlg._switch_tab(5)  # Scrolling GIF
    dlg._switch_tab(6)  # Image
    dlg._switch_tab(7)  # Editor
    dlg._switch_tab(8)  # Upload
    dlg._switch_tab(9)  # About
    dlg._switch_tab(0)  # General
    dlg.close()


def test_selection_overlay_rectangle_move_and_resize(qapp):
    config_manager = ConfigManager()
    pix = QPixmap(1920, 1200)
    pix.fill(Qt.GlobalColor.white)
    tools = ToolManager()
    hist = HistoryManager()
    overlay = SelectionOverlay(pix, QRect(0, 0, 1920, 1200), tools, hist, config_manager, "")
    overlay.show()

    # Create selection
    overlay._start_pos = QPointF(100, 100).toPoint()
    overlay._is_selecting = False
    overlay.selected_rect = QRect(100, 100, 400, 300)
    overlay._has_selection = True
    overlay._init_canvas()

    # Move rectangle from inside
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(200, 200),
        QPointF(200, 200),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press)
    assert overlay._active_handle == HandlePosition.INSIDE

    move = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(350, 350),
        QPointF(350, 350),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseMoveEvent(move)
    assert overlay.selected_rect.x() == 250
    assert overlay.selected_rect.y() == 250

    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(350, 350),
        QPointF(350, 350),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release)
    assert overlay._has_selection is True
    assert overlay.canvas is not None
    overlay.close()


def test_application_hotkey_triggered(qapp, monkeypatch):
    from app.application import QuickglintApp

    app = QuickglintApp([])
    capture_called = []
    monkeypatch.setattr(app, "trigger_capture", lambda: capture_called.append(True))

    app._on_hotkey_triggered()
    qapp.processEvents()
    # Wait for the singleShot 60ms timer
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(100, loop.quit)
    loop.exec()

    assert len(capture_called) == 1


def test_floating_toolbar_dropdown_menus(qapp):
    from app.editor.history import HistoryManager
    from app.editor.tools import ToolManager
    from app.ui.toolbar import FloatingToolbar

    tools = ToolManager()
    hist = HistoryManager()
    toolbar = FloatingToolbar(tools, hist)
    toolbar.show()

    # Verify dropdown menus exist and contain proper actions
    assert toolbar.session_btn is not None
    assert toolbar.session_btn.menu() is not None
    sess_actions = [a.text() for a in toolbar.session_btn.menu().actions() if not a.isSeparator()]
    assert "Yeni Seri Ekran Görüntüsü Başlat" in sess_actions
    assert "Mevcut Seri Oturuma Ekle" in sess_actions
    assert "Seri Oturum Galerisini Aç" in sess_actions

    assert toolbar.tools_btn is not None
    assert toolbar.tools_btn.menu() is not None
    tool_actions = [a.text() for a in toolbar.tools_btn.menu().actions() if not a.isSeparator()]
    assert any("OCR" in a for a in tool_actions)
    assert any("QR" in a for a in tool_actions)
    assert any("Privacy" in a for a in tool_actions)
    assert any("Scrolling" in a for a in tool_actions)
    assert any("GIF" in a for a in tool_actions)

    assert toolbar.measure_btn is not None
    assert toolbar.measure_btn.menu() is not None
    measure_actions = [a.text() for a in toolbar.measure_btn.menu().actions() if not a.isSeparator()]
    assert any("Ölçüm" in a for a in measure_actions)

    assert toolbar.export_btn is not None
    assert toolbar.export_btn.menu() is not None
    export_actions = [a.text() for a in toolbar.export_btn.menu().actions() if not a.isSeparator()]
    assert any("Favori" in a for a in export_actions)
    assert any("Kasaya" in a for a in export_actions)
    assert any("PDF" in a for a in export_actions)
    assert any("Optimize" in a for a in export_actions)
    assert any("ImgBB" in a for a in export_actions)
    assert any("Geçmiş" in a for a in export_actions)

    # Test signals
    signals_received = []
    toolbar.new_session_requested.connect(lambda: signals_received.append("new_session"))
    toolbar.extract_text_requested.connect(lambda: signals_received.append("ocr"))
    toolbar.save_to_vault_requested.connect(lambda: signals_received.append("vault"))

    toolbar.new_session_requested.emit()
    toolbar.extract_text_requested.emit()
    toolbar.save_to_vault_requested.emit()

    assert signals_received == ["new_session", "ocr", "vault"]
    toolbar.close()



