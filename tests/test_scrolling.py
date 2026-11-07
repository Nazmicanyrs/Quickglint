"""Unit tests for Scrolling Screenshot, Overlap Detection, Container Isolation, and Image Stitching."""

import numpy as np
from PIL import Image
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from app.scrolling.aligner import ImageAligner
from app.scrolling.container_detector import ScrollContainerDetector
from app.scrolling.controller import ScrollingCaptureController
from app.scrolling.detector import ScrollDetector
from app.scrolling.overlap import find_vertical_overlap
from app.scrolling.stitcher import ImageStitcher


def create_synthetic_frame(start_num: int, height: int = 200, width: int = 300) -> QImage:
    """Create a synthetic image with distinct horizontal rows of varying shades for deterministic testing."""
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 255, 255))
    painter = QPainter(img)

    for i in range(height):
        val = (start_num + i * 2) % 255
        painter.setPen(QColor(val, val, val))
        painter.drawLine(0, i, width, i)

    painter.end()
    return img


def create_multi_column_frame(start_num: int, height: int = 200, width: int = 400) -> QImage:
    """Create a 3-column frame: Left fixed (80px), Center scrolling (240px), Right fixed (80px)."""
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(20, 20, 20))
    painter = QPainter(img)

    # Left fixed sidebar (always same color/text)
    painter.fillRect(0, 0, 80, height, QColor(40, 40, 40))
    # Right fixed sidebar (always same color/text)
    painter.fillRect(320, 0, 80, height, QColor(40, 40, 40))

    # Center scrolling feed
    for i in range(height):
        val = (start_num + i * 3) % 255
        painter.setPen(QColor(val, val, val))
        painter.drawLine(80, i, 319, i)

    painter.end()
    return img


def test_overlap_detection():
    # Frame 1: rows 0 to 200
    frame1 = create_synthetic_frame(0, height=200, width=100)
    # Frame 2: scrolled by 50px
    frame2 = create_synthetic_frame(50 * 2, height=200, width=100)

    dy = find_vertical_overlap(frame1, frame2)
    assert 40 <= dy <= 60


def test_duplicate_removal():
    frame1 = create_synthetic_frame(0, height=100, width=100)
    # Exactly identical frame (0px movement)
    frame2 = create_synthetic_frame(0, height=100, width=100)

    dy = find_vertical_overlap(frame1, frame2)
    assert dy == 0


def test_unrelated_frame_is_rejected_instead_of_receiving_a_guessed_displacement():
    """A bad registration must never create a synthetic one-third-frame slice."""
    rng = np.random.default_rng(42)
    previous = rng.integers(0, 255, (180, 160), dtype=np.uint8)
    current = rng.integers(0, 255, (180, 160), dtype=np.uint8)

    result = ImageAligner.align_frames(previous, current)

    assert result.is_valid is False
    assert result.dy == 0


def test_single_unambiguous_strip_can_align_a_dynamic_feed():
    """Dynamic cards may invalidate some strips without ending the scroll."""
    frame1 = create_synthetic_frame(0, height=200, width=160)
    frame2 = create_synthetic_frame(50 * 2, height=200, width=160)
    result = ImageAligner.align_frames(frame1, frame2)

    assert result.is_valid is True
    assert 40 <= result.dy <= 60


def test_alignment_reports_high_confidence_for_a_consistent_overlap():
    frame1 = create_synthetic_frame(0, height=220, width=180)
    frame2 = create_synthetic_frame(60 * 2, height=220, width=180)

    result = ImageAligner.align_frames(frame1, frame2)

    assert result.is_valid is True
    assert 50 <= result.dy <= 70
    assert result.confidence >= 0.80


def test_multi_column_container_detection():
    frame1 = create_multi_column_frame(0, height=200, width=400)
    frame2 = create_multi_column_frame(40 * 3, height=200, width=400)

    layout = ScrollContainerDetector.detect_layout([frame1, frame2])
    assert layout.is_multi_column is True
    assert layout.left_fixed_width >= 60
    assert layout.right_fixed_width >= 60
    assert layout.scroll_x_start >= 60
    assert layout.scroll_x_end <= 340


