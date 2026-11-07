"""Tests for annotation objects, rendering, and serialization."""

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPainter
from app.editor.objects import (
    ArrowObject,
    BlurObject,
    EllipseObject,
    HighlighterObject,
    LineObject,
    MagnifierObject,
    PenObject,
    PixelateObject,
    RectangleObject,
    TextObject,
)
from app.utils.constants import ToolType


def test_objects_to_dict_and_render():
    base_img = QImage(200, 200, QImage.Format.Format_RGBA8888)
    base_img.fill(QColor(255, 255, 255))

    target_img = QImage(200, 200, QImage.Format.Format_RGBA8888)
    target_img.fill(QColor(255, 255, 255))
    painter = QPainter(target_img)

    # 1. Line
    line = LineObject(QPoint(10, 10), QPoint(50, 50), color="#FF0000", stroke_width=2)
    line_dict = line.to_dict()
    assert line_dict["type"] == ToolType.LINE.value
    assert line_dict["color"] == "#FF0000"
    line.render(painter, base_img)

    # 2. Arrow
    arrow = ArrowObject(QPoint(10, 10), QPoint(80, 80), color="#00FF00", stroke_width=3)
    arrow_dict = arrow.to_dict()
    assert arrow_dict["type"] == ToolType.ARROW.value
    arrow.render(painter, base_img)

    # 3. Rectangle
    rect = RectangleObject(QRect(20, 20, 40, 40), color="#0000FF")
    rect_dict = rect.to_dict()
    assert rect_dict["type"] == ToolType.RECTANGLE.value
    rect.render(painter, base_img)

    # 4. Ellipse
    ellipse = EllipseObject(QRect(30, 30, 30, 30), color="#FFFF00")
    ellipse_dict = ellipse.to_dict()
    assert ellipse_dict["type"] == ToolType.ELLIPSE.value
    ellipse.render(painter, base_img)

    # 5. Pen
    pen = PenObject([QPoint(1, 1), QPoint(5, 10), QPoint(20, 30)], color="#FF00FF")
    pen_dict = pen.to_dict()
    assert pen_dict["type"] == ToolType.PEN.value
    assert len(pen_dict["points"]) == 3
    pen.render(painter, base_img)

    # 6. Text
    text = TextObject(QPoint(50, 50), "Hello Quickglint", color="#111111", font_size=14)
    text_dict = text.to_dict()
    assert text_dict["type"] == ToolType.TEXT.value
    assert text_dict["text"] == "Hello Quickglint"
    text.render(painter, base_img)

    # 7. Blur & Pixelate
    blur = BlurObject(QRect(10, 10, 50, 50), radius=10)
    blur_dict = blur.to_dict()
    assert blur_dict["type"] == ToolType.BLUR.value
    blur.render(painter, base_img)

    pixelate = PixelateObject(QRect(60, 60, 40, 40), pixel_size=8)
    pix_dict = pixelate.to_dict()
    assert pix_dict["type"] == ToolType.PIXELATE.value
    pixelate.render(painter, base_img)

    # 8. Magnifier
    magnifier = MagnifierObject(QRect(70, 70, 60, 60), zoom_factor=2.5, color="#38BDF8", stroke_width=3)
    mag_dict = magnifier.to_dict()
    assert mag_dict["type"] == ToolType.MAGNIFIER.value
    assert mag_dict["zoom_factor"] == 2.5
    assert mag_dict["rect"] == (70, 70, 60, 60)
    magnifier.render(painter, base_img)

    painter.end()

