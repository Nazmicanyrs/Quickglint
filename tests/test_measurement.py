"""Comprehensive test suite for Quickglint Professional Measurement Studio."""

import json
import math
from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.measurement.canvas import MeasurementCanvas
from app.measurement.engine import MeasurementEngine
from app.measurement.models import ColorInfo, MeasurementItem, MeasurementType, SnapMode
from app.measurement.studio_dialog import MeasurementStudioWindow


@pytest.fixture
def sample_test_image() -> QImage:
    """Creates a deterministic 800x600 test image with colored quadrants."""
    img = QImage(800, 600, QImage.Format.Format_RGB32)
    img.fill(QColor(20, 30, 40))

    # Paint red block at (50, 50, 100, 100)
    for y in range(50, 150):
        for x in range(50, 150):
            img.setPixelColor(x, y, QColor(255, 0, 0))

    # Paint green block at (200, 200, 100, 100)
    for y in range(200, 300):
        for x in range(200, 300):
            img.setPixelColor(x, y, QColor(0, 255, 0))

    return img


# 1. Distance Calculation
def test_distance_calculation():
    p1 = (0.0, 0.0)
    p2 = (300.0, 400.0)
    res = MeasurementEngine.calculate_distance(p1, p2)
    assert math.isclose(res["distance"], 500.0, abs_tol=1e-3)
    assert math.isclose(res["dx"], 300.0, abs_tol=1e-3)
    assert math.isclose(res["dy"], 400.0, abs_tol=1e-3)
    assert math.isclose(res["angle_deg"], 53.13, abs_tol=0.1)


# 2. Horizontal & Vertical Measurements
def test_horizontal_and_vertical():
    # Horizontal
    res_h = MeasurementEngine.calculate_horizontal((100.0, 50.0), (450.0, 200.0))
    assert math.isclose(res_h["distance"], 350.0, abs_tol=1e-3)
    assert math.isclose(res_h["dx"], 350.0, abs_tol=1e-3)
    assert res_h["dy"] == 0.0

    # Vertical
    res_v = MeasurementEngine.calculate_vertical((100.0, 50.0), (300.0, 450.0))
    assert math.isclose(res_v["distance"], 400.0, abs_tol=1e-3)
    assert math.isclose(res_v["dy"], 400.0, abs_tol=1e-3)
    assert res_v["dx"] == 0.0


# 3. Rectangle Calculation & Bounding Box
def test_rectangle_calculation():
    p1 = (400.0, 300.0)
    p2 = (100.0, 100.0)  # Inverted order
    res = MeasurementEngine.calculate_rectangle(p1, p2)

    assert res["left"] == 100.0
    assert res["right"] == 400.0
    assert res["top"] == 100.0
    assert res["bottom"] == 300.0
    assert res["width"] == 300.0
    assert res["height"] == 200.0
    assert res["area"] == 60000.0
    assert res["center_x"] == 250.0
    assert res["center_y"] == 200.0


# 4. 3-Point Angle Calculation
def test_angle_3pt_calculation():
    # 90-degree right angle (Vertex at B)
    pA = (100.0, 0.0)
    pB = (0.0, 0.0)
    pC = (0.0, 100.0)
    res = MeasurementEngine.calculate_angle_3pt(pA, pB, pC)
    assert math.isclose(res["angle_deg"], 90.0, abs_tol=1e-2)
    assert math.isclose(res["supplementary_deg"], 90.0, abs_tol=1e-2)

    # 180-degree straight line
    pA = (-100.0, 0.0)
    pB = (0.0, 0.0)
    pC = (100.0, 0.0)
    res2 = MeasurementEngine.calculate_angle_3pt(pA, pB, pC)
    assert math.isclose(res2["angle_deg"], 180.0, abs_tol=1e-2)

    # 45-degree angle
    pA = (100.0, 0.0)
    pB = (0.0, 0.0)
    pC = (100.0, 100.0)
    res3 = MeasurementEngine.calculate_angle_3pt(pA, pB, pC)
    assert math.isclose(res3["angle_deg"], 45.0, abs_tol=1e-2)


# 5. Pixel Color Sampling (HEX, RGB, HSL)
def test_pixel_color_sampling(sample_test_image):
    # Sample pure Red pixel at (100, 100)
    col_red = MeasurementEngine.sample_pixel_color(sample_test_image, 100, 100)
    assert col_red.hex_value == "#FF0000"
    assert col_red.r == 255 and col_red.g == 0 and col_red.b == 0
    assert math.isclose(col_red.h_deg, 0.0, abs_tol=1.0)
    assert math.isclose(col_red.s_pct, 100.0, abs_tol=1.0)
    assert math.isclose(col_red.l_pct, 50.0, abs_tol=1.0)

    # Sample pure Green pixel at (250, 250)
    col_green = MeasurementEngine.sample_pixel_color(sample_test_image, 250, 250)
    assert col_green.hex_value == "#00FF00"
    assert col_green.g == 255

    # Out of bounds fallback
    col_oob = MeasurementEngine.sample_pixel_color(sample_test_image, -10, 9999)
    assert col_oob.hex_value == "#000000"


