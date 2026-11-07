"""Native Windows Browser Window Detector using Win32 API and DWM Extended Frame Bounds."""

import os
from pathlib import Path
import sys
import time
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QPoint, QRect

from app.utils.logger import logger
from app.window.models import BrowserWindowInfo

if sys.platform == "win32":
    import ctypes
    from ctypes import byref, c_ulong, create_unicode_buffer, sizeof, wintypes

    # Win32 Constants & Structures
    GA_ROOT = 2
    GWL_STYLE = -16
    WS_VISIBLE = 0x10000000
    WS_MINIMIZE = 0x20000000
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]


class BrowserWindowDetector:
    """Detects and calculates pixel-accurate bounds for supported web browser windows."""

    SUPPORTED_BROWSERS: Dict[str, str] = {
        "chrome.exe": "Google Chrome",
        "msedge.exe": "Microsoft Edge",
        "brave.exe": "Brave",
        "opera.exe": "Opera",
        "opera_gx.exe": "Opera GX",
        "vivaldi.exe": "Vivaldi",
        "chromium.exe": "Chromium",
        "arc.exe": "Arc",
        "sidekick.exe": "Sidekick",
        "zen.exe": "Zen Browser",
        "floorp.exe": "Floorp",
        "firefox.exe": "Mozilla Firefox",
    }

    # PID -> (process_name, display_name, cached_timestamp)
    _pid_cache: Dict[int, Tuple[str, str, float]] = {}
    _cache_ttl_sec: float = 3.0

    @classmethod
    def is_supported_browser(cls, process_name: str) -> bool:
        """Checks whether a process executable belongs to a recognized web browser."""
        if not process_name:
            return False
        clean_name = process_name.strip().lower()
        if not clean_name.endswith(".exe"):
            clean_name += ".exe"
        return clean_name in cls.SUPPORTED_BROWSERS

    @classmethod
    def get_browser_display_name(cls, process_name: str) -> str:
        """Returns the user-friendly name of the browser."""
        clean_name = process_name.strip().lower()
        if not clean_name.endswith(".exe"):
            clean_name += ".exe"
        return cls.SUPPORTED_BROWSERS.get(clean_name, "Web Browser")

    @classmethod
    def get_all_browser_windows(cls) -> List[BrowserWindowInfo]:
        """
        Enumerates all open, visible top-level browser windows across all monitors in Z-order.
        Ignores Quickglint's own overlay windows and non-browser applications.
        """
        if sys.platform != "win32":
            return []

        browser_windows: List[BrowserWindowInfo] = []
        own_pid = os.getpid()

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def enum_proc(hwnd: int, lparam: int) -> bool:
            try:
                # 1. Skip invisible / minimized / invalid
                if not ctypes.windll.user32.IsWindow(hwnd):
                    return True
                if not ctypes.windll.user32.IsWindowVisible(hwnd):
                    return True
                if ctypes.windll.user32.IsIconic(hwnd):
                    return True

                # 2. Skip own process (Quickglint overlay)
                pid = cls.get_window_pid(hwnd)
                if pid == 0 or pid == own_pid:
                    return True

                # 3. Check process
                proc_info = cls._get_process_info(pid)
                if not proc_info or not cls.is_supported_browser(proc_info[0]):
                    return True

                # 4. Check window title
                title = cls.get_window_title(hwnd)
                if title.startswith("DevTools -") or title.endswith("- DevTools") or title == "Developer Tools":
                    return True

                # 5. Check bounds
                bounds = cls.get_window_bounds(hwnd)
                if bounds is None or bounds.width() < 60 or bounds.height() < 60:
                    return True

                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                is_maximized = bool(style & 0x01000000)

                browser_windows.append(
                    BrowserWindowInfo(
                        hwnd=hwnd,
                        title=title,
                        process_name=proc_info[0],
                        process_id=pid,
                        display_name=proc_info[1],
                        bounds=bounds,
                        is_maximized=is_maximized,
                        is_valid=True,
                    )
                )
            except Exception as exc:
                logger.debug("Error inspecting hwnd %s: %s", hwnd, exc)
            return True

        cb = WNDENUMPROC(enum_proc)
        ctypes.windll.user32.EnumWindows(cb, 0)
        return browser_windows

    @classmethod
    def detect_browser_at_point(cls, global_point: QPoint) -> Optional[BrowserWindowInfo]:
        """
        Detects the topmost visible browser window beneath the given global cursor point.
        Uses Z-order EnumWindows to completely bypass Quickglint's own full-screen overlay.
        """
        if sys.platform != "win32":
            return None

        try:
            browsers = cls.get_all_browser_windows()
            for b in browsers:
                if b.bounds.contains(global_point):
                    return b
            return None
        except Exception as exc:
            logger.debug("Browser window detection failed at point %s: %s", global_point, exc)
            return None

    @classmethod
    def inspect_window(cls, hwnd: int) -> Optional[BrowserWindowInfo]:
        """
        Inspects an HWND to verify if it is a valid, visible, non-minimized browser window.
        """
        if not hwnd or sys.platform != "win32":
            return None

        try:
            # 1. Check window visibility and minimized state
            if not ctypes.windll.user32.IsWindow(hwnd):
                return None
            if not ctypes.windll.user32.IsWindowVisible(hwnd):
                return None
            if ctypes.windll.user32.IsIconic(hwnd):  # Minimized
                return None

            # 2. Get Process ID & filter out Quickglint's own process
            pid = cls.get_window_pid(hwnd)
            if pid == 0 or pid == os.getpid():
                return None

            # 3. Resolve Process Executable Name (with fast cache)
            proc_info = cls._get_process_info(pid)
            if not proc_info:
                return None

            proc_name, display_name = proc_info
            if not cls.is_supported_browser(proc_name):
                return None

            # 4. Get Window Title & filter DevTools/Helpers
            title = cls.get_window_title(hwnd)

            # Filter out separate DevTools windows
            if title.startswith("DevTools -") or title.endswith("- DevTools") or title == "Developer Tools":
                return None

            # 5. Get Pixel-Accurate Window Bounds via DWM
            bounds = cls.get_window_bounds(hwnd)
            if bounds is None or bounds.width() < 60 or bounds.height() < 60:
                return None

            # Check if maximized
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            is_maximized = bool(style & 0x01000000)  # WS_MAXIMIZE

            return BrowserWindowInfo(
                hwnd=hwnd,
                title=title,
                process_name=proc_name,
                process_id=pid,
                display_name=display_name,
                bounds=bounds,
                is_maximized=is_maximized,
                is_valid=True,
            )
        except Exception as exc:
            logger.debug("Failed inspecting window hwnd=%s: %s", hwnd, exc)
            return None

    @classmethod
    def get_window_bounds(cls, hwnd: int) -> Optional[QRect]:
        """
        Retrieves accurate physical window boundaries without DWM drop-shadow padding.
        Uses DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS) with GetWindowRect fallback.
        """
        if sys.platform != "win32":
            return None

        try:
            rect = RECT()
            # Try DWM extended frame bounds first (Windows 10 / 11)
            hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                byref(rect),
                sizeof(rect),
            )
            if hr != 0:
                # Fallback to standard Win32 GetWindowRect
                if not ctypes.windll.user32.GetWindowRect(hwnd, byref(rect)):
                    return None

            x = rect.left
            y = rect.top
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            if w <= 0 or h <= 0:
                return None

            return QRect(x, y, w, h)
        except Exception as exc:
            logger.debug("Failed getting window bounds for hwnd=%s: %s", hwnd, exc)
            return None

    @classmethod
    def get_window_pid(cls, hwnd: int) -> int:
        """Retrieves process ID for a given window HWND."""
        if sys.platform != "win32":
            return 0
        try:
            pid_val = c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, byref(pid_val))
            return pid_val.value
        except Exception:
            return 0

    @classmethod
    def get_window_title(cls, hwnd: int) -> str:
        """Retrieves window title via GetWindowTextW."""
        if sys.platform != "win32":
            return ""
        try:
            title_buf = create_unicode_buffer(512)
            ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 512)
            return title_buf.value
        except Exception:
            return ""

    @classmethod
    def _get_process_info(cls, pid: int) -> Optional[Tuple[str, str]]:
        """Resolves executable name for a given PID with caching."""
        now = time.time()
        if pid in cls._pid_cache:
            p_name, d_name, t = cls._pid_cache[pid]
            if now - t < cls._cache_ttl_sec:
                return (p_name, d_name)

        h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_proc:
            return None

        try:
            buf_size = c_ulong(1024)
            path_buf = create_unicode_buffer(1024)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, path_buf, byref(buf_size)):
                full_path = path_buf.value
                proc_name = Path(full_path).name.lower()
                display_name = cls.get_browser_display_name(proc_name)

                cls._pid_cache[pid] = (proc_name, display_name, now)
                return (proc_name, display_name)
        finally:
            ctypes.windll.kernel32.CloseHandle(h_proc)

        return None

    @classmethod
    def clear_cache(cls) -> None:
        """Clears process information cache."""
        cls._pid_cache.clear()

