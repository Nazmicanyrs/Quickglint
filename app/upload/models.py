"""Data models, request structures, and expiration presets for Upload & Share subsystem."""

from dataclasses import asdict, dataclass
import time
from typing import Any, Dict, Optional

# Constants
IMGBB_MAX_IMAGE_SIZE = 32 * 1024 * 1024  # 32 MB ImgBB size limit
IMGBB_UPLOAD_ENDPOINT = "https://api.imgbb.com/1/upload"
UPLOAD_TIMEOUT = 30

EXPIRATION_OPTIONS: Dict[str, Optional[int]] = {
    "Provider Default (Never)": None,
    "1 minute (60s)": 60,
    "1 hour (3600s)": 3600,
    "1 day (86400s)": 86400,
    "7 days (604800s)": 604800,
    "30 days (2592000s)": 2592000,
    "180 days (15552000s)": 15552000,
}


@dataclass
class UploadRequest:
    """Encapsulates arguments for an image upload operation."""

    image_bytes: bytes
    file_name: str = "screenshot.png"
    api_key: str = ""
    expiration: Optional[int] = None


@dataclass
class UploadResult:
    """Encapsulates the structured response from an image hosting provider."""

    success: bool
    direct_url: str = ""
    share_url: str = ""
    delete_url: str = ""
    provider_name: str = "ImgBB"
    error_msg: str = ""
    status_code: int = 200
    file_name: str = ""
    size_bytes: int = 0
    width: int = 0
    height: int = 0
    elapsed_sec: float = 0.0
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class ShareHistoryItem:
    """Lightweight metadata log entry for locally tracked uploads."""

    timestamp: float
    provider: str
    direct_url: str
    share_url: str
    delete_url: str = ""
    title: str = "Screenshot"
    size_bytes: int = 0
    expiration: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShareHistoryItem":
        return cls(
            timestamp=data.get("timestamp", time.time()),
            provider=data.get("provider", "ImgBB"),
            direct_url=data.get("direct_url", ""),
            share_url=data.get("share_url", ""),
            delete_url=data.get("delete_url", ""),
            title=data.get("title", "Screenshot"),
            size_bytes=data.get("size_bytes", 0),
            expiration=data.get("expiration"),
        )

