"""Multi-Monitor detection, DPI-aware screen capture, and physical coordinate layout engine."""

import time
import uuid
from typing import List, Optional, Sequence
import cv2
import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPainter, QPolygon

from app.panorama.models import MonitorInfo, PanoramaCaptureMode, PanoramaFrame, StitchConfig, StitchResult
from app.utils.logger import logger


class MultiMonitorManager:
    """Detects connected monitors, captures selected displays, and composes physical desktop layouts."""

    @staticmethod
    def detect_monitors() -> List[MonitorInfo]:
        """Auto-detect all connected monitors with physical resolution, position, DPI, and orientation."""
        screens = QGuiApplication.screens()
        primary_screen = QGuiApplication.primaryScreen()
        monitors: List[MonitorInfo] = []

        for idx, screen in enumerate(screens):
            geom = screen.geometry()
            dpr = float(screen.devicePixelRatio() or 1.0)
            size_px = screen.size() * dpr
            phys_w = max(1, int(round(size_px.width())))
            phys_h = max(1, int(round(size_px.height())))

            info = MonitorInfo(
                index=idx,
                name=screen.name() or f"Display {idx + 1}",
                manufacturer=getattr(screen, "manufacturer", lambda: "")() or "",
                model=getattr(screen, "model", lambda: "")() or "",
                logical_geometry=QRect(geom),
                physical_width=phys_w,
                physical_height=phys_h,
                dpi_x=float(screen.logicalDotsPerInchX() or 96.0),
                dpi_y=float(screen.logicalDotsPerInchY() or 96.0),
                scale_factor=dpr,
                is_primary=(screen == primary_screen),
                refresh_rate=float(screen.refreshRate() or 60.0),
            )
            monitors.append(info)

        return monitors

    @staticmethod
    def capture_monitor(monitor_index: int, include_cursor: bool = False) -> Optional[PanoramaFrame]:
        """Capture a single monitor at its native resolution."""
        screens = QGuiApplication.screens()
        if monitor_index < 0 or monitor_index >= len(screens):
            logger.warning("Requested invalid monitor index %d (available: %d)", monitor_index, len(screens))
            return None

        monitors = MultiMonitorManager.detect_monitors()
        mon_info = monitors[monitor_index]
        screen = screens[monitor_index]

        grabbed = screen.grabWindow(0)
        if grabbed.isNull():
            logger.error("Failed to grab window for monitor %d (%s)", monitor_index, mon_info.name)
            return None

        img = grabbed.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
        if include_cursor:
            cursor_pos = QCursor.pos()
            if mon_info.logical_geometry.contains(cursor_pos):
                local_x = int(round((cursor_pos.x() - mon_info.logical_geometry.x()) * mon_info.scale_factor))
                local_y = int(round((cursor_pos.y() - mon_info.logical_geometry.y()) * mon_info.scale_factor))
                MultiMonitorManager._draw_cursor_on_image(img, QPoint(local_x, local_y))

        # Update physical dimensions from actual captured image
        mon_info.physical_width = img.width()
        mon_info.physical_height = img.height()

        return PanoramaFrame(
            frame_id=f"mon_{monitor_index}_{uuid.uuid4().hex[:6]}",
            title=mon_info.display_label,
            image=img,
            monitor_info=mon_info,
            logical_rect=QRect(mon_info.logical_geometry),
            enabled=True,
            order_index=monitor_index,
        )

    @staticmethod
    def capture_monitors(
        monitor_indices: Optional[Sequence[int]] = None,
        include_cursor: bool = False,
    ) -> List[PanoramaFrame]:
        """Capture multiple monitors simultaneously (all monitors if monitor_indices is None)."""
        screens = QGuiApplication.screens()
        if not screens:
            return []

        indices = list(monitor_indices) if monitor_indices is not None else list(range(len(screens)))
        frames: List[PanoramaFrame] = []
        for order_i, mon_idx in enumerate(indices):
            frame = MultiMonitorManager.capture_monitor(mon_idx, include_cursor=include_cursor)
            if frame is not None:
                frame.order_index = order_i
                frames.append(frame)
        return frames

    @staticmethod
    def monitors_have_physical_overlap(frames: Sequence[PanoramaFrame]) -> bool:
        """Check whether two or more monitor frames have overlapping logical desktop rects."""
        rects = [f.logical_rect for f in frames if f.enabled and f.logical_rect is not None and not f.logical_rect.isEmpty()]
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                inter = rects[i].intersected(rects[j])
                if inter.width() > 4 and inter.height() > 4:
                    return True
        return False

    @staticmethod
    def compose_desktop_layout(
        frames: Sequence[PanoramaFrame],
        config: Optional[StitchConfig] = None,
    ) -> StitchResult:
        """
        Compose multiple monitor frames into a unified high-resolution panorama using real
        desktop coordinates (or user-selected horizontal/vertical layout) without unnecessary
        feature matching when monitors are physically non-overlapping.
        """
        start_t = time.perf_counter()
        cfg = config or StitchConfig()
        active_frames = [f for f in frames if f.enabled and not f.image.isNull()]

        if not active_frames:
            return StitchResult(
                success=False,
                error_message="Birleştirilecek geçerli bir ekran görüntüsü bulunamadı.",
            )

        if len(active_frames) == 1:
            single_img = active_frames[0].image.copy()
            elapsed = (time.perf_counter() - start_t) * 1000.0
            return StitchResult(
                success=True,
                image=single_img,
                mode_used=cfg.mode.value,
                detector_used="desktop_coordinates",
                frames_count=1,
                execution_time_ms=elapsed,
            )

        arrangement = cfg.layout_arrangement
        has_all_rects = all(f.logical_rect is not None and not f.logical_rect.isEmpty() for f in active_frames)

        if arrangement == "physical" and has_all_rects:
            composed = MultiMonitorManager._compose_by_physical_geometry(active_frames, cfg)
        elif arrangement == "vertical":
            composed = MultiMonitorManager._compose_linear_stack(active_frames, cfg, vertical=True)
        else:
            composed = MultiMonitorManager._compose_linear_stack(active_frames, cfg, vertical=False)

        if composed is None or composed.isNull():
            return StitchResult(
                success=False,
                error_message="Çoklu monitör yerleşimi oluşturulurken bellek veya boyut hatası oluştu.",
            )

        if cfg.auto_crop:
            composed = MultiMonitorManager.auto_crop_empty_space(composed, cfg.background_color)

        elapsed = (time.perf_counter() - start_t) * 1000.0
        return StitchResult(
            success=True,
            image=composed,
            mode_used=cfg.mode.value,
            detector_used="desktop_coordinates",
            frames_count=len(active_frames),
            execution_time_ms=elapsed,
        )

    @staticmethod
    def _compose_by_physical_geometry(
        frames: List[PanoramaFrame],
        cfg: StitchConfig,
    ) -> QImage:
        """Place monitors according to their exact OS desktop coordinates with DPI normalization."""
        # Determine target pixel scale factor:
        # If normalize_dpi is enabled, scale logical coordinates by max monitor scale factor
        # so high-DPI monitors retain 100% of their native pixels.
        max_scale = 1.0
        if cfg.normalize_dpi:
            for f in frames:
                if f.monitor_info and f.monitor_info.scale_factor > max_scale:
                    max_scale = f.monitor_info.scale_factor
                elif f.logical_rect and f.logical_rect.width() > 0:
                    inferred = f.width / float(f.logical_rect.width())
                    if inferred > max_scale:
                        max_scale = inferred

        # Compute bounding box in target pixel space
        placements = []
        min_x = None
        min_y = None
        max_r = None
        max_b = None

        for f in frames:
            lrect = f.logical_rect or QRect(0, 0, f.width, f.height)
            if cfg.normalize_dpi:
                tx = int(round(lrect.x() * max_scale))
                ty = int(round(lrect.y() * max_scale))
                tw = int(round(lrect.width() * max_scale))
                th = int(round(lrect.height() * max_scale))
            else:
                tx = lrect.x()
                ty = lrect.y()
                tw = f.width
                th = f.height

            target_rect = QRect(tx, ty, max(1, tw), max(1, th))
            placements.append((f, target_rect))

            min_x = target_rect.left() if min_x is None else min(min_x, target_rect.left())
            min_y = target_rect.top() if min_y is None else min(min_y, target_rect.top())
            max_r = target_rect.right() if max_r is None else max(max_r, target_rect.right())
            max_b = target_rect.bottom() if max_b is None else max(max_b, target_rect.bottom())

        total_w = max(1, (max_r - min_x + 1))
        total_h = max(1, (max_b - min_y + 1))

        # Guard against extreme virtual desktop coordinates (>16384 px) to keep RAM usage safe
        max_dim = 16384
        downscale = 1.0
        if total_w > max_dim or total_h > max_dim:
            downscale = min(max_dim / float(total_w), max_dim / float(total_h))
            total_w = max(1, int(round(total_w * downscale)))
            total_h = max(1, int(round(total_h * downscale)))

        canvas = QImage(total_w, total_h, QImage.Format.Format_RGBA8888)
        bg = QColor(cfg.background_color) if QColor(cfg.background_color).isValid() else QColor(11, 15, 23)
        canvas.fill(bg)

        # Optional brightness harmonization across monitors
        processed_images = [f.image for f, _ in placements]
        if cfg.exposure_compensation and len(processed_images) > 1:
            processed_images = MultiMonitorManager._harmonize_monitor_brightness(processed_images)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        for idx, ((f, trect), src_img) in enumerate(zip(placements, processed_images)):
            dx = int(round((trect.x() - min_x) * downscale))
            dy = int(round((trect.y() - min_y) * downscale))
            dw = int(round(trect.width() * downscale))
            dh = int(round(trect.height() * downscale))
            dest_rect = QRect(dx, dy, max(1, dw), max(1, dh))
            painter.drawImage(dest_rect, src_img)

        painter.end()
        return canvas

    @staticmethod
    def _compose_linear_stack(
        frames: List[PanoramaFrame],
        cfg: StitchConfig,
        vertical: bool = False,
    ) -> QImage:
        """Arrange frames side-by-side (horizontal) or top-to-bottom (vertical) in their current order."""
        images = [f.image for f in frames]
        if cfg.exposure_compensation and len(images) > 1:
            images = MultiMonitorManager._harmonize_monitor_brightness(images)

        if not vertical:
            target_h = max(img.height() for img in images) if cfg.normalize_dpi else None
            scaled_list: List[QImage] = []
            for img in images:
                if target_h and img.height() != target_h and img.height() > 0:
                    new_w = max(1, int(round(img.width() * (target_h / float(img.height())))))
                    scaled_list.append(
                        img.scaled(new_w, target_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
                else:
                    scaled_list.append(img)

            total_w = sum(img.width() for img in scaled_list)
            max_h = max(img.height() for img in scaled_list)
            canvas = QImage(max(1, total_w), max(1, max_h), QImage.Format.Format_RGBA8888)
            bg = QColor(cfg.background_color) if QColor(cfg.background_color).isValid() else QColor(11, 15, 23)
            canvas.fill(bg)

            painter = QPainter(canvas)
            cur_x = 0
            for img in scaled_list:
                y_off = (max_h - img.height()) // 2
                painter.drawImage(cur_x, y_off, img)
                cur_x += img.width()
            painter.end()
            return canvas
        else:
            target_w = max(img.width() for img in images) if cfg.normalize_dpi else None
            scaled_list = []
            for img in images:
                if target_w and img.width() != target_w and img.width() > 0:
                    new_h = max(1, int(round(img.height() * (target_w / float(img.width())))))
                    scaled_list.append(
                        img.scaled(target_w, new_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    )
                else:
                    scaled_list.append(img)

            max_w = max(img.width() for img in scaled_list)
            total_h = sum(img.height() for img in scaled_list)
            canvas = QImage(max(1, max_w), max(1, total_h), QImage.Format.Format_RGBA8888)
            bg = QColor(cfg.background_color) if QColor(cfg.background_color).isValid() else QColor(11, 15, 23)
            canvas.fill(bg)

            painter = QPainter(canvas)
            cur_y = 0
            for img in scaled_list:
                x_off = (max_w - img.width()) // 2
                painter.drawImage(x_off, cur_y, img)
                cur_y += img.height()
            painter.end()
            return canvas

    @staticmethod
    def _harmonize_monitor_brightness(images: List[QImage]) -> List[QImage]:
        """Gently balance luminance differences across monitors using LAB L-channel gain clamping."""
        if len(images) <= 1:
            return images

        try:
            bgr_list = []
            mean_lum = []
            for qimg in images:
                arr = MultiMonitorManager.qimage_to_bgr(qimg)
                bgr_list.append(arr)
                lab = cv2.cvtColor(arr, cv2.COLOR_BGR2LAB)
                l_val = float(np.mean(lab[:, :, 0]))
                mean_lum.append(max(1.0, l_val))

            target_lum = float(np.median(mean_lum))
            balanced: List[QImage] = []
            for arr, lum in zip(bgr_list, mean_lum):
                gain = np.clip(target_lum / lum, 0.88, 1.14)
                if abs(gain - 1.0) < 0.02:
                    balanced.append(MultiMonitorManager.bgr_to_qimage(arr))
                else:
                    lab = cv2.cvtColor(arr, cv2.COLOR_BGR2LAB).astype(np.float32)
                    lab[:, :, 0] = np.clip(lab[:, :, 0] * gain, 0, 255)
                    out_bgr = cv2.cvtColor(lab.astype(np.uint8), cv2.COLOR_LAB2BGR)
                    balanced.append(MultiMonitorManager.bgr_to_qimage(out_bgr))
            return balanced
        except Exception as exc:
            logger.debug("Brightness harmonization skipped: %s", exc)
            return images

    @staticmethod
    def auto_crop_empty_space(image: QImage, background_hex: str = "#0B0F17") -> QImage:
        """Trim outer uniform background borders from a composed panorama."""
        if image.isNull() or image.width() < 8 or image.height() < 8:
            return image

        try:
            bgr = MultiMonitorManager.qimage_to_bgr(image)
            bg_col = QColor(background_hex) if QColor(background_hex).isValid() else QColor(11, 15, 23)
            target_bgr = np.array([bg_col.blue(), bg_col.green(), bg_col.red()], dtype=np.int16)

            diff = np.max(np.abs(bgr.astype(np.int16) - target_bgr), axis=2)
            non_empty = diff > 4
            if not np.any(non_empty):
                return image

            ys, xs = np.where(non_empty)
            x0, x1 = int(np.min(xs)), int(np.max(xs))
            y0, y1 = int(np.min(ys)), int(np.max(ys))
            crop_rect = QRect(x0, y0, max(1, x1 - x0 + 1), max(1, y1 - y0 + 1))
            if crop_rect.width() == image.width() and crop_rect.height() == image.height():
                return image
            return image.copy(crop_rect)
        except Exception as exc:
            logger.debug("Auto crop empty space skipped: %s", exc)
            return image

    @staticmethod
    def qimage_to_bgr(image: QImage) -> np.ndarray:
        """Convert QImage to contiguous OpenCV BGR uint8 numpy array."""
        conv = image.convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = conv.width(), conv.height()
        ptr = conv.constBits()
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, conv.bytesPerLine() // 4, 4))[:, :w, :]
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)

    @staticmethod
    def bgr_to_qimage(bgr: np.ndarray) -> QImage:
        """Convert OpenCV BGR uint8 numpy array to standalone QImage."""
        rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
        h, w, _ = rgba.shape
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        return qimg.copy()

    @staticmethod
    def _draw_cursor_on_image(image: QImage, pos: QPoint) -> None:
        """Draw a clean vector cursor pointer onto a QImage at physical pixel coordinates."""
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        poly = QPolygon([
            pos,
            pos + QPoint(0, 18),
            pos + QPoint(5, 14),
            pos + QPoint(9, 22),
            pos + QPoint(12, 20),
            pos + QPoint(8, 13),
            pos + QPoint(14, 13),
        ])
        painter.setPen(Qt.GlobalColor.black)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawPolygon(poly)
        painter.end()


