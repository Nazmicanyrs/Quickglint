"""Tests for HotkeyRecorderEdit widget and key handling."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from app.ui.hotkey_edit import HotkeyRecorderEdit


def test_hotkey_recorder_edit():
    editor = HotkeyRecorderEdit("PrintScreen")
    assert editor.get_hotkey() == "PrintScreen"

    editor.set_hotkey("Ctrl+Shift+S")
    assert editor.get_hotkey() == "Ctrl+Shift+S"

    # Simulate entering recording mode and pressing 'B'
    editor._is_recording = True
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier, "b")
    editor.keyPressEvent(event)
    assert editor.get_hotkey() == "B"

    # Simulate pressing Ctrl + C
    editor._is_recording = True
    event_ctrl_c = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier, "c")
    editor.keyPressEvent(event_ctrl_c)
    assert editor.get_hotkey() == "Ctrl+C"

