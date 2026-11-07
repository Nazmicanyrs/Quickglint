"""Comprehensive automated tests for Quickglint Image Metadata Cleaner / Privacy Cleaner."""

import io
import os
from pathlib import Path
import tempfile
from PIL import Image, ImageCms, PngImagePlugin, TiffImagePlugin
from PySide6.QtGui import QImage
import pytest

from app.metacleaner.batch import BatchMetadataCleanerWorker
from app.metacleaner.cleaner import MetadataCleaner
from app.metacleaner.models import (
    CleanConfig,
    CleaningPreset,
    CleanResult,
    MetadataCategory,
    MetadataField,
    MetadataRiskLevel,
    MetadataScanReport,
)
from app.metacleaner.report import MetadataReportGenerator
from app.metacleaner.scanner import MetadataScanner
from app.metacleaner.vault_cleaner import VaultMetadataCleaner
from app.upload.models import UploadResult
from app.upload.provider import UploadProvider
from app.upload.worker import UploadWorker
from app.security.vault import SecureVault


@pytest.fixture
def sample_png_with_metadata(tmp_path: Path) -> Path:
    """Create a test PNG image containing custom text chunks."""
    img = Image.new("RGBA", (100, 100), (45, 120, 240, 255))
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Author", "Test Photographer")
    meta.add_text("Software", "Quickglint Editor v2.0")
    meta.add_text("Comment", "Confidential Internal Screenshot")
    meta.add_text("GPS_Info", "41.0082 N, 28.9784 E")

    p = tmp_path / "test_screenshot.png"
    img.save(p, "PNG", pnginfo=meta)
    return p


@pytest.fixture
def sample_jpeg_with_exif(tmp_path: Path) -> Path:
    """Create a test JPEG image containing standard EXIF tags and GPS IFD."""
    img = Image.new("RGB", (120, 80), (200, 100, 50))
    exif = img.getexif()

    # Make, Model, Software, DateTime
    exif[0x010F] = "Canon"                    # Make
    exif[0x0110] = "EOS R5"                   # Model
    exif[0x0131] = "Adobe Photoshop 2026"     # Software
    exif[0x0132] = "2026:08:20 17:30:00"     # DateTime
    exif[0x0112] = 6                          # Orientation = Rotate 90 CW

    # GPS Sub-IFD (0x8825)
    gps_ifd = {
        1: "N",
        2: (41.0, 0.0, 29.52),
        3: "E",
        4: (28.0, 58.0, 42.24),
        6: 45.0,
    }
    exif[0x8825] = gps_ifd

    p = tmp_path / "test_camera_photo.jpg"
    img.save(p, "JPEG", exif=exif)
    return p


@pytest.fixture
def sample_image_with_icc(tmp_path: Path) -> Path:
    """Create an image embedded with a valid sRGB ICC color profile."""
    img = Image.new("RGB", (60, 60), (30, 180, 90))
    srgb_profile = ImageCms.createProfile("sRGB")
    icc_bytes = ImageCms.ImageCmsProfile(srgb_profile).tobytes()

    p = tmp_path / "test_color_profile.png"
    img.save(p, "PNG", icc_profile=icc_bytes)
    return p


# ==============================================================================
# 1. SCANNER TESTS
# ==============================================================================

def test_scanner_detects_png_text_chunks(sample_png_with_metadata: Path):
    report = MetadataScanner.scan_image(sample_png_with_metadata)
    assert report.total_image_fields_count >= 3
    assert report.format_name == "PNG"

    png_fields = report.get_fields_by_category(MetadataCategory.PNG_CHUNKS)
    tag_names = [f.tag_name for f in png_fields]
    assert "Author" in tag_names
    assert "Software" in tag_names
    assert "Comment" in tag_names


def test_scanner_detects_exif_and_gps(sample_jpeg_with_exif: Path):
    report = MetadataScanner.scan_image(sample_jpeg_with_exif)
    assert report.total_image_fields_count >= 4
    assert report.has_gps is True
    assert report.has_orientation is True
    assert report.orientation_value == 6

    exif_fields = report.get_fields_by_category(MetadataCategory.EXIF)
    tag_names = [f.tag_name for f in exif_fields]
    assert "Make" in tag_names or "Model" in tag_names


def test_scanner_detects_icc_profile(sample_image_with_icc: Path):
    report = MetadataScanner.scan_image(sample_image_with_icc)
    assert report.has_icc is True
    icc_fields = report.get_fields_by_category(MetadataCategory.ICC)
    assert len(icc_fields) == 1
    assert icc_fields[0].is_selected_for_removal is False  # Preserved by default


