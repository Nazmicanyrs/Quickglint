"""Data models, enums, and configuration structures for Image Metadata Cleaner."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class MetadataCategory(str, Enum):
    """Categorical grouping of metadata fields."""
    EXIF = "EXIF"
    GPS = "GPS"
    XMP = "XMP"
    IPTC = "IPTC"
    PNG_CHUNKS = "PNG Text Chunks"
    TIFF = "TIFF Tags"
    ICC = "ICC Color Profile"
    FILE_SYSTEM = "File System Metadata"


class MetadataRiskLevel(str, Enum):
    """Risk severity assigned to a metadata field from a privacy perspective."""
    HIGH = "HIGH"        # GPS, device serial, exact timestamps, user names
    MEDIUM = "MEDIUM"    # Author, software, copyright, keywords, descriptions
    LOW = "LOW"          # Image dimensions, color profile, compression format


class CleaningPreset(str, Enum):
    """Pre-configured cleaning modes."""
    QUICK_CLEAN = "quick_clean"
    PRIVACY_CLEAN = "privacy_clean"
    MAXIMUM_PRIVACY = "maximum_privacy"
    PRESERVE_ICC = "preserve_icc"
    CUSTOM = "custom"


@dataclass
class MetadataField:
    """Individual metadata key-value item."""
    category: MetadataCategory
    tag_name: str
    human_name: str
    raw_value: Any
    display_value: str
    risk_level: MetadataRiskLevel = MetadataRiskLevel.LOW
    is_sensitive: bool = False
    is_masked: bool = False
    is_removable: bool = True
    is_selected_for_removal: bool = True


@dataclass
class MetadataScanReport:
    """Detailed summary of all metadata fields detected in an image."""
    image_path: Optional[str] = None
    format_name: str = "Unknown"
    image_size: tuple[int, int] = (0, 0)
    file_size_bytes: int = 0
    fields: List[MetadataField] = field(default_factory=list)
    has_gps: bool = False
    has_icc: bool = False
    has_orientation: bool = False
    orientation_value: int = 1
    scan_time_ms: float = 0.0

    @property
    def image_metadata_fields(self) -> List[MetadataField]:
        return [f for f in self.fields if f.category != MetadataCategory.FILE_SYSTEM]

    @property
    def file_system_fields(self) -> List[MetadataField]:
        return [f for f in self.fields if f.category == MetadataCategory.FILE_SYSTEM]

    @property
    def high_risk_count(self) -> int:
        return sum(1 for f in self.image_metadata_fields if f.risk_level == MetadataRiskLevel.HIGH)

    @property
    def medium_risk_count(self) -> int:
        return sum(1 for f in self.image_metadata_fields if f.risk_level == MetadataRiskLevel.MEDIUM)

    @property
    def low_risk_count(self) -> int:
        return sum(1 for f in self.image_metadata_fields if f.risk_level == MetadataRiskLevel.LOW)

    @property
    def total_image_fields_count(self) -> int:
        return len(self.image_metadata_fields)

    def get_fields_by_category(self, category: MetadataCategory) -> List[MetadataField]:
        return [f for f in self.fields if f.category == category]

    def get_category_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for f in self.image_metadata_fields:
            counts[f.category.value] = counts.get(f.category.value, 0) + 1
        return counts


@dataclass
class CleanConfig:
    """Configuration options for metadata cleaning operation."""
    preset: CleaningPreset = CleaningPreset.PRIVACY_CLEAN
    categories_to_remove: Set[MetadataCategory] = field(
        default_factory=lambda: {
            MetadataCategory.EXIF,
            MetadataCategory.GPS,
            MetadataCategory.XMP,
            MetadataCategory.IPTC,
            MetadataCategory.PNG_CHUNKS,
            MetadataCategory.TIFF,
        }
    )
    specific_tags_to_keep: Set[str] = field(default_factory=set)
    preserve_icc: bool = True
    auto_orient: bool = True
    anonymize_filename: bool = False
    replace_original: bool = False
    output_directory: Optional[Path] = None
    output_format: Optional[str] = None  # None = keep original
    jpeg_quality: int = 95


@dataclass
class CleanResult:
    """Outcome of a metadata cleaning operation."""
    success: bool
    input_path: Optional[Path] = None
    output_path: Optional[Path] = None
    output_bytes: Optional[bytes] = None
    before_report: Optional[MetadataScanReport] = None
    after_report: Optional[MetadataScanReport] = None
    removed_fields_count: int = 0
    preserved_fields_count: int = 0
    error_msg: str = ""
    elapsed_ms: float = 0.0

