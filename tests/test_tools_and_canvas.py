"""Tests for ToolManager, Canvas interaction, and Text input."""

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from app.editor.canvas import AnnotationCanvas
from app.editor.history import HistoryManager
from app.editor.objects import MagnifierObject, TextObject
from app.editor.tools import ToolManager
from app.utils.constants import ToolType


def test_tool_manager():
    tm = ToolManager()
    assert tm.active_tool == ToolType.SELECT
    assert tm.stroke_width == 3

    tm.active_tool = ToolType.PEN
    assert tm.active_tool == ToolType.PEN

    tm.color = "#0088FF"
    assert tm.color == "#0088FF"

    tm.stroke_width = 8
    assert tm.stroke_width == 8


def test_canvas_annotation_layer():
    base_img = QImage(300, 300, QImage.Format.Format_RGBA8888)
    base_img.fill(QColor(240, 240, 240))

    tm = ToolManager()
    history = HistoryManager()
    canvas = AnnotationCanvas(base_img, tm, history)

    # Add text object
    text_obj = TextObject(QPoint(20, 20), "Test Watermark", color="#FF0000", font_size=16)
    canvas.objects.append(text_obj)

    annotated = canvas.get_annotated_image()
    assert annotated.width() == 300
    assert annotated.height() == 300
    assert annotated.format() == QImage.Format.Format_RGBA8888


def test_advanced_color_panel():
    from app.ui.color_panel import AdvancedColorPopup, ColorSwatchButton
    from PySide6.QtWidgets import QApplication

    _ = QApplication.instance() or QApplication([])

    tm = ToolManager()
    tm.color = "#EF4444"

    btn = ColorSwatchButton("#EF4444", size=22, is_selected=True)
    assert btn.color_hex == "#EF4444"

    popup = AdvancedColorPopup(tm)
    popup._select_color("#3B82F6")
    assert tm.color == "#3B82F6"
    assert popup.hex_input.text() == "#3B82F6"


def test_canvas_magnifier_tool_interaction():
    base_img = QImage(200, 200, QImage.Format.Format_RGBA8888)
    base_img.fill(QColor(30, 60, 90))

    tm = ToolManager(magnifier_zoom=2.0)
    tm.active_tool = ToolType.MAGNIFIER
    tm.magnifier_zoom = 2.5
    assert tm.magnifier_zoom == 2.5

    history = HistoryManager()
    canvas = AnnotationCanvas(base_img, tm, history)

    press_evt = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(40, 40),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move_evt = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(120, 120),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    rel_evt = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(120, 120),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    canvas.mousePressEvent(press_evt)
    canvas.mouseMoveEvent(move_evt)
    canvas.mouseReleaseEvent(rel_evt)

    assert len(canvas.objects) == 1
    obj = canvas.objects[0]
    assert isinstance(obj, MagnifierObject)
    assert obj.zoom_factor == 2.5
    assert obj.rect.width() >= 80
    assert obj.rect.height() >= 80

    # Test moving the square magnifier box manually with the mouse
    grab_evt = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(80, 80),
        QPointF(80, 80),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    drag_evt = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(110, 100),
        QPointF(110, 100),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    drop_evt = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(110, 100),
        QPointF(110, 100),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mousePressEvent(grab_evt)
    canvas.mouseMoveEvent(drag_evt)
    canvas.mouseReleaseEvent(drop_evt)

    # Still 1 object (moved, not duplicated), and its top-left moved from (40,40) to (70,60)
    assert len(canvas.objects) == 1
    assert obj.rect.topLeft() == QPoint(70, 60)

    annotated = canvas.get_annotated_image()
    assert not annotated.isNull()




