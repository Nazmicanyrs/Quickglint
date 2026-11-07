"""Lifecycle and capture integration tests for SessionManager."""

from PySide6.QtGui import QColor, QImage

from app.session.session_manager import SessionManager


def make_image() -> QImage:
    image = QImage(16, 12, QImage.Format.Format_ARGB32)
    image.fill(QColor("#0EA5E9"))
    return image


def test_manager_does_not_store_images_without_an_active_session(qapp):
    manager = SessionManager()
    assert not manager.add_screenshot(make_image())


def test_manager_creates_sessions_and_keeps_previous_sessions(qapp):
    manager = SessionManager()
    first = manager.create_session("First")
    assert manager.add_screenshot(make_image())

    second = manager.create_session("Second")
    assert manager.active_session is second
    assert len(first.items) == 1
    assert manager.add_screenshot(make_image())
    assert len(manager.sessions) == 2
    assert len(second.items) == 1


def test_close_active_session_preserves_in_memory_history(qapp):
    manager = SessionManager()
    session = manager.create_session()
    manager.add_screenshot(make_image())

    manager.close_session(session)
    assert manager.active_session is None
    assert manager.sessions == [session]

