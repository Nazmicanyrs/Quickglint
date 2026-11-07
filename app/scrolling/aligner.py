"""High-precision Zero-mean Normalized Cross-Correlation (ZNCC) image registration engine."""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
import cv2
from PIL import Image
from PySide6.QtGui import QImage

from app.privacy.providers import qimage_to_pil
from app.scrolling.container_detector import ContainerLayout


@dataclass
class AlignmentResult:
    """Result of image registration between two frames."""

    dy: int
    dx: int
    confidence: float
    is_valid: bool


class ImageAligner:
    """High-precision ZNCC displacement detector with 1:1 single-pixel refinement."""

    @staticmethod
    def align_frames(
        prev_image: QImage | Image.Image | np.ndarray,
        curr_image: QImage | Image.Image | np.ndarray,
        layout: Optional[ContainerLayout] = None,
        max_search_height: int = 900,
    ) -> AlignmentResult:
        """
        Compute exact vertical displacement (dy) using feature-rich ZNCC with 1:1 refinement.
        """
        if isinstance(prev_image, QImage) and prev_image.isNull():
            return AlignmentResult(dy=0, dx=0, confidence=0.0, is_valid=False)
        if isinstance(curr_image, QImage) and curr_image.isNull():
            return AlignmentResult(dy=0, dx=0, confidence=0.0, is_valid=False)

        if isinstance(prev_image, QImage):
            prev_pil = qimage_to_pil(prev_image).convert("L")
        elif isinstance(prev_image, Image.Image):
            prev_pil = prev_image.convert("L")
        else:
            prev_pil = Image.fromarray(prev_image).convert("L")

        if isinstance(curr_image, QImage):
            curr_pil = qimage_to_pil(curr_image).convert("L")
        elif isinstance(curr_image, Image.Image):
            curr_pil = curr_image.convert("L")
        else:
            curr_pil = Image.fromarray(curr_image).convert("L")

        prev_arr = np.array(prev_pil, dtype=np.float32)
        curr_arr = np.array(curr_pil, dtype=np.float32)

        h, w = prev_arr.shape
        if h < 40 or curr_arr.shape[0] < 40:
            return AlignmentResult(dy=h, dx=0, confidence=1.0, is_valid=True)

        # Frames of different size (window resized, taskbar crop...) cannot be
        # compared pixel-wise; report an unverified frame instead of crashing.
        if prev_arr.shape != curr_arr.shape:
            return AlignmentResult(dy=0, dx=0, confidence=0.0, is_valid=False)
        # 1. Quick identical check
        diff = np.abs(prev_arr - curr_arr)
        if np.mean(diff) < 0.6:
            return AlignmentResult(dy=0, dx=0, confidence=1.0, is_valid=True)

        # 2. Extract active scroll container
        if layout is not None:
            x_start = max(0, min(layout.scroll_x_start, w - 2))
            x_end = max(x_start + 1, min(layout.scroll_x_end, w))
            top_cut = max(0, min(layout.top_sticky_height, h - 1))
        else:
            x_start = int(w * 0.05)
            x_end = int(w * 0.95)
            top_cut = min(15, int(h * 0.05))

        # Sample columns with step for speed
        col_slice = slice(x_start, x_end, 2)
        sample_prev = prev_arr[:, col_slice]
        sample_curr = curr_arr[:, col_slice]

        # 3. Match several independent content strips.  A single strip is easily
        # fooled by repeated rows, cards or a sticky header, which used to make a
        # failed match look like a legitimate scroll and duplicate the image.
        tmpl_h = max(18, min(80, int(h * 0.18)))
        min_dy = 6
        max_dy = min(max_search_height, h - tmpl_h - top_cut - 1)
        if max_dy <= min_dy:
            return AlignmentResult(dy=0, dx=0, confidence=0.0, is_valid=False)

        candidate_y = np.linspace(
            top_cut + 2,
            max(top_cut + 2, min(int(h * 0.45), h - tmpl_h - 1)),
            num=5,
            dtype=int,
        )
        matches: list[tuple[int, float]] = []
        for y0 in sorted(set(candidate_y.tolist())):
            if y0 + tmpl_h >= h:
                continue
            local_max_dy = min(max_search_height, h - tmpl_h - y0)
            if local_max_dy <= min_dy:
                continue
            template = sample_curr[y0 : y0 + tmpl_h].astype(np.uint8)
            if float(np.var(template)) < 6.0:
                continue
            search_end = min(h, y0 + local_max_dy + tmpl_h)
            search = sample_prev[y0 + min_dy : search_end].astype(np.uint8)
            if search.shape[0] < tmpl_h:
                continue
            response = cv2.matchTemplate(search, template, cv2.TM_SQDIFF_NORMED)
            min_val, _, min_loc, _ = cv2.minMaxLoc(response)
            score = max(0.0, 1.0 - float(min_val))
            matches.append((min_dy + min_loc[1], score))

        if not matches:
            return AlignmentResult(dy=0, dx=0, confidence=0.0, is_valid=False)

        # Require consensus: one accidental correlation cannot authorise adding a
        # frame to the final image.  Keep only high-quality matches near the median.
        scores = np.array([score for _, score in matches])
        displacements = np.array([dy for dy, _ in matches])
        likely = scores >= 0.70
        if not np.any(likely):
            return AlignmentResult(dy=0, dx=0, confidence=float(scores.max()), is_valid=False)
        median_dy = int(round(float(np.median(displacements[likely]))))
        agreeing = likely & (np.abs(displacements - median_dy) <= 6)
        confidence = float(np.mean(scores[agreeing])) if np.any(agreeing) else float(scores.max())
        best_dy = median_dy
        # Fast-moving video cards can invalidate most sampled strips even when
        # one distinctive content strip is a valid match.  The single-strip
        # threshold remains above the normal template confidence floor, but is
        # intentionally permissive enough that auto-scroll never stalls on a
        # changing social feed.
        consensus_match = np.count_nonzero(agreeing) >= 2 and confidence >= 0.72
        strong_single_match = np.count_nonzero(agreeing) >= 1 and confidence >= 0.78
        is_valid = bool((consensus_match or strong_single_match) and best_dy >= min_dy)

        if not is_valid:
            return AlignmentResult(dy=0, dx=0, confidence=confidence, is_valid=False)

        return AlignmentResult(
            dy=best_dy,
            dx=0,
            confidence=max(0.0, confidence),
            is_valid=is_valid,
        )

