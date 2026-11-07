"""High-precision PDF generation engine and background worker using QPdfWriter and QPainter."""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QMarginsF, QObject, QPointF, QRectF, QSizeF, Qt, QThread, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
    QPen,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter

from app.pdf.geometry import (
    MM_PER_INCH,
    POINTS_PER_INCH,
    calculate_grid_slots,
    calculate_image_target_rect,
    mm_to_pt,
    resolve_page_dimensions_pt,
)
from app.pdf.models import (
    FitMode,
    HeaderFooterConfig,
    LayoutMode,
    PageNumberPosition,
    PageOrientation,
    PaperSizePreset,
    PDFExportOptions,
    PDFSourceItem,
    QualityLevel,
)
from app.utils.logger import logger


def validate_pdf_file(file_path: Path | str) -> bool:
    """Validates basic PDF binary structure (%PDF header and %%EOF trailer)."""
    p = Path(file_path)
    if not p.exists() or p.stat().st_size < 32:
        return False
    try:
        with open(p, "rb") as f:
            header = f.read(10)
            if b"%PDF-" not in header:
                return False
            f.seek(max(0, p.stat().st_size - 1024))
            tail = f.read()
            if b"%%EOF" not in tail:
                return False
        return True
    except Exception:
        return False


def apply_pdf_security(pdf_path: Path | str, user_password: str, owner_password: str = "", allow_printing: bool = True) -> bool:
    """Applies AES encryption / password protection to the generated PDF if pypdf or PyPDF2 is available."""
    if not user_password and not owner_password:
        return True
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        writer = pypdf.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(
            user_password=user_password,
            owner_pwd=owner_password or user_password,
            permissions_flag=pypdf.constants.UserAccessPermissions.PRINT if allow_printing else 0,
        )
        with open(pdf_path, "wb") as f:
            writer.write(f)
        logger.info("Encrypted PDF document with user password at %s", pdf_path)
        return True
    except ImportError:
        logger.warning("pypdf not installed; skipping PDF encryption. Install pypdf for password protection.")
        return False
    except Exception as exc:
        logger.error("Failed to apply PDF password encryption: %s", exc)
        return False


