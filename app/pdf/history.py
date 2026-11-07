"""Undo/Redo History Manager for PDF Workspace."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from app.pdf.commands import PDFCommand
from app.utils.logger import logger


class PDFHistoryManager(QObject):
    """Manages the undo and redo stacks for PDF document editing."""

    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)
    history_changed = Signal()

    def __init__(self, max_depth: int = 100, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.max_depth: int = max_depth
        self._undo_stack: List[PDFCommand] = []
        self._redo_stack: List[PDFCommand] = []

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def push(self, command: PDFCommand) -> None:
        """Executes a command and pushes it onto the undo stack."""
        try:
            command.execute()
            self._undo_stack.append(command)
            if len(self._undo_stack) > self.max_depth:
                self._undo_stack.pop(0)

            self._redo_stack.clear()
            self._emit_state()
            logger.debug("PDF Command pushed: %s", command.description())
        except Exception as exc:
            logger.error("Failed to execute command %s: %s", command.description(), exc)

    def record_without_execute(self, command: PDFCommand) -> None:
        """Adds a command that has already been executed in place."""
        self._undo_stack.append(command)
        if len(self._undo_stack) > self.max_depth:
            self._undo_stack.pop(0)

        self._redo_stack.clear()
        self._emit_state()

    def undo(self) -> bool:
        """Undoes the most recent command."""
        if not self.can_undo:
            return False

        cmd = self._undo_stack.pop()
        try:
            cmd.undo()
            self._redo_stack.append(cmd)
            self._emit_state()
            logger.debug("PDF Undid: %s", cmd.description())
            return True
        except Exception as exc:
            logger.error("Error during undo of %s: %s", cmd.description(), exc)
            return False

    def redo(self) -> bool:
        """Redoes the most recently undone command."""
        if not self.can_redo:
            return False

        cmd = self._redo_stack.pop()
        try:
            cmd.execute()
            self._undo_stack.append(cmd)
            self._emit_state()
            logger.debug("PDF Redid: %s", cmd.description())
            return True
        except Exception as exc:
            logger.error("Error during redo of %s: %s", cmd.description(), exc)
            return False

    def clear(self) -> None:
        """Clears all history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._emit_state()

    def get_undo_description(self) -> Optional[str]:
        if self._undo_stack:
            return self._undo_stack[-1].description()
        return None

    def get_redo_description(self) -> Optional[str]:
        if self._redo_stack:
            return self._redo_stack[-1].description()
        return None

    def _emit_state(self) -> None:
        self.can_undo_changed.emit(self.can_undo)
        self.can_redo_changed.emit(self.can_redo)
        self.history_changed.emit()

