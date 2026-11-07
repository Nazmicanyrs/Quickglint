"""Data models and type definitions for Quickglint Professional Measurement Studio."""

from dataclasses import dataclass, field
from enum import Enum
import json
import math
from typing import Any, Dict, List, Optional, Tuple
import uuid

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor


class MeasurementType(str, Enum):
    """Supported measurement tool modes."""
    DISTANCE = "distance"
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    RECTANGLE = "rectangle"
    ANGLE = "angle"
    POINT = "point"


class SnapMode(str, Enum):
    """Snapping modes for pixel-perfect placement."""
    NONE = "none"
    PIXEL = "pixel"
    GRID = "grid"
    EDGE = "edge"
    CENTER = "center"


@dataclass
class ColorInfo:
    """Color details of an inspected pixel."""
    hex_value: str
    r: int
    g: int
    b: int
    a: int = 255
    h_deg: float = 0.0
    s_pct: float = 0.0
    l_pct: float = 0.0

    @property
    def rgb_str(self) -> str:
        return f"rgb({self.r}, {self.g}, {self.b})"

    @property
    def rgba_str(self) -> str:
        return f"rgba({self.r}, {self.g}, {self.b}, {self.a / 255:.2f})"

    @property
    def hsl_str(self) -> str:
        return f"hsl({self.h_deg:.0f}°, {self.s_pct:.0f}%, {self.l_pct:.0f}%)"


@dataclass
class MeasurementItem:
    """Represents a single persistent measurement on the canvas in source image coordinates."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    mtype: MeasurementType = MeasurementType.DISTANCE
    points: List[Tuple[float, float]] = field(default_factory=list)  # (x, y) in source image pixels
    color: str = "#38BDF8"  # Hex color string
    visible: bool = True
    created_at: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            type_names = {
                MeasurementType.DISTANCE: "Mesafe (Distance)",
                MeasurementType.HORIZONTAL: "Yatay (Horizontal)",
                MeasurementType.VERTICAL: "Dikey (Vertical)",
                MeasurementType.RECTANGLE: "Dikdörtgen (Rectangle)",
                MeasurementType.ANGLE: "Açı (Angle)",
                MeasurementType.POINT: "Nokta (Point)",
            }
            self.name = f"{type_names.get(self.mtype, 'Ölçüm')} #{self.id}"

    def to_summary_text(self) -> str:
        """Returns concise single-line measurement value summary."""
        if self.mtype == MeasurementType.DISTANCE:
            dist = self.data.get("distance", 0.0)
            return f"Mesafe: {dist:.1f} px"
        elif self.mtype == MeasurementType.HORIZONTAL:
            dx = self.data.get("dx", 0.0)
            return f"Yatay: {abs(dx):.1f} px"
        elif self.mtype == MeasurementType.VERTICAL:
            dy = self.data.get("dy", 0.0)
            return f"Dikey: {abs(dy):.1f} px"
        elif self.mtype == MeasurementType.RECTANGLE:
            w = self.data.get("width", 0.0)
            h = self.data.get("height", 0.0)
            return f"{w:.0f} × {h:.0f} px"
        elif self.mtype == MeasurementType.ANGLE:
            ang = self.data.get("angle_deg", 0.0)
            return f"Açı: {ang:.1f}°"
        elif self.mtype == MeasurementType.POINT:
            x = self.data.get("x", 0.0)
            y = self.data.get("y", 0.0)
            hex_val = self.data.get("hex", "")
            return f"X: {x:.0f}, Y: {y:.0f} ({hex_val})"
        return "Ölçüm"

    def to_css(self) -> str:
        """Exports measurement metrics in CSS format."""
        lines = [f"/* {self.name} */"]
        if self.mtype == MeasurementType.DISTANCE:
            lines.append(f"width: {self.data.get('distance', 0.0):.1f}px;")
        elif self.mtype == MeasurementType.HORIZONTAL:
            lines.append(f"width: {abs(self.data.get('dx', 0.0)):.1f}px;")
        elif self.mtype == MeasurementType.VERTICAL:
            lines.append(f"height: {abs(self.data.get('dy', 0.0)):.1f}px;")
        elif self.mtype == MeasurementType.RECTANGLE:
            lines.append(f"width: {self.data.get('width', 0.0):.1f}px;")
            lines.append(f"height: {self.data.get('height', 0.0):.1f}px;")
            lines.append(f"left: {self.data.get('left', 0.0):.1f}px;")
            lines.append(f"top: {self.data.get('top', 0.0):.1f}px;")
        elif self.mtype == MeasurementType.ANGLE:
            lines.append(f"transform: rotate({self.data.get('angle_deg', 0.0):.1f}deg);")
        elif self.mtype == MeasurementType.POINT:
            hex_val = self.data.get("hex", "")
            if hex_val:
                lines.append(f"color: {hex_val};")
                lines.append(f"background-color: {hex_val};")
            lines.append(f"left: {self.data.get('x', 0.0):.1f}px;")
            lines.append(f"top: {self.data.get('y', 0.0):.1f}px;")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Exports measurement metrics in Markdown table format."""
        lines = [f"### {self.name}", "| Metrik | Değer |", "| :--- | :--- |"]
        lines.append(f"| Tür | `{self.mtype.value}` |")
        for k, v in self.data.items():
            if isinstance(v, float):
                lines.append(f"| {k} | `{v:.2f}` |")
            else:
                lines.append(f"| {k} | `{v}` |")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes to dict for JSON export."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.mtype.value,
            "points": self.points,
            "color": self.color,
            "visible": self.visible,
            "data": self.data,
        }

    def to_json(self) -> str:
        """Returns pretty JSON representation."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

