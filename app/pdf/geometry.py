"""Mathematical geometry, unit conversions, and aspect-ratio-preserving layout calculations."""

from typing import List, Tuple

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage

from app.pdf.models import FitMode, MarginConfig, PageOrientation, PaperSizePreset

# Standard conversion constants
POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4
POINTS_PER_MM = POINTS_PER_INCH / MM_PER_INCH  # ~2.83464567 points / mm


def mm_to_pt(mm: float) -> float:
    """Converts millimeters to PDF points."""
    return mm * POINTS_PER_MM


def pt_to_mm(pt: float) -> float:
    """Converts PDF points to millimeters."""
    return pt / POINTS_PER_MM


def inch_to_pt(inch: float) -> float:
    """Converts inches to PDF points."""
    return inch * POINTS_PER_INCH


def get_paper_dimensions_mm(
    preset: PaperSizePreset,
    custom_w_mm: float = 210.0,
    custom_h_mm: float = 297.0,
) -> Tuple[float, float]:
    """Returns standard paper dimensions (width_mm, height_mm)."""
    if preset == PaperSizePreset.A4:
        return 210.0, 297.0
    elif preset == PaperSizePreset.A3:
        return 297.0, 420.0
    elif preset == PaperSizePreset.A5:
        return 148.0, 210.0
    elif preset == PaperSizePreset.LETTER:
        return 215.9, 279.4
    elif preset == PaperSizePreset.LEGAL:
        return 215.9, 355.6
    elif preset == PaperSizePreset.TABLOID:
        return 279.4, 431.8
    else:
        return max(10.0, custom_w_mm), max(10.0, custom_h_mm)


def resolve_page_dimensions_pt(
    preset: PaperSizePreset,
    orientation: PageOrientation,
    custom_w_mm: float = 210.0,
    custom_h_mm: float = 297.0,
    sample_image: QImage = None,
) -> Tuple[float, float]:
    """
    Returns exact page dimensions in PDF points (width_pt, height_pt) taking orientation into account.
    """
    w_mm, h_mm = get_paper_dimensions_mm(preset, custom_w_mm, custom_h_mm)
    w_pt, h_pt = mm_to_pt(w_mm), mm_to_pt(h_mm)

    is_landscape = False
    if orientation == PageOrientation.LANDSCAPE:
        is_landscape = True
    elif orientation == PageOrientation.PORTRAIT:
        is_landscape = False
    elif orientation == PageOrientation.AUTO:
        if sample_image and not sample_image.isNull():
            is_landscape = sample_image.width() > sample_image.height()
        else:
            is_landscape = False

    if is_landscape:
        return max(w_pt, h_pt), min(w_pt, h_pt)
    else:
        return min(w_pt, h_pt), max(w_pt, h_pt)


def calculate_image_target_rect(
    img_w: int,
    img_h: int,
    container_x: float,
    container_y: float,
    container_w: float,
    container_h: float,
    fit_mode: FitMode = FitMode.FIT,
    custom_scale_pct: float = 100.0,
    dpi: int = 300,
) -> QRectF:
    """
    Calculates drawing destination rectangle preserving aspect ratio without distortion.
    """
    if img_w <= 0 or img_h <= 0 or container_w <= 0 or container_h <= 0:
        return QRectF(container_x, container_y, max(1.0, container_w), max(1.0, container_h))

    img_aspect = img_w / float(img_h)
    box_aspect = container_w / float(container_h)

    if fit_mode == FitMode.FIT:
        # Fit entirely within container box
        if img_aspect > box_aspect:
            draw_w = container_w
            draw_h = container_w / img_aspect
        else:
            draw_h = container_h
            draw_w = container_h * img_aspect
        draw_x = container_x + (container_w - draw_w) / 2.0
        draw_y = container_y + (container_h - draw_h) / 2.0
        return QRectF(draw_x, draw_y, draw_w, draw_h)

    elif fit_mode == FitMode.FILL:
        # Fill container completely (may overflow container for cropping)
        if img_aspect > box_aspect:
            draw_h = container_h
            draw_w = container_h * img_aspect
        else:
            draw_w = container_w
            draw_h = container_w / img_aspect
        draw_x = container_x + (container_w - draw_w) / 2.0
        draw_y = container_y + (container_h - draw_h) / 2.0
        return QRectF(draw_x, draw_y, draw_w, draw_h)

    elif fit_mode == FitMode.ORIGINAL_SIZE:
        # 1:1 physical size based on DPI (72 points / DPI)
        scale_factor = POINTS_PER_INCH / float(max(72, dpi))
        draw_w = img_w * scale_factor
        draw_h = img_h * scale_factor
        draw_x = container_x + (container_w - draw_w) / 2.0
        draw_y = container_y + (container_h - draw_h) / 2.0
        return QRectF(draw_x, draw_y, draw_w, draw_h)

    elif fit_mode == FitMode.CUSTOM_SCALE:
        # Base Fit mode multiplied by custom scale percentage
        base_rect = calculate_image_target_rect(img_w, img_h, container_x, container_y, container_w, container_h, FitMode.FIT)
        scale = max(0.1, custom_scale_pct / 100.0)
        draw_w = base_rect.width() * scale
        draw_h = base_rect.height() * scale
        draw_x = container_x + (container_w - draw_w) / 2.0
        draw_y = container_y + (container_h - draw_h) / 2.0
        return QRectF(draw_x, draw_y, draw_w, draw_h)

    return QRectF(container_x, container_y, container_w, container_h)


def calculate_grid_slots(
    content_rect: QRectF,
    rows: int,
    cols: int,
    spacing_pt: float,
) -> List[QRectF]:
    """
    Divides content rectangle into a grid of slots (rows x cols) with uniform spacing.
    """
    rows = max(1, rows)
    cols = max(1, cols)
    total_w = content_rect.width()
    total_h = content_rect.height()

    available_w = total_w - (cols - 1) * spacing_pt
    available_h = total_h - (rows - 1) * spacing_pt

    slot_w = max(1.0, available_w / float(cols))
    slot_h = max(1.0, available_h / float(rows))

    slots = []
    for r in range(rows):
        for c in range(cols):
            x = content_rect.left() + c * (slot_w + spacing_pt)
            y = content_rect.top() + r * (slot_h + spacing_pt)
            slots.append(QRectF(x, y, slot_w, slot_h))

    return slots

