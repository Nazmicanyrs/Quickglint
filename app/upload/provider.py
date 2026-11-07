"""Abstract Base Class for image upload and sharing providers."""

from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Tuple, Union

from app.upload.models import UploadRequest, UploadResult


class UploadProvider(ABC):
    """Abstract interface defining standard methods for image hosting integrations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider display name (e.g. 'ImgBB')."""
        pass

    @property
    @abstractmethod
    def max_size_bytes(self) -> int:
        """Maximum file size supported by provider in bytes."""
        pass

    @property
    @abstractmethod
    def supported_formats(self) -> List[str]:
        """List of supported extensions in uppercase, e.g. ['PNG', 'JPEG', 'WEBP', 'GIF']."""
        pass

    @abstractmethod
    def upload(
        self,
        image_bytes_or_request: Union[bytes, UploadRequest],
        file_name: str = "screenshot.png",
        api_key: str = "",
        expiration: Optional[int] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> UploadResult:
        """Uploads image binary or request object to provider and returns UploadResult."""
        pass

    @abstractmethod
    def validate_api_key(self, api_key: str) -> Tuple[bool, str]:
        """Validates API key by testing connectivity against provider endpoint."""
        pass

