"""Optical Character Recognition (OCR) module for Quickglint."""

from app.ocr.dialog import TextExtractionDialog
from app.ocr.models import OCRBlock, OCRLine, OCRParagraph, OCRStructuredResult, OCRWord
from app.ocr.provider import AutoOCRProvider, EasyOCRProvider, MockOCRProvider, OCRProvider, TesseractProvider, WindowsNativeOCRProvider
from app.ocr.worker import OCRWorker

__all__ = [
    "OCRWord",
    "OCRLine",
    "OCRParagraph",
    "OCRBlock",
    "OCRStructuredResult",
    "OCRProvider",
    "WindowsNativeOCRProvider",
    "TesseractProvider",
    "EasyOCRProvider",
    "MockOCRProvider",
    "AutoOCRProvider",
    "OCRWorker",
    "TextExtractionDialog",
]

