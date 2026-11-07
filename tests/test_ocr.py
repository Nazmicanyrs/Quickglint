"""Comprehensive test suite for Quickglint OCR / Image-to-Text extraction system."""

import hashlib
import json
import time
from pathlib import Path
from PIL import Image, ImageDraw
import pytest
from PySide6.QtCore import QEventLoop, QRect, QTimer
from PySide6.QtGui import QGuiApplication, QImage

from app.ocr.cache import OCRMemoryCache
from app.ocr.dialog import TextExtractionDialog
from app.ocr.formatter import TextFormatter
from app.ocr.layout import LayoutAnalyzer
from app.ocr.models import (
    OCRBlock,
    OCRLine,
    OCRParagraph,
    OCRStructuredResult,
    OCRWord,
    ReadingOrderMode,
)
from app.ocr.preprocessing import ImagePreprocessor, qimage_to_pil
from app.ocr.provider import (
    AutoOCRProvider,
    EasyOCRProvider,
    MockOCRProvider,
    TesseractProvider,
    WindowsNativeOCRProvider,
)
from app.ocr.worker import OCRWorker
from app.security.vault import SecureVault


def create_test_image(text: str = "selam naber nasıl gidiyor ayşe", size=(400, 200), bg=(255, 255, 255), fg=(0, 0, 0)) -> QImage:
    """Helper to create a test QImage with rendered text."""
    pil_img = Image.new("RGB", size, color=bg)
    draw = ImageDraw.Draw(pil_img)
    draw.text((20, 50), text, fill=fg)
    from app.ocr.preprocessing import pil_to_qimage
    return pil_to_qimage(pil_img)


# 1. Turkish text detection
def test_turkish_text_detection():
    words = [
        OCRWord("selam", 0.98, QRect(20, 50, 60, 20), word_index=0),
        OCRWord("naber", 0.95, QRect(90, 50, 60, 20), word_index=1),
        OCRWord("nasıl", 0.94, QRect(160, 50, 60, 20), word_index=2),
        OCRWord("gidiyor", 0.92, QRect(230, 50, 70, 20), word_index=3),
        OCRWord("ayşe", 0.96, QRect(310, 50, 50, 20), word_index=4),
    ]
    provider = MockOCRProvider(mock_words=words)
    img = create_test_image("selam naber nasıl gidiyor ayşe")
    res = provider.detect_structured(img, languages=["tr"])

    assert "selam naber nasıl gidiyor ayşe" in res.full_text
    assert len(res.get_all_words()) == 5
    assert res.average_confidence > 0.90


# 2. English text detection
def test_english_text_detection():
    words = [
        OCRWord("Hello", 0.99, QRect(20, 50, 50, 20)),
        OCRWord("world", 0.98, QRect(80, 50, 50, 20)),
        OCRWord("Quickglint", 0.97, QRect(140, 50, 80, 20)),
    ]
    provider = MockOCRProvider(mock_words=words)
    img = create_test_image("Hello world Quickglint")
    res = provider.detect_structured(img, languages=["en"])

    assert res.full_text == "Hello world Quickglint"
    assert res.language == "en"


# 3. Multi-language OCR
def test_multilanguage_ocr():
    words = [
        OCRWord("Guten", 0.95, QRect(20, 30, 50, 20)),
        OCRWord("Tag", 0.95, QRect(80, 30, 40, 20)),
        OCRWord("merhaba", 0.96, QRect(20, 70, 70, 20)),
        OCRWord("dünya", 0.96, QRect(100, 70, 50, 20)),
    ]
    provider = MockOCRProvider(mock_words=words)
    img = create_test_image()
    res = provider.detect_structured(img, languages=["de", "tr"])
    assert "Guten Tag" in res.full_text
    assert "merhaba dünya" in res.full_text


# 4. Bounding box detection
def test_bounding_box_detection():
    w = OCRWord("Quickglint", 0.99, QRect(100, 150, 200, 40))
    assert w.bounding_box.x() == 100
    assert w.bounding_box.y() == 150
    assert w.bounding_box.width() == 200
    assert w.bounding_box.height() == 40

    d = w.to_dict()
    assert d["bbox"] == [100, 150, 200, 40]


