"""GIF and video recording package."""

from app.recorder.countdown_widget import CountdownOverlay
from app.recorder.cursor import CursorRenderer
from app.recorder.frame import RecordedFrame
from app.recorder.gif_encoder import GifEncodingWorker
from app.recorder.optimizer import optimize_frames_for_gif
from app.recorder.preview_dialog import GifPreviewDialog
from app.recorder.recorder import RecordingHUD, ScreenGifRecorder

__all__ = [
    "RecordedFrame",
    "CursorRenderer",
    "CountdownOverlay",
    "RecordingHUD",
    "ScreenGifRecorder",
    "optimize_frames_for_gif",
    "GifEncodingWorker",
    "GifPreviewDialog",
]

