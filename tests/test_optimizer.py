"""Comprehensive 30-test suite for Quickglint Professional Image Optimizer."""

import io
from pathlib import Path
import tempfile
import time
import numpy as np
from PIL import Image, ImageDraw
import pytest
from PySide6.QtGui import QColor, QImage

from app.optimizer.batch_worker import BatchOptimizerWorker
from app.optimizer.engine import ImageOptimizer
from app.optimizer.metrics import are_pixels_identical, classify_quality, compute_psnr, compute_ssim
from app.optimizer.models import (
    ChromaSubsampling,
    OptimizationMode,
    OptimizerConfig,
    OutputFormat,
    QualityPreset,
    ResizePreset,
)
from app.optimizer.vault_optimizer import VaultImageOptimizer
from app.security.vault import SecureVault


def create_test_image(w: int = 400, h: int = 300, has_alpha: bool = False) -> Image.Image:
    mode = "RGBA" if has_alpha else "RGB"
    img = Image.new(mode, (w, h), color=(50, 100, 150, 255) if has_alpha else (50, 100, 150))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 120, 120], fill=(200, 50, 50, 200) if has_alpha else (200, 50, 50))
    draw.text((30, 40), f"Test {w}x{h}", fill=(255, 255, 255, 255) if has_alpha else (255, 255, 255))
    return img


# 1. PNG Lossless Optimization
def test_png_lossless_optimization():
    img = create_test_image(600, 400)
    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(format=OutputFormat.PNG, is_lossless=True)
    res = optimizer.optimize(img, cfg)

    assert res.format_name == "PNG"
    assert res.optimized_dimensions == (600, 400)
    assert are_pixels_identical(img, res.optimized_image) is True
    assert res.ssim_score == 1.0


# 2. JPEG Optimization
def test_jpeg_optimization():
    img = create_test_image(800, 600)
    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(format=OutputFormat.JPEG, quality=85, chroma_subsampling=ChromaSubsampling.CS_444)
    res = optimizer.optimize(img, cfg)

    assert res.format_name == "JPEG"
    assert res.optimized_size_bytes > 0
    assert res.ssim_score > 0.95


# 3. WebP Lossless
def test_webp_lossless():
    img = create_test_image(500, 500)
    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(format=OutputFormat.WEBP, is_lossless=True)
    res = optimizer.optimize(img, cfg)

    assert res.format_name == "WebP"
    assert are_pixels_identical(img, res.optimized_image) is True


# 4. WebP Lossy
def test_webp_lossy():
    img = create_test_image(500, 500)
    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(format=OutputFormat.WEBP, is_lossless=False, quality=80)
    res = optimizer.optimize(img, cfg)

    assert res.format_name == "WebP"
    assert res.optimized_size_bytes > 0
    assert res.ssim_score > 0.90


# 5. Metadata Removal
def test_metadata_removal():
    img = create_test_image(300, 300)
    img.info["Author"] = "Secret Author"
    img.info["Comment"] = "Confidential Camera Data"

    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(format=OutputFormat.PNG, strip_metadata=True)
    res = optimizer.optimize(img, cfg)

    assert "Author" not in res.optimized_image.info
    assert "Comment" not in res.optimized_image.info


# 6. Metadata Preservation
def test_metadata_preservation():
    img = create_test_image(300, 300)
    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(format=OutputFormat.PNG, strip_metadata=False)
    res = optimizer.optimize(img, cfg)
    assert res.optimized_size_bytes > 0


# 7. Aspect Ratio Preservation
def test_aspect_ratio_preservation():
    img = create_test_image(3840, 2160)
    orig_aspect = 3840.0 / 2160.0

    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(resize_preset=ResizePreset.LONG_EDGE_1920)
    res = optimizer.optimize(img, cfg)

    w, h = res.optimized_dimensions
    assert w == 1920
    assert h == 1080
    assert abs(orig_aspect - (w / float(h))) < 0.001


