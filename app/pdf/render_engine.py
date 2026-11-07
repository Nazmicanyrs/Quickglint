"""High-precision rendering engine for PDFDocument and PDFPage onto QPainter (Canvas, Preview, and QPdfWriter)."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
    QStaticText,
    QTextDocument,
    QTransform,
)

from app.pdf.document import (
    BackgroundType,
    ObjectType,
    PageBackground,
    PageNumberConfig,
    PDFAnnotationObject,
    PDFCommentObject,
    PDFDocument,
    PDFImageObject,
    PDFLinkObject,
    PDFObject,
    PDFPage,
    PDFShapeObject,
    PDFSignatureObject,
    PDFTextObject,
    ShapeType,
    SignatureType,
)
from app.pdf.geometry import mm_to_pt
from app.pdf.models import HeaderFooterConfig, PageNumberPosition


class PDFRenderEngine:
    """Universal renderer for painting PDF pages onto screen viewports, image buffers, and vector PDF outputs."""

    @staticmethod
    def render_page(
        painter: QPainter,
        page: PDFPage,
        doc_settings: Optional[Any] = None,
        page_index: int = 1,
        total_pages: int = 1,
        render_guides: bool = False,
        render_links_hotspots: bool = False,
        dpi_scale: float = 1.0,
    ) -> None:
        """Renders the entire background, objects, header/footer, and page numbers of a page."""
        w_pt, h_pt = page.get_dimensions_pt()
        page_rect = QRectF(0, 0, w_pt, h_pt)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # 1. Render Page Background
        PDFRenderEngine._render_background(painter, page.background, page_rect)

        # 2. Render Objects in Z-Index Order
        sorted_objects = sorted(page.objects, key=lambda x: x.z_index)
        for obj in sorted_objects:
            if not getattr(obj, "is_ocr_layer", False):
                PDFRenderEngine.render_object(painter, obj, render_links_hotspots=render_links_hotspots)

        # 3. Render Header and Footer (if doc_settings provided)
        if doc_settings and hasattr(doc_settings, "header_footer"):
            PDFRenderEngine._render_header_footer(
                painter,
                page,
                doc_settings.header_footer,
                page_index=page_index,
                total_pages=total_pages,
                doc_title=getattr(doc_settings, "title", "Quickglint"),
            )

        # 4. Render Page Numbers (if doc_settings provided)
        if doc_settings and hasattr(doc_settings, "page_numbers"):
            PDFRenderEngine._render_page_numbers(
                painter,
                page,
                doc_settings.page_numbers,
                page_index=page_index,
                total_pages=total_pages,
            )

        # 5. Render Optional Editor Margins & Guides
        if render_guides:
            PDFRenderEngine._render_margin_guides(painter, page)

        painter.restore()

    @staticmethod
    def _render_background(painter: QPainter, bg: PageBackground, rect: QRectF) -> None:
        if bg.bg_type == BackgroundType.TRANSPARENT:
            return

        painter.save()
        painter.setOpacity(bg.opacity)

        if bg.bg_type == BackgroundType.WHITE:
            painter.fillRect(rect, QColor("#FFFFFF"))
        elif bg.bg_type == BackgroundType.COLOR:
            painter.fillRect(rect, QColor(bg.color_hex))
        elif bg.bg_type == BackgroundType.GRADIENT_LINEAR:
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor(bg.gradient_start_hex))
            grad.setColorAt(1.0, QColor(bg.gradient_end_hex))
            painter.fillRect(rect, grad)
        elif bg.bg_type == BackgroundType.GRADIENT_RADIAL:
            center = rect.center()
            rad = max(rect.width(), rect.height()) / 2.0
            grad = QRadialGradient(center, rad)
            grad.setColorAt(0.0, QColor(bg.gradient_start_hex))
            grad.setColorAt(1.0, QColor(bg.gradient_end_hex))
            painter.fillRect(rect, grad)
        elif bg.bg_type == BackgroundType.IMAGE and bg.image_base64:
            from app.pdf.document import base64_to_qimage
            bg_img = base64_to_qimage(bg.image_base64)
            if not bg_img.isNull():
                painter.drawImage(rect, bg_img)
        else:
            painter.fillRect(rect, QColor("#FFFFFF"))

        painter.restore()

    @staticmethod
    def render_object(painter: QPainter, obj: PDFObject, render_links_hotspots: bool = False) -> None:
        """Renders an individual PDFObject with its transformations and opacity."""
        painter.save()

        # Apply object opacity
        painter.setOpacity(painter.opacity() * obj.opacity)

        # Apply rotation around center of object
        center = QPointF(obj.x + obj.width / 2.0, obj.y + obj.height / 2.0)
        if abs(obj.rotation) > 1e-4:
            transform = QTransform()
            transform.translate(center.x(), center.y())
            transform.rotate(obj.rotation)
            transform.translate(-center.x(), -center.y())
            painter.setTransform(transform, True)

        obj_rect = QRectF(obj.x, obj.y, obj.width, obj.height)

        if isinstance(obj, PDFImageObject):
            PDFRenderEngine._render_image_object(painter, obj, obj_rect)
        elif isinstance(obj, PDFTextObject):
            PDFRenderEngine._render_text_object(painter, obj, obj_rect)
        elif isinstance(obj, PDFShapeObject):
            PDFRenderEngine._render_shape_object(painter, obj, obj_rect)
        elif isinstance(obj, PDFSignatureObject):
            PDFRenderEngine._render_signature_object(painter, obj, obj_rect)
        elif isinstance(obj, PDFAnnotationObject):
            PDFRenderEngine._render_annotation_object(painter, obj, obj_rect)
        elif isinstance(obj, PDFLinkObject):
            if render_links_hotspots:
                PDFRenderEngine._render_link_hotspot(painter, obj, obj_rect)
        elif isinstance(obj, PDFCommentObject):
            PDFRenderEngine._render_comment_object(painter, obj, obj_rect)

        painter.restore()

    @staticmethod
    def _render_image_object(painter: QPainter, obj: PDFImageObject, rect: QRectF) -> None:
        cropped = obj.get_cropped_image()
        if cropped and not cropped.isNull():
            painter.drawImage(rect, cropped)
        else:
            # Placeholder placeholder
            painter.setPen(QPen(QColor("#94A3B8"), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor("#F1F5F9")))
            painter.drawRect(rect)
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"🖼️ {obj.title}")

    @staticmethod
    def _render_text_object(painter: QPainter, obj: PDFTextObject, rect: QRectF) -> None:
        if obj.highlight_color:
            painter.fillRect(rect, QColor(obj.highlight_color))

        if obj.html:
            doc = QTextDocument()
            doc.setHtml(obj.html)
            doc.setTextWidth(rect.width())
            painter.save()
            painter.translate(rect.topLeft())
            doc.drawContents(painter, QRectF(0, 0, rect.width(), rect.height()))
            painter.restore()
        else:
            font = QFont(obj.font_family, int(obj.font_size_pt))
            font.setBold(obj.is_bold)
            font.setItalic(obj.is_italic)
            font.setUnderline(obj.is_underline)
            font.setStrikeOut(obj.is_strike)
            if abs(obj.letter_spacing) > 1e-3:
                font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, obj.letter_spacing)

            painter.setFont(font)
            painter.setPen(QColor(obj.font_color))

            align = Qt.AlignmentFlag.AlignLeft
            if obj.alignment.lower() == "center":
                align = Qt.AlignmentFlag.AlignHCenter
            elif obj.alignment.lower() == "right":
                align = Qt.AlignmentFlag.AlignRight
            elif obj.alignment.lower() == "justify":
                align = Qt.AlignmentFlag.AlignJustify

            align |= Qt.AlignmentFlag.AlignTop
            painter.drawText(rect, int(align) | int(Qt.TextFlag.TextWordWrap), obj.text)

    @staticmethod
    def _render_shape_object(painter: QPainter, obj: PDFShapeObject, rect: QRectF) -> None:
        pen = QPen(QColor(obj.border_color), obj.border_width_pt)
        brush = QBrush(QColor(obj.fill_color)) if obj.fill_color else Qt.BrushStyle.NoBrush
        painter.setPen(pen)
        painter.setBrush(brush)

        st = obj.shape_type
        if st == ShapeType.RECTANGLE:
            painter.drawRect(rect)
        elif st == ShapeType.ROUNDED_RECT:
            painter.drawRoundedRect(rect, obj.corner_radius_pt, obj.corner_radius_pt)
        elif st == ShapeType.CIRCLE or st == ShapeType.ELLIPSE:
            painter.drawEllipse(rect)
        elif st == ShapeType.LINE:
            painter.drawLine(rect.topLeft(), rect.bottomRight())
        elif st == ShapeType.ARROW:
            # Draw line with arrow head
            p1 = rect.topLeft()
            p2 = rect.bottomRight()
            painter.drawLine(p1, p2)
            # Arrow head
            import math
            angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            head_len = min(16.0, rect.width() / 3.0)
            a1 = angle + math.pi * 0.85
            a2 = angle - math.pi * 0.85
            head_p1 = QPointF(p2.x() + head_len * math.cos(a1), p2.y() + head_len * math.sin(a1))
            head_p2 = QPointF(p2.x() + head_len * math.cos(a2), p2.y() + head_len * math.sin(a2))
            path = QPainterPath()
            path.moveTo(p2)
            path.lineTo(head_p1)
            path.lineTo(head_p2)
            path.closeSubpath()
            painter.fillPath(path, QBrush(QColor(obj.border_color)))
        elif st == ShapeType.POLYGON and obj.points:
            path = QPainterPath()
            first = True
            for px, py in obj.points:
                pt = QPointF(rect.x() + px * rect.width(), rect.y() + py * rect.height())
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.drawRect(rect)

    @staticmethod
    def _render_signature_object(painter: QPainter, obj: PDFSignatureObject, rect: QRectF) -> None:
        if obj.sig_type == SignatureType.DRAWN and obj.points:
            pen = QPen(QColor(obj.ink_color), obj.stroke_width_pt, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for stroke in obj.points:
                if len(stroke) < 2:
                    continue
                path = QPainterPath()
                first = True
                for px, py in stroke:
                    pt = QPointF(rect.x() + px * rect.width(), rect.y() + py * rect.height())
                    if first:
                        path.moveTo(pt)
                        first = False
                    else:
                        path.lineTo(pt)
                painter.drawPath(path)
        elif obj.sig_type == SignatureType.TYPED and obj.typed_text:
            font = QFont(obj.typed_font, 22)
            font.setItalic(True)
            painter.setFont(font)
            painter.setPen(QColor(obj.ink_color))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, obj.typed_text)
        elif obj.sig_type == SignatureType.IMAGE and obj.image:
            painter.drawImage(rect, obj.image)
        else:
            painter.setPen(QColor("#0F172A"))
            painter.setFont(QFont("Segoe Script", 16))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Signature")

    @staticmethod
    def _render_annotation_object(painter: QPainter, obj: PDFAnnotationObject, rect: QRectF) -> None:
        if obj.tool == "pen" and obj.points:
            pen = QPen(QColor(obj.color), obj.stroke_width_pt, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            first = True
            for px, py in obj.points:
                pt = QPointF(rect.x() + px * rect.width(), rect.y() + py * rect.height())
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
            painter.drawPath(path)
        elif obj.tool == "highlighter" and obj.points:
            hl_color = QColor(obj.color)
            hl_color.setAlpha(90)
            pen = QPen(hl_color, obj.stroke_width_pt * 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.BevelJoin)
            painter.setPen(pen)
            path = QPainterPath()
            first = True
            for px, py in obj.points:
                pt = QPointF(rect.x() + px * rect.width(), rect.y() + py * rect.height())
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
            painter.drawPath(path)
        elif obj.tool in ["blur", "pixelate"]:
            # Semi-transparent indicator box on canvas
            painter.fillRect(rect, QColor(0, 136, 255, 60))
            painter.setPen(QPen(QColor(0, 136, 255), 1, Qt.PenStyle.DashLine))
            painter.drawRect(rect)

    @staticmethod
    def _render_link_hotspot(painter: QPainter, obj: PDFLinkObject, rect: QRectF) -> None:
        painter.fillRect(rect, QColor(37, 99, 235, 40))
        painter.setPen(QPen(QColor(37, 99, 235), 1, Qt.PenStyle.DashLine))
        painter.drawRect(rect)
        painter.setPen(QColor("#2563EB"))
        painter.setFont(QFont("Segoe UI", 8))
        target = obj.hyperlink_url or (f"Page {obj.internal_link_page}" if obj.internal_link_page else "Link")
        painter.drawText(rect.adjusted(2, 2, -2, -2), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, f"🔗 {target}")

    @staticmethod
    def _render_comment_object(painter: QPainter, obj: PDFCommentObject, rect: QRectF) -> None:
        painter.setBrush(QBrush(QColor(obj.color_hex)))
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor("#000000"))
        painter.setFont(QFont("Segoe UI", 12))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "💬")

    @staticmethod
    def _render_header_footer(
        painter: QPainter,
        page: PDFPage,
        cfg: HeaderFooterConfig,
        page_index: int,
        total_pages: int,
        doc_title: str,
    ) -> None:
        if not cfg.header_text and not cfg.footer_text:
            return

        w_pt, h_pt = page.get_dimensions_pt()
        font = QFont(cfg.font_family, cfg.font_size_pt)
        font.setBold(cfg.is_bold)
        painter.setFont(font)
        painter.setPen(QColor("#64748B"))

        now = datetime.datetime.now()
        subs = {
            "{page}": str(page_index),
            "{pages}": str(total_pages),
            "{date}": now.strftime("%Y-%m-%d"),
            "{time}": now.strftime("%H:%M"),
            "{title}": doc_title,
            "{filename}": doc_title,
        }

        # Header
        if cfg.header_text:
            t = cfg.header_text
            for k, v in subs.items():
                t = t.replace(k, v)
            h_rect = QRectF(mm_to_pt(page.margins.left_mm), 8, w_pt - mm_to_pt(page.margins.left_mm + page.margins.right_mm), 18)
            align = Qt.AlignmentFlag.AlignHCenter
            if cfg.header_alignment.lower() == "left":
                align = Qt.AlignmentFlag.AlignLeft
            elif cfg.header_alignment.lower() == "right":
                align = Qt.AlignmentFlag.AlignRight
            painter.drawText(h_rect, int(align) | int(Qt.AlignmentFlag.AlignVCenter), t)

        # Footer
        if cfg.footer_text:
            t = cfg.footer_text
            for k, v in subs.items():
                t = t.replace(k, v)
            f_rect = QRectF(mm_to_pt(page.margins.left_mm), h_pt - 22, w_pt - mm_to_pt(page.margins.left_mm + page.margins.right_mm), 18)
            align = Qt.AlignmentFlag.AlignHCenter
            if cfg.footer_alignment.lower() == "left":
                align = Qt.AlignmentFlag.AlignLeft
            elif cfg.footer_alignment.lower() == "right":
                align = Qt.AlignmentFlag.AlignRight
            painter.drawText(f_rect, int(align) | int(Qt.AlignmentFlag.AlignVCenter), t)

    @staticmethod
    def _render_page_numbers(
        painter: QPainter,
        page: PDFPage,
        cfg: PageNumberConfig,
        page_index: int,
        total_pages: int,
    ) -> None:
        if not cfg.enabled or cfg.position == PageNumberPosition.NONE:
            return

        w_pt, h_pt = page.get_dimensions_pt()
        cur_num = cfg.start_number + page_index - 1
        tot_num = cfg.start_number + total_pages - 1

        t = cfg.format_template.replace("{page}", str(cur_num)).replace("{pages}", str(tot_num))

        font = QFont(cfg.font_family, int(cfg.font_size_pt))
        painter.setFont(font)
        painter.setPen(QColor(cfg.color_hex))

        margin_l = mm_to_pt(page.margins.left_mm)
        margin_r = mm_to_pt(page.margins.right_mm)
        content_w = w_pt - margin_l - margin_r

        pos = cfg.position
        if pos == PageNumberPosition.BOTTOM_RIGHT:
            rect = QRectF(margin_l, h_pt - 24, content_w, 18)
            align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        elif pos == PageNumberPosition.BOTTOM_CENTER:
            rect = QRectF(margin_l, h_pt - 24, content_w, 18)
            align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        elif pos == PageNumberPosition.BOTTOM_LEFT:
            rect = QRectF(margin_l, h_pt - 24, content_w, 18)
            align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        elif pos == PageNumberPosition.TOP_RIGHT:
            rect = QRectF(margin_l, 8, content_w, 18)
            align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        elif pos == PageNumberPosition.TOP_CENTER:
            rect = QRectF(margin_l, 8, content_w, 18)
            align = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        elif pos == PageNumberPosition.TOP_LEFT:
            rect = QRectF(margin_l, 8, content_w, 18)
            align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        else:
            return

        painter.drawText(rect, int(align), t)

    @staticmethod
    def _render_margin_guides(painter: QPainter, page: PDFPage) -> None:
        p_rect = page.get_printable_rect_pt()
        painter.setPen(QPen(QColor(56, 189, 248, 120), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(p_rect)

    @staticmethod
    def render_page_to_image(page: PDFPage, doc_settings: Optional[Any] = None, max_dim: int = 300) -> QImage:
        """Renders page thumbnail / preview image offscreen with smooth scaling."""
        w_pt, h_pt = page.get_dimensions_pt()
        aspect = w_pt / max(1.0, h_pt)
        if aspect >= 1.0:
            out_w = max_dim
            out_h = max(10, int(max_dim / aspect))
        else:
            out_h = max_dim
            out_w = max(10, int(max_dim * aspect))

        img = QImage(out_w, out_h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)

        painter = QPainter(img)
        scale_x = out_w / w_pt
        scale_y = out_h / h_pt
        painter.scale(scale_x, scale_y)

        PDFRenderEngine.render_page(painter, page, doc_settings=doc_settings, render_guides=False)
        painter.end()
        return img

