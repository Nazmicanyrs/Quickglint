"""A single in-memory image belonging to a screenshot session."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from PySide6.QtGui import QImage


@dataclass
class SessionItem:
    """A session image and its transient gallery state.

    ``QImage.copy`` is used when creating/duplicating items so an overlay or a
    caller cannot mutate the version owned by the session afterwards.
    """

    image: QImage
    title: str = ""
    selected: bool = True
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

    def clone(self) -> "SessionItem":
        """Return an independent duplicate, preserving the selection state."""
        suffix = " Copy" if self.title else "Screenshot Copy"
        return SessionItem(
            image=self.image.copy(),
            title=f"{self.title}{suffix}",
            selected=self.selected,
        )

