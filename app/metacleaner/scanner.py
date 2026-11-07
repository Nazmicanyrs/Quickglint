"""Comprehensive metadata scanner extracting EXIF, GPS, XMP, IPTC, PNG chunks, and ICC profiles."""

import datetime
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import ExifTags, Image, PngImagePlugin, TiffImagePlugin

from app.metacleaner.models import (
    MetadataCategory,
    MetadataField,
    MetadataRiskLevel,
    MetadataScanReport,
)
from app.utils.logger import logger


# High-risk keywords for privacy classification
HIGH_RISK_TAGS = {
    "gps", "latitude", "longitude", "altitude", "serial", "serialnumber", "body_serial_number",
    "lens_serial_number", "owner_name", "user_comment", "unique_camera_model", "author",
    "by-line", "creator", "artist", "camera_owner_name"
}

MEDIUM_RISK_TAGS = {
    "datetime", "datetimeoriginal", "datetimedigitized", "software", "processingsoftware",
    "copyright", "description", "caption", "title", "headline", "keywords", "subject",
    "source", "history", "creatortool", "modifydate", "documentname", "hostcomputer"
}


class MetadataScanner:
    """Scans and categorizes all metadata embedded inside an image and its filesystem layer."""

    @classmethod
    def scan_image(cls, image_source: Union[str, Path, bytes, Image.Image]) -> MetadataScanReport:
        """Analyze all metadata embedded in the image and return a structured report."""
        start_time = time.perf_counter()
        report = MetadataScanReport()

        pil_img: Optional[Image.Image] = None
        file_path: Optional[Path] = None

        if isinstance(image_source, (str, Path)):
            file_path = Path(image_source)
            report.image_path = str(file_path)
            if file_path.exists():
                report.file_size_bytes = file_path.stat().st_size
                cls._scan_filesystem_metadata(file_path, report)
                try:
                    pil_img = Image.open(file_path)
                except Exception as exc:
                    logger.warning("Could not open image file for metadata scan: %s", exc)
        elif isinstance(image_source, bytes):
            report.file_size_bytes = len(image_source)
            import io
            try:
                pil_img = Image.open(io.BytesIO(image_source))
            except Exception as exc:
                logger.warning("Could not open image bytes for metadata scan: %s", exc)
        elif isinstance(image_source, Image.Image):
            pil_img = image_source
            report.file_size_bytes = len(pil_img.tobytes()) if hasattr(pil_img, "tobytes") else 0

        if pil_img:
            report.format_name = pil_img.format or "RAW/In-Memory"
            report.image_size = pil_img.size

            # 1. Scan EXIF & GPS
            cls._scan_exif_metadata(pil_img, report)

            # 2. Scan PNG text chunks
            cls._scan_png_chunks(pil_img, report)

            # 3. Scan XMP
            cls._scan_xmp_metadata(pil_img, report)

            # 4. Scan IPTC / Photoshop blocks
            cls._scan_iptc_metadata(pil_img, report)

            # 5. Scan ICC profile
            cls._scan_icc_profile(pil_img, report)

            # 6. Scan other info dict items
            cls._scan_info_dict(pil_img, report)

        report.scan_time_ms = (time.perf_counter() - start_time) * 1000.0
        return report

    @classmethod
    def _scan_filesystem_metadata(cls, file_path: Path, report: MetadataScanReport) -> None:
        """Extract filesystem level metadata (distinct from image metadata)."""
        stat = file_path.stat()

        created_dt = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        modified_dt = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        report.fields.append(
            MetadataField(
                category=MetadataCategory.FILE_SYSTEM,
                tag_name="filename",
                human_name="Dosya Adı",
                raw_value=file_path.name,
                display_value=file_path.name,
                risk_level=MetadataRiskLevel.MEDIUM if any(c.isdigit() for c in file_path.name) else MetadataRiskLevel.LOW,
                is_sensitive=False,
                is_removable=False,
                is_selected_for_removal=False,
            )
        )
        report.fields.append(
            MetadataField(
                category=MetadataCategory.FILE_SYSTEM,
                tag_name="file_size",
                human_name="Dosya Boyutu",
                raw_value=stat.st_size,
                display_value=f"{stat.st_size / 1024.0:.1f} KB ({stat.st_size} bytes)",
                risk_level=MetadataRiskLevel.LOW,
                is_sensitive=False,
                is_removable=False,
                is_selected_for_removal=False,
            )
        )
        report.fields.append(
            MetadataField(
                category=MetadataCategory.FILE_SYSTEM,
                tag_name="file_created",
                human_name="Oluşturulma Tarihi (OS)",
                raw_value=stat.st_ctime,
                display_value=created_dt,
                risk_level=MetadataRiskLevel.LOW,
                is_sensitive=False,
                is_removable=False,
                is_selected_for_removal=False,
            )
        )
        report.fields.append(
            MetadataField(
                category=MetadataCategory.FILE_SYSTEM,
                tag_name="file_modified",
                human_name="Değiştirilme Tarihi (OS)",
                raw_value=stat.st_mtime,
                display_value=modified_dt,
                risk_level=MetadataRiskLevel.LOW,
                is_sensitive=False,
                is_removable=False,
                is_selected_for_removal=False,
            )
        )

    @classmethod
    def _scan_exif_metadata(cls, pil_img: Image.Image, report: MetadataScanReport) -> None:
        """Extract standard EXIF and GPS IFD data."""
        try:
            exif_data = pil_img.getexif()
            if not exif_data:
                return

            tag_names = {v: k for k, v in ExifTags.TAGS.items()}
            gps_tag_names = {v: k for k, v in ExifTags.GPSTAGS.items()}

            for tag_id, val in exif_data.items():
                tag_name = ExifTags.TAGS.get(tag_id, f"Tag_{tag_id}")

                # Check for Orientation
                if tag_name == "Orientation":
                    report.has_orientation = True
                    try:
                        report.orientation_value = int(val)
                    except Exception:
                        report.orientation_value = 1

                # Check GPS sub-IFD
                if tag_name == "GPSInfo" or tag_id == 0x8825:
                    report.has_gps = True
                    gps_ifd = exif_data.get_ifd(0x8825) if hasattr(exif_data, "get_ifd") else val
                    if isinstance(gps_ifd, dict):
                        cls._parse_gps_ifd(gps_ifd, report)
                    continue

                display_val = cls._format_exif_value(val)
                risk = cls._evaluate_risk(tag_name, display_val)

                report.fields.append(
                    MetadataField(
                        category=MetadataCategory.EXIF,
                        tag_name=tag_name,
                        human_name=cls._get_human_tag_name(tag_name),
                        raw_value=val,
                        display_value=display_val,
                        risk_level=risk,
                        is_sensitive=(risk == MetadataRiskLevel.HIGH),
                    )
                )

            # Check for Exif sub-IFD (0x8769)
            if hasattr(exif_data, "get_ifd"):
                exif_sub_ifd = exif_data.get_ifd(0x8769)
                if exif_sub_ifd:
                    for sub_id, sub_val in exif_sub_ifd.items():
                        sub_tag = ExifTags.TAGS.get(sub_id, f"ExifIFD_{sub_id}")
                        disp = cls._format_exif_value(sub_val)
                        risk = cls._evaluate_risk(sub_tag, disp)
                        report.fields.append(
                            MetadataField(
                                category=MetadataCategory.EXIF,
                                tag_name=sub_tag,
                                human_name=cls._get_human_tag_name(sub_tag),
                                raw_value=sub_val,
                                display_value=disp,
                                risk_level=risk,
                                is_sensitive=(risk == MetadataRiskLevel.HIGH),
                            )
                        )
        except Exception as exc:
            logger.debug("Failed to parse EXIF metadata: %s", exc)

    @classmethod
    def _parse_gps_ifd(cls, gps_dict: dict, report: MetadataScanReport) -> None:
        """Parse GPS tags into coordinates and human-readable location indicators."""
        lat_val = gps_dict.get(2) or gps_dict.get("GPSLatitude")
        lat_ref = gps_dict.get(1) or gps_dict.get("GPSLatitudeRef") or "N"
        lon_val = gps_dict.get(4) or gps_dict.get("GPSLongitude")
        lon_ref = gps_dict.get(3) or gps_dict.get("GPSLongitudeRef") or "E"
        alt_val = gps_dict.get(6) or gps_dict.get("GPSAltitude")

        coords_str = ""
        if lat_val and lon_val:
            try:
                dec_lat = cls._convert_dms_to_decimal(lat_val, str(lat_ref))
                dec_lon = cls._convert_dms_to_decimal(lon_val, str(lon_ref))
                coords_str = f"{dec_lat:.5f}, {dec_lon:.5f}"
            except Exception:
                coords_str = f"{lat_val} {lat_ref}, {lon_val} {lon_ref}"

        for tag_id, val in gps_dict.items():
            tag_name = ExifTags.GPSTAGS.get(tag_id, str(tag_id))
            display_val = str(val)

            # Mask coordinates for privacy view
            if tag_name in ("GPSLatitude", "2") and coords_str:
                display_val = f"Enlem: {coords_str.split(',')[0]} (Hassas Konum)"
            elif tag_name in ("GPSLongitude", "4") and coords_str:
                display_val = f"Boylam: {coords_str.split(',')[1]} (Hassas Konum)"
            elif tag_name in ("GPSAltitude", "6"):
                display_val = f"Yükseklik: {val}m"

            report.fields.append(
                MetadataField(
                    category=MetadataCategory.GPS,
                    tag_name=f"GPS_{tag_name}",
                    human_name=f"GPS {tag_name}",
                    raw_value=val,
                    display_value=display_val,
                    risk_level=MetadataRiskLevel.HIGH,
                    is_sensitive=True,
                    is_masked=True,
                )
            )

    @classmethod
    def _scan_png_chunks(cls, pil_img: Image.Image, report: MetadataScanReport) -> None:
        """Scan PNG textual chunks (tEXt, zTXt, iTXt)."""
        if not hasattr(pil_img, "text") or not pil_img.text:
            return

        for k, v in pil_img.text.items():
            risk = cls._evaluate_risk(k, v)
            report.fields.append(
                MetadataField(
                    category=MetadataCategory.PNG_CHUNKS,
                    tag_name=k,
                    human_name=f"PNG Text ({k})",
                    raw_value=v,
                    display_value=str(v),
                    risk_level=risk,
                    is_sensitive=(risk == MetadataRiskLevel.HIGH),
                )
            )

    @classmethod
    def _scan_xmp_metadata(cls, pil_img: Image.Image, report: MetadataScanReport) -> None:
        """Extract and parse XMP packet tags."""
        xmp_raw = pil_img.info.get("xmp") or pil_img.info.get("XML:com.adobe.xmp")
        if not xmp_raw:
            return

        xmp_str = xmp_raw.decode("utf-8", errors="ignore") if isinstance(xmp_raw, bytes) else str(xmp_raw)

        # Quick regex extraction of common XMP attributes
        import re
        xmp_tags = [
            ("dc:creator", "Yazar / Oluşturan", MetadataRiskLevel.HIGH),
            ("dc:title", "Başlık", MetadataRiskLevel.MEDIUM),
            ("dc:description", "Açıklama", MetadataRiskLevel.MEDIUM),
            ("dc:rights", "Telif Hakkı", MetadataRiskLevel.MEDIUM),
            ("xmp:CreatorTool", "Oluşturan Yazılım", MetadataRiskLevel.MEDIUM),
            ("xmp:CreateDate", "Oluşturulma Tarihi", MetadataRiskLevel.MEDIUM),
            ("xmp:ModifyDate", "Değiştirilme Tarihi", MetadataRiskLevel.MEDIUM),
            ("photoshop:Credit", "Kredi / Ajans", MetadataRiskLevel.MEDIUM),
            ("photoshop:City", "Şehir Bilgisi", MetadataRiskLevel.HIGH),
            ("photoshop:Country", "Ülke Bilgisi", MetadataRiskLevel.HIGH),
        ]

        found_any = False
        for tag_pattern, human_name, risk in xmp_tags:
            match = re.search(rf'<{tag_pattern}[^>]*>(.*?)</{tag_pattern}>', xmp_str, re.DOTALL | re.IGNORECASE)
            if match:
                found_any = True
                val = match.group(1).strip()
                # strip nested rdf:li if present
                li_match = re.search(r'<rdf:li[^>]*>(.*?)</rdf:li>', val, re.DOTALL | re.IGNORECASE)
                if li_match:
                    val = li_match.group(1).strip()

                report.fields.append(
                    MetadataField(
                        category=MetadataCategory.XMP,
                        tag_name=tag_pattern,
                        human_name=human_name,
                        raw_value=val,
                        display_value=val,
                        risk_level=risk,
                        is_sensitive=(risk == MetadataRiskLevel.HIGH),
                    )
                )

        if not found_any and len(xmp_str) > 20:
            report.fields.append(
                MetadataField(
                    category=MetadataCategory.XMP,
                    tag_name="xmp_raw_packet",
                    human_name="XMP Veri Paketi",
                    raw_value=f"{len(xmp_str)} bytes",
                    display_value=f"XMP XML Paketi ({len(xmp_str)} karakter)",
                    risk_level=MetadataRiskLevel.MEDIUM,
                )
            )

    @classmethod
    def _scan_iptc_metadata(cls, pil_img: Image.Image, report: MetadataScanReport) -> None:
        """Scan IPTC metadata blocks if present."""
        photoshop = pil_img.info.get("photoshop")
        if not photoshop:
            return

        report.fields.append(
            MetadataField(
                category=MetadataCategory.IPTC,
                tag_name="photoshop_iptc_block",
                human_name="IPTC / Photoshop Bilgi Bloğu",
                raw_value=f"{len(photoshop)} bytes",
                display_value="IPTC Başlık, Telif ve Konum Bloğu",
                risk_level=MetadataRiskLevel.MEDIUM,
            )
        )

    @classmethod
    def _scan_icc_profile(cls, pil_img: Image.Image, report: MetadataScanReport) -> None:
        """Detect and describe ICC color profile."""
        icc = pil_img.info.get("icc_profile")
        if not icc:
            return

        report.has_icc = True
        desc = "ICC Color Profile"
        try:
            from PIL import ImageCms
            import io
            profile = ImageCms.getOpenProfile(io.BytesIO(icc))
            desc = ImageCms.getProfileDescription(profile) or desc
        except Exception:
            pass

        report.fields.append(
            MetadataField(
                category=MetadataCategory.ICC,
                tag_name="icc_profile",
                human_name="ICC Renk Profili",
                raw_value=f"{len(icc)} bytes",
                display_value=f"{desc} ({len(icc)} bytes)",
                risk_level=MetadataRiskLevel.LOW,
                is_sensitive=False,
                is_removable=True,
                is_selected_for_removal=False,  # Keep ICC by default
            )
        )

    @classmethod
    def _scan_info_dict(cls, pil_img: Image.Image, report: MetadataScanReport) -> None:
        """Scan generic metadata stored in PIL image.info, ignoring internal codec/decoder stream headers."""
        ignored_codec_keys = {
            "icc_profile", "xmp", "XML:com.adobe.xmp", "photoshop", "exif",
            "jfif", "jfif_version", "jfif_unit", "jfif_density", "dpi",
            "progressive", "progression", "transparency", "background",
            "loop", "duration", "interlace", "gamma", "aspect",
            "compression", "quantization", "subsampling", "adobe", "adobe_transform",
        }
        for k, v in pil_img.info.items():
            if k.lower() in ignored_codec_keys:
                continue

            # Determine category
            category = MetadataCategory.EXIF
            if pil_img.format == "PNG":
                category = MetadataCategory.PNG_CHUNKS
            elif pil_img.format == "TIFF":
                category = MetadataCategory.TIFF

            disp = str(v)
            if len(disp) > 100:
                disp = disp[:97] + "..."

            risk = cls._evaluate_risk(k, disp)
            report.fields.append(
                MetadataField(
                    category=category,
                    tag_name=k,
                    human_name=cls._get_human_tag_name(k),
                    raw_value=v,
                    display_value=disp,
                    risk_level=risk,
                    is_sensitive=(risk == MetadataRiskLevel.HIGH),
                )
            )

    @classmethod
    def _evaluate_risk(cls, tag_name: str, value: str) -> MetadataRiskLevel:
        """Assign privacy risk level based on tag semantics."""
        tn_lower = tag_name.lower().replace(" ", "").replace("_", "")

        for hr in HIGH_RISK_TAGS:
            if hr in tn_lower:
                return MetadataRiskLevel.HIGH

        for mr in MEDIUM_RISK_TAGS:
            if mr in tn_lower:
                return MetadataRiskLevel.MEDIUM

        return MetadataRiskLevel.LOW

    @classmethod
    def _get_human_tag_name(cls, tag: str) -> str:
        """Map raw tag names to clean Turkish/English labels."""
        mapping = {
            "Make": "Kamera Üreticisi (Make)",
            "Model": "Cihaz Modeli (Model)",
            "Software": "İşleme Yazılımı (Software)",
            "DateTime": "Tarih ve Saat",
            "DateTimeOriginal": "Çekim Tarihi (Original)",
            "DateTimeDigitized": "Dijitalleşme Tarihi",
            "Orientation": "Görüntü Yönü (Orientation)",
            "Artist": "Sanatçı / Fotoğrafçı",
            "Copyright": "Telif Hakkı (Copyright)",
            "UserComment": "Kullanıcı Yorumu",
            "LensModel": "Lens Bilgisi",
            "ExposureTime": "Pozlama Süresi",
            "FNumber": "Diyafram (F-Stop)",
            "ISOSpeedRatings": "ISO Değeri",
            "GPSInfo": "GPS Konum Bilgisi",
            "Comment": "Yorum",
            "Description": "Açıklama",
            "Author": "Yazar",
        }
        return mapping.get(tag, tag)

    @classmethod
    def _format_exif_value(cls, val: Any) -> str:
        """Format rational, tuple, or binary EXIF values nicely."""
        if isinstance(val, bytes):
            try:
                return val.decode("utf-8", errors="ignore").strip("\x00")
            except Exception:
                return f"Binary Data ({len(val)} bytes)"
        if isinstance(val, (tuple, list)):
            return ", ".join(str(x) for x in val)
        return str(val)

    @classmethod
    def _convert_dms_to_decimal(cls, dms: Any, ref: str) -> float:
        """Convert degrees/minutes/seconds tuple to decimal degrees."""
        if isinstance(dms, (list, tuple)) and len(dms) == 3:
            deg = float(dms[0])
            minute = float(dms[1])
            sec = float(dms[2])
            dec = deg + (minute / 60.0) + (sec / 3600.0)
            if ref in ("S", "W"):
                dec = -dec
            return dec
        return float(dms)

