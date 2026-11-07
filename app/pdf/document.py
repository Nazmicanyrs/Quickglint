"""Professional PDF Document Model with hierarchical pages, layers, and non-destructive objects."""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from enum import Enum
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QTransform

from app.pdf.geometry import (
    MM_PER_INCH,
    POINTS_PER_INCH,
    get_paper_dimensions_mm,
    mm_to_pt,
    pt_to_mm,
)
from app.pdf.models import (
    FitMode,
    HeaderFooterConfig,
    MarginConfig,
    MetadataConfig,
    PageNumberPosition,
    PageOrientation,
    PaperSizePreset,
    QualityLevel,
)
from app.utils.logger import logger


class ObjectType(str, Enum):
    IMAGE = "image"
    TEXT = "text"
    SHAPE = "shape"
    SIGNATURE = "signature"
    ANNOTATION = "annotation"
    LINK = "link"
    COMMENT = "comment"


class ShapeType(str, Enum):
    RECTANGLE = "rectangle"
    ROUNDED_RECT = "rounded_rect"
    CIRCLE = "circle"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    POLYGON = "polygon"
    STAR = "star"


class BackgroundType(str, Enum):
    WHITE = "white"
    TRANSPARENT = "transparent"
    COLOR = "color"
    GRADIENT_LINEAR = "gradient_linear"
    GRADIENT_RADIAL = "gradient_radial"
    IMAGE = "image"


class SignatureType(str, Enum):
    DRAWN = "drawn"
    TYPED = "typed"
    IMAGE = "image"


@dataclass
class BleedConfig:
    top_mm: float = 0.0
    bottom_mm: float = 0.0
    left_mm: float = 0.0
    right_mm: float = 0.0


@dataclass
class PageBackground:
    bg_type: BackgroundType = BackgroundType.WHITE
    color_hex: str = "#FFFFFF"
    gradient_start_hex: str = "#FFFFFF"
    gradient_end_hex: str = "#F1F5F9"
    gradient_angle_deg: float = 0.0
    image_base64: Optional[str] = None
    opacity: float = 1.0


@dataclass
class CropRect:
    """Normalized crop coordinates relative to original image [0.0 - 1.0]."""
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0

    def is_default(self) -> bool:
        return (
            abs(self.x) < 1e-5
            and abs(self.y) < 1e-5
            and abs(self.width - 1.0) < 1e-5
            and abs(self.height - 1.0) < 1e-5
        )


