"""Storage service for saving screenshot images to disk."""

from pathlib import Path
from typing import Optional, Tuple

from PIL import Image
from PySide6.QtGui import QImage

from app.utils.constants import DEFAULT_JPEG_QUALITY
from app.utils.helpers import generate_timestamp_filename, qimage_to_pil
from app.utils.logger import logger


class StorageService:
    """Handles saving images to disk in PNG, JPEG, and WEBP formats."""

    @staticmethod
    def save_image(
        image: QImage,
        destination_path: Path,
        quality: int = DEFAULT_JPEG_QUALITY,
    ) -> Tuple[bool, Optional[str]]:
        """
        Save QImage to the given destination path.
        Supports .png, .jpg/.jpeg, and .webp extensions.
        Returns (success, error_message).
        """
        try:
            destination_path = Path(destination_path)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            ext = destination_path.suffix.lower()

            pil_img = qimage_to_pil(image)

            if ext in [".jpg", ".jpeg"]:
                # Convert RGBA to RGB for JPEG
                if pil_img.mode in ("RGBA", "LA") or (
                    pil_img.mode == "P" and "transparency" in pil_img.info
                ):
                    bg = Image.new("RGB", pil_img.size, (255, 255, 255))
                    bg.paste(pil_img, mask=pil_img.split()[3])  # 3 is alpha
                    pil_img = bg
                else:
                    pil_img = pil_img.convert("RGB")
                pil_img.save(str(destination_path), format="JPEG", quality=quality, optimize=True)
            elif ext == ".webp":
                pil_img.save(str(destination_path), format="WEBP", quality=quality)
            else:
                # Default PNG
                pil_img.save(str(destination_path), format="PNG", optimize=True)

            logger.info("Successfully saved screenshot to: %s", destination_path)
            return True, None
        except Exception as exc:
            error_msg = f"Failed to save image to {destination_path}: {exc}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg

    @staticmethod
    def get_quick_save_path(
        save_dir: str | Path,
        format_ext: str = "png",
        config_manager: Optional[object] = None,
        metadata: Optional[object] = None,
        template: Optional[str] = None,
    ) -> Path:
        """Generate a safe, collision-free path inside save_dir using SmartNamingService."""
        from app.services.naming_service import CaptureMetadata, SmartNamingService

        meta = metadata if isinstance(metadata, CaptureMetadata) else None
        return SmartNamingService.resolve_safe_path(
            save_dir=save_dir,
            ext=format_ext.lower(),
            template=template,
            metadata=meta,
            config_manager=config_manager,
            increment_counter=True,
        )