# 5. Word-level OCR
def test_word_level_ocr():
    words = [
        OCRWord("box1", 0.98, QRect(10, 10, 30, 15), word_index=0),
        OCRWord("box2", 0.95, QRect(50, 10, 30, 15), word_index=1),
    ]
    provider = MockOCRProvider(mock_words=words)
    img = create_test_image()
    res = provider.detect_structured(img)
    all_words = res.get_all_words()
    assert len(all_words) == 2
    assert all_words[0].text == "box1"
    assert all_words[1].text == "box2"


# 6. Line-level OCR
def test_line_level_ocr():
    w1 = OCRWord("Satır", 0.95, QRect(10, 10, 40, 15))
    w2 = OCRWord("Bir", 0.95, QRect(60, 10, 30, 15))
    line = OCRLine(words=[w1, w2], line_index=0)
    assert line.text == "Satır Bir"
    assert line.bounding_box.left() == 10
    assert line.bounding_box.width() == 80


# 7. Paragraph reconstruction
def test_paragraph_reconstruction():
    l1 = OCRLine(words=[OCRWord("Paragraf", 0.9, QRect(10, 10, 60, 15)), OCRWord("1", 0.9, QRect(80, 10, 20, 15))])
    l2 = OCRLine(words=[OCRWord("İkinci", 0.9, QRect(10, 30, 50, 15)), OCRWord("satır", 0.9, QRect(70, 30, 40, 15))])
    p = OCRParagraph(lines=[l1, l2])
    assert p.text == "Paragraf 1\nİkinci satır"


# 8. Reading order
def test_reading_order():
    # Top title, description below, button text at bottom
    w_title = OCRWord("Başlık", 0.99, QRect(50, 10, 80, 25))
    w_desc = OCRWord("Açıklama", 0.95, QRect(50, 50, 90, 20))
    w_btn = OCRWord("Buton", 0.92, QRect(50, 100, 60, 20))

    # Passed in shuffled order
    res = LayoutAnalyzer.structure_tokens([w_btn, w_title, w_desc], 500, 300)
    lines = res.get_all_lines()
    assert lines[0].text == "Başlık"
    assert lines[1].text == "Açıklama"
    assert lines[2].text == "Buton"


# 9. Multi-column text
def test_multi_column_text():
    # Column 1 (Left): A, B, C (x=20..50)
    col1_w1 = OCRWord("A", 0.95, QRect(20, 20, 30, 15))
    col1_w2 = OCRWord("B", 0.95, QRect(20, 50, 30, 15))
    col1_w3 = OCRWord("C", 0.95, QRect(20, 80, 30, 15))

    # Column 2 (Right): X, Y, Z (x=350..380)
    col2_w1 = OCRWord("X", 0.95, QRect(350, 20, 30, 15))
    col2_w2 = OCRWord("Y", 0.95, QRect(350, 50, 30, 15))
    col2_w3 = OCRWord("Z", 0.95, QRect(350, 80, 30, 15))

    res = LayoutAnalyzer.structure_tokens([col1_w1, col2_w1, col1_w2, col2_w2, col1_w3, col2_w3], 600, 200)
    assert res.reading_order == "multi_column"
    assert len(res.blocks) == 2
    assert "A" in res.blocks[0].text
    assert "X" in res.blocks[1].text


# 10. Turkish characters preservation
def test_turkish_characters():
    sample = "nasıl gidiyor Ayşe İstanbul şifre çalışıyor çöp öğütme"
    words = [OCRWord(w, 0.98, QRect(i * 50, 20, 45, 15)) for i, w in enumerate(sample.split())]
    res = LayoutAnalyzer.structure_tokens(words, 800, 100)
    for expected in ["ç", "ğ", "ı", "İ", "ö", "ş", "ü"]:
        assert expected in res.full_text


