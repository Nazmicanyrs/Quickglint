"""Command pattern history system for unlimited Undo/Redo."""

from abc import ABC, abstractmethod
from typing import List, Optional
from PySide6.QtCore import QObject, Signal
from app.editor.objects import CanvasObject


class Command(ABC):
    """Abstract base command."""

    @abstractmethod
    def execute(self) -> None:
        """Execute command."""
        pass

    @abstractmethod
    def undo(self) -> None:
        """Undo command."""
        pass


class AddObjectCommand(Command):
    """Command for adding an annotation object to the canvas."""

    def __init__(self, target_list: List[CanvasObject], obj: CanvasObject) -> None:
        self.target_list = target_list
        self.obj = obj

    def execute(self) -> None:
        if self.obj not in self.target_list:
            self.target_list.append(self.obj)

    def undo(self) -> None:
        if self.obj in self.target_list:
            self.target_list.remove(self.obj)


class RemoveObjectCommand(Command):
    """Command for removing an annotation object from the canvas."""

    def __init__(self, target_list: List[CanvasObject], obj: CanvasObject) -> None:
        self.target_list = target_list
        self.obj = obj
        self.index = -1

    def execute(self) -> None:
        if self.obj in self.target_list:
            self.index = self.target_list.index(self.obj)
            self.target_list.remove(self.obj)

    def undo(self) -> None:
        if self.index >= 0 and self.index <= len(self.target_list):
            self.target_list.insert(self.index, self.obj)
        else:
            self.target_list.append(self.obj)


class HistoryManager(QObject):
    """Manages command stacks for Undo and Redo operations."""

    history_changed = Signal(bool, bool)  # (can_undo, can_redo)

    def __init__(self, max_depth: int = 50, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.max_depth = max_depth
        self.undo_stack: List[Command] = []
        self.redo_stack: List[Command] = []

    def execute_command(self, command: Command) -> None:
        """Execute a new command and append to undo stack."""
        command.execute()
        self.undo_stack.append(command)
        if len(self.undo_stack) > self.max_depth:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self._emit_change()

    def undo(self) -> bool:
        """Undo the last command."""
        if not self.can_undo():
            return False

        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)
        self._emit_change()
        return True

    def redo(self) -> bool:
        """Redo the last undone command."""
        if not self.can_redo():
            return False

        command = self.redo_stack.pop()
        command.execute()
        self.undo_stack.append(command)
        self._emit_change()
        return True

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def clear(self) -> None:
        """Clear all undo/redo history."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._emit_change()

    def _emit_change(self) -> None:
        self.history_changed.emit(self.can_undo(), self.can_redo())

