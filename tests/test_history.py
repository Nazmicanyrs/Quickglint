"""Tests for HistoryManager and Undo/Redo command stack."""

from PySide6.QtCore import QPoint, QRect
from app.editor.history import AddObjectCommand, HistoryManager, RemoveObjectCommand
from app.editor.objects import ArrowObject, RectangleObject


def test_history_undo_redo():
    history = HistoryManager()
    objects = []

    assert not history.can_undo()
    assert not history.can_redo()

    rect_obj = RectangleObject(QRect(10, 10, 50, 50), color="#FF0000")
    cmd1 = AddObjectCommand(objects, rect_obj)
    history.execute_command(cmd1)

    assert len(objects) == 1
    assert history.can_undo()
    assert not history.can_redo()

    arrow_obj = ArrowObject(QPoint(0, 0), QPoint(100, 100), color="#00FF00")
    cmd2 = AddObjectCommand(objects, arrow_obj)
    history.execute_command(cmd2)

    assert len(objects) == 2
    assert objects[1] == arrow_obj

    # Undo second command
    success = history.undo()
    assert success is True
    assert len(objects) == 1
    assert objects[0] == rect_obj
    assert history.can_redo()

    # Redo second command
    success = history.redo()
    assert success is True
    assert len(objects) == 2
    assert objects[1] == arrow_obj

    # Undo all
    history.undo()
    history.undo()
    assert len(objects) == 0
    assert not history.can_undo()
    assert history.can_redo()


def test_remove_object_command():
    history = HistoryManager()
    rect_obj = RectangleObject(QRect(0, 0, 10, 10))
    objects = [rect_obj]

    remove_cmd = RemoveObjectCommand(objects, rect_obj)
    history.execute_command(remove_cmd)

    assert len(objects) == 0

    history.undo()
    assert len(objects) == 1
    assert objects[0] == rect_obj

