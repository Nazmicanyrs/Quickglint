"""Data models, enums, and configuration options for Professional PDF Export."""

from dataclasses import dataclass, field
import enum
from pathlib import Path
from typing import Callable, List, Optional
import uuid

from PySide6.QtGui import QColor, QImage


class PaperSizePreset(enum.Enum):
    """Standard paper size presets."""

    A4 = "A4"          # 210 x 297 mm
    A3 = "A3"          # 297 x 420 mm
    A5 = "A5"          # 148 x 210 mm
    LETTER = "Letter"  # 8.5 x 11 inches (215.9 x 279.4 mm)
    LEGAL = "Legal"    # 8.5 x 14 inches (215.9 x 355.6 mm)
    TABLOID = "Tabloid"# 11 x 17 inches (279.4 x 431.8 mm)
    CUSTOM = "Custom"


class PageOrientation(enum.Enum):
    """Page orientation settings."""

    PORTRAIT = "Portrait"
    LANDSCAPE = "Landscape"
    AUTO = "Auto"


class FitMode(enum.Enum):
    """Image placement and scaling modes."""

    FIT = "Fit"                     # Aspect ratio preserved, entire image visible within margins
    FILL = "Fill"                   # Aspect ratio preserved, fills target box, cropped if necessary
    ORIGINAL_SIZE = "Original Size" # Pixel-1:1 relative to DPI setting
    CUSTOM_SCALE = "Custom Scale"   # Scaled by user-specified percentage (25%..200%)


class LayoutMode(enum.Enum):
    """Page layout and grid arrangements."""

    SINGLE = "Single (1 image / page)"
    GRID_2V = "2 Vertical"
    GRID_2H = "2 Horizontal"
    GRID_4 = "4 Grid (2x2)"
    GRID_6 = "6 Grid (3x2)"
    GRID_9 = "9 Grid (3x3)"
    CONTACT_SHEET = "Contact Sheet"
    CUSTOM_GRID = "Custom Grid"


class QualityLevel(enum.Enum):
    """PDF image compression and quality levels."""

    MAXIMUM = "Maximum (Lossless / PNG)"
    HIGH = "High (95% JPEG / Flate)"
    BALANCED = "Balanced (85% JPEG)"
    SMALL_FILE = "Small File (70% JPEG / Optimized)"


class PageNumberPosition(enum.Enum):
    """Placement position for page numbers."""

    NONE = "None"
    BOTTOM_LEFT = "Bottom Left"
    BOTTOM_CENTER = "Bottom Center"
    BOTTOM_RIGHT = "Bottom Right"
    TOP_LEFT = "Top Left"
    TOP_CENTER = "Top Center"
    TOP_RIGHT = "Top Right"


@dataclass
class MarginConfig:
    """Page margin definitions in millimeters."""

    top_mm: float = 10.0
    bottom_mm: float = 10.0
    left_mm: float = 10.0
    right_mm: float = 10.0
    linked: bool = True

    def set_all(self, val_mm: float) -> None:
        self.top_mm = val_mm
        self.bottom_mm = val_mm
        self.left_mm = val_mm
        self.right_mm = val_mm


@dataclass
class HeaderFooterConfig:
    """Header and footer text and styling options."""

    header_text: str = ""
    footer_text: str = ""
    font_family: str = "Segoe UI"
    font_size_pt: int = 9
    is_bold: bool = False
    header_alignment: str = "Center"  # Left, Center, Right
    footer_alignment: str = "Center"


@dataclass
class MetadataConfig:
    """PDF document metadata."""

    title: str = "Quickglint Export"
    author: str = ""
    subject: str = "Screenshots"
    keywords: str = "Quickglint, Screenshots, PDF"
    creator: str = "Quickglint"
    preserve_image_exif: bool = False


@dataclass
class PDFExportOptions:
    """Complete options bundle for PDF rendering and printing."""

    paper_size: PaperSizePreset = PaperSizePreset.A4
    custom_width_mm: float = 210.0
    custom_height_mm: float = 297.0
    orientation: PageOrientation = PageOrientation.AUTO
    margins: MarginConfig = field(default_factory=MarginConfig)

    fit_mode: FitMode = FitMode.FIT
    custom_scale_pct: float = 100.0  # Used when fit_mode is CUSTOM_SCALE

    layout_mode: LayoutMode = LayoutMode.SINGLE
    grid_rows: int = 2
    grid_cols: int = 2
    grid_spacing_mm: float = 5.0
    show_contact_sheet_labels: bool = True

    quality: QualityLevel = QualityLevel.HIGH
    jpeg_quality_pct: int = 90
    dpi: int = 300

    background_color: QColor = field(default_factory=lambda: QColor(255, 255, 255))
    is_transparent_background: bool = False

    page_number_position: PageNumberPosition = PageNumberPosition.BOTTOM_RIGHT
    page_number_format: str = "Page {page} of {total}"  # or "Page {page}"

    header_footer: HeaderFooterConfig = field(default_factory=HeaderFooterConfig)
    metadata: MetadataConfig = field(default_factory=MetadataConfig)


class PDFSourceItem:
    """Represents an individual screenshot or image item to be included in PDF export."""

    def __init__(
        self,
        title: str,
        file_path: Optional[Path | str] = None,
        qimage: Optional[QImage] = None,
        vault_decrypt_fn: Optional[Callable[[], QImage]] = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.title = title
        self.file_path = Path(file_path) if file_path else None
        self._cached_qimage = qimage
        self._vault_decrypt_fn = vault_decrypt_fn
        self._thumbnail: Optional[QImage] = None

    def get_image(self) -> Optional[QImage]:
        """Loads and returns the high-resolution source QImage in memory."""
        if self._cached_qimage and not self._cached_qimage.isNull():
            return self._cached_qimage

        if self._vault_decrypt_fn:
            img = self._vault_decrypt_fn()
            return img

        if self.file_path and self.file_path.exists():
            img = QImage(str(self.file_path))
            if not img.isNull():
                return img

        return None

    def get_thumbnail(self, max_size: int = 160) -> Optional[QImage]:
        """Returns or computes a fast low-resolution thumbnail for responsive UI lists."""
        if self._thumbnail and not self._thumbnail.isNull():
            return self._thumbnail

        full = self.get_image()
        if full and not full.isNull():
            from PySide6.QtCore import Qt
            self._thumbnail = full.scaled(
                max_size,
                max_size,
                aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
                mode=Qt.TransformationMode.SmoothTransformation,
            )
            return self._thumbnail
        return None

    def release_cache(self) -> None:
        """Frees volatile memory cache if backed by file or vault function."""
        if self.file_path or self._vault_decrypt_fn:
            self._cached_qimage = None

