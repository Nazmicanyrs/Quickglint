"""Pure in-memory model for a named, ordered screenshot session."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional
from uuid import uuid4

from PySide6.QtGui import QImage

from app.session.session_item import SessionItem


@dataclass
class ScreenshotSession:
    """An ordered collection of screenshots; it deliberately has no disk cache."""

    name: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    items: list[SessionItem] = field(default_factory=list)
    current_index: int = -1
    is_dirty: bool = False

    @property
    def current_item(self) -> Optional[SessionItem]:
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    @property
    def selected_items(self) -> list[SessionItem]:
        return [item for item in self.items if item.selected]

    def add_image(self, image: QImage, title: str = "") -> SessionItem:
        """Append a valid image and make it the current item."""
        if image.isNull():
            raise ValueError("Cannot add a null image to a screenshot session.")
        item = SessionItem(image=image.copy(), title=title or self._next_title())
        self.items.append(item)
        self.current_index = len(self.items) - 1
        self.is_dirty = True
        return item

    def add_images(self, images: Iterable[tuple[QImage, str]]) -> list[SessionItem]:
        return [self.add_image(image, title) for image, title in images if not image.isNull()]

    def remove(self, index: int) -> Optional[SessionItem]:
        if not 0 <= index < len(self.items):
            return None
        removed = self.items.pop(index)
        if not self.items:
            self.current_index = -1
        else:
            self.current_index = min(index, len(self.items) - 1)
        self.is_dirty = True
        return removed

    def duplicate(self, index: int) -> Optional[SessionItem]:
        if not 0 <= index < len(self.items):
            return None
        item = self.items[index].clone()
        self.items.insert(index + 1, item)
        self.current_index = index + 1
        self.is_dirty = True
        return item

    def reorder(self, old_index: int, new_index: int) -> bool:
        if not 0 <= old_index < len(self.items) or not 0 <= new_index < len(self.items):
            return False
        if old_index == new_index:
            return True
        current_id = self.current_item.id if self.current_item else None
        item = self.items.pop(old_index)
        self.items.insert(new_index, item)
        self.current_index = next((i for i, x in enumerate(self.items) if x.id == current_id), new_index)
        self.is_dirty = True
        return True

    def apply_order(self, item_ids: list[str]) -> bool:
        """Apply an order received from the thumbnail drag-and-drop view."""
        if len(item_ids) != len(self.items) or set(item_ids) != {item.id for item in self.items}:
            return False
        current_id = self.current_item.id if self.current_item else None
        by_id = {item.id: item for item in self.items}
        self.items = [by_id[item_id] for item_id in item_ids]
        self.current_index = next((i for i, item in enumerate(self.items) if item.id == current_id), -1)
        self.is_dirty = True
        return True

    def set_current(self, index: int) -> bool:
        if not 0 <= index < len(self.items):
            return False
        self.current_index = index
        return True

    def set_selected(self, index: int, selected: bool) -> bool:
        if not 0 <= index < len(self.items):
            return False
        self.items[index].selected = selected
        self.is_dirty = True
        return True

    def select_all(self, selected: bool) -> None:
        for item in self.items:
            item.selected = selected
        self.is_dirty = True

    def rename(self, name: str) -> None:
        name = name.strip()
        if name:
            self.name = name
            self.is_dirty = True

    def mark_exported(self) -> None:
        self.is_dirty = False

    def _next_title(self) -> str:
        return f"Screenshot {len(self.items) + 1}"

