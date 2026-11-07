"""Windows autostart (Run on startup) service using Windows Registry."""

import sys
from pathlib import Path
from typing import Tuple

from app.utils.logger import logger

REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "QuickglintCapture"
LEGACY_REG_NAME = "QuickglintCapture"


class AutostartService:
    """Manages automatic application launch on system startup."""

    @staticmethod
    def is_supported() -> bool:
        """Return True if autostart can be managed on the current OS."""
        return sys.platform == "win32"

    @staticmethod
    def is_enabled() -> bool:
        """Check if Quickglint (or legacy Quickglint) is registered in Windows Startup registry."""
        if not AutostartService.is_supported():
            return False

        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_READ
            ) as key:
                for reg_name in (APP_REG_NAME, LEGACY_REG_NAME):
                    try:
                        val, _ = winreg.QueryValueEx(key, reg_name)
                        if val:
                            return True
                    except FileNotFoundError:
                        pass
                return False
        except Exception as exc:
            logger.warning("Failed to check autostart registry status: %s", exc)
            return False

    @staticmethod
    def enable() -> Tuple[bool, str]:
        """Register the current executable/script in Windows Startup registry."""
        if not AutostartService.is_supported():
            return False, "Autostart is only supported on Windows."

        try:
            import winreg

            # If running as bundled pyinstaller exe:
            if getattr(sys, "frozen", False):
                app_path = f'"{sys.executable}"'
            else:
                # Running as python script
                main_script = Path(__file__).resolve().parent.parent.parent / "main.py"
                python_exe = sys.executable
                # Use pythonw if available to avoid cmd window on startup
                pythonw_exe = Path(python_exe).with_name("pythonw.exe")
                exec_cmd = str(pythonw_exe) if pythonw_exe.exists() else python_exe
                app_path = f'"{exec_cmd}" "{main_script}"'

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, app_path)
                try:
                    winreg.DeleteValue(key, LEGACY_REG_NAME)
                except FileNotFoundError:
                    pass

            logger.info("Successfully enabled autostart in registry: %s", app_path)
            return True, "Autostart enabled."
        except Exception as exc:
            err = f"Failed to enable autostart: {exc}"
            logger.error(err, exc_info=True)
            return False, err

    @staticmethod
    def disable() -> Tuple[bool, str]:
        """Remove Quickglint from Windows Startup registry."""
        if not AutostartService.is_supported():
            return False, "Autostart is only supported on Windows."

        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_SET_VALUE
            ) as key:
                for reg_name in (APP_REG_NAME, LEGACY_REG_NAME):
                    try:
                        winreg.DeleteValue(key, reg_name)
                        logger.info("Successfully removed autostart registry entry: %s", reg_name)
                    except FileNotFoundError:
                        pass
            return True, "Autostart disabled."
        except Exception as exc:
            err = f"Failed to disable autostart: {exc}"
            logger.error(err, exc_info=True)
            return False, err

