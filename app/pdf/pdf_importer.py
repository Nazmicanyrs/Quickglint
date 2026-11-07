"""PDF Importer: loads existing PDF files and converts pages into editable PDFPage objects."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional
import tempfile

from PySide6.QtCore import QSizeF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPdf import QPdfDocument

from app.pdf.document import (
    BackgroundType,
    PageBackground,
    PDFDocument,
    PDFImageObject,
    PDFPage,
    PaperSizePreset,
    qimage_to_base64_png,
)
from app.pdf.models import PageOrientation
from app.utils.logger import logger


class PDFImporter:
    """Reads PDF files and generates editable PDFDocument and PDFPage instances."""

    @staticmethod
    def import_pdf(file_path: Path | str) -> Optional[PDFDocument]:
        """Loads a PDF file, rendering its pages as high-resolution editable canvas backdrops."""
        p = Path(file_path)
        if not p.exists():
            logger.error("PDF file to import does not exist: %s", p)
            return None

        try:
            pdf_doc = QPdfDocument()
            status = pdf_doc.load(str(p))
            if status != QPdfDocument.Error.None_:
                logger.error("Failed to load PDF with QPdfDocument: error code %s", status)
                # Fallback check
                return None

            page_count = pdf_doc.pageCount()
            if page_count <= 0:
                logger.warning("Imported PDF has 0 pages.")
                return None

            doc = PDFDocument(title=p.stem)
            doc.pages.clear()

            for i in range(page_count):
                page_size_pt = pdf_doc.pagePointSize(i)
                w_pt = page_size_pt.width()
                h_pt = page_size_pt.height()

                # Render page at high resolution (300 DPI scale ~ 4.16x)
                scale_factor = 3.0
                render_w = int(w_pt * scale_factor)
                render_h = int(h_pt * scale_factor)

                render_img = pdf_doc.render(i, QSizeF(render_w, render_h).toSize())
                
                is_landscape = w_pt > h_pt
                page = PDFPage(
                    paper_size=PaperSizePreset.CUSTOM,
                    orientation=PageOrientation.LANDSCAPE if is_landscape else PageOrientation.PORTRAIT,
                    custom_width_mm=w_pt * 25.4 / 72.0,
                    custom_height_mm=h_pt * 25.4 / 72.0,
                )
                
                # Add background image object
                img_obj = PDFImageObject(
                    image=render_img,
                    x_pt=0,
                    y_pt=0,
                    width_pt=w_pt,
                    height_pt=h_pt,
                    title=f"Imported Page {i + 1}",
                    locked=True,  # Default lock background so user can draw/annotate on top
                )
                page.add_object(img_obj)
                doc.pages.append(page)

            doc.is_modified = True
            logger.info("Successfully imported PDF %s with %d pages", p.name, len(doc.pages))
            return doc

        except Exception as exc:
            logger.error("Exception during PDF import of %s: %s", p, exc)
            return None