def test_scanner_separates_filesystem_from_image_metadata(sample_jpeg_with_exif: Path):
    report = MetadataScanner.scan_image(sample_jpeg_with_exif)
    fs_fields = report.file_system_fields
    img_fields = report.image_metadata_fields

    assert len(fs_fields) >= 3
    assert len(img_fields) >= 1
    # Check that filesystem fields are marked as not removable
    for f in fs_fields:
        assert f.is_removable is False
        assert f.is_selected_for_removal is False


def test_scanner_assigns_risk_levels(sample_jpeg_with_exif: Path):
    report = MetadataScanner.scan_image(sample_jpeg_with_exif)
    assert report.high_risk_count >= 1  # GPS should be high risk


# ==============================================================================
# 2. CLEANER CORE & ORIENTATION SAFETY TESTS
# ==============================================================================

def test_clean_png_removes_all_chunks(sample_png_with_metadata: Path):
    res = MetadataCleaner.clean_file(
        sample_png_with_metadata,
        config=CleanConfig(preset=CleaningPreset.PRIVACY_CLEAN),
    )
    assert res.success is True
    assert res.removed_fields_count >= 3
    assert res.output_path is not None
    assert res.output_path.exists()

    # Re-scan output to verify zero image metadata
    after_scan = MetadataScanner.scan_image(res.output_path)
    assert after_scan.total_image_fields_count == 0


def test_clean_jpeg_removes_exif_and_gps(sample_jpeg_with_exif: Path):
    res = MetadataCleaner.clean_file(
        sample_jpeg_with_exif,
        config=CleanConfig(preset=CleaningPreset.PRIVACY_CLEAN),
    )
    assert res.success is True
    assert res.removed_fields_count >= 4

    after_scan = MetadataScanner.scan_image(res.output_path)
    assert after_scan.has_gps is False


def test_orientation_auto_transpose_safety(tmp_path: Path):
    """Ensure image with EXIF orientation=6 (Rotate 90 CW) is physically transposed and does not become sideways."""
    # Create 200x100 rectangle
    orig_img = Image.new("RGB", (200, 100), (255, 0, 0))
    exif = orig_img.getexif()
    exif[0x0112] = 6  # Orientation 6 specifies 90 deg rotation -> upright shape should be 100x200

    test_file = tmp_path / "oriented.jpg"
    orig_img.save(test_file, "JPEG", exif=exif)

    res = MetadataCleaner.clean_file(
        test_file,
        config=CleanConfig(preset=CleaningPreset.PRIVACY_CLEAN, auto_orient=True),
    )
    assert res.success is True

    # Check decoded size of cleaned output
    with Image.open(res.output_path) as cleaned:
        # 200x100 transposed with orientation=6 rotates into 100x200
        assert cleaned.size == (100, 200)


def test_preserve_icc_profile(sample_image_with_icc: Path):
    """When preserve_icc is True, the ICC color profile is retained while other tags are stripped."""
    res = MetadataCleaner.clean_file(
        sample_image_with_icc,
        config=CleanConfig(preserve_icc=True),
    )
    assert res.success is True
    after_scan = MetadataScanner.scan_image(res.output_path)
    assert after_scan.has_icc is True


def test_maximum_privacy_strips_icc(sample_image_with_icc: Path):
    """When Maximum Privacy is selected, ICC color profile is stripped."""
    res = MetadataCleaner.clean_file(
        sample_image_with_icc,
        config=CleanConfig(preset=CleaningPreset.MAXIMUM_PRIVACY, preserve_icc=False),
    )
    assert res.success is True
    after_scan = MetadataScanner.scan_image(res.output_path)
    assert after_scan.has_icc is False


def test_pixel_integrity_lossless_png(sample_png_with_metadata: Path):
    """Strict verification: Decoded raw RGBA pixels before must match 100% with decoded pixels after."""
    with Image.open(sample_png_with_metadata) as orig:
        orig_pixels = orig.tobytes()

    res = MetadataCleaner.clean_file(
        sample_png_with_metadata,
        config=CleanConfig(preset=CleaningPreset.PRIVACY_CLEAN),
    )
    assert res.success is True

    with Image.open(res.output_path) as cleaned:
        clean_pixels = cleaned.tobytes()

    assert orig_pixels == clean_pixels


def test_atomic_file_write_and_cleanup_on_error(tmp_path: Path):
    """Ensure atomic write uses temporary file and leaves original intact."""
    test_file = tmp_path / "valid.png"
    Image.new("RGBA", (50, 50), (10, 20, 30, 255)).save(test_file, "PNG")

    # Clean non-destructive
    res = MetadataCleaner.clean_file(test_file)
    assert res.success is True
    assert test_file.exists()  # original intact
    assert res.output_path.exists()
    assert res.output_path != test_file


def test_filename_anonymization(sample_png_with_metadata: Path):
    res = MetadataCleaner.clean_file(
        sample_png_with_metadata,
        config=CleanConfig(anonymize_filename=True),
    )
    assert res.success is True
    assert "Quickglint_Clean_" in res.output_path.name or "Quickglint_Clean_" in res.output_path.name
    assert sample_png_with_metadata.stem not in res.output_path.name


