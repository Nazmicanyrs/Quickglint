"""Data models for Quickglint Favorites subsystem."""

from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class FavoriteItem:
    """Represents a favorited screenshot reference with metadata."""

    file_path: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = ""
    created_at: float = field(default_factory=time.time)
    favorited_at: float = field(default_factory=time.time)
    file_size: int = 0
    width: int = 0
    height: int = 0
    tags: List[str] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        if not self.filename and self.file_path:
            self.filename = Path(self.file_path).name

        if self.file_path and os.path.exists(self.file_path):
            try:
                p = Path(self.file_path)
                if self.file_size == 0:
                    self.file_size = p.stat().st_size
                if self.created_at == 0:
                    self.created_at = p.stat().st_ctime
            except Exception:
                pass

    @property
    def exists(self) -> bool:
        """Returns True if the referenced file currently exists on disk."""
        return bool(self.file_path and os.path.exists(self.file_path))

    @property
    def formatted_size(self) -> str:
        """Human-readable file size string."""
        if not self.exists or self.file_size <= 0:
            return "0 KB"
        size_kb = self.file_size / 1024
        if size_kb >= 1024:
            return f"{size_kb / 1024:.2f} MB"
        return f"{size_kb:.1f} KB"

    @property
    def formatted_dimensions(self) -> str:
        """Human-readable resolution string."""
        if self.width > 0 and self.height > 0:
            return f"{self.width} × {self.height} px"
        return ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FavoriteItem to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FavoriteItem":
        """Deserialize FavoriteItem from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            file_path=data.get("file_path", ""),
            filename=data.get("filename", ""),
            created_at=data.get("created_at", time.time()),
            favorited_at=data.get("favorited_at", time.time()),
            file_size=data.get("file_size", 0),
            width=data.get("width", 0),
            height=data.get("height", 0),
            tags=data.get("tags", []),
            note=data.get("note", ""),
        )