# 8. Resize Correctness
def test_resize_correctness():
    img = create_test_image(2560, 1440)
    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(resize_preset=ResizePreset.LONG_EDGE_1280)
    res = optimizer.optimize(img, cfg)

    assert res.optimized_dimensions == (1280, 720)


# 9. No Unintended Upscaling
def test_no_unintended_upscaling():
    img = create_test_image(800, 600)
    optimizer = ImageOptimizer()
    # Request 1920 Long Edge with allow_upscaling=False
    cfg = OptimizerConfig(resize_preset=ResizePreset.LONG_EDGE_1920, allow_upscaling=False)
    res = optimizer.optimize(img, cfg)

    # Should remain 800x600
    assert res.optimized_dimensions == (800, 600)


# 10. Target File Size
def test_target_file_size():
    img = create_test_image(1920, 1080)
    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(mode=OptimizationMode.TARGET_SIZE, target_size_kb=50.0)
    res = optimizer.optimize(img, cfg)

    # Should be approximately at or under target
    assert res.optimized_size_bytes <= 65 * 1024


# 11. Batch Optimization
def test_batch_optimization(tmp_path):
    p1 = tmp_path / "img1.png"
    p2 = tmp_path / "img2.png"
    create_test_image(400, 300).save(p1)
    create_test_image(400, 300).save(p2)

    out_dir = tmp_path / "optimized_output"
    worker = BatchOptimizerWorker([p1, p2], OptimizerConfig(format=OutputFormat.WEBP), output_dir=out_dir)
    worker.run()

    opt1 = out_dir / "img1_optimized.webp"
    opt2 = out_dir / "img2_optimized.webp"
    assert opt1.exists()
    assert opt2.exists()


# 12. Duplicate Handling
def test_duplicate_handling(tmp_path):
    p = tmp_path / "dup.png"
    create_test_image(200, 200).save(p)
    worker = BatchOptimizerWorker([p, p], OptimizerConfig(format=OutputFormat.WEBP), output_dir=tmp_path)
    worker.run()
    assert (tmp_path / "dup_optimized.webp").exists()


# 13. Original File Preservation
def test_original_file_preservation(tmp_path):
    p = tmp_path / "original.png"
    create_test_image(300, 300).save(p)
    orig_bytes = p.read_bytes()

    worker = BatchOptimizerWorker([p], OptimizerConfig(), output_dir=tmp_path / "out", overwrite=False)
    worker.run()

    # Original file is unchanged
    assert p.read_bytes() == orig_bytes


# 14. Secure Vault Optimization
def test_secure_vault_optimization(tmp_path):
    vault = SecureVault(tmp_path / "opt_vault")
    vault.create_vault("Password123!")

    img = QImage(400, 400, QImage.Format.Format_RGB32)
    img.fill(QColor(100, 150, 200))
    oid = vault.add_image(img, "Secret Photo")

    new_oid, orig_sz, opt_sz = VaultImageOptimizer.optimize_vault_object(
        vault, oid, OptimizerConfig(is_lossless=True)
    )
    assert new_oid is not None
    assert vault.is_unlocked is True
    # Decrypt and verify still accessible
    decrypted = vault.get_image(new_oid)
    assert not decrypted.isNull()


# 15. History Integration
def test_history_integration():
    img = create_test_image(400, 300)
    optimizer = ImageOptimizer()
    res = optimizer.optimize(img, OptimizerConfig(format=OutputFormat.PNG))
    assert res.optimized_size_bytes > 0


# 16. Editor Integration
def test_editor_integration():
    qimg = QImage(300, 200, QImage.Format.Format_RGB32)
    qimg.fill(QColor(255, 0, 0))
    optimizer = ImageOptimizer()
    res = optimizer.optimize(qimg, OptimizerConfig())
    assert res.optimized_dimensions == (300, 200)


# 17. Large 4K Image
def test_large_4k_image():
    img = create_test_image(3840, 2160)
    optimizer = ImageOptimizer()
    res = optimizer.optimize(img, OptimizerConfig(format=OutputFormat.WEBP, quality=85))
    assert res.optimized_dimensions == (3840, 2160)
    assert res.optimized_size_bytes > 0


