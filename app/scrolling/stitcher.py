"""Advanced Smart Stitching Engine with container awareness and fixed sidebar preservation."""

from typing import List, Optional
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage, QPainter

from app.scrolling.aligner import ImageAligner
from app.scrolling.container_detector import ContainerLayout, ScrollContainerDetector
from app.utils.logger import logger


class ImageStitcher:
    """Stitches consecutive overlapping vertical screen frames without duplicating fixed elements."""

    def __init__(self, sticky_header_height: int = 0) -> None:
        self.sticky_header_height = sticky_header_height

    def stitch(
        self,
        frames: List[QImage],
        precalculated_displacements: Optional[List[int]] = None,
        layout: Optional[ContainerLayout] = None,
    ) -> Optional[QImage]:
        """
        Stitch a sequence of QImages vertically into one tall high-resolution QImage.
        """
        if not frames:
            return None
        if len(frames) == 1:
            return frames[0].copy()

        # 1. Detect layout if not provided
        if layout is None:
            layout = ScrollContainerDetector.detect_layout(frames)

        first_frame = frames[0]
        source_w = first_frame.width()
        h0 = first_frame.height()

        # Drop frames whose size differs from the first one (window resized
        # mid-capture); they cannot be composited safely.
        keep = [i for i, f in enumerate(frames) if i == 0 or (not f.isNull() and f.width() == source_w)]
        if len(keep) != len(frames):
            logger.warning("Skipping %d frame(s) with mismatching size while stitching.", len(frames) - len(keep))
            if precalculated_displacements and len(precalculated_displacements) == len(frames):
                precalculated_displacements = [precalculated_displacements[i] for i in keep]
            frames = [frames[i] for i in keep]
            if len(frames) == 1:
                return frames[0].copy()

        # Clamp the layout to the real image bounds.
        sx = max(0, min(layout.scroll_x_start, source_w - 1))
        ex = max(sx + 1, min(layout.scroll_x_end, source_w))
        if (sx, ex) != (layout.scroll_x_start, layout.scroll_x_end):
            layout = ContainerLayout(
                total_width=layout.total_width,
                total_height=layout.total_height,
                left_fixed_width=layout.left_fixed_width,
                right_fixed_width=layout.right_fixed_width,
                top_sticky_height=layout.top_sticky_height,
                scroll_x_start=sx,
                scroll_x_end=ex,
                is_multi_column=layout.is_multi_column,
            )
        # In a multi-column page, a scrolling screenshot should contain the
        # feed itself, not repeated navigation/recommendation rails.  Cropping
        # also gives the result a clean, document-like shape instead of empty
        # gutters below the first viewport.
        crop_to_feed = layout.is_multi_column and (layout.scroll_x_end - layout.scroll_x_start) < source_w
        w = layout.scroll_x_end - layout.scroll_x_start if crop_to_feed else source_w

        # 2. Determine displacements
        if precalculated_displacements and len(precalculated_displacements) == len(frames):
            displacements = precalculated_displacements
        else:
            displacements = [h0]
            for i in range(1, len(frames)):
                align_res = ImageAligner.align_frames(frames[i - 1], frames[i], layout)
                displacements.append(align_res.dy)

        # Only accepted, physically possible slices consume canvas space.
        valid_displacements = [max(0, min(int(dy), frame.height())) for dy, frame in zip(displacements[1:], frames[1:])]
        total_height = h0 + sum(dy for dy in valid_displacements if dy > 5)
        logger.info(
            "Stitching %d frames. Layout multi-col: %s, Total height: %d px",
            len(frames),
            layout.is_multi_column,
            total_height,
        )

        # 3. Create destination image buffer
        stitched = QImage(w, total_height, QImage.Format.Format_RGB32)
        if stitched.isNull():
            logger.error("Cannot allocate stitched image %dx%d px (out of memory).", w, total_height)
            return None

        # Sample background color from top corner
        sample_x = layout.scroll_x_start + min(10, w - 1) if crop_to_feed else min(10, w - 1)
        bg_color = QColor(first_frame.pixelColor(sample_x, min(10, h0 - 1)))
        stitched.fill(bg_color)

        painter = QPainter(stitched)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        try:
            # Step 1: Draw the initial viewport (the feed only for multi-column pages).
            if crop_to_feed:
                painter.drawImage(0, 0, first_frame.copy(QRect(layout.scroll_x_start, 0, w, h0)))
            else:
                painter.drawImage(0, 0, first_frame)
            current_y = h0

            # Step 2: Composite subsequent frames
            if layout.is_multi_column:
                # Multi-column mode (e.g. X/Twitter, YouTube): Only center feed scrolls!
                xs = layout.scroll_x_start
                xe = layout.scroll_x_end
                feed_w = xe - xs

                for i in range(1, len(frames)):
                    curr_frame = frames[i]
                    dy = valid_displacements[i - 1]
                    if dy <= 5:
                        continue
                    h = curr_frame.height()

                    # Crop newly revealed center feed slice
                    slice_rect = QRect(xs, h - dy, feed_w, dy)
                    target_x = 0 if crop_to_feed else xs
                    target_rect = QRect(target_x, current_y, feed_w, dy)

                    cropped_feed = curr_frame.copy(slice_rect)
                    painter.drawImage(target_rect, cropped_feed)
                    current_y += dy
            else:
                # Full width scroll mode
                for i in range(1, len(frames)):
                    curr_frame = frames[i]
                    dy = valid_displacements[i - 1]
                    if dy <= 5:
                        continue
                    h = curr_frame.height()

                    slice_rect = QRect(0, h - dy, w, dy)
                    target_rect = QRect(0, current_y, w, dy)

                    cropped_slice = curr_frame.copy(slice_rect)
                    painter.drawImage(target_rect, cropped_slice)
                    current_y += dy

        finally:
            painter.end()

        return stitched

