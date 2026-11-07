"""Tool manager and state container for annotation tools."""

from typing import Optional
from PySide6.QtCore import QObject, Signal
from app.utils.constants import (
    DEFAULT_DRAWING_COLOR,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_STROKE_WIDTH,
    ToolType,
)


class ToolManager(QObject):
    """Holds active tool state, colors, brush sizes, blur levels, and typography."""

    tool_changed = Signal(ToolType)
    color_changed = Signal(str)
    stroke_width_changed = Signal(int)
    font_size_changed = Signal(int)
    font_family_changed = Signal(str)
    blur_settings_changed = Signal()
    magnifier_zoom_changed = Signal(float)

    def __init__(
        self,
        initial_color: str = DEFAULT_DRAWING_COLOR,
        initial_stroke: int = DEFAULT_STROKE_WIDTH,
        initial_font_size: int = DEFAULT_FONT_SIZE,
        initial_font_family: str = DEFAULT_FONT_FAMILY,
        blur_radius: int = 15,
        pixel_size: int = 12,
        blur_tint: str = "",
        blur_tint_opacity: float = 0.2,
        magnifier_zoom: float = 2.0,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._active_tool: ToolType = ToolType.SELECT
        self._color: str = initial_color
        self._stroke_width: int = initial_stroke
        self._font_size: int = initial_font_size
        self._font_family: str = initial_font_family
        self._bold: bool = True
        self._blur_radius: int = blur_radius
        self._pixel_size: int = pixel_size
        self._blur_tint: str = blur_tint
        self._blur_tint_opacity: float = blur_tint_opacity
        self._magnifier_zoom: float = max(1.2, float(magnifier_zoom))

    @property
    def active_tool(self) -> ToolType:
        return self._active_tool

    @active_tool.setter
    def active_tool(self, tool: ToolType) -> None:
        if self._active_tool != tool:
            self._active_tool = tool
            self.tool_changed.emit(tool)

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, color_hex: str) -> None:
        if self._color != color_hex:
            self._color = color_hex
            self.color_changed.emit(color_hex)

    @property
    def stroke_width(self) -> int:
        return self._stroke_width

    @stroke_width.setter
    def stroke_width(self, width: int) -> None:
        if self._stroke_width != width:
            self._stroke_width = max(1, width)
            self.stroke_width_changed.emit(self._stroke_width)

    @property
    def font_size(self) -> int:
        return self._font_size

    @font_size.setter
    def font_size(self, size: int) -> None:
        if self._font_size != size:
            self._font_size = max(8, size)
            self.font_size_changed.emit(self._font_size)

    @property
    def font_family(self) -> str:
        return self._font_family

    @font_family.setter
    def font_family(self, family: str) -> None:
        if self._font_family != family:
            self._font_family = family
            self.font_family_changed.emit(family)

    @property
    def bold(self) -> bool:
        return self._bold

    @bold.setter
    def bold(self, is_bold: bool) -> None:
        self._bold = is_bold

    @property
    def blur_radius(self) -> int:
        return self._blur_radius

    @blur_radius.setter
    def blur_radius(self, radius: int) -> None:
        self._blur_radius = max(2, radius)
        self.blur_settings_changed.emit()

    @property
    def pixel_size(self) -> int:
        return self._pixel_size

    @pixel_size.setter
    def pixel_size(self, size: int) -> None:
        self._pixel_size = max(2, size)
        self.blur_settings_changed.emit()

    @property
    def blur_tint(self) -> str:
        return self._blur_tint

    @blur_tint.setter
    def blur_tint(self, tint_hex: str) -> None:
        self._blur_tint = tint_hex
        self.blur_settings_changed.emit()

    @property
    def blur_tint_opacity(self) -> float:
        return self._blur_tint_opacity

    @blur_tint_opacity.setter
    def blur_tint_opacity(self, opacity: float) -> None:
        self._blur_tint_opacity = max(0.0, min(1.0, opacity))
        self.blur_settings_changed.emit()

    @property
    def magnifier_zoom(self) -> float:
        return self._magnifier_zoom

    @magnifier_zoom.setter
    def magnifier_zoom(self, zoom: float) -> None:
        clamped = max(1.2, min(5.0, float(zoom)))
        if self._magnifier_zoom != clamped:
            self._magnifier_zoom = clamped
            self.magnifier_zoom_changed.emit(self._magnifier_zoom)

