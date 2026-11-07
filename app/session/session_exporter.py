"""Background, atomic exporter for screenshot sessions."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, Optional
from uuid import uuid4

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from app.services.storage_service import StorageService
from app.session.session_item import SessionItem


def sanitize_prefix(value: str, default: str = "Screenshot") -> str:
    """Create a portable filename prefix without retaining a path component."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value.strip())
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    return cleaned[:80] or default


def build_export_paths(
    directory: Path,
    prefix: str,
    extension: str,
    indexed_items: Iterable[tuple[int, SessionItem]],
) -> list[tuple[SessionItem, Path]]:
    """Use current session indexes so selected-only exports remain deterministic."""
    safe_prefix = sanitize_prefix(prefix)
    ext = extension.lower().lstrip(".")
    return [(item, directory / f"{safe_prefix}_{index:03d}.{ext}") for index, item in indexed_items]


@dataclass(frozen=True)
class ExportResult:
    written: tuple[Path, ...]
    skipped: tuple[Path, ...]
    cancelled: bool = False
    error: str = ""


class SessionExportWorker(QThread):
    """Writes each QImage off the UI thread and commits it atomically."""

    progress = Signal(int, int, str)
    completed = Signal(object)

    def __init__(
        self,
        export_plan: list[tuple[SessionItem, Path]],
        quality: int = 95,
        collision_policy: str = "rename",
    ) -> None:
        super().__init__()
        self.export_plan = [(item, path) for item, path in export_plan]
        self.quality = max(1, min(100, quality))
        self.collision_policy = collision_policy
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        written: list[Path] = []
        skipped: list[Path] = []
        total = len(self.export_plan)
        try:
            for position, (item, requested_path) in enumerate(self.export_plan, start=1):
                if self._cancelled:
                    self.completed.emit(ExportResult(tuple(written), tuple(skipped), cancelled=True))
                    return
                target = self._resolve_collision(requested_path)
                if target is None:
                    skipped.append(requested_path)
                    self.progress.emit(position, total, requested_path.name)
                    continue
                ok, error = self._save_atomic(item.image, target)
                if not ok:
                    if self._cancelled:
                        self.completed.emit(ExportResult(tuple(written), tuple(skipped), cancelled=True))
                        return
                    self.completed.emit(ExportResult(tuple(written), tuple(skipped), error=error or target.name))
                    return
                written.append(target)
                self.progress.emit(position, total, target.name)
            self.completed.emit(ExportResult(tuple(written), tuple(skipped), cancelled=self._cancelled))
        except Exception as exc:
            self.completed.emit(ExportResult(tuple(written), tuple(skipped), error=str(exc)))

    def _resolve_collision(self, path: Path) -> Optional[Path]:
        if not path.exists() or self.collision_policy == "replace":
            return path
        if self.collision_policy == "skip":
            return None
        counter = 1
        candidate = path
        while candidate.exists():
            candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
            counter += 1
        return candidate

    def _save_atomic(self, image: QImage, destination: Path) -> tuple[bool, str]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = destination.with_name(f".{destination.stem}.{uuid4().hex}.tmp{destination.suffix}")
        try:
            ok, error = StorageService.save_image(image, tmp_path, self.quality)
            if not ok:
                return False, error or "Image could not be encoded."
            if self._cancelled:
                tmp_path.unlink(missing_ok=True)
                return False, "Export cancelled."
            tmp_path.replace(destination)
            return True, ""
        except Exception as exc:
            return False, str(exc)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

