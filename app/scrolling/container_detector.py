"""Analyzes temporal variance across frames to detect scrollable containers vs fixed sidebars and sticky headers."""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
from PIL import Image
from PySide6.QtCore import QRect
from PySide6.QtGui import QImage

from app.privacy.providers import qimage_to_pil


@dataclass
class ContainerLayout:
    """Represents detected layout partitions of the screen."""

    total_width: int
    total_height: int
    left_fixed_width: int
    right_fixed_width: int
    top_sticky_height: int
    scroll_x_start: int
    scroll_x_end: int
    is_multi_column: bool


class ScrollContainerDetector:
    """Detects active scrolling viewport vs static/fixed sidebars and sticky headers."""

    @staticmethod
    def detect_layout(frames: List[QImage]) -> ContainerLayout:
        """
        Analyze at least 2 consecutive frames to find which vertical columns are actively scrolling.
        """
        if len(frames) < 2:
            w, h = (frames[0].width(), frames[0].height()) if frames else (1920, 1080)
            return ContainerLayout(
                total_width=w,
                total_height=h,
                left_fixed_width=0,
                right_fixed_width=0,
                top_sticky_height=0,
                scroll_x_start=0,
                scroll_x_end=w,
                is_multi_column=False,
            )

        f1_pil = qimage_to_pil(frames[0]).convert("L")
        f2_pil = qimage_to_pil(frames[1]).convert("L")

        arr1 = np.array(f1_pil, dtype=np.float32)
        arr2 = np.array(f2_pil, dtype=np.float32)

        h, w = arr1.shape

        # 1. Compute column-wise absolute difference
        col_diff = np.mean(np.abs(arr1 - arr2), axis=0)  # shape (w,)

        # Threshold for active motion (scrolling feed content has large motion > 10.0)
        threshold = 3.5
        active_cols = np.where(col_diff >= threshold)[0]
        active_mask = col_diff >= threshold

        if len(active_cols) < 50:
            # If motion is uniform or very narrow, treat full width as scrollable
            return ContainerLayout(
                total_width=w,
                total_height=h,
                left_fixed_width=0,
                right_fixed_width=0,
                top_sticky_height=0,
                scroll_x_start=0,
                scroll_x_end=w,
                is_multi_column=False,
            )

        # 2. Find the *largest continuous* active area.
        # Tiny gaps are normal inside a text feed; bridge them before finding
        # runs, while keeping a genuinely static sidebar separate.
        gap_start = None
        for idx, active in enumerate(active_mask):
            if not active and gap_start is None:
                gap_start = idx
            elif active and gap_start is not None:
                if idx - gap_start <= 24:
                    active_mask[gap_start:idx] = True
                gap_start = None

        runs: list[tuple[int, int]] = []
        run_start = None
        for idx, active in enumerate(active_mask):
            if active and run_start is None:
                run_start = idx
            elif not active and run_start is not None:
                runs.append((run_start, idx))
                run_start = None
        if run_start is not None:
            runs.append((run_start, w))

        x_start, x_end = max(runs, key=lambda run: run[1] - run[0])
        # A very narrow changing element is not a usable scroll viewport.
        if x_end - x_start < max(50, int(w * 0.20)):
            x_start, x_end = 0, w

        # Check if left sidebar is static (at least 60px width)
        left_fixed_w = x_start if x_start >= 60 else 0
        # Check if right sidebar is static (at least 60px width)
        right_fixed_w = (w - x_end) if (w - x_end) >= 60 else 0

        # Adjust scroll bounds
        scroll_x_start = left_fixed_w
        scroll_x_end = w - right_fixed_w

        # 3. Detect Top Sticky Header (row-wise difference inside scrollable column)
        center_arr1 = arr1[:, scroll_x_start:scroll_x_end]
        center_arr2 = arr2[:, scroll_x_start:scroll_x_end]

        row_diff = np.mean(np.abs(center_arr1 - center_arr2), axis=1)  # shape (h,)

        top_sticky_h = 0
        # Check top 120 pixels for static rows
        for y in range(min(120, h // 4)):
            if row_diff[y] < 2.0:
                top_sticky_h = y + 1
            else:
                break

        # Only register sticky header if at least 25px
        if top_sticky_h < 25:
            top_sticky_h = 0

        is_multi_col = (left_fixed_w > 0) or (right_fixed_w > 0)

        return ContainerLayout(
            total_width=w,
            total_height=h,
            left_fixed_width=left_fixed_w,
            right_fixed_width=right_fixed_w,
            top_sticky_height=top_sticky_h,
            scroll_x_start=scroll_x_start,
            scroll_x_end=scroll_x_end,
            is_multi_column=is_multi_col,
        )

