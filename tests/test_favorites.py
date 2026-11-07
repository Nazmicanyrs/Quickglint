"""Comprehensive test suite for Quickglint Add to Favorites (Favoriler) subsystem."""

import os
from pathlib import Path
import tempfile
import time
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.favorites.manager import FavoritesManager
from app.favorites.models import FavoriteItem
from app.ui.favorites_dialog import FavoritesDialog
from app.ui.toolbar import FloatingToolbar
from app.utils.i18n import set_language, tr
from config.config_manager import ConfigManager


@pytest.fixture(autouse=True)
def isolated_favorites_env(tmp_path):
    """Isolates the favorites JSON storage for deterministic tests."""
    test_fav_file = tmp_path / "favorites.json"
    with patch.object(FavoritesManager, "get_favorites_file_path", return_value=test_fav_file):
        FavoritesManager.clear_all()
        yield test_fav_file
        FavoritesManager.clear_all()


@pytest.fixture
def dummy_screenshot_files(tmp_path):
    """Creates dummy screenshot image files on disk."""
    files = []
    for i in range(5):
        p = tmp_path / f"Screenshot_20260822_{i:02d}.png"
        img = QImage(300 + i * 50, 200 + i * 30, QImage.Format.Format_RGB32)
        img.fill(QColor(10 + i * 20, 50, 100))
        img.save(str(p))
        files.append(str(p))
    return files


# TEST 01 & 04: Normal screenshot favoriye eklenebilmeli
def test_add_favorite(dummy_screenshot_files):
    f0 = dummy_screenshot_files[0]
    item = FavoritesManager.add_favorite(f0, note="Login page design")

    assert item is not None
    assert item.file_path == f0
    assert item.filename == Path(f0).name
    assert item.note == "Login page design"
    assert item.exists is True
    assert FavoritesManager.is_favorite(f0) is True
    assert len(FavoritesManager.get_items()) == 1


# TEST 02 & 18: Favori screenshot tekrar favoriye eklenmemeli (Duplicate Prevention)
def test_duplicate_favorite_prevention(dummy_screenshot_files):
    f0 = dummy_screenshot_files[0]
    item1 = FavoritesManager.add_favorite(f0)
    item2 = FavoritesManager.add_favorite(f0)

    assert item1.id == item2.id
    assert len(FavoritesManager.get_items()) == 1


# TEST 03 & 16: Favoriden çıkarıldığında gerçek dosya silinmemeli
def test_remove_from_favorites_does_not_delete_file(dummy_screenshot_files):
    f0 = dummy_screenshot_files[0]
    FavoritesManager.add_favorite(f0)
    assert os.path.exists(f0) is True

    removed = FavoritesManager.remove_favorite(f0)
    assert removed is True
    assert FavoritesManager.is_favorite(f0) is False
    assert len(FavoritesManager.get_items()) == 0
    # Crucial: Disk file MUST still exist!
    assert os.path.exists(f0) is True


# TEST 05: Toggle Favorite
def test_toggle_favorite(dummy_screenshot_files):
    f0 = dummy_screenshot_files[0]
    is_fav, success = FavoritesManager.toggle_favorite(f0)
    assert is_fav is True
    assert success is True
    assert FavoritesManager.is_favorite(f0) is True

    is_fav2, success2 = FavoritesManager.toggle_favorite(f0)
    assert is_fav2 is False
    assert success2 is True
    assert FavoritesManager.is_favorite(f0) is False


# TEST 06: Toolbar Favorite Button
def test_toolbar_favorite_button():
    from app.editor.history import HistoryManager
    from app.editor.tools import ToolManager

    tm = ToolManager()
    hm = HistoryManager()
    tb = FloatingToolbar(tool_manager=tm, history_manager=hm)

    assert hasattr(tb, "favorite_btn")
    tb.set_is_favorite(True)
    assert "star_filled" in tb.favorite_btn.toolTip() or tb.favorite_btn.toolTip() != ""
    tb.set_is_favorite(False)
    tb.close()


# TEST 08 & 09: Keyboard Shortcut in Config
def test_keyboard_shortcut_configuration(tmp_path):
    cfg_file = tmp_path / "fav_settings.json"
    cm = ConfigManager(custom_path=cfg_file)
    fav_shortcut = cm.get("hotkeys", "action_favorite", "Ctrl+Shift+F")
    assert fav_shortcut == "Ctrl+Shift+F"

    # Can be modified and saved
    cm.set("hotkeys", "action_favorite", "Ctrl+Alt+F")
    cm.save()

    cm2 = ConfigManager(custom_path=cfg_file)
    assert cm2.get("hotkeys", "action_favorite") == "Ctrl+Alt+F"


# TEST 10: Persistence across reload
def test_favorites_persistence(dummy_screenshot_files):
    f0 = dummy_screenshot_files[0]
    f1 = dummy_screenshot_files[1]
    FavoritesManager.add_favorite(f0, note="First Note")
    FavoritesManager.add_favorite(f1, note="Second Note")

    items = FavoritesManager.get_items()
    assert len(items) == 2
    paths = [it.file_path for it in items]
    assert f0 in paths
    assert f1 in paths