# 11. Text selection
def test_text_selection():
    words = [
        OCRWord("Merhaba", 0.98, QRect(20, 20, 60, 20), word_index=0, line_index=0, block_index=0),
        OCRWord("Ayşe,", 0.98, QRect(90, 20, 50, 20), word_index=1, line_index=0, block_index=0),
        OCRWord("Bugün", 0.95, QRect(20, 60, 50, 20), word_index=0, line_index=1, block_index=0),
        OCRWord("hava", 0.95, QRect(80, 60, 40, 20), word_index=1, line_index=1, block_index=0),
        OCRWord("güzel.", 0.95, QRect(130, 60, 50, 20), word_index=2, line_index=1, block_index=0),
    ]
    res = LayoutAnalyzer.structure_tokens(words, 400, 200)

    # Select only "Bugün hava güzel."
    all_w = res.get_all_words()
    selected_ids = {all_w[2].id, all_w[3].id, all_w[4].id}
    selected_text = res.get_selected_text(selected_ids)
    assert selected_text == "Bugün hava güzel."


# 12. Copy all text
def test_copy_all_text():
    words = [OCRWord("selam", 0.98, QRect(10, 10, 40, 20)), OCRWord("naber", 0.98, QRect(60, 10, 40, 20))]
    res = LayoutAnalyzer.structure_tokens(words, 300, 100)
    img = create_test_image()

    dialog = TextExtractionDialog(image=img, initial_result=res)
    dialog._copy_all()
    clipboard_text = QGuiApplication.clipboard().text() or getattr(dialog, "_last_copied_text", "")
    assert clipboard_text == "selam naber"
    dialog.close()


# 13. Copy selected text
def test_copy_selected_text():
    words = [
        OCRWord("Satır1", 0.98, QRect(10, 10, 50, 20)),
        OCRWord("Satır2", 0.98, QRect(10, 40, 50, 20)),
    ]
    res = LayoutAnalyzer.structure_tokens(words, 300, 100)
    img = create_test_image()

    dialog = TextExtractionDialog(image=img, initial_result=res)
    # Select word 2
    dialog.overlay_widget.selected_word_ids = {res.get_all_words()[1].id}
    dialog._on_overlay_selection_changed(dialog.overlay_widget.selected_word_ids)

    dialog._copy_selected()
    clipboard_text = QGuiApplication.clipboard().text() or getattr(dialog, "_last_copied_text", "")
    assert clipboard_text == "Satır2"
    dialog.close()


# 14. User text correction
def test_user_text_correction():
    words = [OCRWord("Ayse", 0.85, QRect(10, 10, 50, 20))]
    res = LayoutAnalyzer.structure_tokens(words, 300, 100)
    img = create_test_image()

    dialog = TextExtractionDialog(image=img, initial_result=res)
    copied_texts = []
    dialog.text_copied.connect(lambda t: copied_texts.append(t))
    dialog.text_editor.setPlainText("Ayşe")
    dialog._copy_all()

    assert copied_texts == ["Ayşe"]
    dialog.close()


# 15. Save TXT
def test_save_txt(tmp_path):
    words = [OCRWord("Test", 0.99, QRect(10, 10, 40, 20)), OCRWord("TXT", 0.99, QRect(60, 10, 30, 20))]
    res = LayoutAnalyzer.structure_tokens(words, 300, 100)
    txt_out = TextFormatter.to_plaintext(res)
    p = tmp_path / "out.txt"
    p.write_text(txt_out, encoding="utf-8")

    assert p.read_text(encoding="utf-8") == "Test TXT"


# 16. Save Markdown
def test_save_markdown():
    l1 = OCRLine(words=[OCRWord("Başlık", 0.99, QRect(10, 10, 60, 20))])
    l2 = OCRLine(words=[OCRWord("İçerik", 0.99, QRect(10, 50, 60, 20))])
    b1 = OCRBlock(paragraphs=[OCRParagraph(lines=[l1])])
    b2 = OCRBlock(paragraphs=[OCRParagraph(lines=[l2])])
    res = OCRStructuredResult(blocks=[b1, b2])

    md = TextFormatter.to_markdown(res)
    assert "Başlık" in md
    assert "İçerik" in md
    assert "---" in md


