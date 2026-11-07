"""Asynchronous background worker for multi-file batch image optimization."""

import os
from pathlib import Path
import time
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, Signal

from app.optimizer.engine import ImageOptimizer
from app.optimizer.models import OptimizationResult, OptimizerConfig, OutputFormat
from app.utils.logger import logger


class BatchOptimizerWorker(QThread):
    """Processes multiple image files sequentially in the background without blocking the UI."""

    progress = Signal(int, int, str)  # (current, total, filename)
    file_completed = Signal(str, object)  # (filename, OptimizationResult)
    batch_finished = Signal(int, float)  # (total_saved_bytes, total_elapsed_sec)
    failed = Signal(str, str)  # (filename, error_msg)

    def __init__(
        self,
        file_paths: List[Path | str],
        config: OptimizerConfig,
        output_dir: Optional[Path | str] = None,
        suffix: str = "_optimized",
        overwrite: bool = False,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.file_paths = [Path(p) for p in file_paths]
        self.config = config
        self.output_dir = Path(output_dir) if output_dir else None
        self.suffix = suffix
        self.overwrite = overwrite
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        optimizer = ImageOptimizer()
        total_files = len(self.file_paths)
        total_saved_bytes = 0
        t0 = time.time()

        for idx, src_path in enumerate(self.file_paths):
            if self._is_cancelled:
                logger.info("Batch optimization cancelled by user.")
                break

            filename = src_path.name
            self.progress.emit(idx + 1, total_files, filename)

            try:
                if not src_path.exists():
                    raise FileNotFoundError(f"File not found: {src_path}")

                res = optimizer.optimize(src_path, self.config)

                # Determine destination path
                ext = f".{res.format_name.lower()}"
                if ext == ".jpeg":
                    ext = ".jpg"

                if self.output_dir:
                    out_dir = self.output_dir
                    out_dir.mkdir(parents=True, exist_ok=True)
                    dest_path = out_dir / f"{src_path.stem}{self.suffix}{ext}"
                elif self.overwrite:
                    dest_path = src_path.with_suffix(ext)
                else:
                    dest_path = src_path.parent / f"{src_path.stem}{self.suffix}{ext}"

                # Write optimized bytes
                tmp_dest = dest_path.with_suffix(dest_path.suffix + ".tmp")
                with open(tmp_dest, "wb") as f:
                    f.write(res.optimized_bytes)
                    f.flush()
                    os.fsync(f.fileno())

                tmp_dest.replace(dest_path)

                saved = max(0, res.original_size_bytes - res.optimized_size_bytes)
                total_saved_bytes += saved
                self.file_completed.emit(filename, res)

            except Exception as exc:
                logger.error("Batch optimize failed for '%s': %s", src_path, exc)
                self.failed.emit(filename, str(exc))

        elapsed = time.time() - t0
        self.batch_finished.emit(total_saved_bytes, elapsed)

