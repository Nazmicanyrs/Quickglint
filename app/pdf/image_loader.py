"""Image loader supporting PNG, JPG, WebP, BMP, TIFF, GIF, and Secure Vault memory objects."""

import io
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageSequence
from PySide6.QtGui import QImage

from app.pdf.models import PDFSourceItem
from app.utils.logger import logger


def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Converts a PIL Image object to a PySide6 QImage without temporary disk files."""
    if pil_img.mode != "RGBA" and pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGBA")

    buf = io.BytesIO()
    # Save as uncompressed/fast PNG in volatile RAM
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    qimg = QImage()
    qimg.loadFromData(buf.getvalue(), "PNG")
    return qimg


def load_image_from_file(file_path: Path | str, export_all_gif_frames: bool = False) -> List[PDFSourceItem]:
    """
    Loads one or more PDFSourceItems from a file.
    For animated GIFs, returns either the first frame or multiple items (one per frame).
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Source image file does not exist: {path}")

    filename = path.name
    ext = path.suffix.lower()

    items = []
    try:
        with Image.open(path) as pil_img:
            # Handle animated GIF
            if ext == ".gif" and getattr(pil_img, "is_animated", False):
                if export_all_gif_frames:
                    for idx, frame in enumerate(ImageSequence.Iterator(pil_img)):
                        frame_rgba = frame.convert("RGBA")
                        qimg = pil_to_qimage(frame_rgba)
                        item = PDFSourceItem(title=f"{filename} (Frame {idx+1})", qimage=qimg)
                        items.append(item)
                    return items
                else:
                    # Single first frame
                    pil_img.seek(0)
                    qimg = pil_to_qimage(pil_img)
                    return [PDFSourceItem(title=filename, file_path=path, qimage=qimg)]

            # Normal image (PNG, JPG, WebP, BMP, TIFF)
            qimg = pil_to_qimage(pil_img)
            items.append(PDFSourceItem(title=filename, file_path=path, qimage=qimg))
            return items
    except Exception as exc:
        logger.error("Failed to load image '%s': %s", path, exc)
        raise ValueError(f"Corrupted or unsupported image file: {path.name}") from exc


def create_source_from_qimage(image: QImage, title: str = "Screenshot") -> PDFSourceItem:
    """Creates a PDFSourceItem from an active in-memory QImage."""
    return PDFSourceItem(title=title, qimage=image.copy())