def qimage_to_base64_png(qimg: QImage) -> str:
    """Converts a QImage to base64 encoded PNG string."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    qimg.save(buf, "PNG")
    return bytes(ba.toBase64().data()).decode("ascii")


def base64_to_qimage(b64_str: str) -> QImage:
    """Decodes base64 string into a QImage."""
    from PySide6.QtCore import QByteArray
    ba = QByteArray.fromBase64(b64_str.encode("ascii"))
    img = QImage()
    img.loadFromData(ba, "PNG")
    return img


# ==============================================================================
# BASE PDF OBJECT & DERIVATIVES
# ==============================================================================


class PDFObject:
    """Abstract base class for all editable objects inside a PDF page."""

    def __init__(
        self,
        obj_type: ObjectType,
        x_pt: float = 0.0,
        y_pt: float = 0.0,
        width_pt: float = 100.0,
        height_pt: float = 100.0,
        rotation_deg: float = 0.0,
        opacity: float = 1.0,
        z_index: int = 0,
        locked: bool = False,
        obj_id: Optional[str] = None,
    ) -> None:
        self.id: str = obj_id or str(uuid.uuid4())
        self.type: ObjectType = obj_type
        self.x: float = x_pt
        self.y: float = y_pt
        self.width: float = width_pt
        self.height: float = height_pt
        self.rotation: float = rotation_deg
        self.opacity: float = max(0.0, min(1.0, opacity))
        self.z_index: int = z_index
        self.locked: bool = locked
        self.hyperlink_url: Optional[str] = None
        self.internal_link_page: Optional[int] = None  # 1-based page index

    @property
    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.width, self.height)

    @rect.setter
    def rect(self, r: QRectF) -> None:
        self.x = r.x()
        self.y = r.y()
        self.width = r.width()
        self.height = r.height()

    def clone(self) -> PDFObject:
        """Deep copy of the object."""
        d = self.to_dict()
        d["id"] = str(uuid.uuid4())
        return PDFObject.from_dict(d)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "opacity": self.opacity,
            "z_index": self.z_index,
            "locked": self.locked,
            "hyperlink_url": self.hyperlink_url,
            "internal_link_page": self.internal_link_page,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> PDFObject:
        t = data.get("type", "")
        if t == ObjectType.IMAGE.value:
            return PDFImageObject.from_dict(data)
        elif t == ObjectType.TEXT.value:
            return PDFTextObject.from_dict(data)
        elif t == ObjectType.SHAPE.value:
            return PDFShapeObject.from_dict(data)
        elif t == ObjectType.SIGNATURE.value:
            return PDFSignatureObject.from_dict(data)
        elif t == ObjectType.ANNOTATION.value:
            return PDFAnnotationObject.from_dict(data)
        elif t == ObjectType.LINK.value:
            return PDFLinkObject.from_dict(data)
        elif t == ObjectType.COMMENT.value:
            return PDFCommentObject.from_dict(data)
        
        # Fallback base object
        obj = PDFObject(
            obj_type=ObjectType(t) if t in [o.value for o in ObjectType] else ObjectType.SHAPE,
            x_pt=data.get("x", 0.0),
            y_pt=data.get("y", 0.0),
            width_pt=data.get("width", 100.0),
            height_pt=data.get("height", 100.0),
            rotation_deg=data.get("rotation", 0.0),
            opacity=data.get("opacity", 1.0),
            z_index=data.get("z_index", 0),
            locked=data.get("locked", False),
            obj_id=data.get("id"),
        )
        obj.hyperlink_url = data.get("hyperlink_url")
        obj.internal_link_page = data.get("internal_link_page")
        return obj


class PDFImageObject(PDFObject):
    """High-resolution image object with non-destructive crop and scaling."""

    def __init__(
        self,
        image: Optional[QImage] = None,
        x_pt: float = 0.0,
        y_pt: float = 0.0,
        width_pt: float = 200.0,
        height_pt: float = 150.0,
        rotation_deg: float = 0.0,
        opacity: float = 1.0,
        z_index: int = 0,
        locked: bool = False,
        crop: Optional[CropRect] = None,
        lock_aspect_ratio: bool = True,
        title: str = "Image",
        obj_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            obj_type=ObjectType.IMAGE,
            x_pt=x_pt,
            y_pt=y_pt,
            width_pt=width_pt,
            height_pt=height_pt,
            rotation_deg=rotation_deg,
            opacity=opacity,
            z_index=z_index,
            locked=locked,
            obj_id=obj_id,
        )
        self._image: Optional[QImage] = image
        self.crop: CropRect = crop or CropRect()
        self.lock_aspect_ratio: bool = lock_aspect_ratio
        self.title: str = title
        self._cached_b64: Optional[str] = None

    @property
    def original_image(self) -> Optional[QImage]:
        return self._image

    @original_image.setter
    def original_image(self, img: Optional[QImage]) -> None:
        self._image = img
        self._cached_b64 = None

    def get_cropped_image(self) -> Optional[QImage]:
        """Returns the cropped region of the original image."""
        if not self._image or self._image.isNull():
            return None
        if self.crop.is_default():
            return self._image

        orig_w = self._image.width()
        orig_h = self._image.height()
        cx = int(self.crop.x * orig_w)
        cy = int(self.crop.y * orig_h)
        cw = max(1, int(self.crop.width * orig_w))
        ch = max(1, int(self.crop.height * orig_h))
        return self._image.copy(cx, cy, cw, ch)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "crop": asdict(self.crop),
            "lock_aspect_ratio": self.lock_aspect_ratio,
            "title": self.title,
            "image_base64": qimage_to_base64_png(self._image) if self._image and not self._image.isNull() else "",
        })
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFImageObject:
        crop_data = data.get("crop", {})
        crop = CropRect(
            x=crop_data.get("x", 0.0),
            y=crop_data.get("y", 0.0),
            width=crop_data.get("width", 1.0),
            height=crop_data.get("height", 1.0),
        )
        b64 = data.get("image_base64", "")
        img = base64_to_qimage(b64) if b64 else None

        obj = cls(
            image=img,
            x_pt=data.get("x", 0.0),
            y_pt=data.get("y", 0.0),
            width_pt=data.get("width", 200.0),
            height_pt=data.get("height", 150.0),
            rotation_deg=data.get("rotation", 0.0),
            opacity=data.get("opacity", 1.0),
            z_index=data.get("z_index", 0),
            locked=data.get("locked", False),
            crop=crop,
            lock_aspect_ratio=data.get("lock_aspect_ratio", True),
            title=data.get("title", "Image"),
            obj_id=data.get("id"),
        )
        obj.hyperlink_url = data.get("hyperlink_url")
        obj.internal_link_page = data.get("internal_link_page")
        return obj


class PDFTextObject(PDFObject):
    """Vector selectable and rich text object with full formatting."""

    def __init__(
        self,
        text: str = "New Text",
        html: str = "",
        x_pt: float = 0.0,
        y_pt: float = 0.0,
        width_pt: float = 200.0,
        height_pt: float = 50.0,
        font_family: str = "Segoe UI",
        font_size_pt: float = 14.0,
        font_color: str = "#000000",
        highlight_color: str = "",
        is_bold: bool = False,
        is_italic: bool = False,
        is_underline: bool = False,
        is_strike: bool = False,
        alignment: str = "left",  # left, center, right, justify
        line_height: float = 1.2,
        letter_spacing: float = 0.0,
        rotation_deg: float = 0.0,
        opacity: float = 1.0,
        z_index: int = 0,
        locked: bool = False,
        is_ocr_layer: bool = False,
        obj_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            obj_type=ObjectType.TEXT,
            x_pt=x_pt,
            y_pt=y_pt,
            width_pt=width_pt,
            height_pt=height_pt,
            rotation_deg=rotation_deg,
            opacity=opacity,
            z_index=z_index,
            locked=locked,
            obj_id=obj_id,
        )
        self.text: str = text
        self.html: str = html
        self.font_family: str = font_family
        self.font_size_pt: float = font_size_pt
        self.font_color: str = font_color
        self.highlight_color: str = highlight_color
        self.is_bold: bool = is_bold
        self.is_italic: bool = is_italic
        self.is_underline: bool = is_underline
        self.is_strike: bool = is_strike
        self.alignment: str = alignment
        self.line_height: float = line_height
        self.letter_spacing: float = letter_spacing
        self.is_ocr_layer: bool = is_ocr_layer

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "text": self.text,
            "html": self.html,
            "font_family": self.font_family,
            "font_size_pt": self.font_size_pt,
            "font_color": self.font_color,
            "highlight_color": self.highlight_color,
            "is_bold": self.is_bold,
            "is_italic": self.is_italic,
            "is_underline": self.is_underline,
            "is_strike": self.is_strike,
            "alignment": self.alignment,
            "line_height": self.line_height,
            "letter_spacing": self.letter_spacing,
            "is_ocr_layer": self.is_ocr_layer,
        })
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFTextObject:
        obj = cls(
            text=data.get("text", ""),
            html=data.get("html", ""),
            x_pt=data.get("x", 0.0),
            y_pt=data.get("y", 0.0),
            width_pt=data.get("width", 200.0),
            height_pt=data.get("height", 50.0),
            font_family=data.get("font_family", "Segoe UI"),
            font_size_pt=data.get("font_size_pt", 14.0),
            font_color=data.get("font_color", "#000000"),
            highlight_color=data.get("highlight_color", ""),
            is_bold=data.get("is_bold", False),
            is_italic=data.get("is_italic", False),
            is_underline=data.get("is_underline", False),
            is_strike=data.get("is_strike", False),
            alignment=data.get("alignment", "left"),
            line_height=data.get("line_height", 1.2),
            letter_spacing=data.get("letter_spacing", 0.0),
            rotation_deg=data.get("rotation", 0.0),
            opacity=data.get("opacity", 1.0),
            z_index=data.get("z_index", 0),
            locked=data.get("locked", False),
            is_ocr_layer=data.get("is_ocr_layer", False),
            obj_id=data.get("id"),
        )
        obj.hyperlink_url = data.get("hyperlink_url")
        obj.internal_link_page = data.get("internal_link_page")
        return obj


class PDFShapeObject(PDFObject):
    """Vector shape object (rectangles, circles, arrows, lines, polygons)."""

    def __init__(
        self,
        shape_type: ShapeType = ShapeType.RECTANGLE,
        x_pt: float = 0.0,
        y_pt: float = 0.0,
        width_pt: float = 120.0,
        height_pt: float = 80.0,
        fill_color: str = "#3B82F6",
        border_color: str = "#1D4ED8",
        border_width_pt: float = 2.0,
        corner_radius_pt: float = 6.0,
        rotation_deg: float = 0.0,
        opacity: float = 1.0,
        z_index: int = 0,
        locked: bool = False,
        points: Optional[List[Tuple[float, float]]] = None,
        obj_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            obj_type=ObjectType.SHAPE,
            x_pt=x_pt,
            y_pt=y_pt,
            width_pt=width_pt,
            height_pt=height_pt,
            rotation_deg=rotation_deg,
            opacity=opacity,
            z_index=z_index,
            locked=locked,
            obj_id=obj_id,
        )
        self.shape_type: ShapeType = shape_type
        self.fill_color: str = fill_color
        self.border_color: str = border_color
        self.border_width_pt: float = border_width_pt
        self.corner_radius_pt: float = corner_radius_pt
        self.points: List[Tuple[float, float]] = points or []

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "shape_type": self.shape_type.value,
            "fill_color": self.fill_color,
            "border_color": self.border_color,
            "border_width_pt": self.border_width_pt,
            "corner_radius_pt": self.corner_radius_pt,
            "points": self.points,
        })
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFShapeObject:
        st = data.get("shape_type", ShapeType.RECTANGLE.value)
        obj = cls(
            shape_type=ShapeType(st) if st in [s.value for s in ShapeType] else ShapeType.RECTANGLE,
            x_pt=data.get("x", 0.0),
            y_pt=data.get("y", 0.0),
            width_pt=data.get("width", 120.0),
            height_pt=data.get("height", 80.0),
            fill_color=data.get("fill_color", "#3B82F6"),
            border_color=data.get("border_color", "#1D4ED8"),
            border_width_pt=data.get("border_width_pt", 2.0),
            corner_radius_pt=data.get("corner_radius_pt", 6.0),
            rotation_deg=data.get("rotation", 0.0),
            opacity=data.get("opacity", 1.0),
            z_index=data.get("z_index", 0),
            locked=data.get("locked", False),
            points=data.get("points", []),
            obj_id=data.get("id"),
        )
        obj.hyperlink_url = data.get("hyperlink_url")
        obj.internal_link_page = data.get("internal_link_page")
        return obj


class PDFSignatureObject(PDFObject):
    """Digital and handwritten signature object."""

    def __init__(
        self,
        sig_type: SignatureType = SignatureType.DRAWN,
        points: Optional[List[List[Tuple[float, float]]]] = None,
        typed_text: str = "",
        typed_font: str = "Segoe Script",
        image: Optional[QImage] = None,
        ink_color: str = "#0F172A",
        stroke_width_pt: float = 2.5,
        x_pt: float = 0.0,
        y_pt: float = 0.0,
        width_pt: float = 160.0,
        height_pt: float = 60.0,
        rotation_deg: float = 0.0,
        opacity: float = 1.0,
        z_index: int = 0,
        locked: bool = False,
        obj_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            obj_type=ObjectType.SIGNATURE,
            x_pt=x_pt,
            y_pt=y_pt,
            width_pt=width_pt,
            height_pt=height_pt,
            rotation_deg=rotation_deg,
            opacity=opacity,
            z_index=z_index,
            locked=locked,
            obj_id=obj_id,
        )
        self.sig_type: SignatureType = sig_type
        self.points: List[List[Tuple[float, float]]] = points or []
        self.typed_text: str = typed_text
        self.typed_font: str = typed_font
        self.image: Optional[QImage] = image
        self.ink_color: str = ink_color
        self.stroke_width_pt: float = stroke_width_pt

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "sig_type": self.sig_type.value,
            "points": self.points,
            "typed_text": self.typed_text,
            "typed_font": self.typed_font,
            "ink_color": self.ink_color,
            "stroke_width_pt": self.stroke_width_pt,
            "image_base64": qimage_to_base64_png(self.image) if self.image and not self.image.isNull() else "",
        })
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFSignatureObject:
        st = data.get("sig_type", SignatureType.DRAWN.value)
        b64 = data.get("image_base64", "")
        img = base64_to_qimage(b64) if b64 else None
        return cls(
            sig_type=SignatureType(st) if st in [s.value for s in SignatureType] else SignatureType.DRAWN,
            points=data.get("points", []),
            typed_text=data.get("typed_text", ""),
            typed_font=data.get("typed_font", "Segoe Script"),
            image=img,
            ink_color=data.get("ink_color", "#0F172A"),
            stroke_width_pt=data.get("stroke_width_pt", 2.5),
            x_pt=data.get("x", 0.0),
            y_pt=data.get("y", 0.0),
            width_pt=data.get("width", 160.0),
            height_pt=data.get("height", 60.0),
            rotation_deg=data.get("rotation", 0.0),
            opacity=data.get("opacity", 1.0),
            z_index=data.get("z_index", 0),
            locked=data.get("locked", False),
            obj_id=data.get("id"),
        )


class PDFAnnotationObject(PDFObject):
    """Freehand pen, highlighter, blur, and pixelate annotations."""

    def __init__(
        self,
        tool: str = "pen",
        color: str = "#EF4444",
        stroke_width_pt: float = 3.0,
        points: Optional[List[Tuple[float, float]]] = None,
        blur_radius: int = 15,
        pixel_size: int = 12,
        x_pt: float = 0.0,
        y_pt: float = 0.0,
        width_pt: float = 100.0,
        height_pt: float = 100.0,
        rotation_deg: float = 0.0,
        opacity: float = 1.0,
        z_index: int = 0,
        locked: bool = False,
        obj_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            obj_type=ObjectType.ANNOTATION,
            x_pt=x_pt,
            y_pt=y_pt,
            width_pt=width_pt,
            height_pt=height_pt,
            rotation_deg=rotation_deg,
            opacity=opacity,
            z_index=z_index,
            locked=locked,
            obj_id=obj_id,
        )
        self.tool: str = tool
        self.color: str = color
        self.stroke_width_pt: float = stroke_width_pt
        self.points: List[Tuple[float, float]] = points or []
        self.blur_radius: int = blur_radius
        self.pixel_size: int = pixel_size

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "tool": self.tool,
            "color": self.color,
            "stroke_width_pt": self.stroke_width_pt,
            "points": self.points,
            "blur_radius": self.blur_radius,
            "pixel_size": self.pixel_size,
        })
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFAnnotationObject:
        return cls(
            tool=data.get("tool", "pen"),
            color=data.get("color", "#EF4444"),
            stroke_width_pt=data.get("stroke_width_pt", 3.0),
            points=data.get("points", []),
            blur_radius=data.get("blur_radius", 15),
            pixel_size=data.get("pixel_size", 12),
            x_pt=data.get("x", 0.0),
            y_pt=data.get("y", 0.0),
            width_pt=data.get("width", 100.0),
            height_pt=data.get("height", 100.0),
            rotation_deg=data.get("rotation", 0.0),
            opacity=data.get("opacity", 1.0),
            z_index=data.get("z_index", 0),
            locked=data.get("locked", False),
            obj_id=data.get("id"),
        )


class PDFLinkObject(PDFObject):
    """Clickable interactive hotspot linking to an external URL or page jump."""

    def __init__(
        self,
        url: str = "",
        target_page: Optional[int] = None,
        tooltip: str = "",
        x_pt: float = 0.0,
        y_pt: float = 0.0,
        width_pt: float = 120.0,
        height_pt: float = 30.0,
        rotation_deg: float = 0.0,
        opacity: float = 1.0,
        z_index: int = 0,
        locked: bool = False,
        obj_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            obj_type=ObjectType.LINK,
            x_pt=x_pt,
            y_pt=y_pt,
            width_pt=width_pt,
            height_pt=height_pt,
            rotation_deg=rotation_deg,
            opacity=opacity,
            z_index=z_index,
            locked=locked,
            obj_id=obj_id,
        )
        self.hyperlink_url = url
        self.internal_link_page = target_page
        self.tooltip: str = tooltip

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "tooltip": self.tooltip,
        })
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFLinkObject:
        obj = cls(
            url=data.get("hyperlink_url", ""),
            target_page=data.get("internal_link_page"),
            tooltip=data.get("tooltip", ""),
            x_pt=data.get("x", 0.0),
            y_pt=data.get("y", 0.0),
            width_pt=data.get("width", 120.0),
            height_pt=data.get("height", 30.0),
            rotation_deg=data.get("rotation", 0.0),
            opacity=data.get("opacity", 1.0),
            z_index=data.get("z_index", 0),
            locked=data.get("locked", False),
            obj_id=data.get("id"),
        )
        return obj


class PDFCommentObject(PDFObject):
    """Sticky note / review comment attached to a page location."""

    def __init__(
        self,
        comment_text: str = "",
        author: str = "Reviewer",
        x_pt: float = 0.0,
        y_pt: float = 0.0,
        width_pt: float = 32.0,
        height_pt: float = 32.0,
        color_hex: str = "#FACC15",
        obj_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            obj_type=ObjectType.COMMENT,
            x_pt=x_pt,
            y_pt=y_pt,
            width_pt=width_pt,
            height_pt=height_pt,
            obj_id=obj_id,
        )
        self.comment_text: str = comment_text
        self.author: str = author
        self.color_hex: str = color_hex

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "comment_text": self.comment_text,
            "author": self.author,
            "color_hex": self.color_hex,
        })
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFCommentObject:
        return cls(
            comment_text=data.get("comment_text", ""),
            author=data.get("author", "Reviewer"),
            x_pt=data.get("x", 0.0),
            y_pt=data.get("y", 0.0),
            width_pt=data.get("width", 32.0),
            height_pt=data.get("height", 32.0),
            color_hex=data.get("color_hex", "#FACC15"),
            obj_id=data.get("id"),
        )


# ==============================================================================
# PDF PAGE & DOCUMENT MODEL
# ==============================================================================


class PDFPage:
    """Represents a single page with its layout, dimensions, background, and objects."""

    def __init__(
        self,
        paper_size: PaperSizePreset = PaperSizePreset.A4,
        orientation: PageOrientation = PageOrientation.PORTRAIT,
        custom_width_mm: float = 210.0,
        custom_height_mm: float = 297.0,
        margins: Optional[MarginConfig] = None,
        bleed: Optional[BleedConfig] = None,
        background: Optional[PageBackground] = None,
        page_id: Optional[str] = None,
    ) -> None:
        self.id: str = page_id or str(uuid.uuid4())
        self.paper_size: PaperSizePreset = paper_size
        self.orientation: PageOrientation = orientation
        self.custom_width_mm: float = custom_width_mm
        self.custom_height_mm: float = custom_height_mm
        self.margins: MarginConfig = margins or MarginConfig()
        self.bleed: BleedConfig = bleed or BleedConfig()
        self.background: PageBackground = background or PageBackground()
        self.objects: List[PDFObject] = []
        self._thumbnail_cache: Optional[QImage] = None

    def get_dimensions_mm(self) -> Tuple[float, float]:
        """Calculates page width and height in mm according to preset and orientation."""
        if self.paper_size == PaperSizePreset.CUSTOM:
            w = self.custom_width_mm
            h = self.custom_height_mm
        else:
            w, h = get_paper_dimensions_mm(self.paper_size)

        if self.orientation == PageOrientation.LANDSCAPE:
            return max(w, h), min(w, h)
        return min(w, h), max(w, h)

    def get_dimensions_pt(self) -> Tuple[float, float]:
        """Calculates page width and height in points (72 pt per inch)."""
        w_mm, h_mm = self.get_dimensions_mm()
        return mm_to_pt(w_mm), mm_to_pt(h_mm)

    @property
    def width_pt(self) -> float:
        return self.get_dimensions_pt()[0]

    @property
    def height_pt(self) -> float:
        return self.get_dimensions_pt()[1]

    def get_printable_rect_pt(self) -> QRectF:
        """Returns the inner printable rectangle bounded by margins."""
        w_pt, h_pt = self.get_dimensions_pt()
        top_pt = mm_to_pt(self.margins.top_mm)
        bottom_pt = mm_to_pt(self.margins.bottom_mm)
        left_pt = mm_to_pt(self.margins.left_mm)
        right_pt = mm_to_pt(self.margins.right_mm)

        return QRectF(
            left_pt,
            top_pt,
            max(10.0, w_pt - left_pt - right_pt),
            max(10.0, h_pt - top_pt - bottom_pt),
        )

    def add_object(self, obj: PDFObject) -> None:
        """Appends an object and sets its z-index."""
        max_z = max([o.z_index for o in self.objects], default=-1)
        obj.z_index = max_z + 1
        self.objects.append(obj)
        self.invalidate_thumbnail()

    def remove_object(self, obj: PDFObject) -> bool:
        """Removes an object from the page."""
        if obj in self.objects:
            self.objects.remove(obj)
            self.invalidate_thumbnail()
            return True
        return False

    def remove_object_by_id(self, obj_id: str) -> Optional[PDFObject]:
        for o in self.objects:
            if o.id == obj_id:
                self.objects.remove(o)
                self.invalidate_thumbnail()
                return o
        return None

    def get_object_by_id(self, obj_id: str) -> Optional[PDFObject]:
        for o in self.objects:
            if o.id == obj_id:
                return o
        return None

    def bring_to_front(self, obj: PDFObject) -> None:
        if obj in self.objects:
            max_z = max([o.z_index for o in self.objects], default=0)
            obj.z_index = max_z + 1
            self.objects.sort(key=lambda x: x.z_index)
            self.invalidate_thumbnail()

    def send_to_back(self, obj: PDFObject) -> None:
        if obj in self.objects:
            min_z = min([o.z_index for o in self.objects], default=0)
            obj.z_index = min_z - 1
            self.objects.sort(key=lambda x: x.z_index)
            self.invalidate_thumbnail()

    def bring_forward(self, obj: PDFObject) -> None:
        if obj in self.objects:
            self.objects.sort(key=lambda x: x.z_index)
            idx = self.objects.index(obj)
            if idx < len(self.objects) - 1:
                self.objects[idx], self.objects[idx + 1] = self.objects[idx + 1], self.objects[idx]
                for i, o in enumerate(self.objects):
                    o.z_index = i
                self.invalidate_thumbnail()

    def send_backward(self, obj: PDFObject) -> None:
        if obj in self.objects:
            self.objects.sort(key=lambda x: x.z_index)
            idx = self.objects.index(obj)
            if idx > 0:
                self.objects[idx], self.objects[idx - 1] = self.objects[idx - 1], self.objects[idx]
                for i, o in enumerate(self.objects):
                    o.z_index = i
                self.invalidate_thumbnail()

    def fit_content_to_page(self) -> None:
        """Scales all objects to fit within page margins."""
        if not self.objects:
            return
        p_rect = self.get_printable_rect_pt()
        min_x = min(o.x for o in self.objects)
        min_y = min(o.y for o in self.objects)
        max_x = max(o.x + o.width for o in self.objects)
        max_y = max(o.y + o.height for o in self.objects)
        total_w = max(1.0, max_x - min_x)
        total_h = max(1.0, max_y - min_y)

        scale_x = p_rect.width() / total_w
        scale_y = p_rect.height() / total_h
        scale = min(scale_x, scale_y)

        for o in self.objects:
            rel_x = (o.x - min_x) * scale
            rel_y = (o.y - min_y) * scale
            o.x = p_rect.x() + rel_x
            o.y = p_rect.y() + rel_y
            o.width *= scale
            o.height *= scale
        self.invalidate_thumbnail()

    def center_content(self) -> None:
        """Centers the bounding box of all objects on the page."""
        if not self.objects:
            return
        p_rect = self.get_printable_rect_pt()
        min_x = min(o.x for o in self.objects)
        min_y = min(o.y for o in self.objects)
        max_x = max(o.x + o.width for o in self.objects)
        max_y = max(o.y + o.height for o in self.objects)
        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0

        target_center_x = p_rect.center().x()
        target_center_y = p_rect.center().y()

        dx = target_center_x - center_x
        dy = target_center_y - center_y

        for o in self.objects:
            o.x += dx
            o.y += dy
        self.invalidate_thumbnail()

    def invalidate_thumbnail(self) -> None:
        self._thumbnail_cache = None

    def clone(self) -> PDFPage:
        """Deep duplicates this page and all contained objects."""
        d = self.to_dict()
        d["id"] = str(uuid.uuid4())
        for obj_d in d.get("objects", []):
            obj_d["id"] = str(uuid.uuid4())
        return PDFPage.from_dict(d)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "paper_size": self.paper_size.value,
            "orientation": self.orientation.value,
            "custom_width_mm": self.custom_width_mm,
            "custom_height_mm": self.custom_height_mm,
            "margins": asdict(self.margins),
            "bleed": asdict(self.bleed),
            "background": asdict(self.background),
            "objects": [o.to_dict() for o in self.objects],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PDFPage:
        ps_str = data.get("paper_size", PaperSizePreset.A4.value)
        ori_str = data.get("orientation", PageOrientation.PORTRAIT.value)
        
        paper_size = PaperSizePreset(ps_str) if ps_str in [p.value for p in PaperSizePreset] else PaperSizePreset.A4
        orientation = PageOrientation(ori_str) if ori_str in [o.value for o in PageOrientation] else PageOrientation.PORTRAIT

        m_data = data.get("margins", {})
        margins = MarginConfig(
            top_mm=m_data.get("top_mm", 10.0),
            bottom_mm=m_data.get("bottom_mm", 10.0),
            left_mm=m_data.get("left_mm", 10.0),
            right_mm=m_data.get("right_mm", 10.0),
            linked=m_data.get("linked", True),
        )

        b_data = data.get("bleed", {})
        bleed = BleedConfig(
            top_mm=b_data.get("top_mm", 0.0),
            bottom_mm=b_data.get("bottom_mm", 0.0),
            left_mm=b_data.get("left_mm", 0.0),
            right_mm=b_data.get("right_mm", 0.0),
        )

        bg_data = data.get("background", {})
        bg_t = bg_data.get("bg_type", BackgroundType.WHITE.value)
        background = PageBackground(
            bg_type=BackgroundType(bg_t) if bg_t in [b.value for b in BackgroundType] else BackgroundType.WHITE,
            color_hex=bg_data.get("color_hex", "#FFFFFF"),
            gradient_start_hex=bg_data.get("gradient_start_hex", "#FFFFFF"),
            gradient_end_hex=bg_data.get("gradient_end_hex", "#F1F5F9"),
            gradient_angle_deg=bg_data.get("gradient_angle_deg", 0.0),
            image_base64=bg_data.get("image_base64"),
            opacity=bg_data.get("opacity", 1.0),
        )

        page = cls(
            paper_size=paper_size,
            orientation=orientation,
            custom_width_mm=data.get("custom_width_mm", 210.0),
            custom_height_mm=data.get("custom_height_mm", 297.0),
            margins=margins,
            bleed=bleed,
            background=background,
            page_id=data.get("id"),
        )

        for obj_d in data.get("objects", []):
            page.objects.append(PDFObject.from_dict(obj_d))

        return page


@dataclass
class PageNumberConfig:
    enabled: bool = True
    position: PageNumberPosition = PageNumberPosition.BOTTOM_RIGHT
    format_template: str = "{page} / {pages}"
    start_number: int = 1
    font_family: str = "Segoe UI"
    font_size_pt: float = 9.0
    color_hex: str = "#64748B"


@dataclass
class PDFSecurityConfig:
    enabled: bool = False
    user_password: str = ""
    owner_password: str = ""
    allow_printing: bool = True
    allow_copying: bool = True
    allow_editing: bool = False
    allow_annotations: bool = True


@dataclass
class DocumentSettings:
    title: str = "Quickglint Document"
    author: str = "Quickglint User"
    subject: str = "Exported Document"
    keywords: str = "Quickglint, PDF, Export"
    creator: str = "Quickglint PDF Builder"
    header_footer: HeaderFooterConfig = field(default_factory=HeaderFooterConfig)
    page_numbers: PageNumberConfig = field(default_factory=PageNumberConfig)
    security: PDFSecurityConfig = field(default_factory=PDFSecurityConfig)
    quality: QualityLevel = QualityLevel.HIGH
    jpeg_quality_pct: int = 90
    dpi: int = 300
    flatten_annotations: bool = False
    include_ocr_layer: bool = True


class PDFDocument:
    """Root container representing the entire multi-page PDF project."""

    FILE_EXTENSION = ".quickglintpdf"

    def __init__(self, title: str = "Untitled Document") -> None:
        self.id: str = str(uuid.uuid4())
        self.settings: DocumentSettings = DocumentSettings(title=title)
        self.pages: List[PDFPage] = []
        self.file_path: Optional[Path] = None
        self.is_modified: bool = False

    @classmethod
    def create_empty(
        cls,
        title: str = "Untitled Document",
        paper_size: PaperSizePreset = PaperSizePreset.A4,
        orientation: PageOrientation = PageOrientation.PORTRAIT,
    ) -> PDFDocument:
        """Creates a document pre-populated with a single standard page."""
        doc = cls(title=title)
        p = PDFPage(paper_size=paper_size, orientation=orientation)
        doc.pages.append(p)
        return doc

    @classmethod
    def create_from_image(cls, image: QImage, title: str = "Screenshot") -> PDFDocument:
        """Creates a document containing one page tailored to fit the given image."""
        doc = cls(title=title)
        
        is_landscape = image.width() > image.height()
        orientation = PageOrientation.LANDSCAPE if is_landscape else PageOrientation.PORTRAIT
        page = PDFPage(paper_size=PaperSizePreset.A4, orientation=orientation)
        
        p_rect = page.get_printable_rect_pt()
        img_aspect = image.width() / max(1, image.height())
        target_w = p_rect.width()
        target_h = target_w / img_aspect

        if target_h > p_rect.height():
            target_h = p_rect.height()
            target_w = target_h * img_aspect

        img_x = p_rect.x() + (p_rect.width() - target_w) / 2.0
        img_y = p_rect.y() + (p_rect.height() - target_h) / 2.0

        img_obj = PDFImageObject(
            image=image,
            x_pt=img_x,
            y_pt=img_y,
            width_pt=target_w,
            height_pt=target_h,
            title=title,
        )
        page.add_object(img_obj)
        doc.pages.append(page)
        return doc

    @classmethod
    def create_from_images(cls, images: List[Tuple[QImage, str]]) -> PDFDocument:
        """Creates a multi-page document from a list of (image, title) pairs."""
        doc = cls(title="Batch Screenshots")
        for img, t in images:
            p_doc = cls.create_from_image(img, title=t)
            if p_doc.pages:
                doc.pages.append(p_doc.pages[0])
        if not doc.pages:
            doc.pages.append(PDFPage())
        return doc

    def add_page(self, page: Optional[PDFPage] = None, index: Optional[int] = None) -> PDFPage:
        """Inserts a new page at the given index or appends to the end."""
        p = page or PDFPage()
        if index is not None and 0 <= index <= len(self.pages):
            self.pages.insert(index, p)
        else:
            self.pages.append(p)
        self.is_modified = True
        return p

    def remove_page(self, page_or_index: PDFPage | int) -> Optional[PDFPage]:
        """Removes a page while ensuring at least one page remains."""
        if len(self.pages) <= 1:
            logger.warning("Cannot remove the last remaining page from document.")
            return None

        if isinstance(page_or_index, int):
            if 0 <= page_or_index < len(self.pages):
                self.is_modified = True
                return self.pages.pop(page_or_index)
        elif page_or_index in self.pages:
            self.pages.remove(page_or_index)
            self.is_modified = True
            return page_or_index
        return None

    def duplicate_page(self, index: int) -> Optional[PDFPage]:
        """Duplicates the page at index and inserts it right after."""
        if 0 <= index < len(self.pages):
            new_page = self.pages[index].clone()
            self.pages.insert(index + 1, new_page)
            self.is_modified = True
            return new_page
        return None

    def move_page(self, from_index: int, to_index: int) -> bool:
        """Reorders page from one index to another."""
        if 0 <= from_index < len(self.pages) and 0 <= to_index < len(self.pages):
            p = self.pages.pop(from_index)
            self.pages.insert(to_index, p)
            self.is_modified = True
            return True
        return False

    def get_page(self, index: int) -> Optional[PDFPage]:
        if 0 <= index < len(self.pages):
            return self.pages[index]
        return None

    def get_page_count(self) -> int:
        return len(self.pages)

    # --------------------------------------------------------------------------
    # SERIALIZATION / PROJECT SAVING (.quickglintpdf)
    # --------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        pn = self.settings.page_numbers
        return {
            "format_version": "1.0",
            "id": self.id,
            "settings": {
                "title": self.settings.title,
                "author": self.settings.author,
                "subject": self.settings.subject,
                "keywords": self.settings.keywords,
                "creator": self.settings.creator,
                "header_footer": asdict(self.settings.header_footer),
                "page_numbers": {
                    "enabled": pn.enabled,
                    "position": pn.position.value,
                    "format_template": pn.format_template,
                    "start_number": pn.start_number,
                    "font_family": pn.font_family,
                    "font_size_pt": pn.font_size_pt,
                    "color_hex": pn.color_hex,
                },
                "security": asdict(self.settings.security),
                "quality": self.settings.quality.value,
                "jpeg_quality_pct": self.settings.jpeg_quality_pct,
                "dpi": self.settings.dpi,
                "flatten_annotations": self.settings.flatten_annotations,
                "include_ocr_layer": self.settings.include_ocr_layer,
            },
            "pages": [p.to_dict() for p in self.pages],
        }

    def save_project(self, file_path: Path | str) -> bool:
        """Saves the document model and all assets to a .quickglintpdf JSON file."""
        p = Path(file_path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            data = self.to_dict()
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.file_path = p
            self.is_modified = False
            logger.info("Saved Quickglint PDF project to %s", p)
            return True
        except Exception as exc:
            logger.error("Failed to save project to %s: %s", p, exc)
            return False

    @classmethod
    def load_project(cls, file_path: Path | str) -> Optional[PDFDocument]:
        """Loads a .quickglintpdf project file."""
        p = Path(file_path)
        if not p.exists():
            logger.error("Project file does not exist: %s", p)
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)

            s_data = data.get("settings", {})
            doc = cls(title=s_data.get("title", "Quickglint Document"))
            doc.id = data.get("id", str(uuid.uuid4()))
            doc.settings.author = s_data.get("author", "")
            doc.settings.subject = s_data.get("subject", "")
            doc.settings.keywords = s_data.get("keywords", "")
            doc.settings.creator = s_data.get("creator", "Quickglint")
            doc.settings.jpeg_quality_pct = s_data.get("jpeg_quality_pct", 90)
            doc.settings.dpi = s_data.get("dpi", 300)
            doc.settings.flatten_annotations = s_data.get("flatten_annotations", False)
            doc.settings.include_ocr_layer = s_data.get("include_ocr_layer", True)

            q_val = s_data.get("quality", QualityLevel.HIGH.value)
            doc.settings.quality = QualityLevel(q_val) if q_val in [q.value for q in QualityLevel] else QualityLevel.HIGH

            # Load Header/Footer
            hf_d = s_data.get("header_footer", {})
            doc.settings.header_footer = HeaderFooterConfig(
                header_text=hf_d.get("header_text", ""),
                footer_text=hf_d.get("footer_text", ""),
                font_family=hf_d.get("font_family", "Segoe UI"),
                font_size_pt=hf_d.get("font_size_pt", 9),
                is_bold=hf_d.get("is_bold", False),
                header_alignment=hf_d.get("header_alignment", "Center"),
                footer_alignment=hf_d.get("footer_alignment", "Center"),
            )

            # Load Page Numbers
            pn_d = s_data.get("page_numbers", {})
            pn_pos = pn_d.get("position", PageNumberPosition.BOTTOM_RIGHT.value)
            doc.settings.page_numbers = PageNumberConfig(
                enabled=pn_d.get("enabled", True),
                position=PageNumberPosition(pn_pos) if pn_pos in [pos.value for pos in PageNumberPosition] else PageNumberPosition.BOTTOM_RIGHT,
                format_template=pn_d.get("format_template", "{page} / {pages}"),
                start_number=pn_d.get("start_number", 1),
                font_family=pn_d.get("font_family", "Segoe UI"),
                font_size_pt=pn_d.get("font_size_pt", 9.0),
                color_hex=pn_d.get("color_hex", "#64748B"),
            )

            # Load Pages
            doc.pages = []
            for p_data in data.get("pages", []):
                doc.pages.append(PDFPage.from_dict(p_data))

            if not doc.pages:
                doc.pages.append(PDFPage())

            doc.file_path = p
            doc.is_modified = False
            return doc
        except Exception as exc:
            logger.error("Failed to parse project file %s: %s", p, exc)
            return None

