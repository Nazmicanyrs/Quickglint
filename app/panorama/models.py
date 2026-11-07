"""Data models and configuration structures for Panorama Capture & Multi-Monitor Stitching."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage


class PanoramaCaptureMode(Enum):
    """Supported capture and stitching modes for Panorama Capture."""

    FULL_DESKTOP = "full_desktop"        # Capture all connected monitors using real desktop geometry
    SELECTED_MONITOR = "selected_monitor"  # Capture a single selected monitor
    CUSTOM_LAYOUT = "custom_layout"      # Combine user-selected monitors
    MANUAL_STITCHING = "manual_stitching"  # OpenCV feature-based stitching of ordered images


class FeatureDetectorType(Enum):
    """Feature extraction algorithms for OpenCV panorama stitching."""

    ORB = "orb"
    SIFT = "sift"
    AUTO = "auto"


class BlendingMode(Enum):
    """Seam blending algorithms."""

    MULTIBAND = "multiband"  # Laplacian pyramid multi-band blending
    FEATHER = "feather"      # Linear distance feather blending
    NONE = "none"            # Direct overlay


class AlignmentMode(Enum):
    """Geometric transformation model for image alignment."""

    HOMOGRAPHY = "homography"  # Full 8-DOF perspective correction
    AFFINE = "affine"          # 4/6-DOF translation + rotation + scale
    TRANSLATION = "translation"  # Pure 2D translation (ideal for screen captures)
    DESKTOP_COORDS = "desktop_coords"  # Physical monitor coordinates without feature matching


@dataclass
class MonitorInfo:
    """Physical and logical metadata for a connected display monitor."""

    index: int
    name: str
    manufacturer: str = ""
    model: str = ""
    logical_geometry: QRect = field(default_factory=QRect)
    physical_width: int = 0
    physical_height: int = 0
    dpi_x: float = 96.0
    dpi_y: float = 96.0
    scale_factor: float = 1.0
    is_primary: bool = False
    refresh_rate: float = 60.0

    @property
    def orientation(self) -> str:
        """Return 'horizontal' (landscape) or 'vertical' (portrait)."""
        w = self.physical_width or self.logical_geometry.width()
        h = self.physical_height or self.logical_geometry.height()
        return "horizontal" if w >= h else "vertical"

    @property
    def display_label(self) -> str:
        """Human-readable summary for UI lists."""
        primary_tag = " ★" if self.is_primary else ""
        scale_pct = int(round(self.scale_factor * 100))
        orient = "Yatay" if self.orientation == "horizontal" else "Dikey"
        return (
            f"Ekran {self.index + 1}: {self.name}{primary_tag} "
            f"({self.physical_width}×{self.physical_height} px, %{scale_pct} DPI, {orient})"
        )


@dataclass
class PanoramaFrame:
    """A single source image frame participating in panorama creation."""

    frame_id: str
    title: str
    image: QImage
    monitor_info: Optional[MonitorInfo] = None
    logical_rect: Optional[QRect] = None
    enabled: bool = True
    order_index: int = 0
    source_path: str = ""

    @property
    def width(self) -> int:
        return self.image.width() if not self.image.isNull() else 0

    @property
    def height(self) -> int:
        return self.image.height() if not self.image.isNull() else 0


@dataclass
class StitchConfig:
    """Configuration parameters for Panorama Stitching Engine."""

    mode: PanoramaCaptureMode = PanoramaCaptureMode.FULL_DESKTOP
    detector: FeatureDetectorType = FeatureDetectorType.ORB
    alignment: AlignmentMode = AlignmentMode.HOMOGRAPHY
    blending: BlendingMode = BlendingMode.MULTIBAND
    exposure_compensation: bool = True
    auto_crop: bool = True
    normalize_dpi: bool = True
    layout_arrangement: str = "physical"  # "physical" | "horizontal" | "vertical"
    match_confidence: float = 0.65
    ransac_reproj_threshold: float = 4.0
    multiband_levels: int = 4
    feather_sharpness: float = 0.02
    max_features: int = 2500
    background_color: str = "#0B0F17"


@dataclass
class PairMatchInfo:
    """Diagnostic details about feature matching between two adjacent frames."""

    frame_a_index: int
    frame_b_index: int
    keypoints_a: int = 0
    keypoints_b: int = 0
    good_matches: int = 0
    inliers: int = 0
    overlap_ratio: float = 0.0
    used_fallback: bool = False


@dataclass
class StitchResult:
    """Output of a panorama composition or OpenCV stitching operation."""

    success: bool
    image: Optional[QImage] = None
    mode_used: str = ""
    detector_used: str = ""
    frames_count: int = 0
    execution_time_ms: float = 0.0
    pair_matches: List[PairMatchInfo] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error_message: str = ""

    @property
    def width(self) -> int:
        return self.image.width() if self.image and not self.image.isNull() else 0

    @property
    def height(self) -> int:
        return self.image.height() if self.image and not self.image.isNull() else 0


