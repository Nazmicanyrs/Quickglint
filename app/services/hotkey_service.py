"""Global hotkey service for triggering screenshot captures from anywhere."""

from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal
from app.utils.logger import logger


class HotkeyService(QObject):
    """Listens for global system hotkeys in a background thread and emits Qt signals."""

    triggered = Signal()
    error_occurred = Signal(str)

    def __init__(self, hotkey_str: str = "PrintScreen", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.current_hotkey_str = hotkey_str
        self._listener = None
        self._is_running = False

    def _normalize_hotkey_for_pynput(self, hotkey_str: str) -> str:
        """Convert friendly hotkey strings to pynput format."""
        s = hotkey_str.strip()
        # Handle Print Screen variants
        if s.lower().replace(" ", "").replace("_", "") in ["printscreen", "prntscrn", "prtscn", "prtscr", "print"]:
            return "<print_screen>"

        # Parse combos like Ctrl+Shift+S or Alt+Shift+S
        parts = [p.strip().lower() for p in s.split("+")]
        formatted_parts = []
        for p in parts:
            if p in ["ctrl", "control"]:
                formatted_parts.append("<ctrl>")
            elif p in ["shift"]:
                formatted_parts.append("<shift>")
            elif p in ["alt"]:
                formatted_parts.append("<alt>")
            elif p in ["cmd", "super", "win", "windows"]:
                formatted_parts.append("<cmd>")
            elif p in ["printscreen", "prntscrn", "prtscn", "prtscr", "print"]:
                formatted_parts.append("<print_screen>")
            elif p.startswith("f") and p[1:].isdigit():
                formatted_parts.append(f"<{p}>")
            else:
                formatted_parts.append(p)

        return "+".join(formatted_parts)

    def _on_hotkey_activated(self) -> None:
        """Callback when hotkey is pressed."""
        logger.info("Global hotkey activated: %s", self.current_hotkey_str)
        self.triggered.emit()

    def start(self, hotkey_str: Optional[str] = None) -> bool:
        """Start listening for the specified hotkey.

        A previously working listener is kept alive if the new one fails to register.
        """
        requested = hotkey_str or self.current_hotkey_str
        pynput_hotkey = self._normalize_hotkey_for_pynput(requested)
        logger.info("Starting hotkey listener with combination: %s (raw: %s)", pynput_hotkey, requested)

        try:
            from pynput import keyboard

            hotkeys_dict = {
                pynput_hotkey: self._on_hotkey_activated
            }

            new_listener = keyboard.GlobalHotKeys(hotkeys_dict)
            new_listener.daemon = True
            new_listener.start()
        except Exception as exc:
            err_msg = f"Failed to register global hotkey '{requested}': {exc}"
            logger.error(err_msg, exc_info=True)
            self.error_occurred.emit(err_msg)
            return False

        self.stop()
        self.current_hotkey_str = requested
        self._listener = new_listener
        self._is_running = True
        return True

    def stop(self) -> None:
        """Stop hotkey listener."""
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception as exc:
                logger.warning("Error stopping hotkey listener: %s", exc)
            self._listener = None
        self._is_running = False

    def is_running(self) -> bool:
        """Check if listener is running."""
        return self._is_running

