"""Bottom info banner service that appends a non-overlapping metadata footer below screenshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import getpass
import socket
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from app.services.naming_service import CaptureMetadata

BANNER_THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg_color": "#0F172A",
        "text_color": "#F8FAFC",
        "separator_color": "#334155",
    },
    "light": {
        "bg_color": "#F8FAFC",
        "text_color": "#0F172A",
        "separator_color": "#CBD5E1",
    },
}


@dataclass
class InfoBannerSettings:
    """Configuration for rendering a metadata info band below the image."""

    enabled: bool = False
    auto_apply_on_save: bool = False
    auto_apply_on_copy: bool = False
    apply_on_export: bool = False
    show_datetime: bool = True
    show_window_title: bool = True
    show_app_name: bool = True
    show_url: bool = False
    show_resolution: bool = True
    show_custom_text: bool = False
    custom_text: str = ""
    # Sensitive fields default to False!
    show_computer_name: bool = False
    show_user_name: bool = False
    theme: str = "dark"               # "dark" | "light" | "custom"
    bg_color: str = "#0F172A"
    text_color: str = "#F8FAFC"
    separator_color: str = "#334155"
    show_separator: bool = True
    font_size: int = 12
    alignment: str = "left"           # "left" | "center" | "right"
    wrap_long_text: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InfoBannerSettings":
        theme = str(data.get("theme", "dark"))
        preset = BANNER_THEMES.get(theme, {})
        bg = str(data.get("bg_color", preset.get("bg_color", "#0F172A")))
        fg = str(data.get("text_color", preset.get("text_color", "#F8FAFC")))
        sep = str(data.get("separator_color", preset.get("separator_color", "#334155")))
        if theme in BANNER_THEMES:
            bg = BANNER_THEMES[theme]["bg_color"]
            fg = BANNER_THEMES[theme]["text_color"]
            sep = BANNER_THEMES[theme]["separator_color"]

        return cls(
            enabled=bool(data.get("enabled", False)),
            auto_apply_on_save=bool(data.get("auto_apply_on_save", False)),
            auto_apply_on_copy=bool(data.get("auto_apply_on_copy", False)),
            apply_on_export=bool(data.get("apply_on_export", False)),
            show_datetime=bool(data.get("show_datetime", True)),
            show_window_title=bool(data.get("show_window_title", True)),
            show_app_name=bool(data.get("show_app_name", True)),
            show_url=bool(data.get("show_url", False)),
            show_resolution=bool(data.get("show_resolution", True)),
            show_custom_text=bool(data.get("show_custom_text", False)),
            custom_text=str(data.get("custom_text", "")),
            show_computer_name=bool(data.get("show_computer_name", False)),
            show_user_name=bool(data.get("show_user_name", False)),
            theme=theme,
            bg_color=bg,
            text_color=fg,
            separator_color=sep,
            show_separator=bool(data.get("show_separator", True)),
            font_size=max(8, min(36, int(data.get("font_size", 12)))),
            alignment=str(data.get("alignment", "left")),
            wrap_long_text=bool(data.get("wrap_long_text", True)),
        )

    @classmethod
    def from_config(cls, config_manager: Any) -> "InfoBannerSettings":
        if config_manager is None:
            return cls()
        sec = config_manager.get_section("info_banner") if hasattr(config_manager, "get_section") else {}
        return cls.from_dict(sec)


class InfoBannerService:
    """Appends a non-destructive info banner beneath an image (increasing total height)."""

    @staticmethod
    def should_apply(config_manager: Any, action: str = "save", force_override: Optional[bool] = None) -> bool:
        if force_override is not None:
            return bool(force_override)
        settings = InfoBannerSettings.from_config(config_manager)
        if not settings.enabled:
            return False
        if action == "save":
            return settings.auto_apply_on_save or settings.enabled
        if action == "copy":
            return settings.auto_apply_on_copy
        if action in ("export", "batch"):
            return settings.apply_on_export
        return settings.enabled

    @staticmethod
    def build_fields(
        image_width: int,
        image_height: int,
        settings: InfoBannerSettings,
        metadata: Optional[CaptureMetadata] = None,
    ) -> List[str]:
        """Collect enabled metadata fields in display order."""
        meta = metadata or CaptureMetadata()
        parts: List[str] = []

        if settings.show_datetime:
            ts = meta.timestamp or datetime.now()
            parts.append(ts.strftime("%Y-%m-%d %H:%M:%S"))

        if settings.show_app_name and meta.app_name.strip():
            parts.append(meta.app_name.strip())

        if settings.show_window_title and meta.window_title.strip():
            parts.append(meta.window_title.strip())

        if settings.show_url and meta.url.strip():
            parts.append(meta.url.strip())

        if settings.show_resolution:
            res_txt = meta.resolution.strip() if meta.resolution else f"{image_width} × {image_height} px"
            parts.append(res_txt)

        if settings.show_computer_name:
            try:
                host = socket.gethostname()
                if host:
                    parts.append(host)
            except Exception:
                pass

        if settings.show_user_name:
            try:
                user = getpass.getuser()
                if user:
                    parts.append(user)
            except Exception:
                pass

        if settings.show_custom_text and settings.custom_text.strip():
            parts.append(settings.custom_text.strip())

        return parts

    @staticmethod
    def _wrap_or_elide_text(
        full_text: str,
        fm: QFontMetrics,
        available_width: int,
        wrap: bool,
    ) -> List[str]:
        """Either wrap full_text across multiple lines or elide it to fit available_width."""
        if available_width <= 20:
            return [full_text[:10]]

        if not wrap:
            return [fm.elidedText(full_text, Qt.TextElideMode.ElideRight, available_width)]

        if fm.horizontalAdvance(full_text) <= available_width:
            return [full_text]

        # Word / token wrap
        tokens = full_text.split(" ")
        lines: List[str] = []
        current = ""

        for tok in tokens:
            candidate = f"{current} {tok}".strip() if current else tok
            if fm.horizontalAdvance(candidate) <= available_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                # If a single token is wider than available_width, elide or slice it
                if fm.horizontalAdvance(tok) > available_width:
                    lines.append(fm.elidedText(tok, Qt.TextElideMode.ElideRight, available_width))
                    current = ""
                else:
                    current = tok
            if len(lines) >= 4:
                break

        if current and len(lines) < 4:
            lines.append(current)

        return lines or [fm.elidedText(full_text, Qt.TextElideMode.ElideRight, available_width)]

    @classmethod
    def apply_info_banner(
        cls,
        image: QImage,
        settings: Optional[InfoBannerSettings] = None,
        config_manager: Optional[Any] = None,
        metadata: Optional[CaptureMetadata] = None,
    ) -> QImage:
        """
        Return a new QImage with the info banner appended BELOW the original image.
        The original image pixels are never covered; the returned QImage has height = image.height() + banner_height.
        """
        if image.isNull() or image.width() <= 0 or image.height() <= 0:
            return image

        cfg = settings or InfoBannerSettings.from_config(config_manager)
        fields = cls.build_fields(image.width(), image.height(), cfg, metadata)
        if not fields:
            return image

        full_text = "  •  ".join(fields)

        # Scale font size proportionally to image width and DPI
        img_w = image.width()
        img_h = image.height()
        dpi_scale = 1.0
        if image.dotsPerMeterX() > 0:
            dpi = image.dotsPerMeterX() * 0.0254
            if dpi > 110:
                dpi_scale = min(2.0, dpi / 96.0)

        width_scale = max(0.75, min(2.2, img_w / 1000.0))
        scaled_font_px = max(10, min(42, int(round(cfg.font_size * width_scale * dpi_scale))))

        font = QFont("Segoe UI")
        font.setPixelSize(scaled_font_px)
        font.setWeight(QFont.Weight.Medium)
        fm = QFontMetrics(font)

        pad_x = max(10, int(round(scaled_font_px * 1.1)))
        pad_y = max(8, int(round(scaled_font_px * 0.65)))
        available_w = max(24, img_w - pad_x * 2)

        lines = cls._wrap_or_elide_text(full_text, fm, available_w, cfg.wrap_long_text)
        line_h = fm.height()
        line_gap = max(2, int(round(scaled_font_px * 0.2)))
        sep_px = 1 if cfg.show_separator else 0

        banner_h = sep_px + pad_y * 2 + len(lines) * line_h + max(0, len(lines) - 1) * line_gap
        total_h = img_h + banner_h

        result = QImage(img_w, total_h, QImage.Format.Format_RGBA8888)
        result.setDotsPerMeterX(image.dotsPerMeterX())
        result.setDotsPerMeterY(image.dotsPerMeterY())
        result.fill(Qt.GlobalColor.transparent)

        painter = QPainter(result)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

            # 1. Draw untouched original image at top (0, 0)
            painter.drawImage(0, 0, image)

            # 2. Fill bottom banner background
            bg_qcolor = QColor(cfg.bg_color if QColor.isValidColorName(cfg.bg_color) else "#0F172A")
            banner_rect = QRectF(0, img_h, img_w, banner_h)
            painter.fillRect(banner_rect, bg_qcolor)

            # 3. Optional separator line between image and banner
            if cfg.show_separator:
                sep_qcolor = QColor(cfg.separator_color if QColor.isValidColorName(cfg.separator_color) else "#334155")
                painter.setPen(QPen(sep_qcolor, 1))
                painter.drawLine(QPointF(0, img_h + 0.5), QPointF(img_w, img_h + 0.5))

            # 4. Render text lines with alignment
            fg_qcolor = QColor(cfg.text_color if QColor.isValidColorName(cfg.text_color) else "#F8FAFC")
            painter.setPen(fg_qcolor)
            painter.setFont(font)

            if cfg.alignment == "center":
                align_flag = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            elif cfg.alignment == "right":
                align_flag = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            else:
                align_flag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

            curr_y = img_h + sep_px + pad_y
            for line in lines:
                line_rect = QRectF(pad_x, curr_y, available_w, line_h)
                painter.drawText(line_rect, align_flag, line)
                curr_y += line_h + line_gap
        finally:
            painter.end()

        return result


