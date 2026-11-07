"""Configuration manager for Quickglint application with Smart Privacy, Scrolling, and GIF settings."""

import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from app.utils.constants import (
    DEFAULT_CAPTURE_HOTKEY,
    DEFAULT_DRAWING_COLOR,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_IMAGE_FORMAT,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_STROKE_WIDTH,
)
from app.utils.helpers import get_default_screenshots_dir
from app.utils.logger import logger


DEFAULT_SETTINGS: Dict[str, Any] = {
    "general": {
        "start_with_windows": False,
        "minimize_to_tray": True,
        "show_notifications": True,
        "default_save_dir": str(get_default_screenshots_dir()),
        "vault_location": "",
        "language": "tr",
    },
    "hotkeys": {
        "capture_hotkey": DEFAULT_CAPTURE_HOTKEY,
        "action_smart_window": "Alt+PrintScreen",
        "action_panorama": "Ctrl+Shift+M",
        "action_scrolling": "Ctrl+Shift+L",
        "action_gif": "Ctrl+Shift+G",
        "tool_select": "Esc",
        "tool_pen": "P",
        "tool_highlighter": "H",
        "tool_line": "L",
        "tool_arrow": "A",
        "tool_rectangle": "R",
        "tool_ellipse": "E",
        "tool_text": "T",
        "tool_blur": "B",
        "tool_pixelate": "M",
        "tool_magnifier": "Z",
        "action_copy": "Ctrl+C",
        "action_save": "Ctrl+S",
        "action_undo": "Ctrl+Z",
        "action_redo": "Ctrl+Y",
        "action_privacy": "Ctrl+Shift+P",
        "action_ocr": "Ctrl+Shift+O",
        "action_copy_ocr": "Ctrl+Shift+C",
        "action_favorite": "Ctrl+Shift+F",
    },
    "image": {
        "default_format": DEFAULT_IMAGE_FORMAT,
        "jpeg_quality": DEFAULT_JPEG_QUALITY,
        "include_cursor": False,
    },
    "editor": {
        "default_color": DEFAULT_DRAWING_COLOR,
        "default_brush_size": DEFAULT_STROKE_WIDTH,
        "default_font_size": DEFAULT_FONT_SIZE,
        "default_font_family": DEFAULT_FONT_FAMILY,
        "blur_radius": 15,
        "pixel_size": 12,
        "blur_tint": "",
        "blur_tint_opacity": 0.2,
        "toolbar_position": "bottom_right",
        "dark_mode": True,
    },
    "privacy": {
        "enabled": True,
        "default_effect": "pixelate",
        "detect_emails": True,
        "detect_phones": True,
        "detect_ips": True,
        "detect_urls": True,
        "detect_api_keys": True,
        "detect_tokens": True,
        "detect_credit_cards": True,
        "detect_iban": True,
        "detect_file_paths": True,
        "auto_redact_on_save": False,
        "ocr_engine": "auto",
    },
    "scrolling": {
        "scroll_speed": "normal",
        "max_captures": 40,
        "max_height": 40000,
        "step_clicks": 4,
        "delay_seconds": 0.4,
    },
    "recorder": {
        "fps": 15,
        "max_duration": 60.0,
        "show_cursor": True,
        "highlight_cursor": True,
        "show_click_effects": True,
        "quality_colors": 256,
        "loop": 0,
    },
    "ocr": {
        "engine": "auto",
        "languages": ["tr", "en"],
        "auto_detect_after_capture": False,
        "enhance_contrast": False,
        "upscale_small": True,
    },
    "qr": {
        "enabled": True,
        "show_panel_automatically": True,
        "highlight_detected": True,
    },
    "naming": {
        "template": "Quickglint_{date}_{time}_{n}",
        "counter": 1,
    },
    "watermark": {
        "enabled": False,
        "auto_apply_on_save": False,
        "auto_apply_on_copy": False,
        "apply_on_export": False,
        "watermark_type": "text",  # "text" | "image"
        "text": "Quickglint",
        "image_path": "",
        "position": "bottom_right",  # 9-point grid: top_left, top_center, top_right, middle_left, center, middle_right, bottom_left, bottom_center, bottom_right
        "margin": 20,
        "opacity": 65,
        "scale_percent": 18,
        "rotation": 0,
        "font_family": "Segoe UI",
        "text_color": "#FFFFFF",
        "shadow_enabled": True,
        "tiled": False,
        "tile_spacing": 25,
        "diagonal_banner": False,
        "active_profile": "Varsayılan",
        "profiles": {},
    },
    "info_banner": {
        "enabled": False,
        "auto_apply_on_save": False,
        "auto_apply_on_copy": False,
        "apply_on_export": False,
        "show_datetime": True,
        "show_window_title": True,
        "show_app_name": True,
        "show_url": False,
        "show_resolution": True,
        "show_custom_text": False,
        "custom_text": "",
        "show_computer_name": False,  # Sensitive -> OFF by default
        "show_user_name": False,      # Sensitive -> OFF by default
        "theme": "dark",              # "dark" | "light" | "custom"
        "bg_color": "#0F172A",
        "text_color": "#F8FAFC",
        "separator_color": "#334155",
        "show_separator": True,
        "font_size": 12,
        "alignment": "left",          # "left" | "center" | "right"
        "wrap_long_text": True,
    },
    "panorama": {
        "default_mode": "full_desktop",
        "detector": "auto",
        "alignment": "homography",
        "blending": "multiband",
        "exposure_compensation": True,
        "normalize_dpi": True,
        "auto_crop": True,
        "default_format": "PNG",
        "jpeg_quality": 95,
    },
    "upload": {
        "privacy_check": True,
        "clean_metadata": True,
        "copy_share_url": True,
        "copy_direct_url": False,
        "save_history": True,
        "expiration": None,
    },
}


