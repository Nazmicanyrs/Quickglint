"""Core Image Optimizer engine implementing format analysis, resizing, compression, and target size solver."""

import io
from pathlib import Path
import time
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageSequence
from PySide6.QtGui import QImage

from app.optimizer.metrics import are_pixels_identical, classify_quality, compute_psnr, compute_ssim
from app.optimizer.models import (
    ChromaSubsampling,
    OptimizationMode,
    OptimizationResult,
    OptimizerConfig,
    OutputFormat,
    QualityPreset,
    ResizePreset,
)
from app.pdf.image_loader import pil_to_qimage
from app.utils.logger import logger


class ImageOptimizer:
    """High-performance local image optimizer utilizing Pillow and NumPy."""

    @classmethod
    def load_pil_image(cls, source: Image.Image | QImage | bytes | str | Path) -> Image.Image:
        """Loads and returns a PIL Image from multiple input types."""
        if isinstance(source, Image.Image):
            return source.copy()
        elif isinstance(source, QImage):
            # Convert QImage to PIL Image via in-memory bytes
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            qba = QByteArray()
            buf = QBuffer(qba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            source.save(buf, "PNG")
            return Image.open(io.BytesIO(bytes(qba.data())))
        elif isinstance(source, bytes):
            return Image.open(io.BytesIO(source))
        elif isinstance(source, (str, Path)):
            return Image.open(str(source))
        else:
            raise TypeError(f"Unsupported image source type: {type(source)}")

    @classmethod
    def analyze_optimal_format(cls, image: Image.Image) -> OutputFormat:
        """
        Analyzes image characteristics (transparency, color palette, text/UI edges) to recommend optimal format.
        """
        # 1. Transparency check
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            # Check if any pixel is truly transparent
            alpha = image.convert("RGBA").split()[-1]
            if min(alpha.getdata()) < 255:
                return OutputFormat.WEBP

        # 2. Text / Screenshot / Palette Complexity check
        img_rgb = image.convert("RGB")
        colors = img_rgb.getcolors(maxcolors=256)
        if colors is not None and len(colors) < 256:
            # Low color count (solid colors/UI/diagrams) -> PNG / WebP Lossless
            return OutputFormat.PNG

        # 3. High color variance / photographic -> WebP (or JPEG)
        return OutputFormat.WEBP

    @classmethod
    def apply_resizing(cls, image: Image.Image, config: OptimizerConfig) -> Image.Image:
        """
        Resizes image according to preset with strict aspect-ratio lock and upscale protection.
        """
        preset = config.resize_preset
        if preset == ResizePreset.ORIGINAL:
            return image

        orig_w, orig_h = image.size
        target_w, target_h = orig_w, orig_h

        if preset == ResizePreset.LONG_EDGE_3840:
            target_w, target_h = cls._calc_long_edge_dims(orig_w, orig_h, 3840)
        elif preset == ResizePreset.LONG_EDGE_2560:
            target_w, target_h = cls._calc_long_edge_dims(orig_w, orig_h, 2560)
        elif preset == ResizePreset.LONG_EDGE_1920:
            target_w, target_h = cls._calc_long_edge_dims(orig_w, orig_h, 1920)
        elif preset == ResizePreset.LONG_EDGE_1280:
            target_w, target_h = cls._calc_long_edge_dims(orig_w, orig_h, 1280)
        elif preset == ResizePreset.LONG_EDGE_1024:
            target_w, target_h = cls._calc_long_edge_dims(orig_w, orig_h, 1024)
        elif preset == ResizePreset.CUSTOM:
            target_w = max(1, config.custom_width)
            target_h = max(1, config.custom_height)
            # Aspect ratio preservation
            aspect = orig_w / float(orig_h)
            if target_w / float(target_h) > aspect:
                target_w = int(target_h * aspect)
            else:
                target_h = int(target_w / aspect)

        # Upscale check
        if not config.allow_upscaling and (target_w > orig_w or target_h > orig_h):
            return image

        if (target_w, target_h) == (orig_w, orig_h):
            return image

        return image.resize((target_w, target_h), Image.Resampling.LANCZOS)

    @classmethod
    def _calc_long_edge_dims(cls, orig_w: int, orig_h: int, max_edge: int) -> Tuple[int, int]:
        aspect = orig_w / float(orig_h)
        if orig_w >= orig_h:
            new_w = max_edge
            new_h = max(1, int(max_edge / aspect))
        else:
            new_h = max_edge
            new_w = max(1, int(max_edge * aspect))
        return new_w, new_h

    def optimize(
        self,
        source: Image.Image | QImage | bytes | str | Path,
        config: Optional[OptimizerConfig] = None,
    ) -> OptimizationResult:
        """
        Executes optimization pipeline and returns an OptimizationResult with metrics.
        """
        config = config or OptimizerConfig()
        t0 = time.perf_counter()

        pil_orig = self.load_pil_image(source)
        orig_bytes_len = len(source) if isinstance(source, bytes) else 0

        # If source is file or QImage, measure base PNG byte size if needed
        if orig_bytes_len == 0:
            buf = io.BytesIO()
            pil_orig.save(buf, format="PNG")
            orig_bytes_len = buf.tell()

        # Handle Target File Size Mode
        if config.mode == OptimizationMode.TARGET_SIZE and config.target_size_kb is not None:
            return self._solve_target_size(pil_orig, orig_bytes_len, config)

        # 1. Determine Effective Format
        chosen_format = config.format
        if chosen_format == OutputFormat.AUTO:
            chosen_format = self.analyze_optimal_format(pil_orig)

        # 2. Apply Resizing
        resized_img = self.apply_resizing(pil_orig, config)

        # 3. Perform Compression
        if chosen_format == OutputFormat.PNG:
            out_bytes = self._compress_png(resized_img, config)
            fmt_str = "PNG"
        elif chosen_format == OutputFormat.JPEG:
            out_bytes = self._compress_jpeg(resized_img, config)
            fmt_str = "JPEG"
        elif chosen_format == OutputFormat.WEBP:
            out_bytes = self._compress_webp(resized_img, config)
            fmt_str = "WebP"
        else:
            out_bytes = self._compress_webp(resized_img, config)
            fmt_str = "WebP"

        opt_bytes_len = len(out_bytes)
        reduction_pct = max(0.0, ((orig_bytes_len - opt_bytes_len) / float(orig_bytes_len)) * 100.0)

        # 4. Compute Metrics
        decoded_opt = Image.open(io.BytesIO(out_bytes))
        is_lossless = config.is_lossless or (chosen_format == OutputFormat.PNG and resized_img.size == pil_orig.size)

        if is_lossless and resized_img.size == pil_orig.size and are_pixels_identical(pil_orig, decoded_opt):
            ssim_score = 1.0
            psnr_score = 100.0
        else:
            ssim_score = compute_ssim(pil_orig, decoded_opt)
            psnr_score = compute_psnr(pil_orig, decoded_opt)

        quality_label = classify_quality(ssim_score, psnr_score, is_lossless)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        return OptimizationResult(
            original_size_bytes=orig_bytes_len,
            optimized_size_bytes=opt_bytes_len,
            reduction_pct=reduction_pct,
            original_dimensions=pil_orig.size,
            optimized_dimensions=resized_img.size,
            format_name=fmt_str,
            ssim_score=ssim_score,
            psnr_score=psnr_score,
            quality_label=quality_label,
            elapsed_ms=elapsed_ms,
            optimized_bytes=out_bytes,
            optimized_image=decoded_opt,
        )

    def _compress_png(self, img: Image.Image, config: OptimizerConfig) -> bytes:
        """Compresses image to PNG with lossless optimization and metadata stripping."""
        buf = io.BytesIO()
        # Ensure RGBA / RGB
        target = img.copy()
        if config.strip_metadata and hasattr(target, "info"):
            target.info.clear()

        target.save(
            buf,
            format="PNG",
            optimize=True,
            compress_level=config.png_compress_level,
        )
        return buf.getvalue()

    def _compress_jpeg(self, img: Image.Image, config: OptimizerConfig) -> bytes:
        """Compresses image to JPEG with configurable subsampling, progressive encoding, and EXIF strip."""
        buf = io.BytesIO()
        # Convert RGBA to RGB with white background
        if img.mode in ("RGBA", "LA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                rgb_img.paste(img, mask=img.split()[3])
            else:
                rgb_img.paste(img.convert("RGB"))
            target = rgb_img
        else:
            target = img.convert("RGB")

        # Map chroma subsampling
        subsampling = 0  # 4:4:4
        if config.chroma_subsampling == ChromaSubsampling.CS_422:
            subsampling = 1
        elif config.chroma_subsampling == ChromaSubsampling.CS_420:
            subsampling = 2

        target.save(
            buf,
            format="JPEG",
            quality=max(1, min(100, config.quality)),
            optimize=True,
            progressive=config.progressive_jpeg,
            subsampling=subsampling,
        )
        return buf.getvalue()

    def _compress_webp(self, img: Image.Image, config: OptimizerConfig) -> bytes:
        """Compresses image to WebP (Lossless or Lossy with effort level 0..6)."""
        buf = io.BytesIO()
        target = img.copy()

        lossless = config.is_lossless or config.mode == OptimizationMode.LOSSLESS

        target.save(
            buf,
            format="WEBP",
            lossless=lossless,
            quality=max(1, min(100, config.quality)),
            method=config.webp_method,
        )
        return buf.getvalue()

    def _solve_target_size(
        self,
        pil_orig: Image.Image,
        orig_bytes_len: int,
        config: OptimizerConfig,
    ) -> OptimizationResult:
        """
        Binary search solver to hit target file size (KB) by adjusting quality and resolution.
        """
        target_bytes = int((config.target_size_kb or 1024) * 1024)
        low_q, high_q = 10, 95
        best_result = None

        # Binary search quality in WebP/JPEG
        test_cfg = OptimizerConfig(
            mode=OptimizationMode.CUSTOM,
            format=OutputFormat.WEBP if config.format == OutputFormat.AUTO else config.format,
            quality=85,
            resize_preset=config.resize_preset,
            custom_width=config.custom_width,
            custom_height=config.custom_height,
        )

        for _ in range(6):
            mid_q = (low_q + high_q) // 2
            test_cfg.quality = mid_q
            res = self.optimize(pil_orig, test_cfg)

            if res.optimized_size_bytes <= target_bytes:
                best_result = res
                low_q = mid_q + 1
            else:
                high_q = mid_q - 1

        if best_result is None:
            # Scale down dimensions if target still exceeded at Q10
            scale_cfg = OptimizerConfig(
                mode=OptimizationMode.CUSTOM,
                format=test_cfg.format,
                quality=50,
                resize_preset=ResizePreset.CUSTOM,
                custom_width=int(pil_orig.width * 0.7),
                custom_height=int(pil_orig.height * 0.7),
            )
            best_result = self.optimize(pil_orig, scale_cfg)

        return best_result