# TEST 12: Search Favorites
def test_favorites_search_filtering(dummy_screenshot_files):
    FavoritesManager.add_favorite(dummy_screenshot_files[0], note="Bug report #123")
    FavoritesManager.add_favorite(dummy_screenshot_files[1], note="Feature dashboard")
    FavoritesManager.add_favorite(dummy_screenshot_files[2], note="Release notes")

    dialog = FavoritesDialog()
    assert len(dialog._filtered_items) == 3

    # Search for "bug"
    dialog.search_edit.setText("bug")
    assert len(dialog._filtered_items) == 1
    assert "00" in dialog._filtered_items[0].filename

    # Search for non-existent
    dialog.search_edit.setText("nonexistent_keyword_xyz")
    assert len(dialog._filtered_items) == 0

    dialog.close()


# TEST 13: Sorting Favorites
def test_favorites_sorting(dummy_screenshot_files):
    t0 = FavoritesManager.add_favorite(dummy_screenshot_files[0])
    time.sleep(0.01)
    t1 = FavoritesManager.add_favorite(dummy_screenshot_files[1])
    time.sleep(0.01)
    t2 = FavoritesManager.add_favorite(dummy_screenshot_files[2])

    dialog = FavoritesDialog()

    # Default Newest first
    dialog.sort_combo.setCurrentIndex(0)
    assert dialog._filtered_items[0].file_path == dummy_screenshot_files[2]

    # Oldest first
    dialog.sort_combo.setCurrentIndex(1)
    assert dialog._filtered_items[0].file_path == dummy_screenshot_files[0]

    # Name A-Z
    dialog.sort_combo.setCurrentIndex(2)
    assert dialog._filtered_items[0].filename <= dialog._filtered_items[1].filename

    dialog.close()


# TEST 14, 15 & 19: Missing file detection and cleanup
def test_missing_file_detection_and_clean(tmp_path):
    p_temp = tmp_path / "temp_screenshot.png"
    img = QImage(100, 100, QImage.Format.Format_RGB32)
    img.save(str(p_temp))

    item = FavoritesManager.add_favorite(str(p_temp))
    assert item.exists is True

    # Delete file from disk externally
    os.remove(str(p_temp))

    # Re-check item exists
    item_reloaded = FavoritesManager.get_item_by_path(str(p_temp))
    assert item_reloaded is not None
    assert item_reloaded.exists is False

    # Clean missing files
    cleaned = FavoritesManager.clean_missing_files()
    assert cleaned == 1
    assert len(FavoritesManager.get_items()) == 0


# TEST 17 & 24: Live Signal and Count Sync
def test_signal_and_count_sync(dummy_screenshot_files):
    dialog = FavoritesDialog()
    assert dialog.count_badge.text() == "0"

    FavoritesManager.add_favorite(dummy_screenshot_files[0])
    assert dialog.count_badge.text() == "1"

    FavoritesManager.add_favorite(dummy_screenshot_files[1])
    assert dialog.count_badge.text() == "2"

    FavoritesManager.remove_favorite(dummy_screenshot_files[0])
    assert dialog.count_badge.text() == "1"

    dialog.close()


# TEST 20: Format Properties
def test_item_format_properties(dummy_screenshot_files):
    f0 = dummy_screenshot_files[0]
    item = FavoritesManager.add_favorite(f0, width=1920, height=1080)
    assert "1920 × 1080 px" == item.formatted_dimensions
    assert "KB" in item.formatted_size or "MB" in item.formatted_size


# TEST 21: Localization
def test_localization_keys():
    set_language("tr")
    assert "Favoriler" in tr("fav_title")
    assert "Favorilere Ekle" in tr("fav_add")

    set_language("en")
    assert "Favorites" in tr("fav_title")
    assert "Add to Favorites" in tr("fav_add")


# TEST 22: Performance with 100+ items
def test_performance_bulk_favorites(tmp_path):
    items = []
    for i in range(120):
        item = FavoriteItem(
            file_path=str(tmp_path / f"Bulk_Screenshot_{i:04d}.png"),
            filename=f"Bulk_Screenshot_{i:04d}.png",
            favorited_at=time.time() - i,
            file_size=1024 * (i + 1),
            width=1920,
            height=1080,
        )
        items.append(item)

    FavoritesManager._save_items(items)
    loaded = FavoritesManager.get_items()
    assert len(loaded) == 120

    dialog = FavoritesDialog()
    assert len(dialog._filtered_items) == 120
    assert dialog.count_badge.text() == "120"
    dialog.close()


# TEST 23: Multi-select remove
def test_multi_select_remove(dummy_screenshot_files):
    dialog = FavoritesDialog()
    FavoritesManager.add_favorite(dummy_screenshot_files[0])
    FavoritesManager.add_favorite(dummy_screenshot_files[1])
    FavoritesManager.add_favorite(dummy_screenshot_files[2])

    items_to_remove = [
        FavoritesManager.get_item_by_path(dummy_screenshot_files[0]),
        FavoritesManager.get_item_by_path(dummy_screenshot_files[1]),
    ]
    dialog._remove_multiple_favorites(items_to_remove)

    assert len(FavoritesManager.get_items()) == 1
    assert FavoritesManager.is_favorite(dummy_screenshot_files[2]) is True
    dialog.close()

