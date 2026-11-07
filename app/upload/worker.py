"""Asynchronous QThread worker for non-blocking image uploading."""

from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

from app.upload.models import UploadRequest, UploadResult
from app.upload.provider import UploadProvider


class UploadWorker(QThread):
    """Executes network upload operations in the background without blocking the UI thread."""

    progress = Signal(int)  # 0..100 percentage
    finished = Signal(object)  # UploadResult

    def __init__(
        self,
        image_bytes: bytes,
        file_name: str,
        provider: UploadProvider,
        api_key: str,
        expiration: Optional[int] = None,
        clean_metadata: bool = True,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.image_bytes = image_bytes
        self.file_name = file_name
        self.provider = provider
        self.api_key = api_key
        self.expiration = expiration
        self.clean_metadata = clean_metadata
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        self.progress.emit(20)

        img_to_upload = self.image_bytes
        if self.clean_metadata:
            try:
                from app.metacleaner.cleaner import MetadataCleaner
                from app.metacleaner.models import CleanConfig, CleaningPreset
                cleaned_bytes, _ = MetadataCleaner.clean_bytes(
                    self.image_bytes,
                    config=CleanConfig(preset=CleaningPreset.PRIVACY_CLEAN),
                )
                img_to_upload = cleaned_bytes
            except Exception:
                pass

        self.progress.emit(40)
        req = UploadRequest(
            image_bytes=img_to_upload,
            file_name=self.file_name,
            api_key=self.api_key,
            expiration=self.expiration,
        )
        res = self.provider.upload(
            image_bytes_or_request=req,
            is_cancelled=lambda: self._is_cancelled,
        )
        self.progress.emit(100)
        self.finished.emit(res)

