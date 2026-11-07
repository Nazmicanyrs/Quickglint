"""Autosave and project crash recovery manager for PDF projects."""

from __future__ import annotations

import getpass
import json
from pathlib import Path
import tempfile
import time
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from app.pdf.document import PDFDocument
from app.utils.logger import logger


class PDFAutosaveManager(QObject):
    """Periodically saves active PDF project to a recovery backup file."""

    backup_saved = Signal(str)

    AUTOSAVE_INTERVAL_MS = 30000  # 30 seconds

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setInterval(self.AUTOSAVE_INTERVAL_MS)
        self.timer.timeout.connect(self._on_autosave_timer)

        self._active_doc: Optional[PDFDocument] = None
        # Per-user directory (not the shared temp root) so other users/instances
        # cannot read or overwrite the recovery file.
        backup_dir = Path(tempfile.gettempdir()) / f"quickglint_autosave_{getpass.getuser()}"
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            backup_dir = Path(tempfile.gettempdir())
        self._backup_path: Path = backup_dir / "quickglint_pdf_autosave.quickglintpdf"

    def start(self, doc: PDFDocument) -> None:
        self._active_doc = doc
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def clear_recovery(self) -> None:
        if self._backup_path.exists():
            try:
                self._backup_path.unlink()
            except Exception:
                pass

    def has_recovery_project(self) -> bool:
        return self._backup_path.exists() and self._backup_path.stat().st_size > 50

    def recover_project(self) -> Optional[PDFDocument]:
        if self.has_recovery_project():
            try:
                doc = PDFDocument.load_project(self._backup_path)
                logger.info("Successfully recovered unsaved project from %s", self._backup_path)
                return doc
            except Exception as exc:
                logger.error("Failed to recover project: %s", exc)
        return None

    def _on_autosave_timer(self) -> None:
        if self._active_doc and self._active_doc.is_modified:
            try:
                self._active_doc.save_project(self._backup_path)
                self.backup_saved.emit(str(self._backup_path))
                logger.debug("Autosaved project to %s", self._backup_path)
            except Exception as exc:
                logger.warning("Autosave failed: %s", exc)