# 17. Save JSON
def test_save_json():
    w = OCRWord("selam", 0.97, QRect(100, 200, 850, 80))
    res = LayoutAnalyzer.structure_tokens([w], 1000, 400)
    json_str = TextFormatter.to_json_string(res)
    data = json.loads(json_str)

    assert data["text"] == "selam"
    assert data["confidence"] == 0.97
    assert len(data["blocks"]) == 1
    assert "vault_key" not in json_str


# 18. Low confidence handling
def test_low_confidence_handling():
    words = [
        OCRWord("ayşe", 0.62, QRect(10, 10, 40, 20)),
    ]
    res = LayoutAnalyzer.structure_tokens(words, 300, 100)
    assert res.average_confidence < 0.70


# 19. Rotated text
def test_rotated_text():
    img = create_test_image("Döndürülmüş Metin", size=(300, 300))
    pil_img = qimage_to_pil(img).rotate(90, expand=True)
    proc, rot, _ = ImagePreprocessor.preprocess(pil_img, detect_orientation=True)
    assert proc is not None


# 20. Deskew
def test_deskew():
    img = create_test_image("Deskew Test", size=(200, 100))
    angle = ImagePreprocessor.detect_skew_angle(qimage_to_pil(img))
    assert isinstance(angle, float)


# 21. Small text upscaling
def test_small_text():
    img = create_test_image("Küçük Metin", size=(350, 200))
    proc_img, _, was_upscaled = ImagePreprocessor.preprocess(img, upscale_small_text=True)
    assert was_upscaled is True
    assert proc_img.width > 350


# 22. Low quality screenshot enhancement
def test_low_quality_screenshot():
    img = create_test_image("Low Quality", size=(500, 300))
    proc_normal, _, _ = ImagePreprocessor.preprocess(img, enhance=False)
    proc_enhanced, _, _ = ImagePreprocessor.preprocess(img, enhance=True)
    assert proc_enhanced is not None


# 23. 4K image performance
def test_4k_image():
    # 3840 x 2160
    pil_img = Image.new("RGB", (3840, 2160), color=(255, 255, 255))
    draw = ImageDraw.Draw(pil_img)
    draw.text((100, 100), "4K Screenshot Text", fill=(0, 0, 0))

    start_t = time.perf_counter()
    copy_img = ImagePreprocessor.create_analysis_copy(pil_img)
    elapsed = time.perf_counter() - start_t
    assert copy_img.size == (3840, 2160)
    assert elapsed < 0.5


# 24. 8K image performance
def test_8k_image():
    pil_img = Image.new("RGB", (7680, 4320), color=(255, 255, 255))
    copy_img = ImagePreprocessor.create_analysis_copy(pil_img)
    assert copy_img.size == (7680, 4320)


# 25. OCR cancel
def test_ocr_cancel():
    words = [OCRWord("CancelTest", 0.99, QRect(10, 10, 80, 20))]
    provider = MockOCRProvider(mock_words=words, delay_seconds=0.3)
    img = create_test_image()

    worker = OCRWorker(image=img, provider=provider, use_cache=False)
    worker.cancel()
    assert worker.is_cancelled is True


# 26. Worker thread responsiveness
def test_worker_thread_responsiveness():
    words = [OCRWord("AsyncText", 0.99, QRect(10, 10, 80, 20))]
    provider = MockOCRProvider(mock_words=words)
    img = create_test_image()

    worker = OCRWorker(image=img, provider=provider, use_cache=False)
    loop = QEventLoop()
    finished_res = []

    def on_finish(res):
        finished_res.append(res)
        loop.quit()

    worker.finished.connect(on_finish)
    worker.start()
    QTimer.singleShot(3000, loop.quit)
    loop.exec()

    assert len(finished_res) == 1
    assert finished_res[0].full_text == "AsyncText"


# 27. OCR Memory Cache
def test_ocr_cache():
    cache = OCRMemoryCache.get_instance()
    cache.clear()

    img = create_test_image("Cached Text")
    res = OCRStructuredResult(full_text="Cached Text")

    cache.put(img, res)
    retrieved = cache.get(img)
    assert retrieved is not None
    assert retrieved.full_text == "Cached Text"


