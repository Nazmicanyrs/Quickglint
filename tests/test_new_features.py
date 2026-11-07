"""Tests for auto-redact on save and settings import/export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage

from app.privacy.auto_redactor import AutoRedactor
from app.privacy.detection_result import DetectionResult, PrivacyAction, SensitiveType
from config.config_manager import ConfigManager


# ---------------------------------------------------------------------------
# 1. Settings import / export
# ---------------------------------------------------------------------------
def test_settings_export_and_import_roundtrip(tmp_path: Path) -> None:
    cfg_path = tmp_path / "settings.json"
    export_path = tmp_path / "exported_settings.json"

    cm1 = ConfigManager(custom_path=cfg_path)
    cm1.set("general", "language", "en")
    cm1.set("privacy", "auto_redact_on_save", True)
    cm1.export_to_file(export_path)

    assert export_path.exists()
    raw = json.loads(export_path.read_text(encoding="utf-8"))
    assert raw["format"] == ConfigManager.EXPORT_FORMAT

    cm2 = ConfigManager(custom_path=tmp_path / "other.json")
    assert cm2.get("general", "language") == "tr"
    applied = cm2.import_from_file(export_path)
    assert applied > 0
    assert cm2.get("general", "language") == "en"
    assert cm2.get("privacy", "auto_redact_on_save") is True


def test_settings_import_rejects_invalid_files(tmp_path: Path) -> None:
    cm = ConfigManager(custom_path=tmp_path / "settings.json")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"format": "WrongFormat", "settings": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        cm.import_from_file(bad)


def test_settings_import_skips_wrong_types(tmp_path: Path) -> None:
    cm = ConfigManager(custom_path=tmp_path / "settings.json")
    f = tmp_path / "export.json"
    f.write_text(
        json.dumps(
            {
                "format": ConfigManager.EXPORT_FORMAT,
                "version": 1,
                "settings": {
                    "image": {"jpeg_quality": "not_an_int", "include_cursor": True},
                },
            }
        ),
        encoding="utf-8",
    )
    applied = cm.import_from_file(f)
    assert applied == 1
    assert cm.get("image", "include_cursor") is True
    assert isinstance(cm.get("image", "jpeg_quality"), int)


# ---------------------------------------------------------------------------
# 2. Automatic privacy redaction
# ---------------------------------------------------------------------------
def _make_solid_image(w: int = 120, h: int = 80, color: QColor = QColor(255, 255, 255)) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(color)
    return img


def test_auto_redactor_disabled_by_default(tmp_path: Path) -> None:
    cm = ConfigManager(custom_path=tmp_path / "settings.json")
    assert AutoRedactor.is_enabled(cm) is False
    cm.set("privacy", "auto_redact_on_save", True)
    assert AutoRedactor.is_enabled(cm) is True


def test_auto_redactor_masks_detected_boxes_and_respects_category_toggles(tmp_path: Path) -> None:
    cm = ConfigManager(custom_path=tmp_path / "settings.json")
    cm.set("privacy", "enabled", True)
    cm.set("privacy", "auto_redact_on_save", True)
    cm.set("privacy", "default_effect", "blackout")
    cm.set("privacy", "detect_emails", True)
    cm.set("privacy", "detect_phones", False)

    img = _make_solid_image()

    def fake_scan(_img: QImage) -> List[DetectionResult]:
        return [
            DetectionResult(
                type=SensitiveType.EMAIL,
                text="user@example.com",
                confidence=0.99,
                bounding_box=QRect(10, 10, 30, 20),
                reason="Email",
            ),
            DetectionResult(
                type=SensitiveType.PHONE,
                text="+905551112233",
                confidence=0.95,
                bounding_box=QRect(60, 40, 30, 20),
                reason="Phone",
            ),
        ]

    res = AutoRedactor.redact(img, cm, scan_func=fake_scan)
    assert res.count == 1
    assert res.image.pixelColor(20, 20) == QColor(0, 0, 0)
    assert res.image.pixelColor(70, 50) == QColor(255, 255, 255)


@pytest.mark.parametrize("effect", [PrivacyAction.PIXELATE, PrivacyAction.BLUR, PrivacyAction.BLACKOUT])
def test_apply_masks_effects(effect: PrivacyAction) -> None:
    img = _make_solid_image()
    for x in range(10, 40):
        for y in range(10, 30):
            img.setPixelColor(x, y, QColor((x * 17) % 255, (y * 31) % 255, 100))
    out = AutoRedactor.apply_masks(img, [QRect(10, 10, 30, 20)], effect=effect)
    assert not out.isNull()
    assert out.size() == img.size()


def test_settings_dialog_builds_new_controls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.security.credential_store.CredentialStore.get_credential",
        classmethod(lambda cls, s, a: ""),
    )
    monkeypatch.setattr(
        "app.security.credential_store.CredentialStore.has_credential",
        classmethod(lambda cls, s, a: False),
    )
    from app.ui.settings_dialog import SettingsDialog

    cm = ConfigManager(custom_path=tmp_path / "settings.json")
    dlg = SettingsDialog(cm)
    assert hasattr(dlg, "priv_auto_redact_cb")
    assert hasattr(dlg, "btn_export_settings")
    assert hasattr(dlg, "btn_import_settings")
    assert hasattr(dlg, "naming_template_edit")
    assert hasattr(dlg, "wm_enabled_cb")
    assert hasattr(dlg, "wm_profile_combo")
    assert hasattr(dlg, "ib_enabled_cb")
    assert dlg.ib_comp_cb.isChecked() is False
    assert dlg.ib_user_cb.isChecked() is False
    assert not hasattr(dlg, "drive_enabled_cb")
    dlg.close()


# ---------------------------------------------------------------------------
# 3. Feature 1: Watermark (Text, PNG, 9-point grid, Tiling, Profiles)
# ---------------------------------------------------------------------------
def test_watermark_text_and_tiling_and_profiles(tmp_path: Path) -> None:
    from app.services.watermark_service import WatermarkService, WatermarkSettings

    base = _make_solid_image(300, 200, QColor(30, 40, 50))
    orig_copy = base.copy()

    # 1. Text watermark at bottom_right
    settings = WatermarkSettings(
        enabled=True,
        watermark_type="text",
        text="CONFIDENTIAL",
        position="bottom_right",
        margin=16,
        opacity=85,
        scale_percent=25,
        rotation=-15,
        text_color="#FFFFFF",
        shadow_enabled=True,
        tiled=False,
    )
    out = WatermarkService.apply_watermark(base, settings=settings)
    assert out.size() == base.size()
    # Non-destructive: base is untouched
    assert base.pixelColor(150, 100) == orig_copy.pixelColor(150, 100)

    # 2. Tiled watermark (even with rotation=0, automatically angles tiles diagonally at -35 deg)
    tiled_settings = WatermarkSettings(
        enabled=True,
        watermark_type="text",
        text="TILE",
        opacity=70,
        scale_percent=15,
        rotation=0,
        tiled=True,
        tile_spacing=20,
    )
    out_tiled = WatermarkService.apply_watermark(base, settings=tiled_settings)
    assert out_tiled.size() == base.size()

    # 2b. Book / movie style corner-to-corner diagonal watermark (diagonal_banner & diagonal_cross)
    diag_settings = WatermarkSettings(
        enabled=True,
        watermark_type="text",
        text="ÖRNEK / DRAFT",
        opacity=80,
        scale_percent=20,
        diagonal_banner=True,
    )
    out_diag = WatermarkService.apply_watermark(base, settings=diag_settings)
    assert out_diag.size() == base.size()

    cross_settings = WatermarkSettings(
        enabled=True,
        watermark_type="text",
        text="GİZLİ / CONFIDENTIAL",
        position="diagonal_cross",
        opacity=80,
        scale_percent=20,
    )
    out_cross = WatermarkService.apply_watermark(base, settings=cross_settings)
    assert out_cross.size() == base.size()

    # 3. Image (PNG) watermark with transparency
    png_path = tmp_path / "logo.png"
    logo = QImage(64, 64, QImage.Format.Format_RGBA8888)
    logo.fill(QColor(255, 0, 0, 180))
    logo.save(str(png_path), "PNG")

    img_settings = WatermarkSettings(
        enabled=True,
        watermark_type="image",
        image_path=str(png_path),
        position="center",
        opacity=90,
        scale_percent=20,
    )
    out_img = WatermarkService.apply_watermark(base, settings=img_settings)
    # Center pixel should have blended red over (30, 40, 50)
    center_px = out_img.pixelColor(150, 100)
    assert center_px.red() > 120

    # 4. Profile save / load / delete
    cm = ConfigManager(custom_path=tmp_path / "wm_settings.json")
    WatermarkService.save_profile(cm, "Kurumsal", settings)
    profiles = cm.get("watermark", "profiles", {})
    assert "Kurumsal" in profiles
    loaded = WatermarkSettings.from_dict(profiles["Kurumsal"])
    assert loaded.text == "CONFIDENTIAL"
    assert loaded.rotation == -15
    WatermarkService.delete_profile(cm, "Kurumsal")
    assert "Kurumsal" not in cm.get("watermark", "profiles", {})


# ---------------------------------------------------------------------------
# 4. Feature 2: Smart File Naming (Variables, Sanitization, Reserved, Collision)
# ---------------------------------------------------------------------------
def test_smart_file_naming_templates_and_security(tmp_path: Path) -> None:
    from datetime import datetime
    from app.services.naming_service import CaptureMetadata, SmartNamingService

    meta = CaptureMetadata(
        timestamp=datetime(2026, 11, 5, 19, 45, 30),
        window_title='Fatura: "Özet" <2026> | Chrome*',
        app_name="chrome.exe",
        mode="bolge",
        ocr_text="",  # Empty OCR -> should not trigger OCR and should collapse cleanly
    )

    stem = SmartNamingService.format_stem(
        "Quickglint_{date}_{time}_{app}_{window}_{ocr}_{n}",
        metadata=meta,
        counter=7,
    )
    assert "2026-11-05" in stem
    assert "19-45-30" in stem
    assert "007" in stem
    # No invalid Windows characters
    for bad_ch in '<>:"/\\|?*':
        assert bad_ch not in stem
    # No double underscores from empty {ocr}
    assert "__" not in stem

    # When OCR text is already present, first meaningful line is used
    meta.ocr_text = "\n  \nSipariş #9842 Detayı\nİkinci Satır"
    stem_with_ocr = SmartNamingService.format_stem("{app}_{ocr}_{n}", metadata=meta, counter=1)
    assert "Sipariş_#9842_Detayı" in stem_with_ocr

    # Windows reserved device names (CON, NUL, COM1) are neutralized
    reserved_stem = SmartNamingService.format_stem("CON", metadata=meta, counter=1)
    assert reserved_stem.upper() != "CON"

    # Invalid template falls back to default
    fallback_stem = SmartNamingService.format_stem("{unclosed_brace", metadata=meta, counter=3)
    assert fallback_stem.startswith("Quickglint_2026-11-05_19-45-30_003")

    # Collision resolution never overwrites existing files
    cm = ConfigManager(custom_path=tmp_path / "naming.json")
    cm.set("naming", "template", "Shot_{date}_{n}")
    cm.set("naming", "counter", 1)

    p1 = SmartNamingService.resolve_safe_path(
        tmp_path, ext="png", metadata=meta, config_manager=cm, increment_counter=False
    )
    p1.write_bytes(b"existing")
    p2 = SmartNamingService.resolve_safe_path(
        tmp_path, ext="png", metadata=meta, config_manager=cm, increment_counter=False
    )
    assert p1 != p2
    assert p2.name.endswith("_2.png")


# ---------------------------------------------------------------------------
# 5. Feature 3: Bottom Info Banner (Extends height, sensitive defaults OFF)
# ---------------------------------------------------------------------------
def test_bottom_info_banner_extends_height_and_preserves_image() -> None:
    from datetime import datetime
    from app.services.info_banner_service import InfoBannerService, InfoBannerSettings
    from app.services.naming_service import CaptureMetadata

    default_cfg = InfoBannerSettings()
    # Sensitive fields MUST default to False
    assert default_cfg.show_computer_name is False
    assert default_cfg.show_user_name is False

    base = _make_solid_image(400, 150, QColor(10, 200, 120))
    meta = CaptureMetadata(
        timestamp=datetime(2026, 11, 5, 19, 50, 0),
        window_title="Uzun Pencere Başlığı — Quickglint Test Uygulaması",
        app_name="Quickglint",
        url="https://example.org/docs",
        resolution="400 × 150 px",
    )
    cfg = InfoBannerSettings(
        enabled=True,
        show_datetime=True,
        show_window_title=True,
        show_app_name=True,
        show_url=True,
        show_resolution=True,
        show_custom_text=True,
        custom_text="Test Notu",
        theme="dark",
        wrap_long_text=True,
    )

    out = InfoBannerService.apply_info_banner(base, settings=cfg, metadata=meta)
    assert out.width() == base.width()
    assert out.height() > base.height()
    # Original image region (y < 150) is 100% preserved and not covered
    assert out.pixelColor(200, 75) == QColor(10, 200, 120)
    assert out.pixelColor(200, 149) == QColor(10, 200, 120)
    # Banner region (y >= 150) has dark theme background / separator
    assert out.pixelColor(5, out.height() - 2) == QColor("#0F172A")