# 6. Precision Snapping Engine
def test_snap_engine():
    w, h = 1920, 1080

    # None snap
    assert MeasurementEngine.snap_point((123.45, 67.89), w, h, SnapMode.NONE) == (123.45, 67.89)

    # Pixel snap
    assert MeasurementEngine.snap_point((123.45, 67.89), w, h, SnapMode.PIXEL) == (123.0, 68.0)

    # Grid snap (16px)
    assert MeasurementEngine.snap_point((34.0, 47.0), w, h, SnapMode.GRID, grid_size=16) == (32.0, 48.0)
    assert MeasurementEngine.snap_point((25.0, 25.0), w, h, SnapMode.GRID, grid_size=8) == (24.0, 24.0)

    # Center snap (w/2 = 960, h/2 = 540)
    assert MeasurementEngine.snap_point((962.0, 538.0), w, h, SnapMode.CENTER, snap_tolerance=5.0) == (960.0, 540.0)

    # Edge snap
    assert MeasurementEngine.snap_point((3.0, 1078.0), w, h, SnapMode.EDGE, snap_tolerance=5.0) == (0.0, float(h - 1))


# 7. Formats & Export (CSS, JSON, Markdown)
def test_measurement_item_formats():
    item = MeasurementItem(
        name="Header Card",
        mtype=MeasurementType.RECTANGLE,
        points=[(10.0, 20.0), (310.0, 220.0)],
        data={"width": 300.0, "height": 200.0, "left": 10.0, "top": 20.0, "area": 60000.0},
    )

    # Summary text
    assert "300 × 200 px" in item.to_summary_text()

    # CSS
    css = item.to_css()
    assert "width: 300.0px;" in css
    assert "height: 200.0px;" in css
    assert "left: 10.0px;" in css

    # Markdown
    md = item.to_markdown()
    assert "### Header Card" in md
    assert "| `rectangle` |" in md

    # JSON
    j = json.loads(item.to_json())
    assert j["name"] == "Header Card"
    assert j["type"] == "rectangle"
    assert j["data"]["width"] == 300.0


# 8. Canvas Coordinate Transformation
def test_canvas_coordinate_transforms(sample_test_image):
    canvas = MeasurementCanvas(sample_test_image)
    canvas.resize(1000, 800)
    canvas.pan_offset = QPointF(50.0, 50.0)
    canvas.zoom_factor = 2.0

    # Image point (100, 100) -> Widget point: (100*2 + 50, 100*2 + 50) = (250, 250)
    wpt = canvas.image_to_widget((100.0, 100.0))
    assert wpt.x() == 250.0
    assert wpt.y() == 250.0

    # Widget point (250, 250) -> Image point (100, 100)
    ix, iy = canvas.widget_to_image(QPointF(250.0, 250.0))
    assert math.isclose(ix, 100.0, abs_tol=1e-3)
    assert math.isclose(iy, 100.0, abs_tol=1e-3)


# 9. Canvas Item Creation & Export Overlays
def test_canvas_export_overlays(sample_test_image):
    canvas = MeasurementCanvas(sample_test_image)
    item = MeasurementItem(
        mtype=MeasurementType.DISTANCE,
        points=[(10.0, 10.0), (100.0, 100.0)],
        data=MeasurementEngine.calculate_distance((10.0, 10.0), (100.0, 100.0)),
    )
    canvas.measurements.append(item)

    out_img = canvas.export_image_with_overlays()
    assert not out_img.isNull()
    assert out_img.width() == sample_test_image.width()
    assert out_img.height() == sample_test_image.height()


# 10. Studio Window Initialization & Tool Switching
def test_studio_window_initialization(sample_test_image):
    win = MeasurementStudioWindow(image=sample_test_image)
    assert win.canvas is not None
    assert win.canvas.image.width() == 800
    assert win.canvas.image.height() == 600

    # Switch tools
    win._select_tool(MeasurementType.RECTANGLE)
    assert win.canvas.active_tool == MeasurementType.RECTANGLE

    # Add item
    item = MeasurementItem(
        mtype=MeasurementType.RECTANGLE,
        points=[(0.0, 0.0), (50.0, 50.0)],
        data=MeasurementEngine.calculate_rectangle((0.0, 0.0), (50.0, 50.0)),
    )
    win.canvas.measurements.append(item)
    win._refresh_measurements_list()
    assert win.items_list.count() == 1
    assert win.list_badge.text() == "1"

    # Test clear
    win._on_clear_all_measurements()
    assert win.items_list.count() == 0
    assert win.list_badge.text() == "0"
    win.close()

