"""Controller for orchestrating professional smart scrolling capture workflow."""

import sys
import time
from typing import List, Optional
from PySide6.QtCore import QCoreApplication, QObject, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QWidget

from app.capture.engine import CaptureEngine
from app.scrolling.aligner import ImageAligner
from app.scrolling.container_detector import ContainerLayout, ScrollContainerDetector
from app.scrolling.detector import ScrollDetector
from app.scrolling.progress_dialog import ScrollingProgressDialog
from app.scrolling.scroller import PageScroller
from app.scrolling.stitcher import ImageStitcher
from app.utils.logger import logger


class ScrollingCaptureController(QObject):
    """Manages smartphone-like step-by-step and auto-scrolling capture sessions with live preview."""

    frame_captured = Signal(int, int, QImage)  # count, height, preview_img
    capture_finished = Signal(QImage)
    capture_failed = Signal(str)

    def __init__(
        self,
        region: QRect,
        on_complete_callback,
        on_cancel_callback,
        parent_widget: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent_widget)
        self.region = region
        self.on_complete = on_complete_callback
        self.on_cancel = on_cancel_callback
        self.parent_widget = parent_widget
        self._busy = False

        # Adjust capture region to exclude taskbar if full screen
        primary_screen = QGuiApplication.primaryScreen()
        if primary_screen:
            avail_geo = primary_screen.availableGeometry()
            if self.region.height() >= primary_screen.geometry().height() - 10:
                self.region = self.region.intersected(avail_geo)

        self.frames: List[QImage] = []
        self.displacements: List[int] = []
        self.layout: Optional[ContainerLayout] = None

        self.detector = ScrollDetector(max_captures=50, max_height=50000, consecutive_no_change_limit=3)
        # Smaller steps retain a larger overlap, which makes registration
        # substantially more reliable on feeds containing video and cards.
        self.scroller = PageScroller(step_clicks=3, delay_seconds=0.35)
        self.stitcher = ImageStitcher()

        # UI Progress HUD
        self.progress_hud = ScrollingProgressDialog(parent_widget)
        self._connect_hud_signals()

        # Auto-scroll timer
        self.auto_timer = QTimer(self)
        # Leave enough time for wheel animation, image decoding and browser
        # compositing before the next capture.  Stability is preferred over a
        # barely perceptible increase in capture speed.
        self.auto_timer.setInterval(1050)
        self.auto_timer.timeout.connect(self._perform_single_step)

    def _connect_hud_signals(self) -> None:
        self.progress_hud.step_scroll_requested.connect(self._on_user_step_scroll)
        self.progress_hud.toggle_auto_scroll_requested.connect(self._toggle_auto_scroll)
        self.progress_hud.finish_requested.connect(self.finish_and_edit)
        self.progress_hud.cancel_requested.connect(self.cancel)

    def start(self) -> None:
        """Position progress HUD and capture initial frame."""
        logger.info("Starting professional scroll capture for region: %s", self.region)
        self.frames.clear()
        self.displacements.clear()
        self.layout = None
        self.detector = ScrollDetector(max_captures=50, max_height=50000, consecutive_no_change_limit=3)

        # Place HUD near top-right of target region
        hud_x = max(20, self.region.right() - self.progress_hud.width() - 10)
        hud_y = max(20, self.region.top() + 10)
        self.progress_hud.move(hud_x, hud_y)
        self.progress_hud.show()
        self.progress_hud.raise_()

        # Capture first frame immediately
        first_frame = CaptureEngine.capture_region(self.region, include_cursor=False)
        self.frames.append(first_frame)
        self.displacements.append(first_frame.height())
        self.detector.analyze_frame(first_frame)
        self.progress_hud.update_stats(1, first_frame.height(), first_frame)

    def _on_user_step_scroll(self) -> None:
        """User tapped 'Daha Fazla Kaydır' (Scroll More)."""
        self._perform_single_step()

    def _toggle_auto_scroll(self) -> None:
        if self.auto_timer.isActive():
            self.auto_timer.stop()
            self.progress_hud.set_auto_scroll_state(False)
        else:
            self.progress_hud.set_auto_scroll_state(True)
            self.auto_timer.start()

    @staticmethod
    def _wait(seconds: float) -> None:
        """Sleep while keeping the Qt event loop (HUD buttons) responsive."""
        app = QCoreApplication.instance()
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                break
            if app is not None:
                app.processEvents()
            time.sleep(min(0.02, remaining))

    def _capture_settled_frame(self) -> QImage:
        """Capture after a short, bounded check that smooth scrolling stopped.

        Modern browsers often keep compositing for a fraction of a second after
        the wheel event.  Capturing during that period is a common source of
        one-pixel seams.  Dynamic video normally produces no verified vertical
        displacement, so it does not cause this method to keep waiting.
        """
        frame = CaptureEngine.capture_region(self.region, include_cursor=False)
        for _ in range(2):
            self._wait(0.12)
            candidate = CaptureEngine.capture_region(self.region, include_cursor=False)
            movement = ImageAligner.align_frames(frame, candidate, self.layout)
            if movement.is_valid and movement.dy >= 8:
                frame = candidate
                self._wait(0.18)
                continue
            return candidate
        return frame

    def _perform_single_step(self) -> None:
        """Scroll down one unit and capture; guarded against re-entrancy and errors."""
        if self._busy:
            return
        self._busy = True
        try:
            self._perform_single_step_impl()
        except Exception as exc:
            logger.error("Scroll step failed: %s", exc, exc_info=True)
        finally:
            self._busy = False

    def _perform_single_step_impl(self) -> None:
        """Scroll down one unit and capture new frame after smooth-scrolling settles."""
        center_point = self.region.center()
        self.scroller.scroll_down(target_pos=center_point)
        # The scroller already waits for the wheel event; this additional
        # settling period prevents sampling a frame during smooth scrolling or
        # while a newly visible image is still being composited.
        self._wait(0.35)

        # Capture new settled frame
        new_frame = self._capture_settled_frame()
        if new_frame is None or new_frame.isNull():
            logger.warning("Captured frame is empty; skipping scroll step.")
            return

        # Detect container layout once we have 2 frames
        if len(self.frames) == 1 or self.layout is None:
            self.layout = ScrollContainerDetector.detect_layout([self.frames[0], new_frame])

        # High-precision alignment on active scroll container
        align_res = ImageAligner.align_frames(self.frames[-1], new_frame, self.layout)
        dy = align_res.dy

        # Never invent a displacement after a failed registration.  The old
        # fallback (one third of the image height) was the direct cause of
        # duplicated/overlaid screenshots.  An unverified frame is discarded.
        if not align_res.is_valid or dy <= 5:
            # A failed registration is not proof that the page ended.  Feeds
            # with autoplaying video, lazy-loaded images and animated controls
            # can temporarily defeat matching while still scrolling normally.
            # Keep the last accepted frame and try the next scroll step; this
            # produces a larger (but still valid) displacement on retry.
            #
            # Only an explicitly identical frame from the aligner counts as
            # "no movement" and may stop auto-scroll at the end of a page.
            is_identical = align_res.is_valid and dy == 0 and align_res.confidence >= 0.99
            if is_identical:
                self.detector.no_change_count += 1
                if self.detector.no_change_count >= 3:
                    logger.info("End of page reached (3 identical frames). Stopping auto-scroll.")
                    self.auto_timer.stop()
                    self.progress_hud.set_auto_scroll_state(False)
            else:
                self.detector.no_change_count = 0
                logger.warning(
                    "Scroll frame could not be verified (confidence=%.2f); continuing capture.",
                    align_res.confidence,
                )
            return
        else:
            self.detector.no_change_count = 0

        self.frames.append(new_frame)
        self.displacements.append(dy)

        should_stop, _, reason = self.detector.analyze_frame(new_frame, displacement=dy)
        logger.info(
            "Scroll step frame #%d (dy=%d px, conf=%.2f, multi-col=%s)",
            len(self.frames),
            dy,
            align_res.confidence,
            self.layout.is_multi_column if self.layout else False,
        )

        # Instant thumbnail update (0ms lag, no freeze)
        self.progress_hud.update_stats(len(self.frames), sum(self.displacements), new_frame)

        if should_stop:
            logger.info("Scroll end reached: %s", reason)
            self.auto_timer.stop()
            self.progress_hud.set_auto_scroll_state(False)

    def finish_and_edit(self) -> None:
        """User clicked '✓ Bitir ve Düzenle'."""
        self.auto_timer.stop()
        self.progress_hud.close()

        if not self.frames:
            self.on_cancel()
            return

        logger.info("Finishing scroll capture. Instantly stitching %d frames with container layout...", len(self.frames))
        stitched = self.stitcher.stitch(
            self.frames,
            precalculated_displacements=self.displacements,
            layout=self.layout,
        )

        if stitched is not None and not stitched.isNull():
            self.on_complete(stitched)
        else:
            self.on_cancel()

    def cancel(self) -> None:
        """User cancelled capture."""
        self.auto_timer.stop()
        self.progress_hud.close()
        self.frames.clear()
        self.displacements.clear()
        self.on_cancel()

