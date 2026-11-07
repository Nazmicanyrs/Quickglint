"""Tests for ConfigManager persistence and defaults."""

import tempfile
from pathlib import Path
from config.config_manager import ConfigManager, DEFAULT_SETTINGS


def test_config_defaults_and_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / "test_settings.json"
        cfg = ConfigManager(custom_path=config_path)

        # Check default values
        assert cfg.get("hotkeys", "capture_hotkey") == "PrintScreen"
        assert cfg.get("image", "default_format") == "PNG"

        # Update values
        cfg.set("hotkeys", "capture_hotkey", "Ctrl+Shift+S")
        cfg.set("editor", "default_color", "#00FF00")

        # Reload from disk
        cfg2 = ConfigManager(custom_path=config_path)
        assert cfg2.get("hotkeys", "capture_hotkey") == "Ctrl+Shift+S"
        assert cfg2.get("editor", "default_color") == "#00FF00"
        assert cfg2.get("image", "default_format") == "PNG"

        # Reset
        cfg2.reset_to_defaults()
        assert cfg2.get("hotkeys", "capture_hotkey") == "PrintScreen"