def test_multi_column_stitching():
    frame1 = create_multi_column_frame(0, height=150, width=400)
    frame2 = create_multi_column_frame(40 * 3, height=150, width=400)
    frame3 = create_multi_column_frame(80 * 3, height=150, width=400)

    stitcher = ImageStitcher()
    stitched = stitcher.stitch([frame1, frame2, frame3])

    assert stitched is not None
    # Fixed sidebars are intentionally removed from a scrolling capture.
    assert stitched.width() == 240
    assert stitched.height() > 200


def test_vertical_stitching():
    frame1 = create_synthetic_frame(0, height=100, width=80)
    frame2 = create_synthetic_frame(50 * 2, height=100, width=80)
    frame3 = create_synthetic_frame(100 * 2, height=100, width=80)

    stitcher = ImageStitcher()
    stitched = stitcher.stitch([frame1, frame2, frame3])

    assert stitched is not None
    assert stitched.width() == 80
    assert stitched.height() > 150


def test_stitcher_does_not_leave_blank_space_for_discarded_frames():
    frame1 = create_synthetic_frame(0, height=100, width=80)
    frame2 = create_synthetic_frame(100, height=100, width=80)
    stitched = ImageStitcher().stitch([frame1, frame2], precalculated_displacements=[100, 0])

    assert stitched is not None
    assert stitched.height() == 100


def test_end_detection():
    detector = ScrollDetector(consecutive_no_change_limit=2)
    frame = create_synthetic_frame(0, height=100, width=80)

    stop1, _, _ = detector.analyze_frame(frame)
    assert stop1 is False

    # First no change
    stop2, _, _ = detector.analyze_frame(frame)
    assert stop2 is False

    # Second no change triggers end detection
    stop3, _, reason = detector.analyze_frame(frame)
    assert stop3 is True
    assert "End of scroll" in reason


def test_no_change_detection():
    detector = ScrollDetector()
    frame = create_synthetic_frame(10, height=100, width=80)

    detector.analyze_frame(frame)
    # Consecutive identical frame
    _, dy, _ = detector.analyze_frame(frame)
    assert dy == 0


def test_max_capture_limit():
    detector = ScrollDetector(max_captures=3)
    frame1 = create_synthetic_frame(0, height=100, width=80)
    frame2 = create_synthetic_frame(20, height=100, width=80)
    frame3 = create_synthetic_frame(40, height=100, width=80)

    detector.analyze_frame(frame1)
    detector.analyze_frame(frame2)
    should_stop, _, reason = detector.analyze_frame(frame3)
    assert should_stop is True
    assert "Maximum capture limit" in reason


def test_max_height_limit():
    detector = ScrollDetector(max_height=220)
    frame1 = create_synthetic_frame(0, height=100, width=80)
    frame2 = create_synthetic_frame(50 * 2, height=100, width=80)
    frame3 = create_synthetic_frame(100 * 2, height=100, width=80)
    frame4 = create_synthetic_frame(150 * 2, height=100, width=80)

    detector.analyze_frame(frame1)
    detector.analyze_frame(frame2)
    detector.analyze_frame(frame3)
    should_stop, _, reason = detector.analyze_frame(frame4)
    assert should_stop is True
    assert detector.current_height >= 220


def test_controller_instantiation(qapp):
    """Verify ScrollingCaptureController initializes and connects HUD signals cleanly."""
    controller = ScrollingCaptureController(
        region=QRect(0, 0, 800, 600),
        on_complete_callback=lambda img: None,
        on_cancel_callback=lambda: None,
    )
    assert controller is not None
    assert controller.progress_hud is not None
    assert controller.scroller.step_clicks == 3
    assert controller.auto_timer.interval() == 1050
    assert callable(controller._capture_settled_frame)

