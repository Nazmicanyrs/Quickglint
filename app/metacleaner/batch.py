"""Asynchronous batch metadata cleaner worker thread with cancel and progress reporting."""

from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import QThread, Signal

from app.metacleaner.cleaner import MetadataCleaner
from app.metacleaner.models import CleanConfig, CleanResult
from app.utils.logger import logger


class BatchMetadataCleanerWorker(QThread):
    """Worker thread processing a batch of images asynchronously."""

    progress = Signal(int, int, str)       # current, total, filename
    item_cleaned = Signal(object)           # CleanResult
    finished = Signal(list)                # List[CleanResult]
    error = Signal(str)

    def __init__(
        self,
        file_paths: List[Path],
        config: Optional[CleanConfig] = None,
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self.file_paths = [Path(p) for p in file_paths]
        self.config = config or CleanConfig()
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request worker cancellation."""
        self._is_cancelled = True

    def run(self) -> None:
        """Execute the batch cleaning loop."""
        results: List[CleanResult] = []
        total = len(self.file_paths)

        try:
            for idx, file_path in enumerate(self.file_paths, start=1):
                if self._is_cancelled:
                    break

                self.progress.emit(idx, total, file_path.name)

                res = MetadataCleaner.clean_file(file_path, config=self.config)
                results.append(res)
                self.item_cleaned.emit(res)

            self.finished.emit(results)
        except Exception as exc:
            logger.error("Batch metadata cleaning failed: %s", exc)
            self.error.emit(str(exc))

