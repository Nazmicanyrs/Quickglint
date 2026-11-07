"""Local lightweight Share History Manager with zero sensitive data persistence."""

import json
import os
from pathlib import Path
import time
from typing import List, Optional

from app.upload.models import ShareHistoryItem
from app.utils.logger import logger


class ShareHistoryManager:
    """Manages local history of uploaded image links."""

    @classmethod
    def _get_history_file(cls) -> Path:
        import shutil

        appdata = os.environ.get("APPDATA")
        candidates = []
        if appdata:
            candidates.append(Path(appdata) / "Quickglint")
        candidates.append(Path.home() / ".quickglint")
        candidates.append(Path.cwd() / ".quickglint")

        hist_dir = candidates[-1]
        for cand in candidates:
            try:
                cand.mkdir(parents=True, exist_ok=True)
                hist_dir = cand
                break
            except Exception:
                continue

        target = hist_dir / "share_history.json"
        if not target.exists() and appdata:
            legacy_file = Path(appdata) / "Quickglint" / "share_history.json"
            if legacy_file.exists():
                try:
                    shutil.copy2(legacy_file, target)
                except Exception:
                    pass
        return target

    @classmethod
    def get_items(cls) -> List[ShareHistoryItem]:
        """Loads all recorded share history items (most recent first)."""
        file_path = cls._get_history_file()
        if not file_path.exists():
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
                items = [ShareHistoryItem.from_dict(d) for d in raw_list]
                items.sort(key=lambda x: x.timestamp, reverse=True)
                return items
        except Exception as exc:
            logger.error("Failed to read share history: %s", exc)
            return []

    @classmethod
    def add_item(cls, item: ShareHistoryItem) -> None:
        """Appends a new share history item and keeps the latest 100 entries."""
        try:
            items = cls.get_items()
            items.insert(0, item)
            items = items[:100]  # Cap at 100 items

            file_path = cls._get_history_file()
            tmp_path = file_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump([it.to_dict() for it in items], f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            tmp_path.replace(file_path)
        except Exception as exc:
            logger.error("Failed to save share history item: %s", exc)

    @classmethod
    def get_history_file_path(cls) -> Path:
        """Returns the absolute file path to the share history JSON file."""
        return cls._get_history_file()

    @classmethod
    def delete_item(cls, share_url_or_direct_url: str) -> bool:
        """Deletes a share history entry matching the given URL."""
        try:
            items = cls.get_items()
            initial_count = len(items)
            items = [it for it in items if it.share_url != share_url_or_direct_url and it.direct_url != share_url_or_direct_url]
            if len(items) == initial_count:
                return False

            file_path = cls._get_history_file()
            tmp_path = file_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump([it.to_dict() for it in items], f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            tmp_path.replace(file_path)
            return True
        except Exception as exc:
            logger.error("Failed to delete share history item: %s", exc)
            return False

    @classmethod
    def clear_history(cls) -> None:
        """Clears all local share history entries."""
        file_path = cls._get_history_file()
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as exc:
                logger.error("Failed to clear share history: %s", exc)


