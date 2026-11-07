"""Constants and configuration defaults for Quickglint application."""

from enum import Enum, auto


class ToolType(Enum):
    """Available drawing and annotation tools."""
    SELECT = "select"
    ARROW = "arrow"
    LINE = "line"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    PEN = "pen"
    HIGHLIGHTER = "highlighter"
    TEXT = "text"
    BLUR = "blur"
    PIXELATE = "pixelate"
    RULER = "ruler"
    MAGNIFIER = "magnifier"


# Default Application Metadata
APP_NAME = "Quickglint"
APP_VERSION = "2.1.0"
APP_AUTHOR = "Nazmican Yaraş"
APP_AUTHOR_URL = "https://github.com/Nazmicanyrs/"
APP_LICENSE = "QSNCSL 1.0.0 — Source-Available Non-Commercial License"
APP_DESCRIPTION = "Modern, hafif ve güçlü ekran görüntüsü yakalama, anotasyon ve üretkenlik aracı."

# Curated Quick Toolbar Palette (10 High-Contrast Colors)
DEFAULT_PALETTE = [
    "#EF4444",  # Crimson Red
    "#F97316",  # Bright Orange
    "#FACC15",  # Vibrant Yellow
    "#22C55E",  # Emerald Green
    "#06B6D4",  # Electric Cyan
    "#3B82F6",  # Sky Blue
    "#8B5CF6",  # Royal Purple
    "#EC4899",  # Hot Pink
    "#FFFFFF",  # Pure White
    "#0F172A",  # Midnight Dark
]

# Extended Curated Theme Palettes for Advanced Color Panel
EXTENDED_PALETTES = {
    "vibrant": [
        "#DC2626", "#EF4444", "#F87171",  # Reds
        "#EA580C", "#F97316", "#FB923C",  # Oranges
        "#CA8A04", "#FACC15", "#FDE047",  # Yellows
        "#16A34A", "#22C55E", "#4ADE80",  # Greens
        "#0891B2", "#06B6D4", "#67E8F9",  # Cyans
        "#2563EB", "#3B82F6", "#60A5FA",  # Blues
        "#7C3AED", "#8B5CF6", "#A78BFA",  # Purples
        "#DB2777", "#EC4899", "#F472B6",  # Pinks
    ],
    "pastel": [
        "#FECDD3", "#FED7AA", "#FEF08A", "#BBF7D0",
        "#A5F3FC", "#BFDBFE", "#DDD6FE", "#FBCFE8",
    ],
    "monochrome": [
        "#FFFFFF", "#F1F5F9", "#CBD5E1", "#94A3B8",
        "#64748B", "#475569", "#1E293B", "#0F172A",
    ],
}


DEFAULT_DRAWING_COLOR = "#FF0000"
DEFAULT_STROKE_WIDTH = 3
DEFAULT_FONT_SIZE = 18
DEFAULT_FONT_FAMILY = "Segoe UI"
HIGHLIGHTER_OPACITY = 0.35

# Stroke width choices
STROKE_WIDTH_OPTIONS = [1, 2, 3, 5, 8, 12]

# Font size choices
FONT_SIZE_OPTIONS = [10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48]

# Selection handle constants
HANDLE_SIZE = 8
HANDLE_COLOR = "#0088FF"
SELECTION_BORDER_COLOR = "#0088FF"
DIM_BACKGROUND_COLOR = "#000000"
DIM_BACKGROUND_OPACITY = 120  # 0-255

# Hotkey defaults
DEFAULT_CAPTURE_HOTKEY = "PrintScreen"

# Supported image formats
SUPPORTED_IMAGE_FORMATS = ["PNG", "JPEG", "WEBP"]
DEFAULT_IMAGE_FORMAT = "PNG"
DEFAULT_JPEG_QUALITY = 95