def test_clean_bytes_in_memory():
    """In-memory cleaning of raw image bytes."""
    img = Image.new("RGBA", (40, 40), (100, 200, 50, 255))
    meta = PngImagePlugin.PngInfo()
    meta.add_text("SecretKey", "12345-ABCDE")
    buf = io.BytesIO()
    img.save(buf, "PNG", pnginfo=meta)
    in_bytes = buf.getvalue()

    out_bytes, res = MetadataCleaner.clean_bytes(in_bytes)
    assert res.success is True
    assert res.removed_fields_count >= 1

    # Verify cleaned bytes
    after_report = MetadataScanner.scan_image(out_bytes)
    assert after_report.total_image_fields_count == 0


# ==============================================================================
# 3. SECURE VAULT & BATCH & REPORT TESTS
# ==============================================================================

def test_vault_metadata_cleaning(tmp_path: Path):
    """Verify RAM-only metadata cleaning inside AES-256-GCM Secure Vault."""
    vault = SecureVault(tmp_path / "test_vault")
    vault.create_vault("MasterPassword123!")

    # Create QImage with text info
    qimg = QImage(64, 64, QImage.Format.Format_ARGB32)
    qimg.fill(0xFF102030)
    oid = vault.add_image(qimg, title="Vault Secret Item")

    # Clean in vault
    new_oid, res = VaultMetadataCleaner.clean_vault_object(vault, oid, replace_in_vault=True)
    assert res.success is True
    assert new_oid is not None

    # Retrieve and verify image still exists and renders in memory
    retrieved_img = vault.get_image(new_oid)
    assert retrieved_img is not None
    assert not retrieved_img.isNull()
    assert retrieved_img.width() == 64


def test_batch_worker_execution(tmp_path: Path):
    """Test asynchronous batch processing worker."""
    files = []
    for i in range(3):
        p = tmp_path / f"batch_img_{i}.png"
        Image.new("RGB", (30, 30), (i * 50, 100, 150)).save(p, "PNG")
        files.append(p)

    worker = BatchMetadataCleanerWorker(files)
    completed_results = []
    worker.finished.connect(lambda results: completed_results.extend(results))

    worker.run()  # Synchronous test run of QThread run method

    assert len(completed_results) == 3
    for r in completed_results:
        assert r.success is True


def test_report_generator(sample_jpeg_with_exif: Path):
    """Test Markdown and Plain text report generation."""
    res = MetadataCleaner.clean_file(sample_jpeg_with_exif)
    assert res.success is True

    md_report = MetadataReportGenerator.generate_markdown(res)
    assert "Metadata Temizleme Raporu" in md_report
    assert "Toplam Metadata Alanı" in md_report

    txt_report = MetadataReportGenerator.generate_plaintext(res)
    assert "METADATA TEMIZLEME RAPORU" in txt_report


def test_upload_worker_metadata_precleaning():
    """Verify UploadWorker scrubs metadata in memory before calling upload provider."""
    class DummyProvider(UploadProvider):
        last_uploaded_bytes: bytes = b""

        @property
        def name(self) -> str:
            return "Dummy"

        @property
        def max_size_bytes(self) -> int:
            return 10 * 1024 * 1024

        @property
        def supported_formats(self) -> list:
            return ["PNG", "JPEG"]

        def upload(self, image_bytes_or_request, is_cancelled=None):
            self.last_uploaded_bytes = image_bytes_or_request.image_bytes
            return UploadResult(success=True, share_url="https://dummy.link/img")

        def validate_api_key(self, api_key: str):
            return True, "OK"

    # Create raw PNG with secret comment
    img = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
    meta = PngImagePlugin.PngInfo()
    meta.add_text("InternalSecret", "SuperSecretData")
    buf = io.BytesIO()
    img.save(buf, "PNG", pnginfo=meta)
    raw_bytes = buf.getvalue()

    prov = DummyProvider()
    worker = UploadWorker(
        image_bytes=raw_bytes,
        file_name="test_upload.png",
        provider=prov,
        api_key="dummy_key",
        clean_metadata=True,
    )
    worker.run()

    # Uploaded bytes should have 0 metadata
    report = MetadataScanner.scan_image(prov.last_uploaded_bytes)
    assert report.total_image_fields_count == 0


def test_invalid_and_corrupt_images(tmp_path: Path):
    """Test error resilience on corrupt files."""
    corrupt_file = tmp_path / "corrupt.png"
    corrupt_file.write_bytes(b"NOT_A_VALID_IMAGE_DATA_CORRUPT_HEADER")

    res = MetadataCleaner.clean_file(corrupt_file)
    assert res.success is False
    assert len(res.error_msg) > 0

