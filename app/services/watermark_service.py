"""Non-destructive text and PNG image watermark service with 9-point grid, tiling, and profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QTransform

from app.utils.logger import logger

GRID_POSITIONS: List[Tuple[str, str]] = [
    ("diagonal_full", "Köşeden Köşeye Çapraz (Kitap / Film Tarzı)"),
    ("diagonal_cross", "Çift Çapraz X (Kitap / Film Koruması)"),
    ("top_left", "Sol Üst"),
    ("top_center", "Üst Orta"),
    ("top_right", "Sağ Üst"),
    ("middle_left", "Sol Orta"),
    ("center", "Merkez"),
    ("middle_right", "Sağ Orta"),
    ("bottom_left", "Sol Alt"),
    ("bottom_center", "Alt Orta"),
    ("bottom_right", "Sağ Alt"),
]


@dataclass
class WatermarkSettings:
    """Configuration state for rendering a non-destructive watermark."""

    enabled: bool = False
    auto_apply_on_save: bool = False
    auto_apply_on_copy: bool = False
    apply_on_export: bool = False
    watermark_type: str = "text"  # "text" | "image"
    text: str = "Quickglint"
    image_path: str = ""
    position: str = "bottom_right"
    margin: int = 20
    opacity: int = 65             # 0 - 100
    scale_percent: int = 18       # % of target image width (5 - 80)
    rotation: int = 0             # -180 to 180 degrees
    font_family: str = "Segoe UI"
    text_color: str = "#FFFFFF"
    shadow_enabled: bool = True
    tiled: bool = False
    tile_spacing: int = 25        # % of target image width
    diagonal_banner: bool = False # Book / movie style corner-to-corner diagonal watermark

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WatermarkSettings":
        return cls(
            enabled=bool(data.get("enabled", False)),
            auto_apply_on_save=bool(data.get("auto_apply_on_save", False)),
            auto_apply_on_copy=bool(data.get("auto_apply_on_copy", False)),
            apply_on_export=bool(data.get("apply_on_export", False)),
            watermark_type=str(data.get("watermark_type", "text")),
            text=str(data.get("text", "Quickglint")),
            image_path=str(data.get("image_path", "")),
            position=str(data.get("position", "bottom_right")),
            margin=max(0, int(data.get("margin", 20))),
            opacity=max(0, min(100, int(data.get("opacity", 65)))),
            scale_percent=max(3, min(90, int(data.get("scale_percent", 18)))),
            rotation=max(-180, min(180, int(data.get("rotation", 0)))),
            font_family=str(data.get("font_family", "Segoe UI")),
            text_color=str(data.get("text_color", "#FFFFFF")),
            shadow_enabled=bool(data.get("shadow_enabled", True)),
            tiled=bool(data.get("tiled", False)),
            tile_spacing=max(8, min(100, int(data.get("tile_spacing", 25)))),
            diagonal_banner=bool(data.get("diagonal_banner", False)),
        )

    def to_profile_dict(self) -> Dict[str, Any]:
        """Serialize visual watermark parameters into a reusable profile dictionary."""
        d = asdict(self)
        return d

    @classmethod
    def from_config(cls, config_manager: Any) -> "WatermarkSettings":
        if config_manager is None:
            return cls()
        sec = config_manager.get_section("watermark") if hasattr(config_manager, "get_section") else {}
        return cls.from_dict(sec)


class WatermarkService:
    """Renders text or PNG watermarks onto a QImage copy or active QPainter without modifying originals."""

    @staticmethod
    def should_apply(config_manager: Any, action: str = "save", force_override: Optional[bool] = None) -> bool:
        """Check whether watermark should be burned into the output for the given action."""
        if force_override is not None:
            return bool(force_override)
        settings = WatermarkSettings.from_config(config_manager)
        if not settings.enabled:
            return False
        if action == "save":
            return settings.auto_apply_on_save or settings.enabled
        if action == "copy":
            return settings.auto_apply_on_copy
        if action in ("export", "batch"):
            return settings.apply_on_export
        return settings.enabled

    @classmethod
    def build_stamp(
        cls,
        target_width: int,
        settings: WatermarkSettings,
        apply_rotation: bool = True,
        desired_width_override: Optional[float] = None,
    ) -> Optional[QImage]:
        """Create a pre-rendered RGBA stamp (including rotation and shadow) scaled to target_width."""
        if settings.opacity <= 0 or target_width <= 4:
            return None

        desired_w = (
            float(desired_width_override)
            if desired_width_override is not None
            else max(24.0, target_width * (settings.scale_percent / 100.0))
        )
        base_stamp: Optional[QImage] = None

        if settings.watermark_type == "image" and settings.image_path:
            img_path = Path(settings.image_path)
            if img_path.exists() and img_path.is_file():
                loaded = QImage(str(img_path))
                if not loaded.isNull() and loaded.width() > 0 and loaded.height() > 0:
                    loaded = loaded.convertToFormat(QImage.Format.Format_RGBA8888)
                    scaled_w = max(12, int(round(desired_w)))
                    base_stamp = loaded.scaledToWidth(
                        scaled_w,
                        Qt.TransformationMode.SmoothTransformation,
                    )

        if base_stamp is None:
            # Render text watermark
            txt = (settings.text or "").strip()
            if not txt:
                return None

            # Pick font size proportional to desired_w
            font = QFont(settings.font_family or "Segoe UI")
            font.setBold(True)
            font.setPixelSize(48)
            fm = QFontMetricsF(font)
            ref_w = max(1.0, fm.horizontalAdvance(txt))
            scaled_px = max(10, min(320, int(round(48.0 * (desired_w / ref_w)))))
            font.setPixelSize(scaled_px)
            fm = QFontMetricsF(font)

            pad = max(6, int(scaled_px * 0.25))
            txt_w = int(fm.horizontalAdvance(txt)) + pad * 2
            txt_h = int(fm.height()) + pad * 2

            base_stamp = QImage(max(1, txt_w), max(1, txt_h), QImage.Format.Format_RGBA8888)
            base_stamp.fill(Qt.GlobalColor.transparent)

            p = QPainter(base_stamp)
            try:
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                p.setFont(font)

                baseline_y = pad + fm.ascent()
                if settings.shadow_enabled:
                    shadow_offset = max(1.5, scaled_px * 0.06)
                    p.setPen(QColor(0, 0, 0, 170))
                    p.drawText(QPointF(pad + shadow_offset, baseline_y + shadow_offset), txt)

                c = QColor(settings.text_color if QColor.isValidColorName(settings.text_color) else "#FFFFFF")
                p.setPen(c)
                p.drawText(QPointF(pad, baseline_y), txt)
            finally:
                p.end()

        if base_stamp is None or base_stamp.isNull():
            return None

        if apply_rotation:
            effective_rot = float(settings.rotation)
            # In tiled mode ("Çapraz Döşeme"), default 0° rotation automatically uses -35° diagonal angle
            if settings.tiled and effective_rot == 0.0:
                effective_rot = -35.0
            if effective_rot != 0.0:
                transform = QTransform()
                transform.rotate(effective_rot)
                base_stamp = base_stamp.transformed(transform, Qt.TransformationMode.SmoothTransformation)

        return base_stamp

    @classmethod
    def render_on_painter(
        cls,
        painter: QPainter,
        rect: QRectF,
        settings: WatermarkSettings,
    ) -> None:
        """Draw watermark onto an existing QPainter within rect (used for both live preview and output)."""
        if rect.width() <= 4 or rect.height() <= 4 or settings.opacity <= 0:
            return

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.setClipRect(rect)
            painter.setOpacity(max(0.0, min(1.0, settings.opacity / 100.0)))

            is_diag_banner = bool(
                settings.diagonal_banner or settings.position in ("diagonal_full", "diagonal_cross")
            )

            # 1. Book / Movie style corner-to-corner diagonal watermark
            if is_diag_banner and not settings.tiled:
                diag_len = math.hypot(rect.width(), rect.height())
                # Scale across the diagonal (e.g. 55% - 88% of diagonal length)
                scale_ratio = max(0.45, min(0.90, max(0.68, (settings.scale_percent / 100.0) * 3.6)))
                span_w = max(48.0, diag_len * scale_ratio)
                raw_stamp = cls.build_stamp(
                    int(rect.width()),
                    settings,
                    apply_rotation=False,
                    desired_width_override=span_w,
                )
                if raw_stamp is None or raw_stamp.isNull():
                    return

                auto_angle = -math.degrees(math.atan2(rect.height(), rect.width()))
                angle = float(settings.rotation) if settings.rotation != 0 else auto_angle
                center = rect.center()

                angles = [angle, -angle] if settings.position == "diagonal_cross" else [angle]
                for ang in angles:
                    painter.save()
                    painter.translate(center)
                    painter.rotate(ang)
                    painter.drawImage(
                        QPointF(-raw_stamp.width() / 2.0, -raw_stamp.height() / 2.0),
                        raw_stamp,
                    )
                    painter.restore()
                return

            # 2. Tiled diagonal repeat or 9-point grid position
            stamp = cls.build_stamp(int(rect.width()), settings, apply_rotation=True)
            if stamp is None or stamp.isNull():
                return

            sw = stamp.width()
            sh = stamp.height()
            margin = float(max(0, settings.margin))

            if settings.tiled:
                gap = max(24.0, rect.width() * (settings.tile_spacing / 100.0))
                step_x = max(32.0, sw + gap)
                step_y = max(32.0, sh + gap * 0.65)

                row_idx = 0
                y = rect.top() - sh * 0.35
                while y < rect.bottom() + sh:
                    offset_x = (step_x * 0.5) if (row_idx % 2 == 1) else 0.0
                    x = rect.left() - sw * 0.35 + offset_x
                    while x < rect.right() + sw:
                        painter.drawImage(QPointF(x, y), stamp)
                        x += step_x
                    y += step_y
                    row_idx += 1
            else:
                pos = settings.position or "bottom_right"
                if "left" in pos:
                    x = rect.left() + margin
                elif "right" in pos:
                    x = rect.right() - sw - margin
                else:
                    x = rect.left() + (rect.width() - sw) / 2.0

                if "top" in pos:
                    y = rect.top() + margin
                elif "bottom" in pos:
                    y = rect.bottom() - sh - margin
                else:
                    y = rect.top() + (rect.height() - sh) / 2.0

                painter.drawImage(QPointF(x, y), stamp)
        finally:
            painter.restore()

    @classmethod
    def apply_watermark(
        cls,
        image: QImage,
        settings: Optional[WatermarkSettings] = None,
        config_manager: Optional[Any] = None,
    ) -> QImage:
        """Return a new QImage with the configured watermark rendered non-destructively."""
        if image.isNull():
            return image

        cfg = settings or WatermarkSettings.from_config(config_manager)
        if cfg.opacity <= 0:
            return image

        result = image.copy().convertToFormat(QImage.Format.Format_RGBA8888)
        painter = QPainter(result)
        try:
            cls.render_on_painter(painter, QRectF(result.rect()), cfg)
        finally:
            painter.end()
        return result

    # --- Profile Management ---

    @staticmethod
    def save_profile(config_manager: Any, profile_name: str, settings: WatermarkSettings) -> None:
        """Save a named watermark preset into config_manager."""
        if config_manager is None or not profile_name.strip():
            return
        name = profile_name.strip()
        profiles = dict(config_manager.get("watermark", "profiles", {}) or {})
        profiles[name] = settings.to_profile_dict()
        config_manager.set("watermark", "profiles", profiles)
        config_manager.set("watermark", "active_profile", name)

    @staticmethod
    def delete_profile(config_manager: Any, profile_name: str) -> None:
        """Delete a named watermark preset from config_manager."""
        if config_manager is None or not profile_name.strip():
            return
        profiles = dict(config_manager.get("watermark", "profiles", {}) or {})
        if profile_name in profiles:
            del profiles[profile_name]
            config_manager.set("watermark", "profiles", profiles)


