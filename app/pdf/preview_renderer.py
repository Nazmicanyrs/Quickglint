"""High-speed preview renderer with caching for interactive PDF export dialog."""

from typing import Dict, List, Optional

from PySide6.QtGui import QImage, QPixmap

from app.pdf.models import PDFExportOptions, PDFSourceItem
from app.pdf.pdf_generator import PDFGenerator


class PDFPreviewRenderer:
    """Manages page previews for the interactive PDF export window."""

    def __init__(self, options: Optional[PDFExportOptions] = None) -> None:
        self.options = options or PDFExportOptions()
        self._generator = PDFGenerator(self.options)
        self._cache: Dict[int, QPixmap] = {}

    def update_options(self, options: PDFExportOptions) -> None:
        self.options = options
        self._generator = PDFGenerator(self.options)
        self.clear_cache()

    def clear_cache(self) -> None:
        self._cache.clear()

    def get_total_pages(self, items: List[PDFSourceItem]) -> int:
        return self._generator.calculate_total_pages(items)

    def render_page_pixmap(
        self,
        items: List[PDFSourceItem],
        page_num: int,
        preview_width_px: int = 540,
    ) -> QPixmap:
        """Renders and returns QPixmap for the requested page number."""
        if page_num in self._cache:
            return self._cache[page_num]

        qimg = self._generator.render_single_page_to_qimage(
            items=items,
            page_num=page_num,
            target_width_px=preview_width_px,
        )
        pix = QPixmap.fromImage(qimg)
        self._cache[page_num] = pix
        return pix

