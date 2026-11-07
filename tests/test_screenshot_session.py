"""Unit tests for the in-memory ScreenshotSession model."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from app.session.screenshot_session import ScreenshotSession


def make_image(color: str = "#2563EB") -> QImage:
    image = QImage(24, 18, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    return image


def test_new_session_is_empty():
    session = ScreenshotSession("Tutorial")
    assert session.items == []
    assert session.current_item is None
    assert session.current_index == -1


def test_add_duplicate_delete_and_navigation_state():
    session = ScreenshotSession("Tutorial")
    first = session.add_image(make_image(), "First")
    second = session.add_image(make_image("#16A34A"), "Second")

    assert session.current_item is second
    copied = session.duplicate(0)
    assert copied is not None
    assert [item.title for item in session.items] == ["First", "First Copy", "Second"]
    assert copied.image is not first.image

    removed = session.remove(1)
    assert removed is copied
    assert [item.title for item in session.items] == ["First", "Second"]
    assert session.current_index == 1


def test_reorder_and_selection_are_preserved():
    session = ScreenshotSession("Tutorial")
    for title in ("One", "Two", "Three"):
        session.add_image(make_image(), title)
    session.set_current(1)
    session.set_selected(1, False)

    assert session.reorder(2, 0)
    assert [item.title for item in session.items] == ["Three", "One", "Two"]
    assert session.current_item.title == "Two"
    assert [item.title for item in session.selected_items] == ["Three", "One"]


def test_drag_drop_order_validation_rejects_missing_ids():
    session = ScreenshotSession("Tutorial")
    first = session.add_image(make_image())
    second = session.add_image(make_image())

    assert not session.apply_order([first.id])
    assert session.apply_order([second.id, first.id])
    assert session.items[0] is second

