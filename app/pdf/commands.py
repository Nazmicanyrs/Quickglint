"""Command pattern implementations for all undoable/redoable PDF editor operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QImage

from app.pdf.document import (
    CropRect,
    PageBackground,
    PDFDocument,
    PDFImageObject,
    PDFObject,
    PDFPage,
    PDFTextObject,
)
from app.pdf.models import MarginConfig, PageOrientation, PaperSizePreset


class PDFCommand(ABC):
    """Abstract base command."""

    @abstractmethod
    def execute(self) -> None:
        """Execute or re-apply the command."""
        pass

    @abstractmethod
    def undo(self) -> None:
        """Rollback the command."""
        pass

    def description(self) -> str:
        """Short human-readable description for UI undo history menu."""
        return self.__class__.__name__


class AddObjectCommand(PDFCommand):
    """Command for adding an object to a page."""

    def __init__(self, page: PDFPage, obj: PDFObject) -> None:
        self.page = page
        self.obj = obj

    def execute(self) -> None:
        if self.obj not in self.page.objects:
            self.page.add_object(self.obj)

    def undo(self) -> None:
        self.page.remove_object(self.obj)

    def description(self) -> str:
        return f"Add {self.obj.type.value.capitalize()}"


class DeleteObjectCommand(PDFCommand):
    """Command for deleting one or more objects from a page."""

    def __init__(self, page: PDFPage, objects: List[PDFObject]) -> None:
        self.page = page
        self.objects = list(objects)
        self._saved_indices: List[Tuple[PDFObject, int]] = []

    def execute(self) -> None:
        self._saved_indices.clear()
        for o in self.objects:
            if o in self.page.objects:
                idx = self.page.objects.index(o)
                self._saved_indices.append((o, idx))
                self.page.remove_object(o)

    def undo(self) -> None:
        for obj, idx in sorted(self._saved_indices, key=lambda x: x[1]):
            if idx <= len(self.page.objects):
                self.page.objects.insert(idx, obj)
            else:
                self.page.objects.append(obj)
        self.page.invalidate_thumbnail()

    def description(self) -> str:
        return f"Delete {len(self.objects)} Object(s)"


class TransformObjectCommand(PDFCommand):
    """Command for geometric transforms (move, resize, rotate, opacity)."""

    def __init__(
        self,
        page: PDFPage,
        obj: PDFObject,
        old_rect: QRectF,
        new_rect: QRectF,
        old_rotation: float,
        new_rotation: float,
        old_opacity: float = 1.0,
        new_opacity: float = 1.0,
    ) -> None:
        self.page = page
        self.obj = obj
        self.old_rect = old_rect
        self.new_rect = new_rect
        self.old_rotation = old_rotation
        self.new_rotation = new_rotation
        self.old_opacity = old_opacity
        self.new_opacity = new_opacity

    def execute(self) -> None:
        self.obj.rect = self.new_rect
        self.obj.rotation = self.new_rotation
        self.obj.opacity = self.new_opacity
        self.page.invalidate_thumbnail()

    def undo(self) -> None:
        self.obj.rect = self.old_rect
        self.obj.rotation = self.old_rotation
        self.obj.opacity = self.old_opacity
        self.page.invalidate_thumbnail()

    def description(self) -> str:
        return "Transform Object"


class CropImageCommand(PDFCommand):
    """Non-destructive image crop command."""

    def __init__(
        self,
        page: PDFPage,
        image_obj: PDFImageObject,
        old_crop: CropRect,
        new_crop: CropRect,
    ) -> None:
        self.page = page
        self.image_obj = image_obj
        self.old_crop = old_crop
        self.new_crop = new_crop

    def execute(self) -> None:
        self.image_obj.crop = self.new_crop
        self.page.invalidate_thumbnail()

    def undo(self) -> None:
        self.image_obj.crop = self.old_crop
        self.page.invalidate_thumbnail()

    def description(self) -> str:
        return "Crop Image"


class TextEditCommand(PDFCommand):
    """Command for text content or style changes."""

    def __init__(
        self,
        page: PDFPage,
        text_obj: PDFTextObject,
        old_text: str,
        new_text: str,
        old_html: str,
        new_html: str,
        old_styles: Optional[Dict[str, Any]] = None,
        new_styles: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.page = page
        self.text_obj = text_obj
        self.old_text = old_text
        self.new_text = new_text
        self.old_html = old_html
        self.new_html = new_html
        self.old_styles = old_styles or {}
        self.new_styles = new_styles or {}

    def _apply_styles(self, styles: Dict[str, Any]) -> None:
        for k, v in styles.items():
            if hasattr(self.text_obj, k):
                setattr(self.text_obj, k, v)

    def execute(self) -> None:
        self.text_obj.text = self.new_text
        self.text_obj.html = self.new_html
        self._apply_styles(self.new_styles)
        self.page.invalidate_thumbnail()

    def undo(self) -> None:
        self.text_obj.text = self.old_text
        self.text_obj.html = self.old_html
        self._apply_styles(self.old_styles)
        self.page.invalidate_thumbnail()

    def description(self) -> str:
        return "Edit Text"


class LayerOrderCommand(PDFCommand):
    """Command for Z-Index ordering (Bring to Front, Send to Back, etc.)."""

    def __init__(
        self,
        page: PDFPage,
        old_order: List[PDFObject],
        new_order: List[PDFObject],
    ) -> None:
        self.page = page
        self.old_order = list(old_order)
        self.new_order = list(new_order)

    def execute(self) -> None:
        self.page.objects = list(self.new_order)
        for i, o in enumerate(self.page.objects):
            o.z_index = i
        self.page.invalidate_thumbnail()

    def undo(self) -> None:
        self.page.objects = list(self.old_order)
        for i, o in enumerate(self.page.objects):
            o.z_index = i
        self.page.invalidate_thumbnail()

    def description(self) -> str:
        return "Reorder Layers"


class AddPageCommand(PDFCommand):
    """Command for adding a new page."""

    def __init__(self, doc: PDFDocument, page: PDFPage, index: Optional[int] = None) -> None:
        self.doc = doc
        self.page = page
        self.index = index if index is not None else len(doc.pages)

    def execute(self) -> None:
        if self.page not in self.doc.pages:
            self.doc.pages.insert(self.index, self.page)
            self.doc.is_modified = True

    def undo(self) -> None:
        if self.page in self.doc.pages and len(self.doc.pages) > 1:
            self.doc.pages.remove(self.page)
            self.doc.is_modified = True

    def description(self) -> str:
        return "Add Page"


class DeletePageCommand(PDFCommand):
    """Command for deleting a page."""

    def __init__(self, doc: PDFDocument, index: int) -> None:
        self.doc = doc
        self.index = index
        self.page = doc.pages[index] if 0 <= index < len(doc.pages) else None

    def execute(self) -> None:
        if self.page and self.page in self.doc.pages and len(self.doc.pages) > 1:
            self.doc.pages.remove(self.page)
            self.doc.is_modified = True

    def undo(self) -> None:
        if self.page and self.page not in self.doc.pages:
            self.doc.pages.insert(self.index, self.page)
            self.doc.is_modified = True

    def description(self) -> str:
        return f"Delete Page {self.index + 1}"


class DuplicatePageCommand(PDFCommand):
    """Command for duplicating a page."""

    def __init__(self, doc: PDFDocument, index: int) -> None:
        self.doc = doc
        self.index = index
        self._created_page: Optional[PDFPage] = None

    def execute(self) -> None:
        if self._created_page is None:
            self._created_page = self.doc.duplicate_page(self.index)
        elif self._created_page not in self.doc.pages:
            self.doc.pages.insert(self.index + 1, self._created_page)
            self.doc.is_modified = True

    def undo(self) -> None:
        if self._created_page and self._created_page in self.doc.pages and len(self.doc.pages) > 1:
            self.doc.pages.remove(self._created_page)
            self.doc.is_modified = True

    def description(self) -> str:
        return f"Duplicate Page {self.index + 1}"


class ReorderPageCommand(PDFCommand):
    """Command for moving a page."""

    def __init__(self, doc: PDFDocument, from_idx: int, to_idx: int) -> None:
        self.doc = doc
        self.from_idx = from_idx
        self.to_idx = to_idx

    def execute(self) -> None:
        self.doc.move_page(self.from_idx, self.to_idx)

    def undo(self) -> None:
        self.doc.move_page(self.to_idx, self.from_idx)

    def description(self) -> str:
        return "Reorder Pages"


class PageSettingsCommand(PDFCommand):
    """Command for updating page size, orientation, margins, or background."""

    def __init__(
        self,
        page: PDFPage,
        old_paper_size: PaperSizePreset,
        new_paper_size: PaperSizePreset,
        old_orientation: PageOrientation,
        new_orientation: PageOrientation,
        old_custom_size: Tuple[float, float],
        new_custom_size: Tuple[float, float],
        old_margins: MarginConfig,
        new_margins: MarginConfig,
        old_bg: PageBackground,
        new_bg: PageBackground,
    ) -> None:
        self.page = page
        self.old_paper_size = old_paper_size
        self.new_paper_size = new_paper_size
        self.old_orientation = old_orientation
        self.new_orientation = new_orientation
        self.old_custom_size = old_custom_size
        self.new_custom_size = new_custom_size
        self.old_margins = old_margins
        self.new_margins = new_margins
        self.old_bg = old_bg
        self.new_bg = new_bg

    def execute(self) -> None:
        self.page.paper_size = self.new_paper_size
        self.page.orientation = self.new_orientation
        self.page.custom_width_mm, self.page.custom_height_mm = self.new_custom_size
        self.page.margins = self.new_margins
        self.page.background = self.new_bg
        self.page.invalidate_thumbnail()

    def undo(self) -> None:
        self.page.paper_size = self.old_paper_size
        self.page.orientation = self.old_orientation
        self.page.custom_width_mm, self.page.custom_height_mm = self.old_custom_size
        self.page.margins = self.old_margins
        self.page.background = self.old_bg
        self.page.invalidate_thumbnail()

    def description(self) -> str:
        return "Change Page Settings"


class BatchCommand(PDFCommand):
    """Executes a composite list of multiple sub-commands as a single atomic undoable step."""

    def __init__(self, commands: List[PDFCommand], desc: str = "Batch Operation") -> None:
        self.commands = list(commands)
        self._desc = desc

    def execute(self) -> None:
        for cmd in self.commands:
            cmd.execute()

    def undo(self) -> None:
        for cmd in reversed(self.commands):
            cmd.undo()

    def description(self) -> str:
        return self._desc

