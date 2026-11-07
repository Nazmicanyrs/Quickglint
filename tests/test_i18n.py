"""Tests for i18n and language switching."""

from app.utils.i18n import get_language, set_language, tr


def test_i18n_translations():
    # Test Turkish (Default)
    set_language("tr")
    assert get_language() == "tr"
    assert tr("tray_take_screenshot") == "Ekran Görüntüsü Al"
    assert tr("tray_settings") == "Ayarlar"
    assert tr("action_copy") == "Kopyala"
    assert tr("action_save") == "Kaydet"

    # Test English
    set_language("en")
    assert get_language() == "en"
    assert tr("tray_take_screenshot") == "Take Screenshot"
    assert tr("tray_settings") == "Settings"
    assert tr("action_copy") == "Copy"
    assert tr("action_save") == "Save"

    # Test formatted translation
    msg = tr("toast_saved_msg", filename="test.png")
    assert "test.png" in msg

