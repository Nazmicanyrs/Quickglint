"""Smart file naming service with template variables, Windows path sanitization, and collision safety."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import logger

DEFAULT_NAMING_TEMPLATE = "Quickglint_{date}_{time}_{n}"

AVAILABLE_NAMING_VARIABLES: List[Tuple[str, str]] = [
    ("{date}", "Tarih (YYYY-MM-DD)"),
    ("{time}", "Saat (HH-MM-SS)"),
    ("{datetime}", "Tarih ve Saat (YYYY-MM-DD_HH-MM-SS)"),
    ("{n}", "Artan Sayaç (001, 002...)"),
    ("{window}", "Aktif Pencere Başlığı"),
    ("{app}", "Uygulama / Süreç Adı"),
    ("{mode}", "Yakalama Modu (bolge/pencere/kaydirmali/gif)"),
    ("{ocr}", "OCR İlk Satırı (yalnızca OCR çalıştıysa)"),
]

_WINDOWS_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_VALID_TOKEN_RE = re.compile(r"\{(date|time|datetime|n|window|app|mode|ocr)\}")


@dataclass
class CaptureMetadata:
    """Contextual metadata for a captured screenshot used by Smart Naming and Info Banner."""

    timestamp: datetime = field(default_factory=datetime.now)
    window_title: str = ""
    app_name: str = ""
    mode: str = "bolge"
    ocr_text: str = ""
    url: str = ""
    resolution: str = ""


def capture_foreground_window_info() -> Tuple[str, str]:
    """Capture the foreground window title and process name on Windows before overlay activation."""
    if sys.platform != "win32":
        return "", ""
    try:
        import ctypes
        from ctypes import byref, c_ulong, create_unicode_buffer

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return "", ""

        pid_val = c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, byref(pid_val))
        pid = pid_val.value
        if pid == 0 or pid == os.getpid():
            return "", ""

        title_buf = create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, title_buf, 512)
        title = title_buf.value.strip()

        proc_name = ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h_proc:
            try:
                buf_size = c_ulong(1024)
                path_buf = create_unicode_buffer(1024)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_proc, 0, path_buf, byref(buf_size)):
                    proc_name = Path(path_buf.value).stem
            finally:
                ctypes.windll.kernel32.CloseHandle(h_proc)

        return title, proc_name
    except Exception as exc:
        logger.debug("Foreground window inspection skipped: %s", exc)
        return "", ""


class SmartNamingService:
    """Formats, validates, and resolves collision-free screenshot filenames."""

    DEFAULT_TEMPLATE = DEFAULT_NAMING_TEMPLATE
    MAX_PATH_LEN = 245  # Leaves headroom under Windows 260 MAX_PATH for collision suffixes
    MAX_STEM_LEN = 120

    @staticmethod
    def sanitize_component(value: str, max_len: int = 48) -> str:
        """Clean a single variable value for safe inclusion in a Windows filename."""
        if not value:
            return ""
        cleaned = _WINDOWS_INVALID_CHARS_RE.sub(" ", str(value))
        cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len].rstrip(" ._")
        return cleaned

    @classmethod
    def extract_first_meaningful_ocr_line(cls, ocr_text: str) -> str:
        """Extract the first meaningful line from already-computed OCR text (never runs OCR)."""
        if not ocr_text:
            return ""
        for raw_line in ocr_text.splitlines():
            line = raw_line.strip()
            if len(line) >= 2 and any(ch.isalnum() for ch in line):
                return cls.sanitize_component(line, max_len=36)
        return ""

    @classmethod
    def is_template_valid(cls, template: str) -> bool:
        """Check whether a user template is syntactically valid and non-empty."""
        if not isinstance(template, str) or not template.strip():
            return False
        # Reject unbalanced braces
        stripped = _VALID_TOKEN_RE.sub("X", template)
        if "{" in stripped or "}" in stripped:
            return False
        return True

    @classmethod
    def format_stem(
        cls,
        template: Optional[str],
        metadata: Optional[CaptureMetadata] = None,
        counter: int = 1,
    ) -> str:
        """Render a sanitized filename stem (without extension) from template and metadata."""
        meta = metadata or CaptureMetadata()
        active_template = template if (template and cls.is_template_valid(template)) else cls.DEFAULT_TEMPLATE

        now = meta.timestamp or datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H-%M-%S")
        datetime_str = f"{date_str}_{time_str}"
        n_str = f"{max(1, int(counter)):03d}"

        values: Dict[str, str] = {
            "date": date_str,
            "time": time_str,
            "datetime": datetime_str,
            "n": n_str,
            "window": cls.sanitize_component(meta.window_title, max_len=40),
            "app": cls.sanitize_component(meta.app_name, max_len=28),
            "mode": cls.sanitize_component(meta.mode or "bolge", max_len=20),
            "ocr": cls.extract_first_meaningful_ocr_line(meta.ocr_text),
        }

        try:
            rendered = _VALID_TOKEN_RE.sub(lambda m: values.get(m.group(1), ""), active_template)
        except Exception:
            rendered = f"Quickglint_{date_str}_{time_str}_{n_str}"

        # Clean invalid characters and collapse duplicate separators left by empty optional tokens
        rendered = _WINDOWS_INVALID_CHARS_RE.sub("_", rendered)
        rendered = re.sub(r"_{2,}", "_", rendered)
        rendered = re.sub(r"-{2,}", "-", rendered)
        rendered = re.sub(r"(_-|-_)+", "-", rendered)
        rendered = rendered.strip(" ._-")

        if not rendered:
            rendered = f"Quickglint_{date_str}_{time_str}_{n_str}"

        # Guard against Windows reserved device names (e.g. CON, NUL, COM1, CON.txt)
        base_check = rendered.split(".")[0].upper()
        if base_check in _WINDOWS_RESERVED_NAMES:
            rendered = f"Quickglint_{rendered}"

        if len(rendered) > cls.MAX_STEM_LEN:
            rendered = rendered[: cls.MAX_STEM_LEN].rstrip(" ._-")

        return rendered or f"Quickglint_{date_str}_{time_str}_{n_str}"

    @classmethod
    def preview_filename(
        cls,
        template: Optional[str],
        ext: str = "png",
        counter: int = 1,
    ) -> str:
        """Return a live sample filename for the Settings UI preview."""
        sample_meta = CaptureMetadata(
            timestamp=datetime.now(),
            window_title="Proje Raporu - Tarayıcı",
            app_name="chrome",
            mode="bolge",
            ocr_text="Fatura No 2026",
        )
        stem = cls.format_stem(template, metadata=sample_meta, counter=counter)
        clean_ext = ext.lstrip(".").lower() or "png"
        return f"{stem}.{clean_ext}"

    @classmethod
    def resolve_safe_path(
        cls,
        save_dir: str | Path,
        ext: str = "png",
        template: Optional[str] = None,
        metadata: Optional[CaptureMetadata] = None,
        config_manager: Optional[Any] = None,
        increment_counter: bool = True,
    ) -> Path:
        """
        Build a safe, length-bounded, collision-free Path inside save_dir.
        Never overwrites an existing file.
        """
        dir_path = Path(save_dir) if save_dir else Path.home() / "Pictures" / "Screenshots"
        clean_ext = ext.lstrip(".").lower() or "png"

        counter = 1
        if config_manager is not None:
            if template is None:
                template = config_manager.get("naming", "template", cls.DEFAULT_TEMPLATE)
            try:
                counter = max(1, int(config_manager.get("naming", "counter", 1)))
            except Exception:
                counter = 1

        stem = cls.format_stem(template, metadata=metadata, counter=counter)

        # Enforce total path length budget (accounting for directory length + collision suffix + extension)
        dir_str_len = len(str(dir_path))
        ext_len = len(clean_ext) + 1  # ".png"
        collision_reserve = 6         # e.g. "_9999"
        allowed_stem_len = max(12, min(cls.MAX_STEM_LEN, cls.MAX_PATH_LEN - dir_str_len - 1 - ext_len - collision_reserve))

        if len(stem) > allowed_stem_len:
            stem = stem[:allowed_stem_len].rstrip(" ._-")
            if not stem:
                stem = "Quickglint"
            if stem.split(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
                stem = f"QG_{stem}"[:allowed_stem_len].rstrip(" ._-")

        candidate = dir_path / f"{stem}.{clean_ext}"
        collision_idx = 2
        while candidate.exists():
            suffix = f"_{collision_idx}"
            trimmed_stem = stem[: max(8, allowed_stem_len - len(suffix))].rstrip(" ._-")
            candidate = dir_path / f"{trimmed_stem}{suffix}.{clean_ext}"
            collision_idx += 1

        if increment_counter and config_manager is not None:
            try:
                config_manager.set("naming", "counter", counter + 1)
            except Exception as exc:
                logger.debug("Could not persist naming counter: %s", exc)

        return candidate