def _types_compatible(default: Any, value: Any) -> bool:
    """Return True if value has a type compatible with the default setting."""
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    if isinstance(default, list):
        return isinstance(value, list)
    if isinstance(default, dict):
        return isinstance(value, dict)
    return True


def get_config_path() -> Path:
    """Return user configuration path, migrating seamlessly from Quickglint if present."""
    import shutil

    if sys.platform == "win32":
        base_dir = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base_dir = str(Path.home() / "Library" / "Application Support")
    else:
        base_dir = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")

    config_dir = Path(base_dir) / "Quickglint"
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    target_file = config_dir / "settings.json"

    # Backward compatibility: migrate settings from legacy Quickglint directory if present
    if not target_file.exists():
        legacy_file = Path(base_dir) / "Quickglint" / "settings.json"
        if legacy_file.exists():
            try:
                shutil.copy2(legacy_file, target_file)
            except Exception:
                pass

    return target_file


class ConfigManager:
    """Manages application settings with persistent JSON storage."""

    def __init__(self, custom_path: Path | None = None) -> None:
        self.config_file = custom_path or get_config_path()
        self._settings: Dict[str, Any] = deepcopy(DEFAULT_SETTINGS)
        self.load()

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a setting value safely."""
        return self._settings.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        """Set a setting value and persist."""
        if section not in self._settings:
            self._settings[section] = {}
        self._settings[section][key] = value
        self.save()

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get all settings in a section."""
        return deepcopy(self._settings.get(section, {}))

    def update_section(self, section: str, values: Dict[str, Any]) -> None:
        """Update multiple values in a section."""
        if section not in self._settings:
            self._settings[section] = {}
        self._settings[section].update(values)
        self.save()

    def load(self) -> None:
        """Load settings from JSON file with merge against defaults."""
        if not self.config_file.exists():
            self.save()
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    for sec_key, sec_val in loaded.items():
                        default_sec = DEFAULT_SETTINGS.get(sec_key)
                        if isinstance(default_sec, dict) and isinstance(sec_val, dict):
                            for k, v in sec_val.items():
                                dv = default_sec.get(k)
                                # Reject values whose type contradicts the default (bool/int/float/str/list).
                                if dv is not None and not _types_compatible(dv, v):
                                    logger.warning("Ignoring invalid setting %s.%s=%r", sec_key, k, v)
                                    continue
                                self._settings[sec_key][k] = v
                        elif isinstance(default_sec, dict):
                            logger.warning("Ignoring invalid settings section %r", sec_key)
                        else:
                            self._settings[sec_key] = sec_val

            # Auto-migrate naming template from Quickglint to Quickglint
            naming_tmpl = self._settings.get("naming", {}).get("template", "")
            if isinstance(naming_tmpl, str) and naming_tmpl.startswith("Quickglint_"):
                self._settings["naming"]["template"] = "Quickglint_" + naming_tmpl[len("Quickglint_"):]

            logger.info("Loaded configuration from %s", self.config_file)
        except Exception as exc:
            logger.error("Failed to load settings from %s, using defaults: %s", self.config_file, exc)
            # Keep the unreadable file so a later save() does not destroy it.
            try:
                self.config_file.replace(self.config_file.with_suffix(self.config_file.suffix + ".corrupt"))
            except Exception:
                pass
            self._settings = deepcopy(DEFAULT_SETTINGS)

    def save(self) -> None:
        """Save settings to JSON file."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self.config_file.with_suffix(self.config_file.suffix + ".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            tmp_file.replace(self.config_file)
            logger.info("Saved configuration to %s", self.config_file)
        except Exception as exc:
            logger.error("Failed to save settings to %s: %s", self.config_file, exc)

    def reset_to_defaults(self) -> None:
        """Reset all configuration to application defaults."""
        self._settings = deepcopy(DEFAULT_SETTINGS)
        self.save()

    # ------------------------------------------------------------------
    # Import / export
    # ------------------------------------------------------------------
    EXPORT_FORMAT = "QuickglintSettings"
    EXPORT_VERSION = 1

    def export_to_file(self, path: Path | str) -> None:
        """Write all settings to a portable JSON file.

        Secrets (API keys, OAuth tokens) live in the encrypted credential store and
        are intentionally never part of an export.
        """
        target = Path(path)
        payload = {
            "format": self.EXPORT_FORMAT,
            "version": self.EXPORT_VERSION,
            "settings": deepcopy(self._settings),
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(target)
        logger.info("Exported settings to %s", target)

    def import_from_file(self, path: Path | str) -> int:
        """Load settings from an exported file, validating every value.

        Returns the number of values applied. Raises ``ValueError`` for files that
        are not valid Quickglint settings exports; the current settings stay untouched
        in that case. Unknown sections/keys and values of the wrong type are skipped.
        """
        source = Path(path)
        try:
            with open(source, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Dosya okunamadı: {exc}") from exc

        if not isinstance(payload, dict) or payload.get("format") != self.EXPORT_FORMAT:
            raise ValueError("Bu dosya geçerli bir Quickglint ayar dosyası değil.")
        incoming = payload.get("settings")
        if not isinstance(incoming, dict):
            raise ValueError("Ayar dosyasında 'settings' bölümü bulunamadı.")

        applied = 0
        updated = deepcopy(self._settings)
        for sec_key, sec_val in incoming.items():
            default_sec = DEFAULT_SETTINGS.get(sec_key)
            if not isinstance(default_sec, dict) or not isinstance(sec_val, dict):
                continue
            for key, value in sec_val.items():
                if key not in default_sec:
                    continue
                if not _types_compatible(default_sec[key], value):
                    logger.warning("Import: ignoring invalid value for %s.%s", sec_key, key)
                    continue
                updated[sec_key][key] = value
                applied += 1

        if applied == 0:
            raise ValueError("Dosyada uygulanabilir geçerli bir ayar bulunamadı.")

        self._settings = updated
        self.save()
        logger.info("Imported %d settings from %s", applied, source)
        return applied

