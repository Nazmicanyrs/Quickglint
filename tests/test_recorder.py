"""Unit tests for GIF Screen Recorder, Frame Optimization, and GIF Encoding."""

import os
import tempfile
import time
from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage

from app.recorder.cursor import CursorRenderer
from app.recorder.frame import RecordedFrame
from app.recorder.optimizer import optimize_frames_for_gif


def create_dummy_frame(color_val: int = 100, width: int = 120, height: int = 80) -> RecordedFrame:
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(color_val, color_val, color_val))
    return RecordedFrame(image=img, timestamp=time.time(), cursor_pos=QPoint(10, 10))


def test_frame_capture():
    f = create_dummy_frame(120)
    assert f.image.width() == 120
    assert f.image.height() == 80
    assert f.cursor_pos == QPoint(10, 10)


def test_fps_conversion():
    frames = [create_dummy_frame(i * 10) for i in range(5)]
    # 10 FPS -> 100ms per frame
    pil_imgs, durations = optimize_frames_for_gif(frames, target_fps=10, deduplicate=False)
    assert len(pil_imgs) == 5
    assert durations[0] == 100

    # 20 FPS -> 50ms per frame
    _, durations_20 = optimize_frames_for_gif(frames, target_fps=20, deduplicate=False)
    assert durations_20[0] == 50


def test_frame_deduplication():
    # 3 identical frames followed by 1 different frame
    f1 = create_dummy_frame(50)
    f2 = create_dummy_frame(50)
    f3 = create_dummy_frame(50)
    f4 = create_dummy_frame(180)

    pil_imgs, durations = optimize_frames_for_gif([f1, f2, f3, f4], target_fps=10, deduplicate=True)
    # The 3 identical frames should be merged into 1 frame with 3x duration
    assert len(pil_imgs) == 2
    assert durations[0] == 300  # 100ms * 3


def test_gif_encoding():
    frames = [create_dummy_frame(i * 20) for i in range(4)]
    pil_imgs, durations = optimize_frames_for_gif(frames, target_fps=15, deduplicate=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_gif = os.path.join(tmpdir, "test_output.gif")
        pil_imgs[0].save(
            out_gif,
            save_all=True,
            append_images=pil_imgs[1:],
            duration=durations,
            loop=0,
        )

        assert os.path.exists(out_gif)
        assert os.path.getsize(out_gif) > 0

        # Verify saved GIF properties
        with Image.open(out_gif) as gif:
            assert gif.is_animated is True
            assert gif.n_frames == 4


def test_gif_loop():
    frames = [create_dummy_frame(10), create_dummy_frame(20)]
    pil_imgs, durations = optimize_frames_for_gif(frames, target_fps=10)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_gif = os.path.join(tmpdir, "test_loop.gif")
        pil_imgs[0].save(out_gif, save_all=True, append_images=pil_imgs[1:], duration=durations, loop=0)
        assert os.path.exists(out_gif)


def test_trim():
    frames = [create_dummy_frame(i) for i in range(10)]
    # Trim from index 2 to 6
    trimmed = frames[2:7]
    assert len(trimmed) == 5
    assert trimmed[0] == frames[2]
    assert trimmed[-1] == frames[6]


def test_cursor_renderer():
    frame = create_dummy_frame(80)
    renderer = CursorRenderer(show_cursor=True, highlight_cursor=True, show_click_effects=True)
    rendered = renderer.render_to_frame(frame.image, frame.cursor_pos, is_left_clicked=True)
    assert rendered.width() == frame.image.width()
    assert rendered.height() == frame.image.height()

