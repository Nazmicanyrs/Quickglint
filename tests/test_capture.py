"""Tests for capture geometry, filters, and helpers."""

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage
from app.utils.helpers import apply_blur_to_region, apply_pixelate_to_region, clamp, normalize_rect


def test_normalize_rect():
    r1 = QRect(100, 100, -50, -50)
    norm = normalize_rect(r1)
    assert norm.width() == 50
    assert norm.height() == 50
    assert norm.x() == 50
    assert norm.y() == 50


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-5, 0, 10) == 0
    assert clamp(15, 0, 10) == 10


def test_filters():
    img = QImage(100, 100, QImage.Format.Format_ARGB32)
    img.fill(QColor(100, 150, 200))

    # Blur
    blurred = apply_blur_to_region(img, QRect(10, 10, 40, 40), radius=5)
    assert blurred.width() == 100
    assert blurred.height() == 100

    # Pixelate
    pixelated = apply_pixelate_to_region(img, QRect(20, 20, 50, 50), pixel_size=6)
    assert pixelated.width() == 100
    assert pixelated.height() == 100


def test_selection_overlay_inside_hit_test():
    from app.capture.selection_overlay import HandlePosition, SelectionOverlay
    from app.editor.history import HistoryManager
    from app.editor.tools import ToolManager
    from config.config_manager import ConfigManager
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    _ = QApplication.instance() or QApplication([])

    pixmap = QPixmap(500, 500)
    virtual_geo = QRect(0, 0, 500, 500)
    tm = ToolManager()
    hm = HistoryManager()
    cm = ConfigManager()

    overlay = SelectionOverlay(
        full_desktop_pixmap=pixmap,
        virtual_geometry=virtual_geo,
        tool_manager=tm,
        history_manager=hm,
        config_manager=cm,
        default_save_dir="",
    )

    overlay.selected_rect = QRect(100, 100, 200, 200)
    overlay._has_selection = True

    # Hit test inside
    handle = overlay._hit_test(QPoint(150, 150))
    assert handle == HandlePosition.INSIDE

    # Move rectangle translation test
    drag_start = QRect(overlay.selected_rect)
    drag_start.translate(50, 30)
    assert drag_start == QRect(150, 130, 200, 200)


def test_selection_overlay_measurement_hud_rendering():
    from app.capture.selection_overlay import SelectionOverlay
    from app.editor.history import HistoryManager
    from app.editor.tools import ToolManager
    from config.config_manager import ConfigManager
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    _ = QApplication.instance() or QApplication([])

    pixmap = QPixmap(1920, 1080)
    pixmap.fill(QColor(30, 40, 50))
    virtual_geo = QRect(0, 0, 1920, 1080)
    tm = ToolManager()
    hm = HistoryManager()
    cm = ConfigManager()

    overlay = SelectionOverlay(
        full_desktop_pixmap=pixmap,
        virtual_geometry=virtual_geo,
        tool_manager=tm,
        history_manager=hm,
        config_manager=cm,
        default_save_dir="",
    )

    overlay.selected_rect = QRect(200, 150, 800, 500)
    overlay._has_selection = True

    # Render HUD onto target image painter
    test_img = QImage(1920, 1080, QImage.Format.Format_ARGB32)
    test_img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(test_img)
    try:
        overlay._render_selection_measurement_hud(painter)
    finally:
        painter.end()

    assert not test_img.isNull()


def test_selection_overlay_session_capture_signals():
    from app.capture.selection_overlay import SelectionOverlay
    from app.editor.history import HistoryManager
    from app.editor.tools import ToolManager
    from config.config_manager import ConfigManager
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    _ = QApplication.instance() or QApplication([])

    pixmap = QPixmap(200, 200)
    pixmap.fill(QColor(10, 20, 30))
    virtual_geo = QRect(0, 0, 200, 200)
    tm = ToolManager()
    hm = HistoryManager()
    cm = ConfigManager()

    overlay = SelectionOverlay(
        full_desktop_pixmap=pixmap,
        virtual_geometry=virtual_geo,
        tool_manager=tm,
        history_manager=hm,
        config_manager=cm,
        default_save_dir="",
        session_capture_mode=True,
    )
    overlay.selected_rect = QRect(10, 10, 50, 50)
    overlay._has_selection = True

    captured_images = []
    overlay.session_image_captured.connect(lambda img: captured_images.append(img))

    overlay._complete_session_capture()
    assert len(captured_images) == 1
    assert not captured_images[0].isNull()
    assert captured_images[0].width() == 50
    assert captured_images[0].height() == 50




