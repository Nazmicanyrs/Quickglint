"""UI components and widgets package."""

from app.ui.notifications import NotificationManager, ToastNotification
from app.ui.settings_dialog import SettingsDialog
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.ui.toolbar import FloatingToolbar
from app.ui.tray import TrayIconManager

__all__ = [
    "DARK_THEME_QSS",
    "FloatingToolbar",
    "NotificationManager",
    "SettingsDialog",
    "ToastNotification",
    "TrayIconManager",
    "get_icon",
]

