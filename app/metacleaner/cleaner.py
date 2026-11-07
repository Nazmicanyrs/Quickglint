"""Core metadata cleaning engine with physical orientation preservation, ICC management, and atomic file operations."""

import datetime
import io
import os
from pathlib import Path
import time
from typing import Optional, Tuple, Union
from PIL import Image, ImageOps

from app.metacleaner.models import (
    CleanConfig,
    CleaningPreset,
    CleanResult,
    MetadataCategory,
)
from app.metacleaner.scanner import MetadataScanner
from app.utils.logger import logger


class MetadataCleaner:
    """Removes unwanted metadata from image files and in-memory buffers while preserving pixel integrity."""

    @classmethod
    def clean_file(
        cls,
        input_path: Union[str, Path],
        config: Optional[CleanConfig] = None,
        output_path: Optional[Union[str, Path]] = None,
    ) -> CleanResult:
        """Clean an image file non-destructively and atomically."""
        start_time = time.perf_counter()
        cfg = config or CleanConfig()
        in_p = Path(input_path)

        if not in_p.exists():
            return CleanResult(
                success=False,
                input_path=in_p,
                error_msg=f"Giriş dosyası bulunamadı: {in_p}",
            )

        # 1. Scan before report
        before_report = MetadataScanner.scan_image(in_p)

        # Determine target output path
        if output_path:
            out_p = Path(output_path)
        elif cfg.replace_original:
            out_p = in_p
        else:
            out_p = cls.generate_output_path(
                in_p,
                anonymize=cfg.anonymize_filename,
                output_dir=cfg.output_directory,
                target_format=cfg.output_format,
            )

        try:
            # 2. Read and clean image
            with Image.open(in_p) as pil_img:
                clean_img, save_kwargs = cls._process_image_object(pil_img, cfg)

                # Determine target save format based on output destination or config
                suffix_map = {
                    ".jpg": "JPEG",
                    ".jpeg": "JPEG",
                    ".png": "PNG",
                    ".webp": "WEBP",
                    ".tiff": "TIFF",
                    ".tif": "TIFF",
                    ".bmp": "BMP",
                    ".gif": "GIF",
                }
                if out_p.suffix.lower() in suffix_map:
                    target_fmt = suffix_map[out_p.suffix.lower()]
                else:
                    target_fmt = cfg.output_format or pil_img.format or "PNG"

                if target_fmt.upper() in ("JPG", "JPEG"):
                    target_fmt = "JPEG"
                    if clean_img.mode in ("RGBA", "P", "LA"):
                        clean_img = clean_img.convert("RGB")
                    save_kwargs["quality"] = cfg.jpeg_quality
                    save_kwargs["optimize"] = True

                # 3. Write atomically via temporary file
                out_p.parent.mkdir(parents=True, exist_ok=True)
                tmp_p = out_p.with_suffix(out_p.suffix + f".tmp_{int(time.time()*1000)}")

                try:
                    clean_img.save(tmp_p, format=target_fmt, **save_kwargs)

                    # Validate generated output image
                    with Image.open(tmp_p) as test_open:
                        test_open.verify()

                    # Atomic rename/replace
                    if tmp_p.exists():
                        tmp_p.replace(out_p)
                except Exception as save_err:
                    if tmp_p.exists():
                        try:
                            tmp_p.unlink()
                        except Exception:
                            pass
                    raise save_err

            # 4. Scan after report
            after_report = MetadataScanner.scan_image(out_p)

            removed_count = max(0, before_report.total_image_fields_count - after_report.total_image_fields_count)
            preserved_count = after_report.total_image_fields_count
            elapsed = (time.perf_counter() - start_time) * 1000.0

            return CleanResult(
                success=True,
                input_path=in_p,
                output_path=out_p,
                before_report=before_report,
                after_report=after_report,
                removed_fields_count=removed_count,
                preserved_fields_count=preserved_count,
                elapsed_ms=elapsed,
            )
        except Exception as exc:
            logger.error("Failed to clean metadata for %s: %s", in_p, exc)
            return CleanResult(
                success=False,
                input_path=in_p,
                output_path=out_p,
                before_report=before_report,
                error_msg=str(exc),
                elapsed_ms=(time.perf_counter() - start_time) * 1000.0,
            )

    @classmethod
    def clean_bytes(
        cls,
        image_bytes: bytes,
        config: Optional[CleanConfig] = None,
        target_format: Optional[str] = None,
    ) -> Tuple[bytes, CleanResult]:
        """Clean metadata from raw image bytes entirely in memory."""
        start_time = time.perf_counter()
        cfg = config or CleanConfig()

        before_report = MetadataScanner.scan_image(image_bytes)

        try:
            in_buf = io.BytesIO(image_bytes)
            with Image.open(in_buf) as pil_img:
                clean_img, save_kwargs = cls._process_image_object(pil_img, cfg)

                fmt = target_format or cfg.output_format or pil_img.format or "PNG"
                if fmt.upper() in ("JPG", "JPEG"):
                    fmt = "JPEG"
                    if clean_img.mode in ("RGBA", "P", "LA"):
                        clean_img = clean_img.convert("RGB")
                    save_kwargs["quality"] = cfg.jpeg_quality
                    save_kwargs["optimize"] = True

                out_buf = io.BytesIO()
                clean_img.save(out_buf, format=fmt, **save_kwargs)
                out_bytes = out_buf.getvalue()

            after_report = MetadataScanner.scan_image(out_bytes)
            removed = max(0, before_report.total_image_fields_count - after_report.total_image_fields_count)
            elapsed = (time.perf_counter() - start_time) * 1000.0

            result = CleanResult(
                success=True,
                output_bytes=out_bytes,
                before_report=before_report,
                after_report=after_report,
                removed_fields_count=removed,
                preserved_fields_count=after_report.total_image_fields_count,
                elapsed_ms=elapsed,
            )
            return out_bytes, result
        except Exception as exc:
            logger.error("Failed to clean metadata in-memory: %s", exc)
            res = CleanResult(
                success=False,
                before_report=before_report,
                error_msg=str(exc),
                elapsed_ms=(time.perf_counter() - start_time) * 1000.0,
            )
            return image_bytes, res

    @classmethod
    def clean_pil_image(
        cls,
        pil_img: Image.Image,
        config: Optional[CleanConfig] = None,
    ) -> Image.Image:
        """Strip metadata from an existing PIL Image object in memory."""
        cfg = config or CleanConfig()
        clean_img, _ = cls._process_image_object(pil_img, cfg)
        return clean_img

    @classmethod
    def _process_image_object(
        cls,
        pil_img: Image.Image,
        config: CleanConfig,
    ) -> Tuple[Image.Image, dict]:
        """Perform physical orientation transpose, strip metadata tags, and construct save kwargs."""
        save_kwargs = {}

        # 1. Orientation Safety: Physically rotate pixels before EXIF is discarded
        img_to_clean = pil_img
        if config.auto_orient:
            try:
                img_to_clean = ImageOps.exif_transpose(pil_img)
            except Exception as exc:
                logger.debug("exif_transpose skipped: %s", exc)
                img_to_clean = pil_img

        # 2. Extract ICC profile if preserved
        icc_profile = None
        if config.preserve_icc:
            icc_profile = pil_img.info.get("icc_profile")
            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile

        # 3. Create fresh pixel copy with empty metadata
        # Re-creating an image from raw decoded bytes guarantees 0 leftover tags and 100% pixel fidelity
        clean_img = Image.frombytes(img_to_clean.mode, img_to_clean.size, img_to_clean.tobytes())

        # For palette-based images, copy palette
        if img_to_clean.mode == "P" and img_to_clean.palette:
            clean_img.putpalette(img_to_clean.palette)

        return clean_img, save_kwargs

    @classmethod
    def generate_output_path(
        cls,
        input_path: Path,
        anonymize: bool = False,
        output_dir: Optional[Path] = None,
        target_format: Optional[str] = None,
    ) -> Path:
        """Generate a safe, collision-free non-destructive output path."""
        target_dir = output_dir or input_path.parent
        ext = f".{target_format.lower()}" if target_format else input_path.suffix

        if anonymize:
            timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            base_name = f"Quickglint_Clean_{timestamp_str}"
        else:
            base_name = f"{input_path.stem}_clean"

        candidate = target_dir / f"{base_name}{ext}"
        counter = 1
        while candidate.exists():
            candidate = target_dir / f"{base_name}_{counter}{ext}"
            counter += 1

        return candidate

