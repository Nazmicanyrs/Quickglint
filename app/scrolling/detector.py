"""End-of-page and no-change detector for automated scrolling captures."""

from typing import Optional
from PySide6.QtGui import QImage
from app.scrolling.overlap import find_vertical_overlap


class ScrollDetector:
    """Monitors scrolling progress and detects end-of-page conditions."""

    def __init__(
        self,
        max_captures: int = 50,
        max_height: int = 50000,
        consecutive_no_change_limit: int = 3,
    ) -> None:
        self.max_captures = max_captures
        self.max_height = max_height
        self.consecutive_no_change_limit = consecutive_no_change_limit

        self.current_height = 0
        self.capture_count = 0
        self.no_change_count = 0
        self._last_image: Optional[QImage] = None

    def analyze_frame(self, new_image: QImage, displacement: Optional[int] = None) -> tuple[bool, int, str]:
        """
        Analyze new frame against last frame.
        Returns: (should_stop: bool, displacement_dy: int, reason: str)
        """
        self.capture_count += 1

        if self.capture_count >= self.max_captures:
            return True, 0, f"Maximum capture limit reached ({self.max_captures} frames)"

        if self._last_image is None:
            self._last_image = new_image.copy()
            self.current_height = new_image.height()
            return False, new_image.height(), "First frame"

        # The controller may already have registered this pair using the
        # detected scroll container.  Re-measuring against the full window can
        # disagree on multi-column/dynamic pages and prematurely stop capture.
        dy = displacement if displacement is not None else find_vertical_overlap(self._last_image, new_image)

        if dy <= 5:
            self.no_change_count += 1
            if self.no_change_count >= self.consecutive_no_change_limit:
                return True, 0, "End of scroll reached (No significant change detected)"
        else:
            self.no_change_count = 0
            self.current_height += dy

        if self.current_height >= self.max_height:
            return True, dy, f"Maximum image height reached ({self.max_height} px)"

        self._last_image = new_image.copy()
        return False, dy, "Progressing"

