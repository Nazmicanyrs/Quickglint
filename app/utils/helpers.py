"""Helper functions for image processing, geometry, and utility functions."""

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageFilter
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QImage, QPixmap


def get_default_screenshots_dir() -> Path:
    """Return default folder for saving screenshots in User's Pictures/Screenshots or Desktop."""
    pictures_dir = Path.home() / "Pictures" / "Screenshots"
    if not pictures_dir.exists():
        try:
            pictures_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pictures_dir = Path.home() / "Desktop"
    return pictures_dir


def generate_timestamp_filename(prefix: str = "Quickglint", ext: str = "png") -> str:
    """Generate a clean timestamped filename: Quickglint_YYYY-MM-DD_HH-MM-SS.ext"""
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    clean_ext = ext.lstrip(".")
    return f"{prefix}_{timestamp}.{clean_ext}"


def qimage_to_pil(qimage: QImage) -> Image.Image:
    """Convert a QImage to a PIL Image (RGB or RGBA) safely and quickly across all Qt/Python versions."""
    if qimage.isNull() or qimage.width() <= 0 or qimage.height() <= 0:
        return Image.new("RGBA", (1, 1))
    converted = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
    width = converted.width()
    height = converted.height()

    try:
        ptr = converted.constBits()
        return Image.frombuffer("RGBA", (width, height), bytes(ptr), "raw", "RGBA", 0, 1).copy()
    except Exception:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        qba = QByteArray()
        buf = QBuffer(qba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        converted.save(buf, "PNG")
        return Image.open(BytesIO(bytes(qba))).convert("RGBA")


def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Convert a PIL Image to a QImage."""
    if pil_img.mode != "RGBA":
        pil_img = pil_img.convert("RGBA")
    
    data = pil_img.tobytes("raw", "RGBA")
    qimg = QImage(data, pil_img.width, pil_img.height, pil_img.width * 4, QImage.Format.Format_RGBA8888)
    return qimg.copy()


def apply_blur_to_region(base_image: QImage, rect: QRect, radius: int = 15) -> QImage:
    """Apply Gaussian blur to a specific rectangular region of a QImage."""
    if base_image.isNull():
        return base_image
    norm_rect = normalize_rect(rect)
    clipped_rect = norm_rect.intersected(QRect(0, 0, base_image.width(), base_image.height()))
    if clipped_rect.isEmpty() or clipped_rect.width() <= 0 or clipped_rect.height() <= 0:
        return base_image

    radius = max(1, radius)
    # Crop region
    sub_qimage = base_image.copy(clipped_rect)
    pil_sub = qimage_to_pil(sub_qimage)
    
    # Blur sub-image
    blurred_sub = pil_sub.filter(ImageFilter.GaussianBlur(radius=radius))
    blurred_qimage = pil_to_qimage(blurred_sub)

    # Composite back onto a copy of the base image
    result = base_image.copy()
    from PySide6.QtGui import QPainter
    painter = QPainter(result)
    try:
        painter.drawImage(clipped_rect.topLeft(), blurred_qimage)
    finally:
        painter.end()
    return result


def apply_pixelate_to_region(base_image: QImage, rect: QRect, pixel_size: int = 12) -> QImage:
    """Apply pixelate/mosaic filter to a specific rectangular region of a QImage."""
    if base_image.isNull():
        return base_image
    norm_rect = normalize_rect(rect)
    clipped_rect = norm_rect.intersected(QRect(0, 0, base_image.width(), base_image.height()))
    if clipped_rect.isEmpty() or clipped_rect.width() <= 0 or clipped_rect.height() <= 0:
        return base_image

    pixel_size = max(2, pixel_size)
    sub_qimage = base_image.copy(clipped_rect)
    pil_sub = qimage_to_pil(sub_qimage)

    w, h = pil_sub.size
    small_w = max(1, w // pixel_size)
    small_h = max(1, h // pixel_size)

    # Downscale and upscale with nearest neighbor
    small = pil_sub.resize((small_w, small_h), resample=Image.Resampling.NEAREST)
    pixelated = small.resize((w, h), resample=Image.Resampling.NEAREST)

    pixelated_qimage = pil_to_qimage(pixelated)

    result = base_image.copy()
    from PySide6.QtGui import QPainter
    painter = QPainter(result)
    try:
        painter.drawImage(clipped_rect.topLeft(), pixelated_qimage)
    finally:
        painter.end()
    return result


def normalize_rect(rect: QRect) -> QRect:
    """Return a normalized QRect where width and height are positive."""
    return rect.normalized()


def clamp(val: int, min_val: int, max_val: int) -> int:
    """Clamp an integer value between min_val and max_val."""
    return max(min_val, min(val, max_val))


def open_folder_in_file_manager(folder_path: str) -> None:
    """Open folder in Windows Explorer, macOS Finder, or Linux file manager."""
    import os
    import sys
    import subprocess
    from pathlib import Path

    p = Path(folder_path)
    if not p.exists():
        p.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        os.startfile(str(p))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(p)], check=False)
    else:
        subprocess.run(["xdg-open", str(p)], check=False)


def get_app_icon() -> "QIcon":
    """Return the application QIcon containing all embedded resolutions (16x16 up to 256x256)."""
    import sys
    from pathlib import Path
    from PySide6.QtGui import QIcon

    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))
    ico_path = base_dir / "assets" / "icons" / "quickglint.ico"
    png_path = base_dir / "assets" / "icons" / "quickglint.png"

    if ico_path.exists():
        return QIcon(str(ico_path))
    elif png_path.exists():
        return QIcon(str(png_path))

    from app.ui.styles import get_icon
    return get_icon("camera", "#6366F1", 32)



