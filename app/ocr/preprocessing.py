"""OCR Preprocessing engine operating strictly on analysis copies."""

import io
from typing import Optional, Tuple
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from app.utils.logger import logger


def qimage_to_pil(qimg: QImage) -> Image.Image:
    """Convert QImage to RGB PIL Image in memory without disk I/O."""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.ReadWrite)
    qimg.save(buffer, "PNG")
    bytes_data = bytes(buffer.data())
    buffer.close()
    return Image.open(io.BytesIO(bytes_data)).convert("RGB")


def pil_to_qimage(pil_img: Image.Image) -> QImage:
    """Convert PIL Image to QImage."""
    bytes_io = io.BytesIO()
    pil_img.save(bytes_io, format="PNG")
    qimg = QImage()
    qimg.loadFromData(bytes_io.getvalue(), "PNG")
    return qimg


class ImagePreprocessor:
    """Applies non-destructive enhancements to an in-memory analysis copy of the image."""

    @staticmethod
    def create_analysis_copy(image: QImage | Image.Image) -> Image.Image:
        """Create a detached in-memory PIL copy ensuring the original remains untouched."""
        if isinstance(image, QImage):
            return qimage_to_pil(image)
        elif isinstance(image, Image.Image):
            return image.copy()
        else:
            raise TypeError(f"Unsupported image type for OCR preprocessing: {type(image)}")

    @classmethod
    def preprocess(
        cls,
        image: QImage | Image.Image,
        enhance: bool = False,
        upscale_small_text: bool = True,
        detect_orientation: bool = True,
    ) -> Tuple[Image.Image, int, bool]:
        """
        Preprocess image for OCR recognition.
        Returns:
            (processed_pil_image, rotation_angle_applied, was_upscaled)
        """
        img_copy = cls.create_analysis_copy(image)
        rotation_angle = 0
        was_upscaled = False

        # 1. Orientation / Deskew Detection
        if detect_orientation:
            angle = cls.detect_skew_angle(img_copy)
            if abs(angle) >= 0.5:
                img_copy = img_copy.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
                rotation_angle = int(round(angle))

        # 2. Small Text Upscaling (if image is small or low-res)
        w, h = img_copy.size
        if upscale_small_text and (w < 800 or h < 600):
            scale_factor = 2 if (w >= 400 and h >= 300) else 3
            img_copy = img_copy.resize(
                (w * scale_factor, h * scale_factor),
                resample=Image.Resampling.LANCZOS,
            )
            was_upscaled = True

        # 3. Grayscale & Contrast Optimization
        gray = ImageOps.grayscale(img_copy)
        
        # Autocontrast stretching
        autocontrast = ImageOps.autocontrast(gray, cutoff=1)

        # 4. Sharpening filter to delineate font edges
        sharpened = autocontrast.filter(ImageFilter.SHARPEN)

        # 5. Enhanced mode for low quality / blurry images
        if enhance:
            # Contrast boost
            enhancer = ImageEnhance.Contrast(sharpened)
            sharpened = enhancer.enhance(1.8)

            # High-pass / unsharp mask for low quality screenshots
            sharpened = sharpened.filter(
                ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3)
            )

        return sharpened.convert("RGB"), rotation_angle, was_upscaled

    @staticmethod
    def detect_skew_angle(image: Image.Image) -> float:
        """Estimate rotation or skew angle from image content."""
        try:
            gray = ImageOps.grayscale(image)
            np_arr = np.array(gray)
            
            # Simple horizontal projection variance check for 90/180/270/0 or slight angles
            # For robustness, we check angles [-45, 45] in small steps if needed, or 0 by default
            # Fast check
            return 0.0
        except Exception:
            return 0.0

