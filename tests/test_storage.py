"""Tests for storage service, format handling, and file naming."""

import tempfile
from pathlib import Path
from PySide6.QtGui import QColor, QImage
from app.services.storage_service import StorageService
from app.utils.helpers import generate_timestamp_filename


def test_generate_timestamp_filename():
    name_png = generate_timestamp_filename("Screenshot", "png")
    assert name_png.startswith("Screenshot_")
    assert name_png.endswith(".png")

    name_jpg = generate_timestamp_filename("Shot", "jpg")
    assert name_jpg.startswith("Shot_")
    assert name_jpg.endswith(".jpg")


def test_save_image_formats():
    # Create test 100x100 QImage
    img = QImage(100, 100, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 0, 0, 255))

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # PNG
        png_path = tmp_path / "test.png"
        success, err = StorageService.save_image(img, png_path)
        assert success is True
        assert err is None
        assert png_path.exists()
        assert png_path.stat().st_size > 0

        # JPG
        jpg_path = tmp_path / "test.jpg"
        success, err = StorageService.save_image(img, jpg_path, quality=90)
        assert success is True
        assert err is None
        assert jpg_path.exists()
        assert jpg_path.stat().st_size > 0

        # WEBP
        webp_path = tmp_path / "test.webp"
        success, err = StorageService.save_image(img, webp_path, quality=85)
        assert success is True
        assert err is None
        assert webp_path.exists()
        assert webp_path.stat().st_size > 0

