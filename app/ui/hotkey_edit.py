"""Interactive keyboard shortcut recorder widget."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFocusEvent, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget


class HotkeyRecorderEdit(QLineEdit):
    """Line edit widget that records pressed key sequences automatically."""

    hotkey_changed = Signal(str)

    def __init__(self, initial_hotkey: Optional[str | QWidget] = "", parent: Optional[QWidget] = None) -> None:
        if isinstance(initial_hotkey, QWidget):
            parent = initial_hotkey
            initial_hotkey = ""
        super().__init__(parent)
        self.setReadOnly(True)
        self.setText(str(initial_hotkey) if initial_hotkey else "")
        self._is_recording = False
        self.setPlaceholderText("Tuşa basın... / Press key...")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def _update_style(self) -> None:
        if self._is_recording:
            self.setStyleSheet(
                "background-color: #2D3748; color: #63B3ED; border: 2px solid #3182CE; "
                "border-radius: 6px; padding: 6px 10px; font-weight: bold;"
            )
        else:
            self.setStyleSheet(
                "background-color: #1A202C; color: #F7FAFC; border: 1px solid #4A5568; "
                "border-radius: 6px; padding: 6px 10px;"
            )

    def mousePressEvent(self, event) -> None:
        self._is_recording = True
        self.setText("Tuşa basın... (Press any key)")
        self._update_style()
        super().mousePressEvent(event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        self._is_recording = True
        self.setText("Tuşa basın... (Press any key)")
        self._update_style()
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self._is_recording = False
        if self.text() == "Tuşa basın... (Press any key)":
            self.setText(self._last_valid_hotkey if hasattr(self, "_last_valid_hotkey") else "PrintScreen")
        self._update_style()
        super().focusOutEvent(event)

    def set_hotkey(self, hotkey_str: str) -> None:
        self._last_valid_hotkey = hotkey_str
        self.setText(hotkey_str)
        self._is_recording = False
        self._update_style()

    def get_hotkey(self) -> str:
        return self._last_valid_hotkey if hasattr(self, "_last_valid_hotkey") else self.text()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._is_recording:
            return super().keyPressEvent(event)

        key = event.key()
        modifiers = event.modifiers()

        # Ignore standalone modifier presses
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
            Qt.Key.Key_AltGr,
        ):
            return

        # Handle Clear / Backspace
        if key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
            self.setText("")
            self._last_valid_hotkey = ""
            self._is_recording = False
            self._update_style()
            self.clearFocus()
            self.hotkey_changed.emit("")
            return

        # Handle Escape (Cancel recording)
        if key == Qt.Key.Key_Escape:
            self._is_recording = False
            self.setText(self._last_valid_hotkey if hasattr(self, "_last_valid_hotkey") else "")
            self._update_style()
            self.clearFocus()
            return

        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")

        # Map special keys
        special_keys = {
            Qt.Key.Key_Print: "PrintScreen",
            Qt.Key.Key_SysReq: "PrintScreen",
            Qt.Key.Key_F1: "F1",
            Qt.Key.Key_F2: "F2",
            Qt.Key.Key_F3: "F3",
            Qt.Key.Key_F4: "F4",
            Qt.Key.Key_F5: "F5",
            Qt.Key.Key_F6: "F6",
            Qt.Key.Key_F7: "F7",
            Qt.Key.Key_F8: "F8",
            Qt.Key.Key_F9: "F9",
            Qt.Key.Key_F10: "F10",
            Qt.Key.Key_F11: "F11",
            Qt.Key.Key_F12: "F12",
            Qt.Key.Key_Space: "Space",
            Qt.Key.Key_Return: "Enter",
            Qt.Key.Key_Enter: "Enter",
            Qt.Key.Key_Tab: "Tab",
            Qt.Key.Key_Insert: "Insert",
            Qt.Key.Key_Home: "Home",
            Qt.Key.Key_End: "End",
            Qt.Key.Key_PageUp: "PageUp",
            Qt.Key.Key_PageDown: "PageDown",
        }

        if key in special_keys:
            key_name = special_keys[key]
        else:
            text = event.text().upper()
            if text and text.isprintable() and not text.isspace():
                key_name = text
            else:
                # Fallback to Qt key name
                key_name = chr(key) if 32 <= key <= 126 else f"Key_{key}"

        parts.append(key_name)
        combo_str = "+".join(parts)

        self._last_valid_hotkey = combo_str
        self.setText(combo_str)
        self._is_recording = False
        self._update_style()
        self.clearFocus()
        self.hotkey_changed.emit(combo_str)

