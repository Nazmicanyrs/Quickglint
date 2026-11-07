"""GIF frame deduplication, color palette quantization, and 1.0x real-time timestamp sync."""

from typing import List, Tuple
import numpy as np
from PIL import Image
from PySide6.QtGui import QImage

from app.privacy.providers import qimage_to_pil
from app.recorder.frame import RecordedFrame


def optimize_frames_for_gif(
    frames: List[RecordedFrame],
    target_fps: int = 15,
    deduplicate: bool = True,
    max_colors: int = 256,
) -> Tuple[List[Image.Image], List[int]]:
    """
    Process raw frames for optimal GIF encoding at exact 1.0x real-time playback speed.
    Returns: (list_of_pil_images, list_of_durations_in_ms)
    """
    if not frames:
        return [], []

    default_duration_ms = max(20, int(1000 / max(1, target_fps)))
    pil_images: List[Image.Image] = []
    durations: List[int] = []

    last_arr: np.ndarray | None = None

    for i, frame in enumerate(frames):
        # Calculate real-time frame duration from timestamp delta if available
        if i < len(frames) - 1:
            raw_delta_ms = int((frames[i + 1].timestamp - frame.timestamp) * 1000)
            if raw_delta_ms >= 15:
                frame_duration_ms = min(1000, raw_delta_ms)
            else:
                frame_duration_ms = default_duration_ms
        else:
            frame_duration_ms = durations[-1] if durations else default_duration_ms

        pil_img = qimage_to_pil(frame.image)
        curr_arr = np.array(pil_img, dtype=np.int16)

        # Check for duplicate consecutive frames
        if deduplicate and last_arr is not None:
            diff = np.mean(np.abs(curr_arr - last_arr))
            if diff < 0.8:
                # Merge elapsed duration into the previous frame
                if durations:
                    durations[-1] += frame_duration_ms
                continue

        # Quantize colors using adaptive palette
        quantized = pil_img.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)

        pil_images.append(quantized)
        durations.append(frame_duration_ms)
        last_arr = curr_arr

    return pil_images, durations

