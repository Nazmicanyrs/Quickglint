"""Background GIF encoding worker with quality presets and live progress reporting."""

from pathlib import Path
from typing import List, Optional
from PIL import Image
from PySide6.QtCore import QThread, Signal

from app.recorder.cursor import CursorRenderer
from app.recorder.frame import RecordedFrame
from app.recorder.optimizer import optimize_frames_for_gif
from app.utils.logger import logger


class GifEncodingWorker(QThread):
    """Encodes a sequence of RecordedFrames into an optimized animated GIF file."""

    progress_updated = Signal(int)  # 0 to 100
    encoding_finished = Signal(str)  # output_path
    encoding_failed = Signal(str)

    def __init__(
        self,
        frames: List[RecordedFrame],
        output_path: str,
        fps: int = 15,
        loop: int = 0,  # 0 = forever
        cursor_renderer: Optional[CursorRenderer] = None,
        deduplicate: bool = True,
        max_colors: int = 256,
        parent: Optional[QThread] = None,
    ) -> None:
        super().__init__(parent)
        self.frames = frames
        self.output_path = output_path
        self.fps = fps
        self.loop = loop
        self.cursor_renderer = cursor_renderer or CursorRenderer()
        self.deduplicate = deduplicate
        self.max_colors = max_colors

    def run(self) -> None:
        if not self.frames:
            self.encoding_failed.emit("No frames to encode.")
            return

        try:
            logger.info("Starting GIF encoding for %d frames to %s...", len(self.frames), self.output_path)
            self.progress_updated.emit(10)

            # 1. Render cursor and effects onto frames
            rendered_frames: List[RecordedFrame] = []
            total = len(self.frames)

            for i, f in enumerate(self.frames):
                img_with_cursor = self.cursor_renderer.render_to_frame(
                    f.image,
                    f.cursor_pos,
                    is_left_clicked=f.is_left_clicked,
                    is_right_clicked=f.is_right_clicked,
                )
                rendered_frames.append(RecordedFrame(img_with_cursor, f.timestamp))

                if i % max(1, total // 5) == 0:
                    pct = 10 + int((i / total) * 30)
                    self.progress_updated.emit(pct)

            self.progress_updated.emit(45)

            # 2. Optimize and quantize
            pil_images, durations = optimize_frames_for_gif(
                rendered_frames,
                target_fps=self.fps,
                deduplicate=self.deduplicate,
                max_colors=self.max_colors,
            )

            if not pil_images:
                self.encoding_failed.emit("Frame optimization produced empty result.")
                return

            self.progress_updated.emit(75)

            # 3. Save animated GIF
            out_file = Path(self.output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)

            first_frame = pil_images[0]
            first_frame.save(
                out_file,
                save_all=True,
                append_images=pil_images[1:],
                duration=durations,
                loop=self.loop,
                optimize=True,
            )

            self.progress_updated.emit(100)
            logger.info("GIF successfully written to %s (Size: %.2f KB)", out_file, out_file.stat().st_size / 1024)
            self.encoding_finished.emit(str(out_file))

        except Exception as exc:
            logger.error("GIF encoding failed: %s", exc, exc_info=True)
            self.encoding_failed.emit(str(exc))

