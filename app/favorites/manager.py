"""Persistent, centralized Favorites Manager with state synchronization and thumbnail caching."""

import json
import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap

from app.favorites.models import FavoriteItem
from app.utils.logger import logger


class FavoritesSignals(QObject):
    """Central Qt Signal bus for favorites state changes."""

    favorites_changed = Signal()


class FavoritesManager:
    """Centralized manager for persistent favorites, thumbnail caching, and live state sync."""

    _signals = FavoritesSignals()
    _thumbnail_cache: Dict[str, QPixmap] = {}
    _max_cache_size = 200

    @classmethod
    def get_signal_bus(cls) -> FavoritesSignals:
        """Returns the global signal bus for favorites events."""
        return cls._signals

    @classmethod
    def get_favorites_file_path(cls) -> Path:
        """Returns the absolute file path to the favorites JSON file, migrating from Quickglint if present."""
        import shutil

        appdata = os.environ.get("APPDATA")
        candidates = []
        if appdata:
            candidates.append(Path(appdata) / "Quickglint")
        candidates.append(Path.home() / ".quickglint")
        candidates.append(Path.cwd() / ".quickglint")

        fav_dir = candidates[-1]
        for cand in candidates:
            try:
                cand.mkdir(parents=True, exist_ok=True)
                fav_dir = cand
                break
            except Exception:
                continue

        target = fav_dir / "favorites.json"
        if not target.exists() and appdata:
            legacy_file = Path(appdata) / "Quickglint" / "favorites.json"
            if legacy_file.exists():
                try:
                    shutil.copy2(legacy_file, target)
                except Exception:
                    pass
        return target

    @classmethod
    def get_items(cls) -> List[FavoriteItem]:
        """Loads all favorite items sorted by favorited_at descending (newest first)."""
        file_path = cls.get_favorites_file_path()
        if not file_path.exists():
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
                items = [FavoriteItem.from_dict(d) for d in raw_list if isinstance(d, dict)]
                items.sort(key=lambda x: x.favorited_at, reverse=True)
                return items
        except Exception as exc:
            logger.error("Failed to read favorites storage: %s", exc)
            return []

    @classmethod
    def is_favorite(cls, file_path_or_id: str) -> bool:
        """Checks whether a given file path or unique ID is in favorites."""
        if not file_path_or_id:
            return False

        norm_path = os.path.normcase(os.path.abspath(file_path_or_id)) if os.path.isabs(file_path_or_id) else file_path_or_id
        items = cls.get_items()
        for item in items:
            if item.id == file_path_or_id:
                return True
            if item.file_path:
                item_norm = os.path.normcase(os.path.abspath(item.file_path)) if os.path.isabs(item.file_path) else item.file_path
                if item_norm == norm_path:
                    return True
        return False

    @classmethod
    def get_item_by_path(cls, file_path: str) -> Optional[FavoriteItem]:
        """Finds a favorite item by file path."""
        if not file_path:
            return None
        norm_path = os.path.normcase(os.path.abspath(file_path)) if os.path.isabs(file_path) else file_path
        for item in cls.get_items():
            if item.file_path:
                item_norm = os.path.normcase(os.path.abspath(item.file_path)) if os.path.isabs(item.file_path) else item.file_path
                if item_norm == norm_path:
                    return item
        return None

    @classmethod
    def get_item_by_id(cls, item_id: str) -> Optional[FavoriteItem]:
        """Finds a favorite item by ID."""
        for item in cls.get_items():
            if item.id == item_id:
                return item
        return None

    @classmethod
    def add_favorite(
        cls,
        file_path: str,
        note: str = "",
        tags: Optional[List[str]] = None,
        width: int = 0,
        height: int = 0,
    ) -> Optional[FavoriteItem]:
        """
        Adds a screenshot reference to favorites.
        Prevents duplicates (returns existing item if already favorited).
        """
        if not file_path:
            return None

        # Check existing to prevent duplicate
        existing = cls.get_item_by_path(file_path)
        if existing is not None:
            return existing

        # Inspect image dimensions if not provided
        if (width == 0 or height == 0) and os.path.exists(file_path):
            try:
                reader = QImageReader(file_path)
                sz = reader.size()
                if sz.isValid():
                    width = sz.width()
                    height = sz.height()
            except Exception:
                pass

        item = FavoriteItem(
            file_path=file_path,
            filename=Path(file_path).name,
            favorited_at=time.time(),
            width=width,
            height=height,
            tags=tags or [],
            note=note,
        )

        items = cls.get_items()
        items.insert(0, item)

        if cls._save_items(items):
            cls._signals.favorites_changed.emit()
            return item
        return None

    @classmethod
    def remove_favorite(cls, file_path_or_id: str) -> bool:
        """
        Removes an item from favorites.
        IMPORTANT: This ONLY removes the favorite metadata reference and NEVER deletes the file.
        """
        if not file_path_or_id:
            return False

        norm_path = os.path.normcase(os.path.abspath(file_path_or_id)) if os.path.isabs(file_path_or_id) else file_path_or_id
        items = cls.get_items()
        initial_len = len(items)

        def should_keep(it: FavoriteItem) -> bool:
            if it.id == file_path_or_id:
                return False
            if it.file_path:
                it_norm = os.path.normcase(os.path.abspath(it.file_path)) if os.path.isabs(it.file_path) else it.file_path
                if it_norm == norm_path:
                    return False
            return True

        filtered = [it for it in items if should_keep(it)]
        if len(filtered) == initial_len:
            return False

        if cls._save_items(filtered):
            # Clean cache if present
            if file_path_or_id in cls._thumbnail_cache:
                cls._thumbnail_cache.pop(file_path_or_id, None)
            cls._signals.favorites_changed.emit()
            return True
        return False

    @classmethod
    def toggle_favorite(cls, file_path: str, note: str = "") -> Tuple[bool, bool]:
        """
        Toggles the favorite state of a screenshot.
        Returns (is_now_favorite, success).
        """
        if cls.is_favorite(file_path):
            success = cls.remove_favorite(file_path)
            return (False, success)
        else:
            item = cls.add_favorite(file_path, note=note)
            return (True, item is not None)

    @classmethod
    def clean_missing_files(cls) -> int:
        """Removes all favorite entries whose referenced files no longer exist on disk."""
        items = cls.get_items()
        valid = [it for it in items if it.exists]
        removed_count = len(items) - len(valid)
        if removed_count > 0:
            if cls._save_items(valid):
                cls._signals.favorites_changed.emit()
        return removed_count

    @classmethod
    def clear_all(cls) -> None:
        """Clears all favorites."""
        cls._save_items([])
        cls._thumbnail_cache.clear()
        cls._signals.favorites_changed.emit()

    @classmethod
    def get_thumbnail(cls, file_path: str, size: QSize = QSize(160, 110)) -> Optional[QPixmap]:
        """
        Returns a cached or lazily generated thumbnail QPixmap preserving aspect ratio.
        """
        cache_key = f"{file_path}_{size.width()}x{size.height()}"
        if cache_key in cls._thumbnail_cache:
            return cls._thumbnail_cache[cache_key]

        if not file_path or not os.path.exists(file_path):
            return None

        try:
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            # Scale down during decoding for speed & low memory footprint
            reader.setScaledSize(size)
            img = reader.read()
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                if len(cls._thumbnail_cache) >= cls._max_cache_size:
                    cls._thumbnail_cache.clear()
                cls._thumbnail_cache[cache_key] = pix
                return pix
        except Exception as exc:
            logger.error("Failed to generate thumbnail for %s: %s", file_path, exc)

        return None

    @classmethod
    def _save_items(cls, items: List[FavoriteItem]) -> bool:
        """Atomically writes favorite items to disk."""
        try:
            file_path = cls.get_favorites_file_path()
            tmp_path = file_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump([it.to_dict() for it in items], f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            tmp_path.replace(file_path)
            return True
        except Exception as exc:
            logger.error("Failed to save favorites file: %s", exc)
            return False

