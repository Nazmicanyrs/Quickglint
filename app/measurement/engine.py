"""Geometric and color measurement calculation engine with precision snapping."""

import colorsys
import math
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QImage

from app.measurement.models import ColorInfo, MeasurementItem, MeasurementType, SnapMode


class MeasurementEngine:
    """Provides pure math & color extraction algorithms for pixel measurement."""

    @staticmethod
    def calculate_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> Dict[str, float]:
        """Calculates Euclidean distance, delta X, delta Y, and polar angle in degrees."""
        x1, y1 = p1
        x2, y2 = p2
        dx = x2 - x1
        dy = y2 - y1
        distance = math.hypot(dx, dy)
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)
        if angle_deg < 0:
            angle_deg += 360.0

        return {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "dx": dx,
            "dy": dy,
            "distance": distance,
            "angle_deg": angle_deg,
        }

    @staticmethod
    def calculate_horizontal(p1: Tuple[float, float], p2: Tuple[float, float]) -> Dict[str, float]:
        """Calculates horizontal delta between two points."""
        x1, y1 = p1
        x2, y2 = p2
        dx = x2 - x1
        return {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "dx": dx,
            "dy": 0.0,
            "distance": abs(dx),
            "angle_deg": 0.0 if dx >= 0 else 180.0,
        }

    @staticmethod
    def calculate_vertical(p1: Tuple[float, float], p2: Tuple[float, float]) -> Dict[str, float]:
        """Calculates vertical delta between two points."""
        x1, y1 = p1
        x2, y2 = p2
        dy = y2 - y1
        return {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "dx": 0.0,
            "dy": dy,
            "distance": abs(dy),
            "angle_deg": 90.0 if dy >= 0 else 270.0,
        }

    @staticmethod
    def calculate_rectangle(p1: Tuple[float, float], p2: Tuple[float, float]) -> Dict[str, float]:
        """Calculates width, height, bounding box (left/top/right/bottom), area, and center."""
        x1, y1 = p1
        x2, y2 = p2

        left = min(x1, x2)
        right = max(x1, x2)
        top = min(y1, y2)
        bottom = max(y1, y2)

        width = right - left
        height = bottom - top
        area = width * height
        center_x = left + width / 2.0
        center_y = top + height / 2.0

        return {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": width,
            "height": height,
            "area": area,
            "center_x": center_x,
            "center_y": center_y,
        }

    @staticmethod
    def calculate_angle_3pt(
        pA: Tuple[float, float],
        pB: Tuple[float, float],  # Vertex
        pC: Tuple[float, float],
    ) -> Dict[str, float]:
        """Calculates the angle between vector BA and BC with vertex at B."""
        ax, ay = pA
        bx, by = pB
        cx, cy = pC

        # Vector BA = A - B
        v1x, v1y = ax - bx, ay - by
        # Vector BC = C - B
        v2x, v2y = cx - bx, cy - by

        len1 = math.hypot(v1x, v1y)
        len2 = math.hypot(v2x, v2y)

        if len1 == 0.0 or len2 == 0.0:
            return {"angle_deg": 0.0, "supplementary_deg": 180.0, "interior_deg": 0.0}

        dot = v1x * v2x + v1y * v2y
        cos_theta = max(-1.0, min(1.0, dot / (len1 * len2)))
        angle_rad = math.acos(cos_theta)
        angle_deg = math.degrees(angle_rad)

        return {
            "angle_deg": angle_deg,
            "interior_deg": angle_deg,
            "supplementary_deg": 180.0 - angle_deg,
            "len_ba": len1,
            "len_bc": len2,
            "vertex_x": bx,
            "vertex_y": by,
        }

    @staticmethod
    def sample_pixel_color(image: QImage, x: int, y: int) -> ColorInfo:
        """Inspects pixel color at (x, y) coordinates and converts to HEX, RGB, HSL."""
        if image.isNull() or x < 0 or y < 0 or x >= image.width() or y >= image.height():
            return ColorInfo(hex_value="#000000", r=0, g=0, b=0, a=255)

        pixel = image.pixelColor(x, y)
        r, g, b, a = pixel.red(), pixel.green(), pixel.blue(), pixel.alpha()
        hex_val = f"#{r:02X}{g:02X}{b:02X}"

        # Calculate HSL
        h_norm, l_norm, s_norm = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        h_deg = h_norm * 360.0
        s_pct = s_norm * 100.0
        l_pct = l_norm * 100.0

        return ColorInfo(
            hex_value=hex_val,
            r=r,
            g=g,
            b=b,
            a=a,
            h_deg=h_deg,
            s_pct=s_pct,
            l_pct=l_pct,
        )

    @staticmethod
    def snap_point(
        point: Tuple[float, float],
        img_width: int,
        img_height: int,
        mode: SnapMode = SnapMode.NONE,
        grid_size: int = 16,
        snap_tolerance: float = 10.0,
        custom_snap_points: Optional[List[Tuple[float, float]]] = None,
    ) -> Tuple[float, float]:
        """Snaps point according to the selected SnapMode."""
        x, y = point

        # 1. Clamp to image bounds
        x = max(0.0, min(float(img_width - 1), x))
        y = max(0.0, min(float(img_height - 1), y))

        if mode == SnapMode.NONE:
            return x, y

        elif mode == SnapMode.PIXEL:
            return round(x), round(y)

        elif mode == SnapMode.GRID:
            if grid_size <= 0:
                grid_size = 16
            snapped_x = round(x / grid_size) * grid_size
            snapped_y = round(y / grid_size) * grid_size
            snapped_x = max(0.0, min(float(img_width - 1), float(snapped_x)))
            snapped_y = max(0.0, min(float(img_height - 1), float(snapped_y)))
            return snapped_x, snapped_y

        elif mode == SnapMode.CENTER:
            cx, cy = img_width / 2.0, img_height / 2.0
            rx = cx if abs(x - cx) <= snap_tolerance else x
            ry = cy if abs(y - cy) <= snap_tolerance else y
            return rx, ry

        elif mode == SnapMode.EDGE:
            # Snap to left/right/top/bottom edges if close
            rx = x
            ry = y
            if abs(x - 0.0) <= snap_tolerance:
                rx = 0.0
            elif abs(x - (img_width - 1)) <= snap_tolerance:
                rx = float(img_width - 1)

            if abs(y - 0.0) <= snap_tolerance:
                ry = 0.0
            elif abs(y - (img_height - 1)) <= snap_tolerance:
                ry = float(img_height - 1)

            return rx, ry

        return x, y

