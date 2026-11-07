"""Vector and filter drawing object definitions for the annotation layer."""

import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from app.utils.constants import HIGHLIGHTER_OPACITY, ToolType
from app.utils.helpers import apply_blur_to_region, apply_pixelate_to_region, normalize_rect


class CanvasObject(ABC):
    """Base class for all discrete non-destructive canvas annotation objects."""

    def __init__(
        self,
        tool_type: ToolType,
        color: str = "#FF0000",
        stroke_width: int = 3,
        opacity: float = 1.0,
    ) -> None:
        self.tool_type = tool_type
        self.color = color
        self.stroke_width = stroke_width
        self.opacity = opacity

    @abstractmethod
    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        """Render the object onto the target QPainter."""
        pass

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize object to dictionary."""
        pass


class LineObject(CanvasObject):
    """Straight line annotation object."""

    def __init__(
        self,
        start_point: QPoint,
        end_point: QPoint,
        color: str = "#FF0000",
        stroke_width: int = 3,
        opacity: float = 1.0,
    ) -> None:
        super().__init__(ToolType.LINE, color, stroke_width, opacity)
        self.start_point = QPoint(start_point)
        self.end_point = QPoint(end_point)

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        painter.save()
        qcolor = QColor(self.color)
        qcolor.setAlphaF(self.opacity)
        pen = QPen(qcolor, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(self.start_point, self.end_point)
        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "start": (self.start_point.x(), self.start_point.y()),
            "end": (self.end_point.x(), self.end_point.y()),
        }


class ArrowObject(CanvasObject):
    """Vector Arrow annotation object with proportional arrow head."""

    def __init__(
        self,
        start_point: QPoint,
        end_point: QPoint,
        color: str = "#FF0000",
        stroke_width: int = 3,
        opacity: float = 1.0,
    ) -> None:
        super().__init__(ToolType.ARROW, color, stroke_width, opacity)
        self.start_point = QPoint(start_point)
        self.end_point = QPoint(end_point)

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        painter.save()
        qcolor = QColor(self.color)
        qcolor.setAlphaF(self.opacity)
        pen = QPen(qcolor, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        painter.drawLine(self.start_point, self.end_point)

        dx = self.end_point.x() - self.start_point.x()
        dy = self.end_point.y() - self.start_point.y()
        length = math.hypot(dx, dy)

        if length > 2:
            angle = math.atan2(dy, dx)
            head_size = max(14, self.stroke_width * 4.5)
            head_angle = math.radians(28)

            p1 = QPointF(
                self.end_point.x() - head_size * math.cos(angle - head_angle),
                self.end_point.y() - head_size * math.sin(angle - head_angle),
            )
            p2 = QPointF(
                self.end_point.x() - head_size * math.cos(angle + head_angle),
                self.end_point.y() - head_size * math.sin(angle + head_angle),
            )

            arrow_head = QPolygonF([QPointF(self.end_point), p1, p2])
            painter.setBrush(QBrush(qcolor))
            painter.drawPolygon(arrow_head)

        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "start": (self.start_point.x(), self.start_point.y()),
            "end": (self.end_point.x(), self.end_point.y()),
        }


class RectangleObject(CanvasObject):
    """Outlined or filled rectangle annotation."""

    def __init__(
        self,
        rect: QRect,
        color: str = "#FF0000",
        stroke_width: int = 3,
        opacity: float = 1.0,
        fill: bool = False,
    ) -> None:
        super().__init__(ToolType.RECTANGLE, color, stroke_width, opacity)
        self.rect = normalize_rect(rect)
        self.fill = fill

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        painter.save()
        qcolor = QColor(self.color)
        qcolor.setAlphaF(self.opacity)
        if self.fill:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(qcolor))
            painter.drawRect(self.rect)
        else:
            pen = QPen(qcolor, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect)
        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "fill": self.fill,
            "rect": (self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()),
        }


class EllipseObject(CanvasObject):
    """Outlined ellipse/circle annotation."""

    def __init__(
        self,
        rect: QRect,
        color: str = "#FF0000",
        stroke_width: int = 3,
        opacity: float = 1.0,
    ) -> None:
        super().__init__(ToolType.ELLIPSE, color, stroke_width, opacity)
        self.rect = normalize_rect(rect)

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        painter.save()
        qcolor = QColor(self.color)
        qcolor.setAlphaF(self.opacity)
        pen = QPen(qcolor, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.rect)
        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "rect": (self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()),
        }


class PenObject(CanvasObject):
    """Freehand pen/brush stroke."""

    def __init__(
        self,
        points: Optional[List[QPoint]] = None,
        color: str = "#FF0000",
        stroke_width: int = 3,
        opacity: float = 1.0,
    ) -> None:
        super().__init__(ToolType.PEN, color, stroke_width, opacity)
        self.points: List[QPoint] = [QPoint(p) for p in (points or [])]

    def add_point(self, point: QPoint) -> None:
        self.points.append(QPoint(point))

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        if len(self.points) < 2:
            if len(self.points) == 1:
                painter.save()
                qcolor = QColor(self.color)
                qcolor.setAlphaF(self.opacity)
                painter.setPen(QPen(qcolor, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawPoint(self.points[0])
                painter.restore()
            return

        painter.save()
        qcolor = QColor(self.color)
        qcolor.setAlphaF(self.opacity)
        pen = QPen(qcolor, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(QPointF(self.points[0]))
        for i in range(1, len(self.points)):
            p1 = self.points[i - 1]
            p2 = self.points[i]
            mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            path.quadTo(QPointF(p1), mid)
        path.lineTo(QPointF(self.points[-1]))

        painter.drawPath(path)
        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "points": [(p.x(), p.y()) for p in self.points],
        }


class HighlighterObject(CanvasObject):
    """Semi-transparent marker/highlighter stroke."""

    def __init__(
        self,
        points: Optional[List[QPoint]] = None,
        color: str = "#FFD700",
        stroke_width: int = 18,
        opacity: float = HIGHLIGHTER_OPACITY,
    ) -> None:
        super().__init__(ToolType.HIGHLIGHTER, color, stroke_width, opacity)
        self.points: List[QPoint] = [QPoint(p) for p in (points or [])]

    def add_point(self, point: QPoint) -> None:
        self.points.append(QPoint(point))

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        if len(self.points) < 2:
            return

        painter.save()
        qcolor = QColor(self.color)
        qcolor.setAlphaF(self.opacity)
        pen = QPen(qcolor, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.BevelJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(QPointF(self.points[0]))
        for p in self.points[1:]:
            path.lineTo(QPointF(p))

        painter.drawPath(path)
        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "points": [(p.x(), p.y()) for p in self.points],
        }


class TextObject(CanvasObject):
    """Text annotation object."""

    def __init__(
        self,
        position: QPoint,
        text: str,
        color: str = "#FF0000",
        font_size: int = 18,
        font_family: str = "Segoe UI",
        bold: bool = True,
    ) -> None:
        super().__init__(ToolType.TEXT, color, font_size, 1.0)
        self.position = QPoint(position)
        self.text = text
        self.font_size = font_size
        self.font_family = font_family
        self.bold = bold

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        if not self.text:
            return

        painter.save()
        qcolor = QColor(self.color)
        font = QFont(self.font_family, max(8, self.font_size))
        font.setBold(self.bold)
        painter.setFont(font)
        painter.setPen(qcolor)

        lines = self.text.split("\n")
        metrics = QFontMetrics(font)
        line_height = metrics.lineSpacing()

        x = self.position.x()
        y = self.position.y()

        for i, line in enumerate(lines):
            painter.drawText(x, y + (i + 1) * line_height - metrics.descent(), line)

        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "font_size": self.font_size,
            "font_family": self.font_family,
            "bold": self.bold,
            "text": self.text,
            "pos": (self.position.x(), self.position.y()),
        }


class BlurObject(CanvasObject):
    """Gaussian blur filter on a rectangular region with optional tint overlay."""

    def __init__(
        self,
        rect: QRect,
        radius: int = 15,
        tint_color: str = "",
        tint_opacity: float = 0.2,
    ) -> None:
        super().__init__(ToolType.BLUR, "#000000", 0, 1.0)
        self.rect = normalize_rect(rect)
        self.radius = max(1, radius)
        self.tint_color = tint_color
        self.tint_opacity = tint_opacity

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        if base_image is None or base_image.isNull() or self.rect.isEmpty():
            return

        norm_rect = normalize_rect(self.rect)
        clipped_rect = norm_rect.intersected(QRect(0, 0, base_image.width(), base_image.height()))
        if clipped_rect.isEmpty() or clipped_rect.width() <= 0 or clipped_rect.height() <= 0:
            return

        try:
            from PIL import ImageFilter
            from app.utils.helpers import pil_to_qimage, qimage_to_pil

            radius = max(1, self.radius)
            sub_qimage = base_image.copy(clipped_rect)
            pil_sub = qimage_to_pil(sub_qimage)
            blurred_sub = pil_sub.filter(ImageFilter.GaussianBlur(radius=radius))
            blurred_qimage = pil_to_qimage(blurred_sub)

            painter.drawImage(clipped_rect.topLeft(), blurred_qimage)
        except Exception:
            pass

        # Optional tint overlay
        if self.tint_color:
            painter.save()
            tint = QColor(self.tint_color)
            tint.setAlphaF(self.tint_opacity)
            painter.fillRect(clipped_rect, tint)
            painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "radius": self.radius,
            "tint_color": self.tint_color,
            "tint_opacity": self.tint_opacity,
            "rect": (self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()),
        }


class PixelateObject(CanvasObject):
    """Pixelate/Mosaic filter on a rectangular region with optional tint overlay."""

    def __init__(
        self,
        rect: QRect,
        pixel_size: int = 12,
        tint_color: str = "",
        tint_opacity: float = 0.2,
    ) -> None:
        super().__init__(ToolType.PIXELATE, "#000000", 0, 1.0)
        self.rect = normalize_rect(rect)
        self.pixel_size = max(2, pixel_size)
        self.tint_color = tint_color
        self.tint_opacity = tint_opacity

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        if base_image is None or base_image.isNull() or self.rect.isEmpty():
            return

        norm_rect = normalize_rect(self.rect)
        clipped_rect = norm_rect.intersected(QRect(0, 0, base_image.width(), base_image.height()))
        if clipped_rect.isEmpty() or clipped_rect.width() <= 0 or clipped_rect.height() <= 0:
            return

        try:
            from PIL import Image
            from app.utils.helpers import pil_to_qimage, qimage_to_pil

            pixel_size = max(2, self.pixel_size)
            sub_qimage = base_image.copy(clipped_rect)
            pil_sub = qimage_to_pil(sub_qimage)

            w, h = pil_sub.size
            small_w = max(1, w // pixel_size)
            small_h = max(1, h // pixel_size)

            small = pil_sub.resize((small_w, small_h), resample=Image.Resampling.NEAREST)
            pixelated = small.resize((w, h), resample=Image.Resampling.NEAREST)
            pixelated_qimage = pil_to_qimage(pixelated)

            painter.drawImage(clipped_rect.topLeft(), pixelated_qimage)
        except Exception:
            pass

        # Optional tint overlay
        if self.tint_color:
            painter.save()
            tint = QColor(self.tint_color)
            tint.setAlphaF(self.tint_opacity)
            painter.fillRect(clipped_rect, tint)
            painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "pixel_size": self.pixel_size,
            "tint_color": self.tint_color,
            "tint_opacity": self.tint_opacity,
            "rect": (self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()),
        }


class RulerObject(CanvasObject):
    """Interactive measurement line on the annotation canvas with pixel distance and delta labels."""

    def __init__(
        self,
        start_point: QPoint,
        end_point: QPoint,
        color: str = "#38BDF8",
        stroke_width: int = 2,
        opacity: float = 1.0,
    ) -> None:
        super().__init__(ToolType.RULER, color, stroke_width, opacity)
        self.start_point = QPoint(start_point)
        self.end_point = QPoint(end_point)

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        qcolor = QColor(self.color)
        qcolor.setAlphaF(self.opacity)
        pen = QPen(qcolor, self.stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        p1 = self.start_point
        p2 = self.end_point
        painter.drawLine(p1, p2)

        # Endpoint circles
        painter.setBrush(QBrush(qcolor))
        painter.drawEllipse(p1, 4, 4)
        painter.drawEllipse(p2, 4, 4)

        # Distance calculation
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dist = math.hypot(dx, dy)

        # Draw floating badge
        mid_x = (p1.x() + p2.x()) / 2.0
        mid_y = (p1.y() + p2.y()) / 2.0

        label_txt = f"{dist:.1f} px\nΔX {abs(dx)} | ΔY {abs(dy)}"
        font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        lines = label_txt.split("\n")
        w = max(fm.horizontalAdvance(l) for l in lines) + 14
        h = len(lines) * fm.height() + 8
        badge_rect = QRectF(mid_x - w / 2.0, mid_y - h / 2.0, w, h)

        # Pill background
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.setBrush(QBrush(QColor(15, 23, 42, 230)))
        painter.drawRoundedRect(badge_rect, 6, 6)

        # Text
        painter.setPen(QColor("#FFFFFF"))
        curr_y = badge_rect.top() + 4 + fm.ascent()
        for l in lines:
            line_w = fm.horizontalAdvance(l)
            painter.drawText(QPointF(badge_rect.left() + (w - line_w) / 2.0, curr_y), l)
            curr_y += fm.height()

        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "start": (self.start_point.x(), self.start_point.y()),
            "end": (self.end_point.x(), self.end_point.y()),
        }


class MagnifierObject(CanvasObject):
    """Rectangular magnifying lens annotation that zooms into the underlying region of base_image."""

    def __init__(
        self,
        rect: QRect,
        zoom_factor: float = 2.0,
        color: str = "#38BDF8",
        stroke_width: int = 2,
        opacity: float = 1.0,
    ) -> None:
        super().__init__(ToolType.MAGNIFIER, color, stroke_width, opacity)
        self.rect = normalize_rect(rect)
        self.zoom_factor = max(1.2, float(zoom_factor))

    def render(self, painter: QPainter, base_image: Optional[QImage] = None) -> None:
        norm_rect = normalize_rect(self.rect)
        if norm_rect.isEmpty() or norm_rect.width() < 4 or norm_rect.height() < 4:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        lens_rect_f = QRectF(norm_rect)

        if base_image is not None and not base_image.isNull():
            img_rect = base_image.rect()
            center = norm_rect.center()
            src_w = max(2, min(img_rect.width(), int(round(norm_rect.width() / self.zoom_factor))))
            src_h = max(2, min(img_rect.height(), int(round(norm_rect.height() / self.zoom_factor))))
            src_x = center.x() - src_w // 2
            src_y = center.y() - src_h // 2
            src_x = max(0, min(src_x, max(0, img_rect.width() - src_w)))
            src_y = max(0, min(src_y, max(0, img_rect.height() - src_h)))
            src_rect = QRect(src_x, src_y, src_w, src_h).intersected(img_rect)

            if not src_rect.isEmpty() and src_rect.width() > 0 and src_rect.height() > 0:
                sub_img = base_image.copy(src_rect)
                painter.save()
                painter.setClipRect(lens_rect_f)
                painter.drawImage(lens_rect_f, sub_img, QRectF(sub_img.rect()))
                painter.restore()

        # Subtle neutral rectangular border (no colored/red marks or side badges)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 85), 1))
        painter.drawRect(lens_rect_f)

        inner_rect = lens_rect_f.adjusted(1.0, 1.0, -1.0, -1.0)
        if inner_rect.width() > 2 and inner_rect.height() > 2:
            painter.setPen(QPen(QColor(255, 255, 255, 110), 1))
            painter.drawRect(inner_rect)

        painter.restore()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.tool_type.value,
            "color": self.color,
            "stroke_width": self.stroke_width,
            "opacity": self.opacity,
            "zoom_factor": self.zoom_factor,
            "rect": (self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()),
        }