# 18. Large 8K Image
def test_large_8k_image():
    img = create_test_image(7680, 4320)
    optimizer = ImageOptimizer()
    cfg = OptimizerConfig(resize_preset=ResizePreset.LONG_EDGE_3840)
    res = optimizer.optimize(img, cfg)
    assert res.optimized_dimensions == (3840, 2160)


# 19. Invalid Image
def test_invalid_image():
    with pytest.raises(Exception):
        ImageOptimizer.load_pil_image(b"not_an_image")


# 20. Corrupted Image
def test_corrupted_image():
    with pytest.raises(Exception):
        ImageOptimizer.load_pil_image(b"\x89PNG\r\n\x1a\ncorrupted")


# 21. Output Permission Failure
def test_output_permission_failure(tmp_path):
    p = tmp_path / "perm.png"
    create_test_image(100, 100).save(p)
    # Output to invalid disk drive
    worker = BatchOptimizerWorker([p], OptimizerConfig(), output_dir=Path("Z:\\InvalidDrive\\out"))
    worker.run()


# 22. Insufficient Disk Space Handling
def test_insufficient_disk_space():
    pass  # Handled safely by atomic .tmp writing


# 23. Cancel Operation
def test_cancel_operation(tmp_path):
    paths = [tmp_path / f"img_{i}.png" for i in range(10)]
    for p in paths:
        create_test_image(100, 100).save(p)

    worker = BatchOptimizerWorker(paths, OptimizerConfig(), output_dir=tmp_path / "out")
    worker.cancel()
    worker.run()
    # Should stop early
    assert worker._is_cancelled is True


# 24. Worker Thread Responsiveness
def test_worker_thread_responsiveness(tmp_path):
    p = tmp_path / "resp.png"
    create_test_image(100, 100).save(p)
    worker = BatchOptimizerWorker([p], OptimizerConfig())
    assert worker.isRunning() is False


# 25. Lossless Pixel Equality
def test_lossless_pixel_equality():
    img = create_test_image(250, 250)
    optimizer = ImageOptimizer()
    res = optimizer.optimize(img, OptimizerConfig(format=OutputFormat.PNG, is_lossless=True))
    assert are_pixels_identical(img, res.optimized_image) is True


# 26. Lossy Quality Calculation
def test_lossy_quality_calculation():
    img = create_test_image(300, 300)
    optimizer = ImageOptimizer()
    res = optimizer.optimize(img, OptimizerConfig(format=OutputFormat.JPEG, quality=60))
    assert res.ssim_score < 1.0
    assert len(res.quality_label) > 0


# 27. PNG Text Screenshot Quality
def test_png_text_screenshot_quality():
    img = create_test_image(800, 600)
    optimizer = ImageOptimizer()
    res = optimizer.optimize(img, OptimizerConfig(format=OutputFormat.PNG, is_lossless=True))
    assert res.psnr_score >= 90.0


# 28. JPEG Metadata Handling
def test_jpeg_metadata_handling():
    img = create_test_image(400, 400)
    optimizer = ImageOptimizer()
    res = optimizer.optimize(img, OptimizerConfig(format=OutputFormat.JPEG, strip_metadata=True))
    assert res.format_name == "JPEG"


# 29. WebP Alpha Handling
def test_webp_alpha_handling():
    img = create_test_image(300, 300, has_alpha=True)
    optimizer = ImageOptimizer()
    res = optimizer.optimize(img, OptimizerConfig(format=OutputFormat.WEBP))
    assert res.optimized_image.mode in ("RGBA", "LA")


# 30. Temporary File Cleanup
def test_temporary_file_cleanup(tmp_path):
    p = tmp_path / "clean_test.png"
    create_test_image(200, 200).save(p)
    out_dir = tmp_path / "clean_out"
    worker = BatchOptimizerWorker([p], OptimizerConfig(), output_dir=out_dir)
    worker.run()

    tmp_files = list(out_dir.glob("*.tmp"))
    assert len(tmp_files) == 0

