"""Data models, enums, and configuration options for Professional Image Optimizer."""

from dataclasses import dataclass, field
import enum
from typing import Optional, Tuple

from PIL import Image
from PySide6.QtGui import QImage


class OptimizationMode(enum.Enum):
    """Core optimization philosophies."""

    LOSSLESS = "Kayıpsız (Lossless)"
    BALANCED = "Dengeli (Balanced)"
    MAX_COMPRESSION = "Maksimum Sıkıştırma (Max Compression)"
    TARGET_SIZE = "Hedef Dosya Boyutu (Target Size)"
    CUSTOM = "Özel (Custom)"


class OutputFormat(enum.Enum):
    """Supported output image formats."""

    AUTO = "Otomatik (Auto Recommend)"
    PNG = "PNG"
    JPEG = "JPEG"
    WEBP = "WebP"


class ChromaSubsampling(enum.Enum):
    """JPEG color chroma subsampling options."""

    CS_444 = "4:4:4 (En Yüksek Kalite / Metin için)"
    CS_422 = "4:2:2 (Dengeli)"
    CS_420 = "4:2:0 (Maksimum Sıkıştırma)"


class ResizePreset(enum.Enum):
    """Resolution and long-edge scaling presets."""

    ORIGINAL = "Orijinal Boyut"
    LONG_EDGE_3840 = "Uzun Kenar: 3840 px (4K)"
    LONG_EDGE_2560 = "Uzun Kenar: 2560 px (2K)"
    LONG_EDGE_1920 = "Uzun Kenar: 1920 px (Full HD)"
    LONG_EDGE_1280 = "Uzun Kenar: 1280 px (HD)"
    LONG_EDGE_1024 = "Uzun Kenar: 1024 px"
    CUSTOM = "Özel Boyut"


class QualityPreset(enum.Enum):
    """Predefined professional optimization profiles."""

    SCREENSHOT_LOSSLESS = "Ekran Görüntüsü (Kayıpsız PNG)"
    WEB_SHARE = "Web Paylaşımı (WebP 1920px Q88)"
    EMAIL = "E-Posta (JPEG 1280px Q80)"
    SOCIAL_MEDIA = "Sosyal Medya (WebP 2048px Q90)"
    DOCUMENTATION = "Dokümantasyon (PNG / WebP Lossless)"
    MAX_QUALITY = "Maksimum Kalite (Q98 / Orijinal Boyut)"
    MAX_COMPRESSION = "Maksimum Sıkıştırma (WebP Q70)"
    CUSTOM = "Özel Profil"


@dataclass
class OptimizerConfig:
    """Complete options bundle for image optimization execution."""

    mode: OptimizationMode = OptimizationMode.BALANCED
    format: OutputFormat = OutputFormat.AUTO
    quality: int = 88
    is_lossless: bool = False

    target_size_kb: Optional[float] = None

    resize_preset: ResizePreset = ResizePreset.ORIGINAL
    custom_width: int = 1920
    custom_height: int = 1080
    allow_upscaling: bool = False

    strip_metadata: bool = True
    chroma_subsampling: ChromaSubsampling = ChromaSubsampling.CS_444
    progressive_jpeg: bool = True

    webp_method: int = 6  # 0=fastest, 6=slowest/best compression
    png_compress_level: int = 9  # 0..9


@dataclass
class OptimizationResult:
    """Encapsulates the output of an optimization operation with quality metrics."""

    original_size_bytes: int
    optimized_size_bytes: int
    reduction_pct: float
    original_dimensions: Tuple[int, int]
    optimized_dimensions: Tuple[int, int]
    format_name: str

    ssim_score: float = 1.0
    psnr_score: float = 100.0
    quality_label: str = "Mükemmel (Lossless)"
    elapsed_ms: float = 0.0

    optimized_bytes: bytes = field(default_factory=bytes)
    optimized_image: Optional[Image.Image] = None

    @property
    def reduction_str(self) -> str:
        return f"%{self.reduction_pct:.1f}"

    @property
    def orig_size_kb(self) -> float:
        return self.original_size_bytes / 1024.0

    @property
    def opt_size_kb(self) -> float:
        return self.optimized_size_bytes / 1024.0