class PDFGenerator:
    """Renders screenshots, layouts, and complete PDFDocument projects into high-precision PDFs."""

    def __init__(self, options: Optional[PDFExportOptions] = None) -> None:
        self.options = options or PDFExportOptions()

    def get_layout_slots_count(self) -> int:
        """Returns the number of images per page based on layout mode."""
        mode = self.options.layout_mode
        if mode == LayoutMode.SINGLE:
            return 1
        elif mode == LayoutMode.GRID_2V or mode == LayoutMode.GRID_2H:
            return 2
        elif mode == LayoutMode.GRID_4:
            return 4
        elif mode == LayoutMode.GRID_6:
            return 6
        elif mode == LayoutMode.GRID_9:
            return 9
        elif mode == LayoutMode.CONTACT_SHEET:
            return 20
        elif mode == LayoutMode.CUSTOM_GRID:
            return max(1, self.options.grid_rows * self.options.grid_cols)
        return 1

    def calculate_total_pages(self, items: List[PDFSourceItem]) -> int:
        """Calculates total number of PDF pages for the given item list."""
        if not items:
            return 0
        slots = self.get_layout_slots_count()
        return (len(items) + slots - 1) // slots

    def render_single_page_to_qimage(
        self,
        items: List[PDFSourceItem],
        page_num: int = 1,
        target_width_px: int = 540,
    ) -> QImage:
        """Renders a single page to a high-quality QImage for interactive dialog preview."""
        if not items:
            return QImage()

        w_pt, h_pt = resolve_page_dimensions_pt(
            preset=self.options.paper_size,
            orientation=self.options.orientation,
            custom_w_mm=self.options.custom_width_mm,
            custom_h_mm=self.options.custom_height_mm,
            sample_image=items[0].get_image() if items else None,
        )

        aspect = h_pt / max(1.0, w_pt)
        img_w = max(100, target_width_px)
        img_h = int(img_w * aspect)

        img = QImage(img_w, img_h, QImage.Format.Format_ARGB32_Premultiplied)
        if self.options.is_transparent_background:
            img.fill(Qt.GlobalColor.transparent)
        else:
            img.fill(self.options.background_color)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        scale = img_w / max(1.0, w_pt)
        painter.scale(scale, scale)

        top_pt = mm_to_pt(self.options.margins.top_mm)
        bottom_pt = mm_to_pt(self.options.margins.bottom_mm)
        left_pt = mm_to_pt(self.options.margins.left_mm)
        right_pt = mm_to_pt(self.options.margins.right_mm)
        spacing_pt = mm_to_pt(self.options.grid_spacing_mm)

        if self.options.header_footer.header_text.strip():
            self._draw_header(painter, w_pt, top_pt)

        content_rect = QRectF(
            left_pt,
            top_pt,
            max(10.0, w_pt - left_pt - right_pt),
            max(10.0, h_pt - top_pt - bottom_pt),
        )

        slots_per_page = self.get_layout_slots_count()
        total_pages = self.calculate_total_pages(items)
        page_idx = max(0, min(page_num - 1, total_pages - 1))

        start_idx = page_idx * slots_per_page
        end_idx = min(len(items), start_idx + slots_per_page)
        page_items = items[start_idx:end_idx]

        mode = self.options.layout_mode
        if mode == LayoutMode.SINGLE:
            g_rows, g_cols = 1, 1
        elif mode == LayoutMode.GRID_2V:
            g_rows, g_cols = 2, 1
        elif mode == LayoutMode.GRID_2H:
            g_rows, g_cols = 1, 2
        elif mode == LayoutMode.GRID_4:
            g_rows, g_cols = 2, 2
        elif mode == LayoutMode.GRID_6:
            g_rows, g_cols = 3, 2
        elif mode == LayoutMode.GRID_9:
            g_rows, g_cols = 3, 3
        elif mode == LayoutMode.CONTACT_SHEET:
            g_rows, g_cols = 5, 4
        elif mode == LayoutMode.CUSTOM_GRID:
            g_rows, g_cols = self.options.grid_rows, self.options.grid_cols
        else:
            g_rows, g_cols = 1, 1

        slot_rects = calculate_grid_slots(
            content_rect=content_rect,
            rows=g_rows,
            cols=g_cols,
            spacing_pt=spacing_pt,
        )

        for item, s_rect in zip(page_items, slot_rects):
            self._draw_item_in_slot(painter, item, s_rect)

        self._draw_footer_and_page_number(
            painter=painter,
            page_num=page_idx + 1,
            total_pages=total_pages,
            page_w_pt=w_pt,
            page_h_pt=h_pt,
            bottom_pt=bottom_pt,
        )

        painter.end()
        return img

    def render_to_pdf_file(
        self,
        items: List[PDFSourceItem],
        output_path: Path | str,
        on_progress: Optional[Callable[[int, int], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """
        Renders the legacy PDF document atomically to destination.
        Writes to .tmp file, validates output, and performs atomic rename.
        """
        if not items:
            raise ValueError("No images provided for PDF export.")

        final_dest = Path(output_path).resolve()
        final_dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = final_dest.with_suffix(final_dest.suffix + ".tmp")

        try:
            writer = QPdfWriter(str(tmp_dest))
            writer.setResolution(self.options.dpi)
            writer.setTitle(self.options.metadata.title)
            writer.setCreator(self.options.metadata.creator)

            w_pt, h_pt = resolve_page_dimensions_pt(
                preset=self.options.paper_size,
                orientation=self.options.orientation,
                custom_w_mm=self.options.custom_width_mm,
                custom_h_mm=self.options.custom_height_mm,
                sample_image=items[0].get_image() if items else None,
            )

            page_size = QPageSize(QSizeF(w_pt, h_pt), QPageSize.Unit.Point)
            page_layout = QPageLayout(
                page_size,
                QPageLayout.Orientation.Portrait,
                QMarginsF(0, 0, 0, 0),
            )
            writer.setPageLayout(page_layout)

            painter = QPainter(writer)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

            slots_per_page = self.get_layout_slots_count()
            total_pages = self.calculate_total_pages(items)

            top_pt = mm_to_pt(self.options.margins.top_mm)
            bottom_pt = mm_to_pt(self.options.margins.bottom_mm)
            left_pt = mm_to_pt(self.options.margins.left_mm)
            right_pt = mm_to_pt(self.options.margins.right_mm)
            spacing_pt = mm_to_pt(self.options.grid_spacing_mm)

            for page_idx in range(total_pages):
                if is_cancelled and is_cancelled():
                    painter.end()
                    if tmp_dest.exists():
                        tmp_dest.unlink()
                    return False

                if page_idx > 0:
                    writer.newPage()

                # Background
                if not self.options.is_transparent_background:
                    painter.fillRect(QRectF(0, 0, w_pt, h_pt), self.options.background_color)

                # Header
                if self.options.header_footer.header_text.strip():
                    self._draw_header(painter, w_pt, top_pt)

                # Content Area
                content_rect = QRectF(
                    left_pt,
                    top_pt,
                    max(10.0, w_pt - left_pt - right_pt),
                    max(10.0, h_pt - top_pt - bottom_pt),
                )

                start_idx = page_idx * slots_per_page
                end_idx = min(len(items), start_idx + slots_per_page)
                page_items = items[start_idx:end_idx]

                mode = self.options.layout_mode
                if mode == LayoutMode.SINGLE:
                    g_rows, g_cols = 1, 1
                elif mode == LayoutMode.GRID_2V:
                    g_rows, g_cols = 2, 1
                elif mode == LayoutMode.GRID_2H:
                    g_rows, g_cols = 1, 2
                elif mode == LayoutMode.GRID_4:
                    g_rows, g_cols = 2, 2
                elif mode == LayoutMode.GRID_6:
                    g_rows, g_cols = 3, 2
                elif mode == LayoutMode.GRID_9:
                    g_rows, g_cols = 3, 3
                elif mode == LayoutMode.CONTACT_SHEET:
                    g_rows, g_cols = 5, 4
                elif mode == LayoutMode.CUSTOM_GRID:
                    g_rows, g_cols = self.options.grid_rows, self.options.grid_cols
                else:
                    g_rows, g_cols = 1, 1

                slot_rects = calculate_grid_slots(
                    content_rect=content_rect,
                    rows=g_rows,
                    cols=g_cols,
                    spacing_pt=spacing_pt,
                )

                for item, s_rect in zip(page_items, slot_rects):
                    self._draw_item_in_slot(painter, item, s_rect)

                # Footer and Page Number
                self._draw_footer_and_page_number(
                    painter=painter,
                    page_num=page_idx + 1,
                    total_pages=total_pages,
                    page_w_pt=w_pt,
                    page_h_pt=h_pt,
                    bottom_pt=bottom_pt,
                )

                if on_progress:
                    on_progress(page_idx + 1, total_pages)

            painter.end()

            if not validate_pdf_file(tmp_dest):
                raise IOError(f"Corrupted or invalid PDF output generated at {tmp_dest}")

            if final_dest.exists():
                final_dest.unlink()
            tmp_dest.rename(final_dest)

            logger.info("Successfully exported PDF to %s (%d pages)", final_dest, total_pages)
            return True

        except Exception as exc:
            if tmp_dest.exists():
                try:
                    tmp_dest.unlink()
                except Exception:
                    pass
            logger.error("PDF generation failed: %s", exc)
            raise exc

    def render_document_to_pdf(
        self,
        doc: Any,  # PDFDocument
        output_path: Path | str,
        on_progress: Optional[Callable[[int, int], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """
        Renders a full PDFDocument with vector objects, layers, non-destructive image crops,
        rich text, shapes, signatures, and optional security.
        """
        from app.pdf.render_engine import PDFRenderEngine

        pages = doc.pages
        if not pages:
            raise ValueError("Document has no pages to export.")

        final_dest = Path(output_path).resolve()
        final_dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = final_dest.with_suffix(final_dest.suffix + ".tmp")

        try:
            writer = QPdfWriter(str(tmp_dest))
            writer.setResolution(doc.settings.dpi)
            writer.setTitle(doc.settings.title)
            writer.setCreator(doc.settings.creator)

            total_pages = len(pages)
            painter = None

            for page_idx, page in enumerate(pages):
                if is_cancelled and is_cancelled():
                    if painter:
                        painter.end()
                    if tmp_dest.exists():
                        tmp_dest.unlink()
                    return False

                w_pt, h_pt = page.get_dimensions_pt()
                page_size = QPageSize(QSizeF(w_pt, h_pt), QPageSize.Unit.Point)
                page_layout = QPageLayout(
                    page_size,
                    QPageLayout.Orientation.Portrait,
                    QMarginsF(0, 0, 0, 0),
                )
                writer.setPageLayout(page_layout)

                if painter is None:
                    painter = QPainter(writer)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                else:
                    writer.newPage()

                # Render page content
                PDFRenderEngine.render_page(
                    painter=painter,
                    page=page,
                    doc_settings=doc.settings,
                    page_index=page_idx + 1,
                    total_pages=total_pages,
                    render_guides=False,
                )

                if on_progress:
                    on_progress(page_idx + 1, total_pages)

            if painter:
                painter.end()

            if not validate_pdf_file(tmp_dest):
                raise IOError(f"Corrupted PDF output generated at {tmp_dest}")

            # Apply security if enabled
            if doc.settings.security.enabled and doc.settings.security.user_password:
                apply_pdf_security(
                    pdf_path=tmp_dest,
                    user_password=doc.settings.security.user_password,
                    owner_password=doc.settings.security.owner_password,
                    allow_printing=doc.settings.security.allow_printing,
                )

            if final_dest.exists():
                final_dest.unlink()
            tmp_dest.rename(final_dest)

            logger.info("Successfully exported PDFDocument to %s (%d pages)", final_dest, total_pages)
            return True

        except Exception as exc:
            if tmp_dest.exists():
                try:
                    tmp_dest.unlink()
                except Exception:
                    pass
            logger.error("PDF document export failed: %s", exc)
            raise exc

    def _draw_item_in_slot(self, painter: QPainter, item: PDFSourceItem, slot_rect: QRectF) -> None:
        qimg = item.get_image()
        if not qimg or qimg.isNull():
            return

        label_height = 14.0 if (self.options.layout_mode == LayoutMode.CONTACT_SHEET and self.options.show_contact_sheet_labels) else 0.0
        img_slot_rect = QRectF(
            slot_rect.left(),
            slot_rect.top(),
            slot_rect.width(),
            max(5.0, slot_rect.height() - label_height),
        )

        target_rect = calculate_image_target_rect(
            img_w=qimg.width(),
            img_h=qimg.height(),
            container_x=img_slot_rect.left(),
            container_y=img_slot_rect.top(),
            container_w=img_slot_rect.width(),
            container_h=img_slot_rect.height(),
            fit_mode=self.options.fit_mode,
            custom_scale_pct=self.options.custom_scale_pct,
            dpi=self.options.dpi,
        )

        painter.drawImage(target_rect, qimg)

        if label_height > 0:
            painter.setFont(QFont("Segoe UI", 7))
            painter.setPen(QPen(QColor(80, 80, 80)))
            text_rect = QRectF(slot_rect.left(), slot_rect.bottom() - label_height, slot_rect.width(), label_height)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, item.title)

        item.release_cache()

    def _draw_header(self, painter: QPainter, page_w_pt: float, top_pt: float) -> None:
        cfg = self.options.header_footer
        painter.setFont(QFont(cfg.font_family, cfg.font_size_pt, QFont.Weight.Bold if cfg.is_bold else QFont.Weight.Normal))
        painter.setPen(QPen(QColor(60, 60, 60)))

        rect = QRectF(20, top_pt - 18, page_w_pt - 40, 16)
        align = Qt.AlignmentFlag.AlignCenter
        if cfg.header_alignment == "Left":
            align = Qt.AlignmentFlag.AlignLeft
        elif cfg.header_alignment == "Right":
            align = Qt.AlignmentFlag.AlignRight
        painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, cfg.header_text)

    def _draw_footer_and_page_number(
        self,
        painter: QPainter,
        page_num: int,
        total_pages: int,
        page_w_pt: float,
        page_h_pt: float,
        bottom_pt: float,
    ) -> None:
        cfg = self.options.header_footer
        painter.setFont(QFont(cfg.font_family, cfg.font_size_pt, QFont.Weight.Bold if cfg.is_bold else QFont.Weight.Normal))
        painter.setPen(QPen(QColor(100, 100, 100)))

        if cfg.footer_text.strip():
            rect = QRectF(20, page_h_pt - bottom_pt + 4, page_w_pt - 40, 16)
            align = Qt.AlignmentFlag.AlignCenter
            if cfg.footer_alignment == "Left":
                align = Qt.AlignmentFlag.AlignLeft
            elif cfg.footer_alignment == "Right":
                align = Qt.AlignmentFlag.AlignRight
            painter.drawText(rect, align | Qt.AlignmentFlag.AlignVCenter, cfg.footer_text)

        pos = self.options.page_number_position
        if pos != PageNumberPosition.NONE:
            num_str = self.options.page_number_format.format(page=page_num, total=total_pages)
            num_rect = QRectF(20, page_h_pt - bottom_pt + 4, page_w_pt - 40, 16)
            flags = Qt.AlignmentFlag.AlignRight
            if pos in (PageNumberPosition.BOTTOM_LEFT, PageNumberPosition.TOP_LEFT):
                flags = Qt.AlignmentFlag.AlignLeft
            elif pos in (PageNumberPosition.BOTTOM_CENTER, PageNumberPosition.TOP_CENTER):
                flags = Qt.AlignmentFlag.AlignCenter

            if pos in (PageNumberPosition.TOP_LEFT, PageNumberPosition.TOP_CENTER, PageNumberPosition.TOP_RIGHT):
                num_rect = QRectF(20, 10, page_w_pt - 40, 16)

            painter.drawText(num_rect, flags | Qt.AlignmentFlag.AlignVCenter, num_str)


class PDFExportWorker(QThread):
    """Background worker thread for asynchronous non-blocking PDF export."""

    progress = Signal(int, int)  # (current_page, total_pages)
    finished_success = Signal(str)  # output_path
    failed = Signal(str)  # error_message

    def __init__(
        self,
        items: Optional[List[PDFSourceItem]] = None,
        output_path: Path | str = "",
        options: Optional[PDFExportOptions] = None,
        document: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.items = items or []
        self.output_path = output_path
        self.options = options or PDFExportOptions()
        self.document = document
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        generator = PDFGenerator(self.options)
        try:
            if self.document:
                success = generator.render_document_to_pdf(
                    doc=self.document,
                    output_path=self.output_path,
                    on_progress=lambda cur, tot: self.progress.emit(cur, tot),
                    is_cancelled=lambda: self._is_cancelled,
                )
            else:
                success = generator.render_to_pdf_file(
                    items=self.items,
                    output_path=self.output_path,
                    on_progress=lambda cur, tot: self.progress.emit(cur, tot),
                    is_cancelled=lambda: self._is_cancelled,
                )
            if success:
                self.finished_success.emit(str(self.output_path))
        except Exception as exc:
            self.failed.emit(str(exc))

