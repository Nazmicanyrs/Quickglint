"""Data models for Smart Window Capture subsystem."""

from dataclasses import dataclass, field
from typing import Optional
from PySide6.QtCore import QRect


@dataclass
class BrowserWindowInfo:
    """Represents detected browser window metadata and exact physical bounds."""

    hwnd: int
    title: str = ""
    process_name: str = ""
    process_id: int = 0
    display_name: str = "Web Browser"
    bounds: QRect = field(default_factory=QRect)
    is_maximized: bool = False
    is_valid: bool = True

    @property
    def formatted_title(self) -> str:
        """Returns short display label for overlay badge."""
        clean_title = self.title.strip()
        if not clean_title:
            return self.display_name
        if len(clean_title) > 36:
            clean_title = clean_title[:33] + "..."
        return f"{self.display_name} — {clean_title}"

    @property
    def formatted_dimensions(self) -> str:
        """Resolution formatted string."""
        if self.bounds.isValid() and not self.bounds.isEmpty():
            return f"{self.bounds.width()} × {self.bounds.height()} px"
        return ""

