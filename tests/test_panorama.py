"""Unit and integration tests for Panorama Capture (`app.panorama`)."""

from pathlib import Path
import cv2
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication

from app.panorama import (
    AlignmentMode,
    BlendingMode,
    FeatureDetectorType,
    MonitorInfo,
    MultiMonitorManager,
    PanoramaCaptureMode,
    PanoramaEditorDialog,
    PanoramaFrame,
    PanoramaStitcherEngine,
    StitchConfig,
)
from config.config_manager import ConfigManager


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _create_overlapping_textured_pair() -> tuple[QImage, QImage]:
    """Create a 900x400 rich textured scene and split it into two overlapping 550x400 frames (200px overlap)."""
    rng = np.random.default_rng(42)
    full = np.zeros((400, 900, 3), dtype=np.uint8)
    full[:, :] = (28, 36, 52)

    # Draw deterministic geometric landmarks across the entire width so ORB/SIFT find strong keypoints
    for i in range(65):
        cx = int(rng.integers(30, 870))
        cy = int(rng.integers(30, 370))
        r = int(rng.integers(8, 28))
        col = (int(rng.integers(80, 255)), int(rng.integers(80, 255)), int(rng.integers(80, 255)))
        cv2.circle(full, (cx, cy), r, col, -1)
        cv2.rectangle(full, (cx - r // 2, cy - r // 2), (cx + r, cy + r), (255, 255, 255), 2)

    left_bgr = full[:, :550].copy()
    # Slightly darken right frame to also test exposure compensation
    right_bgr = np.clip(full[:, 350:].astype(np.float32) * 0.90, 0, 255).astype(np.uint8)

    return MultiMonitorManager.bgr_to_qimage(left_bgr), MultiMonitorManager.bgr_to_qimage(right_bgr)


class TestPanoramaCaptureModule:
    """Tests for Multi-Monitor Layout & OpenCV Panorama Stitching Engine."""

    def test_detect_monitors_returns_valid_info(self, qapp):
        monitors = MultiMonitorManager.detect_monitors()
        assert len(monitors) >= 1
        m0 = monitors[0]
        assert m0.physical_width > 0
        assert m0.physical_height > 0
        assert m0.orientation in ("horizontal", "vertical")
        assert "Ekran" in m0.display_label

    def test_non_overlapping_monitors_use_desktop_coordinates_without_feature_matching(self, qapp):
        img1 = QImage(400, 300, QImage.Format.Format_RGBA8888)
        img1.fill(QColor("#1D4ED8"))
        img2 = QImage(400, 300, QImage.Format.Format_RGBA8888)
        img2.fill(QColor("#047857"))

        mon1 = MonitorInfo(index=0, name="DP-1", logical_geometry=QRect(0, 0, 400, 300), physical_width=400, physical_height=300, scale_factor=1.0, is_primary=True)
        mon2 = MonitorInfo(index=1, name="HDMI-1", logical_geometry=QRect(400, 0, 400, 300), physical_width=400, physical_height=300, scale_factor=1.0)

        f1 = PanoramaFrame(frame_id="m1", title="Mon 1", image=img1, monitor_info=mon1, logical_rect=mon1.logical_geometry)
        f2 = PanoramaFrame(frame_id="m2", title="Mon 2", image=img2, monitor_info=mon2, logical_rect=mon2.logical_geometry)

        engine = PanoramaStitcherEngine()
        cfg = StitchConfig(mode=PanoramaCaptureMode.FULL_DESKTOP, auto_crop=True)
        res = engine.stitch([f1, f2], config=cfg)

        assert res.success is True
        assert res.detector_used == "desktop_coordinates"
        assert res.width == 800
        assert res.height == 300

    def test_opencv_orb_and_sift_manual_stitching_on_overlapping_frames(self, qapp):
        img_left, img_right = _create_overlapping_textured_pair()
        f1 = PanoramaFrame(frame_id="f1", title="Left", image=img_left)
        f2 = PanoramaFrame(frame_id="f2", title="Right", image=img_right)

        engine = PanoramaStitcherEngine()

        # Test ORB + Multi-band blending
        cfg_orb = StitchConfig(
            mode=PanoramaCaptureMode.MANUAL_STITCHING,
            detector=FeatureDetectorType.ORB,
            alignment=AlignmentMode.HOMOGRAPHY,
            blending=BlendingMode.MULTIBAND,
            exposure_compensation=True,
            auto_crop=True,
        )
        res_orb = engine.stitch([f1, f2], config=cfg_orb)
        assert res_orb.success is True
        assert res_orb.image is not None and not res_orb.image.isNull()
        assert 780 <= res_orb.width <= 980
        assert len(res_orb.pair_matches) == 1
        assert res_orb.pair_matches[0].inliers >= 6

        # Test SIFT + Feather blending
        cfg_sift = StitchConfig(
            mode=PanoramaCaptureMode.MANUAL_STITCHING,
            detector=FeatureDetectorType.SIFT,
            alignment=AlignmentMode.AFFINE,
            blending=BlendingMode.FEATHER,
            exposure_compensation=True,
            auto_crop=True,
        )
        res_sift = engine.stitch([f1, f2], config=cfg_sift)
        assert res_sift.success is True
        assert 780 <= res_sift.width <= 980

    def test_panorama_editor_dialog_reordering_and_zoom(self, qapp, tmp_path):
        cm = ConfigManager(custom_path=tmp_path / "settings.json")
        img_l, img_r = _create_overlapping_textured_pair()
        frames = [
            PanoramaFrame(frame_id="a", title="Frame A", image=img_l),
            PanoramaFrame(frame_id="b", title="Frame B", image=img_r),
        ]
        dlg = PanoramaEditorDialog(
            config_manager=cm,
            initial_frames=frames,
            initial_mode=PanoramaCaptureMode.MANUAL_STITCHING,
        )
        dlg.cancel_stitching()

        assert dlg.frame_list.count() == 2
        dlg.frame_list.setCurrentRow(1)
        dlg.move_selected_frame_up()
        dlg.cancel_stitching()
        assert dlg.frames[0].frame_id == "b"

        # Preview canvas zoom controls
        dlg.preview_canvas.set_image(img_l, fit_to_view=True)
        z0 = dlg.preview_canvas.zoom_factor
        dlg.preview_canvas.zoom_in()
        assert dlg.preview_canvas.zoom_factor > z0
        dlg.preview_canvas.zoom_100()
        assert abs(dlg.preview_canvas.zoom_factor - 1.0) < 1e-4
        dlg.close()