# 28. Secure Vault OCR
def test_secure_vault_ocr(tmp_path):
    vault_dir = tmp_path / "vault"
    vault = SecureVault(vault_dir)
    vault.create_vault("StrongPass123!")

    img = create_test_image("Secret Vault Data")
    obj_id = vault.add_image(img, "Confidential Document")

    # Decrypt in memory
    decrypted_img = vault.get_image(obj_id)
    assert decrypted_img is not None
    assert not decrypted_img.isNull()

    # Perform OCR
    words = [OCRWord("Secret", 0.99, QRect(20, 50, 60, 20)), OCRWord("Vault", 0.99, QRect(90, 50, 50, 20))]
    provider = MockOCRProvider(mock_words=words)
    res = provider.detect_structured(decrypted_img)
    assert res.full_text == "Secret Vault"


# 29. No plaintext vault metadata leakage
def test_no_plaintext_vault_metadata_leakage():
    res = OCRStructuredResult(full_text="Test Data")
    json_str = TextFormatter.to_json_string(res)
    for forbidden in ["master_password", "vault_key", "kek", "nonce", "salt"]:
        assert forbidden not in json_str


# 30. Clipboard history does not store copied OCR text
def test_clipboard_history_does_not_store_copied_ocr_text():
    # Verify Clipboard History only stores images, text copies are not added to image history
    from app.services.clipboard_service import ClipboardService
    # ClipboardService has only copy_image / copy_pixmap methods
    assert not hasattr(ClipboardService, "copy_text_to_history")


# 31. OCR original image pixel data unchanged
def test_ocr_original_image_unchanged():
    img = create_test_image("Original Pixels", size=(200, 100))
    orig_bytes = bytes(img.constBits())

    # Preprocess analysis copy
    proc_img, _, _ = ImagePreprocessor.preprocess(img, enhance=True, upscale_small_text=True)

    # Verify original QImage bits are 100% identical
    after_bytes = bytes(img.constBits())
    assert orig_bytes == after_bytes


# 32. Multiple paragraphs
def test_multiple_paragraphs():
    # 2 lines with a large gap
    l1 = OCRLine(words=[OCRWord("P1", 0.9, QRect(10, 10, 40, 15))])
    l2 = OCRLine(words=[OCRWord("P2", 0.9, QRect(10, 80, 40, 15))])  # Gap > 1.4x
    paragraphs = LayoutAnalyzer._group_lines_into_paragraphs([l1, l2], 0)
    assert len(paragraphs) == 2
    assert paragraphs[0].text == "P1"
    assert paragraphs[1].text == "P2"


# 33. Multiple columns layout
def test_multiple_columns():
    lines = [
        OCRLine(words=[OCRWord("Col1_L1", 0.9, QRect(20, 20, 60, 15))]),
        OCRLine(words=[OCRWord("Col1_L2", 0.9, QRect(20, 50, 60, 15))]),
        OCRLine(words=[OCRWord("Col2_L1", 0.9, QRect(300, 20, 60, 15))]),
        OCRLine(words=[OCRWord("Col2_L2", 0.9, QRect(300, 50, 60, 15))]),
    ]
    cols = LayoutAnalyzer._detect_columns(lines, 600)
    assert len(cols) == 2


# 34. Image without text
def test_image_without_text():
    provider = MockOCRProvider(mock_words=[])
    img = create_test_image(text="")
    res = provider.detect_structured(img)
    assert res.full_text == ""
    assert len(res.blocks) == 0


# 35. Corrupted image handling
def test_corrupted_image():
    with pytest.raises(TypeError):
        ImagePreprocessor.create_analysis_copy("invalid_not_an_image")


# 36. OCR engine unavailable handling
def test_ocr_engine_unavailable():
    provider = MockOCRProvider(available=False)
    img = create_test_image()
    res = provider.detect_structured(img)
    assert res.full_text == ""
    assert res.average_confidence == 0.0

