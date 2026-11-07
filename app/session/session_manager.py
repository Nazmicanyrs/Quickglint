"""Qt-friendly lifecycle manager for transient screenshot sessions."""

from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

from app.session.screenshot_session import ScreenshotSession


class SessionManager(QObject):
    """Owns in-memory sessions and exposes the currently recording session."""

    session_created = Signal(object)
    session_changed = Signal(object)
    active_session_changed = Signal(object)
    session_closed = Signal(object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.sessions: list[ScreenshotSession] = []
        self._active_session: Optional[ScreenshotSession] = None
        self._session_counter = 0

    @property
    def active_session(self) -> Optional[ScreenshotSession]:
        return self._active_session

    def create_session(self, name: str = "") -> ScreenshotSession:
        self._session_counter += 1
        session = ScreenshotSession(name=name.strip() or f"Screenshot Session {self._session_counter}")
        self.sessions.append(session)
        self._active_session = session
        self.session_created.emit(session)
        self.active_session_changed.emit(session)
        return session

    def add_screenshot(self, image: QImage, title: str = "") -> bool:
        """Add a captured image only when a session is actively recording."""
        if self._active_session is None or image.isNull():
            return False
        self._active_session.add_image(image, title)
        self.session_changed.emit(self._active_session)
        return True

    def notify_changed(self, session: ScreenshotSession) -> None:
        if session in self.sessions:
            self.session_changed.emit(session)

    def close_session(self, session: Optional[ScreenshotSession] = None) -> None:
        target = session or self._active_session
        if target is None:
            return
        if target is self._active_session:
            self._active_session = None
            self.active_session_changed.emit(None)
        self.session_closed.emit(target)

