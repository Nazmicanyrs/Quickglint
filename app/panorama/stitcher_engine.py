"""OpenCV-based Panorama Stitching Engine with ORB/SIFT feature matching, exposure compensation, and multi-band blending."""

import gc
import time
from typing import Callable, List, Optional, Sequence, Tuple
import cv2
import numpy as np
from PySide6.QtCore import QRect, QThread, Signal
from PySide6.QtGui import QImage

from app.panorama.models import (
    AlignmentMode,
    BlendingMode,
    FeatureDetectorType,
    PairMatchInfo,
    PanoramaCaptureMode,
    PanoramaFrame,
    StitchConfig,
    StitchResult,
)
from app.panorama.monitor_manager import MultiMonitorManager
from app.utils.logger import logger


class PanoramaStitcherEngine:
    """
    Production-grade Panorama Stitching Engine supporting both:
    1. Coordinate-accurate Multi-Monitor Desktop composition (without redundant feature matching when non-overlapping).
    2. OpenCV Feature-Based Panorama Stitching (ORB / SIFT + RANSAC Homography/Affine + Exposure Compensation + Multi-Band/Feather Blending + Auto Crop).
    """

    MAX_CANVAS_DIMENSION = 14000  # Safety cap to prevent out-of-memory on multi-4K warps

    def __init__(self, config: Optional[StitchConfig] = None) -> None:
        self.config = config or StitchConfig()
        self._cancel_requested = False

    def cancel(self) -> None:
        """Request cooperative cancellation of an active stitching job."""
        self._cancel_requested = True

    def stitch(
        self,
        frames: Sequence[PanoramaFrame],
        config: Optional[StitchConfig] = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> StitchResult:
        """
        Execute panorama composition or feature stitching according to config and frame metadata.
        """
        self._cancel_requested = False
        cfg = config or self.config
        start_t = time.perf_counter()

        def _report(pct: int, msg: str) -> None:
            if progress_callback is not None:
                try:
                    progress_callback(pct, msg)
                except Exception:
                    pass

        active_frames = [f for f in frames if f.enabled and f.image is not None and not f.image.isNull()]
        if not active_frames:
            return StitchResult(
                success=False,
                error_message="Birleştirilecek geçerli görüntü bulunamadı.",
            )

        _report(5, "Görüntüler analiz ediliyor...")

        if len(active_frames) == 1:
            elapsed = (time.perf_counter() - start_t) * 1000.0
            _report(100, "Tamamlandı.")
            return StitchResult(
                success=True,
                image=active_frames[0].image.copy(),
                mode_used=cfg.mode.value,
                detector_used="single_frame",
                frames_count=1,
                execution_time_ms=elapsed,
            )

        # CRITICAL ARCHITECTURAL RULE:
        # When capturing physical monitors simultaneously (FULL_DESKTOP, SELECTED_MONITOR, CUSTOM_LAYOUT)
        # or when alignment is explicitly DESKTOP_COORDS, and monitors do not overlap physically,
        # place them directly using real desktop coordinates without unnecessary feature matching.
        all_have_monitor_coords = all(
            f.logical_rect is not None and not f.logical_rect.isEmpty() for f in active_frames
        )
        is_monitor_capture_mode = cfg.mode in (
            PanoramaCaptureMode.FULL_DESKTOP,
            PanoramaCaptureMode.SELECTED_MONITOR,
            PanoramaCaptureMode.CUSTOM_LAYOUT,
        ) or cfg.alignment == AlignmentMode.DESKTOP_COORDS

        if is_monitor_capture_coords := (
            is_monitor_capture_mode
            and (all_have_monitor_coords or cfg.layout_arrangement in ("horizontal", "vertical"))
            and not MultiMonitorManager.monitors_have_physical_overlap(active_frames)
        ):
            _report(40, "Monitörler gerçek masaüstü koordinatlarına göre yerleştiriliyor...")
            res = MultiMonitorManager.compose_desktop_layout(active_frames, cfg)
            _report(100, "Çoklu monitör panoraması hazır.")
            return res

        # Otherwise perform OpenCV Feature-Based Panorama Stitching (Manual Stitching or overlapping frames)
        return self._stitch_feature_based(active_frames, cfg, start_t, _report)

    def _stitch_feature_based(
        self,
        frames: List[PanoramaFrame],
        cfg: StitchConfig,
        start_t: float,
        report: Callable[[int, str], None],
    ) -> StitchResult:
        """Incremental pairwise OpenCV feature matching, warping, exposure compensation, and blending."""
        warnings: List[str] = []
        pair_matches: List[PairMatchInfo] = []

        detector_name = self._resolve_detector_name(cfg.detector)
        report(10, f"OpenCV {detector_name.upper()} özellik çıkarıcı hazırlanıyor...")

        try:
            # Convert first frame to BGR and create initial validity mask
            base_bgr = MultiMonitorManager.qimage_to_bgr(frames[0].image)
            base_mask = np.full((base_bgr.shape[0], base_bgr.shape[1]), 255, dtype=np.uint8)

            total_pairs = len(frames) - 1
            for idx in range(1, len(frames)):
                if self._cancel_requested:
                    return StitchResult(success=False, error_message="İşlem kullanıcı tarafından iptal edildi.")

                pct_base = 15 + int(((idx - 1) / max(1, total_pairs)) * 70)
                report(pct_base, f"Görüntü {idx}/{total_pairs} eşleştiriliyor ({detector_name.upper()})...")

                next_bgr = MultiMonitorManager.qimage_to_bgr(frames[idx].image)
                next_mask = np.full((next_bgr.shape[0], next_bgr.shape[1]), 255, dtype=np.uint8)

                H, match_info = self._estimate_transform(
                    base_bgr,
                    next_bgr,
                    frame_a_idx=idx - 1,
                    frame_b_idx=idx,
                    detector_name=detector_name,
                    cfg=cfg,
                )
                pair_matches.append(match_info)

                if match_info.used_fallback:
                    warnings.append(
                        f"Kare {idx} ve {idx + 1} arasında yeterli ortak doku bulunamadı; "
                        "kenar hizalama yedek modu kullanıldı."
                    )

                if self._cancel_requested:
                    return StitchResult(success=False, error_message="İşlem kullanıcı tarafından iptal edildi.")

                report(pct_base + 20 // max(1, total_pairs), f"Görüntü {idx + 1} hizalanıyor ve harmanlanıyor...")
                base_bgr, base_mask = self._warp_and_blend_pair(
                    base_bgr,
                    base_mask,
                    next_bgr,
                    next_mask,
                    H,
                    cfg,
                )

                # Release per-iteration intermediates
                del next_bgr
                del next_mask

            if self._cancel_requested:
                return StitchResult(success=False, error_message="İşlem kullanıcı tarafından iptal edildi.")

            if cfg.auto_crop:
                report(90, "Otomatik kırpma ve kenar temizleme uygulanıyor...")
                base_bgr = self.auto_crop_black_borders(base_bgr, base_mask)

            out_qimg = MultiMonitorManager.bgr_to_qimage(base_bgr)
            del base_bgr
            del base_mask
            gc.collect()

            elapsed = (time.perf_counter() - start_t) * 1000.0
            report(100, "Panorama birleştirme tamamlandı.")

            return StitchResult(
                success=True,
                image=out_qimg,
                mode_used=cfg.mode.value,
                detector_used=detector_name,
                frames_count=len(frames),
                execution_time_ms=elapsed,
                pair_matches=pair_matches,
                warnings=warnings,
            )

        except MemoryError:
            gc.collect()
            logger.error("Out of memory during panorama stitching.")
            return StitchResult(
                success=False,
                error_message="Bellek yetersizliği: Görüntüler çok büyük. Lütfen daha az görüntü seçin.",
            )
        except Exception as exc:
            logger.error("Panorama stitching failed: %s", exc, exc_info=True)
            return StitchResult(
                success=False,
                error_message=f"Panorama birleştirme sırasında hata oluştu: {exc}",
            )

    @staticmethod
    def _resolve_detector_name(detector_type: FeatureDetectorType) -> str:
        """Select SIFT or ORB based on config and OpenCV build availability."""
        if detector_type == FeatureDetectorType.SIFT:
            if hasattr(cv2, "SIFT_create"):
                return "sift"
            return "orb"
        if detector_type == FeatureDetectorType.AUTO:
            if hasattr(cv2, "SIFT_create"):
                return "sift"
            return "orb"
        return "orb"

    def _create_detector(self, detector_name: str, max_features: int):
        if detector_name == "sift" and hasattr(cv2, "SIFT_create"):
            return cv2.SIFT_create(nfeatures=max_features)
        return cv2.ORB_create(nfeatures=max_features, scaleFactor=1.2, nlevels=8)

    def _estimate_transform(
        self,
        img_ref: np.ndarray,
        img_new: np.ndarray,
        frame_a_idx: int,
        frame_b_idx: int,
        detector_name: str,
        cfg: StitchConfig,
    ) -> Tuple[np.ndarray, PairMatchInfo]:
        """
        Detect keypoints/descriptors in img_ref and img_new, match them using KNN + Lowe's ratio test,
        and estimate a 3x3 transformation matrix mapping img_new coordinates into img_ref space.
        """
        info = PairMatchInfo(frame_a_index=frame_a_idx, frame_b_index=frame_b_idx)

        # Downscale for feature extraction if images are very large (>2000px) to save RAM & time
        max_feat_dim = 1800
        h1, w1 = img_ref.shape[:2]
        h2, w2 = img_new.shape[:2]
        s1 = min(1.0, max_feat_dim / float(max(h1, w1)))
        s2 = min(1.0, max_feat_dim / float(max(h2, w2)))

        gray_ref = cv2.cvtColor(img_ref, cv2.COLOR_BGR2GRAY)
        gray_new = cv2.cvtColor(img_new, cv2.COLOR_BGR2GRAY)

        if s1 < 1.0:
            gray_ref_small = cv2.resize(gray_ref, (max(1, int(w1 * s1)), max(1, int(h1 * s1))), interpolation=cv2.INTER_AREA)
        else:
            gray_ref_small = gray_ref

        if s2 < 1.0:
            gray_new_small = cv2.resize(gray_new, (max(1, int(w2 * s2)), max(1, int(h2 * s2))), interpolation=cv2.INTER_AREA)
        else:
            gray_new_small = gray_new

        detector = self._create_detector(detector_name, cfg.max_features)
        kp_ref, des_ref = detector.detectAndCompute(gray_ref_small, None)
        kp_new, des_new = detector.detectAndCompute(gray_new_small, None)

        info.keypoints_a = len(kp_ref) if kp_ref is not None else 0
        info.keypoints_b = len(kp_new) if kp_new is not None else 0

        if des_ref is not None and des_new is not None and len(kp_ref) >= 6 and len(kp_new) >= 6:
            norm_type = cv2.NORM_L2 if detector_name == "sift" else cv2.NORM_HAMMING
            matcher = cv2.BFMatcher(norm_type, crossCheck=False)
            raw_matches = matcher.knnMatch(des_new, des_ref, k=2)

            ratio_thresh = 0.75 if detector_name == "sift" else 0.78
            good = []
            for m_pair in raw_matches:
                if len(m_pair) == 2:
                    m, n = m_pair
                    if m.distance < ratio_thresh * n.distance:
                        good.append(m)

            info.good_matches = len(good)

            if len(good) >= 8:
                pts_new = np.float32([kp_new[m.queryIdx].pt for m in good]).reshape(-1, 1, 2) / s2
                pts_ref = np.float32([kp_ref[m.trainIdx].pt for m in good]).reshape(-1, 1, 2) / s1

                H = self._compute_validated_matrix(pts_new, pts_ref, w2, h2, w1, h1, cfg, info)
                if H is not None:
                    return H, info

        # Fallback 1: Translational template/strip matching for overlapping screen captures
        H_trans, overlap = self._estimate_translation_overlap(gray_ref, gray_new)
        if H_trans is not None:
            info.overlap_ratio = overlap
            info.inliers = max(info.inliers, 12)
            return H_trans, info

        # Fallback 2: Place side-by-side (or top-to-bottom if vertical layout selected)
        info.used_fallback = True
        if cfg.layout_arrangement == "vertical":
            H_fallback = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, float(h1)], [0.0, 0.0, 1.0]], dtype=np.float64)
        else:
            H_fallback = np.array([[1.0, 0.0, float(w1)], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        return H_fallback, info

    def _compute_validated_matrix(
        self,
        pts_new: np.ndarray,
        pts_ref: np.ndarray,
        w_new: int,
        h_new: int,
        w_ref: int,
        h_ref: int,
        cfg: StitchConfig,
        info: PairMatchInfo,
    ) -> Optional[np.ndarray]:
        """Compute Homography or Affine matrix and validate against degenerate perspective warps."""
        reproj = max(1.0, float(cfg.ransac_reproj_threshold))

        if cfg.alignment == AlignmentMode.TRANSLATION:
            diffs = (pts_ref - pts_new).reshape(-1, 2)
            med_dx = float(np.median(diffs[:, 0]))
            med_dy = float(np.median(diffs[:, 1]))
            dists = np.hypot(diffs[:, 0] - med_dx, diffs[:, 1] - med_dy)
            inliers = int(np.sum(dists <= reproj * 2.0))
            if inliers >= 6:
                info.inliers = inliers
                return np.array([[1.0, 0.0, med_dx], [0.0, 1.0, med_dy], [0.0, 0.0, 1.0]], dtype=np.float64)

        if cfg.alignment in (AlignmentMode.HOMOGRAPHY, AlignmentMode.DESKTOP_COORDS):
            H, mask = cv2.findHomography(pts_new, pts_ref, cv2.RANSAC, reproj)
            if H is not None and mask is not None:
                inliers = int(np.sum(mask))
                if inliers >= 8 and self._is_homography_sane(H, w_new, h_new, w_ref, h_ref):
                    info.inliers = inliers
                    info.overlap_ratio = round(inliers / float(max(1, len(pts_new))), 3)
                    return H

        # Try partial affine (rotation + uniform scale + translation) which is rock-solid on 2D UI/screen captures
        M_aff, mask_aff = cv2.estimateAffinePartial2D(pts_new, pts_ref, method=cv2.RANSAC, ransacReprojThreshold=reproj)
        if M_aff is not None and mask_aff is not None:
            inliers = int(np.sum(mask_aff))
            if inliers >= 6:
                scale = float(np.hypot(M_aff[0, 0], M_aff[1, 0]))
                if 0.5 <= scale <= 2.0:
                    H_aff = np.vstack([M_aff, [0.0, 0.0, 1.0]]).astype(np.float64)
                    info.inliers = inliers
                    info.overlap_ratio = round(inliers / float(max(1, len(pts_new))), 3)
                    return H_aff

        return None

    @staticmethod
    def _is_homography_sane(H: np.ndarray, w_new: int, h_new: int, w_ref: int, h_ref: int) -> bool:
        """Check that a 3x3 homography does not invert, collapse, or wildly explode image corners."""
        if not np.all(np.isfinite(H)) or abs(H[2, 2]) < 1e-9:
            return False
        H_norm = H / H[2, 2]

        # Reject extreme projective skew
        if abs(H_norm[2, 0]) > 2.5e-3 or abs(H_norm[2, 1]) > 2.5e-3:
            return False

        det = float(np.linalg.det(H_norm[:2, :2]))
        if det < 0.25 or det > 4.0:
            return False

        corners = np.float32([[0, 0], [w_new, 0], [w_new, h_new], [0, h_new]]).reshape(-1, 1, 2)
        warped = cv2.perspectiveTransform(corners, H_norm).reshape(4, 2)
        min_x, min_y = np.min(warped, axis=0)
        max_x, max_y = np.max(warped, axis=0)
        span_w = max_x - min_x
        span_h = max_y - min_y

        if span_w < w_new * 0.35 or span_w > w_new * 3.0:
            return False
        if span_h < h_new * 0.35 or span_h > h_new * 3.0:
            return False

        # Ensure warped polygon remains convex and properly oriented
        if not cv2.isContourConvex(warped.astype(np.float32)):
            return False

        return True

    @staticmethod
    def _estimate_translation_overlap(
        gray_ref: np.ndarray,
        gray_new: np.ndarray,
    ) -> Tuple[Optional[np.ndarray], float]:
        """
        Estimate horizontal or vertical translational overlap using normalized cross-correlation
        on edge strips when feature keypoints are sparse (e.g. clean UI panels).
        """
        h1, w1 = gray_ref.shape[:2]
        h2, w2 = gray_new.shape[:2]

        # 1. Check horizontal overlap (left edge of gray_new matching inside right half of gray_ref)
        if abs(h1 - h2) <= max(h1, h2) * 0.25 and w1 >= 64 and w2 >= 64:
            common_h = min(h1, h2)
            strip_w = max(24, min(96, w2 // 5))
            template = gray_new[:common_h, :strip_w]
            if float(np.std(template)) > 3.5:
                search_x0 = max(0, w1 // 4)
                search_region = gray_ref[:common_h, search_x0:]
                if search_region.shape[1] >= strip_w:
                    res = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val >= 0.78:
                        dx = float(search_x0 + max_loc[0])
                        dy = float(max_loc[1])
                        overlap_ratio = round(max(0.0, (w1 - dx) / float(w2)), 3)
                        H = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]], dtype=np.float64)
                        return H, overlap_ratio

        # 2. Check vertical overlap (top edge of gray_new matching inside bottom half of gray_ref)
        if abs(w1 - w2) <= max(w1, w2) * 0.25 and h1 >= 64 and h2 >= 64:
            common_w = min(w1, w2)
            strip_h = max(24, min(96, h2 // 5))
            template = gray_new[:strip_h, :common_w]
            if float(np.std(template)) > 3.5:
                search_y0 = max(0, h1 // 4)
                search_region = gray_ref[search_y0:, :common_w]
                if search_region.shape[0] >= strip_h:
                    res = cv2.matchTemplate(search_region, template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    if max_val >= 0.78:
                        dx = float(max_loc[0])
                        dy = float(search_y0 + max_loc[1])
                        overlap_ratio = round(max(0.0, (h1 - dy) / float(h2)), 3)
                        H = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]], dtype=np.float64)
                        return H, overlap_ratio

        return None, 0.0

    def _warp_and_blend_pair(
        self,
        base_bgr: np.ndarray,
        base_mask: np.ndarray,
        new_bgr: np.ndarray,
        new_mask: np.ndarray,
        H: np.ndarray,
        cfg: StitchConfig,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Warp `new_bgr` into `base_bgr` coordinate space using `H`, apply exposure compensation
        in the overlap zone, and blend seams using Multi-Band or Feather blending.
        """
        h_base, w_base = base_bgr.shape[:2]
        h_new, w_new = new_bgr.shape[:2]

        corners_base = np.float32([[0, 0], [w_base, 0], [w_base, h_base], [0, h_base]]).reshape(-1, 1, 2)
        corners_new = np.float32([[0, 0], [w_new, 0], [w_new, h_new], [0, h_new]]).reshape(-1, 1, 2)
        warped_corners_new = cv2.perspectiveTransform(corners_new, H)

        all_corners = np.concatenate((corners_base, warped_corners_new), axis=0)
        [xmin, ymin] = np.int32(np.floor(all_corners.min(axis=0).ravel()))
        [xmax, ymax] = np.int32(np.ceil(all_corners.max(axis=0).ravel()))

        out_w = max(1, int(xmax - xmin))
        out_h = max(1, int(ymax - ymin))

        # Safety cap against runaway canvas dimensions
        scale_guard = 1.0
        if out_w > self.MAX_CANVAS_DIMENSION or out_h > self.MAX_CANVAS_DIMENSION:
            scale_guard = min(self.MAX_CANVAS_DIMENSION / float(out_w), self.MAX_CANVAS_DIMENSION / float(out_h))
            out_w = max(1, int(round(out_w * scale_guard)))
            out_h = max(1, int(round(out_h * scale_guard)))

        tx = -xmin
        ty = -ymin
        T = np.array(
            [
                [scale_guard, 0.0, tx * scale_guard],
                [0.0, scale_guard, ty * scale_guard],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )

        # Place base image into expanded canvas
        canvas_base = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        canvas_base_mask = np.zeros((out_h, out_w), dtype=np.uint8)

        if abs(scale_guard - 1.0) < 1e-6:
            y0, x0 = int(ty), int(tx)
            canvas_base[y0 : y0 + h_base, x0 : x0 + w_base] = base_bgr
            canvas_base_mask[y0 : y0 + h_base, x0 : x0 + w_base] = base_mask
        else:
            canvas_base = cv2.warpPerspective(base_bgr, T, (out_w, out_h), flags=cv2.INTER_LINEAR)
            canvas_base_mask = cv2.warpPerspective(base_mask, T, (out_w, out_h), flags=cv2.INTER_NEAREST)

        # Warp new image & mask
        H_total = T @ H
        warped_new = cv2.warpPerspective(
            new_bgr,
            H_total,
            (out_w, out_h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )
        warped_new_mask = cv2.warpPerspective(
            new_mask,
            H_total,
            (out_w, out_h),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )

        # Exposure / Color compensation in overlapping region
        overlap_mask = (canvas_base_mask > 127) & (warped_new_mask > 127)
        if cfg.exposure_compensation and np.any(overlap_mask):
            warped_new = self._compensate_exposure(canvas_base, warped_new, overlap_mask, warped_new_mask > 0)

        # Blend according to configured BlendingMode
        combined_mask = np.where((canvas_base_mask > 0) | (warped_new_mask > 0), 255, 0).astype(np.uint8)

        if not np.any(overlap_mask) or cfg.blending == BlendingMode.NONE:
            out_bgr = canvas_base.copy()
            new_only = warped_new_mask > 127
            out_bgr[new_only] = warped_new[new_only]
            return out_bgr, combined_mask

        if cfg.blending == BlendingMode.MULTIBAND:
            out_bgr = self._multiband_blend(
                canvas_base,
                canvas_base_mask,
                warped_new,
                warped_new_mask,
                levels=max(2, min(6, cfg.multiband_levels)),
            )
        else:
            out_bgr = self._feather_blend(
                canvas_base,
                canvas_base_mask,
                warped_new,
                warped_new_mask,
            )

        return out_bgr, combined_mask

    @staticmethod
    def _compensate_exposure(
        img_ref: np.ndarray,
        img_new: np.ndarray,
        overlap_mask: np.ndarray,
        valid_new_mask: np.ndarray,
    ) -> np.ndarray:
        """Match mean channel brightness and color balance of `img_new` to `img_ref` using the overlap region."""
        overlap_count = int(np.count_nonzero(overlap_mask))
        if overlap_count < 64:
            return img_new

        ref_pixels = img_ref[overlap_mask].astype(np.float32)
        new_pixels = img_new[overlap_mask].astype(np.float32)

        ref_means = np.mean(ref_pixels, axis=0)
        new_means = np.maximum(1.0, np.mean(new_pixels, axis=0))

        gains = np.clip(ref_means / new_means, 0.80, 1.25)
        if np.all(np.abs(gains - 1.0) < 0.015):
            return img_new

        adjusted = img_new.astype(np.float32)
        adjusted[valid_new_mask] = np.clip(adjusted[valid_new_mask] * gains, 0, 255)
        return adjusted.astype(np.uint8)

    @staticmethod
    def _compute_distance_weight(mask_a: np.ndarray, mask_b: np.ndarray) -> np.ndarray:
        """Compute smooth [0..1] blending weight for image A using Euclidean distance transforms."""
        bin_a = (mask_a > 127).astype(np.uint8)
        bin_b = (mask_b > 127).astype(np.uint8)

        dist_a = cv2.distanceTransform(bin_a, cv2.DIST_L2, 3)
        dist_b = cv2.distanceTransform(bin_b, cv2.DIST_L2, 3)

        denom = dist_a + dist_b
        weight_a = np.where(denom > 1e-5, dist_a / np.maximum(denom, 1e-5), bin_a.astype(np.float32))
        weight_a = np.where(bin_a & ~bin_b.astype(bool), 1.0, weight_a)
        weight_a = np.where(bin_b & ~bin_a.astype(bool), 0.0, weight_a)
        return weight_a.astype(np.float32)

    @classmethod
    def _feather_blend(
        cls,
        img_a: np.ndarray,
        mask_a: np.ndarray,
        img_b: np.ndarray,
        mask_b: np.ndarray,
    ) -> np.ndarray:
        """Linear distance-transform feather blending in the overlap zone."""
        w_a = cls._compute_distance_weight(mask_a, mask_b)[:, :, np.newaxis]
        blended = img_a.astype(np.float32) * w_a + img_b.astype(np.float32) * (1.0 - w_a)
        return np.clip(blended, 0, 255).astype(np.uint8)

    @classmethod
    def _multiband_blend(
        cls,
        img_a: np.ndarray,
        mask_a: np.ndarray,
        img_b: np.ndarray,
        mask_b: np.ndarray,
        levels: int = 4,
    ) -> np.ndarray:
        """
        Laplacian Pyramid Multi-Band Blending focused on the overlap bounding box
        for seamless transition with low memory footprint.
        """
        overlap = (mask_a > 127) & (mask_b > 127)
        if not np.any(overlap):
            return cls._feather_blend(img_a, mask_a, img_b, mask_b)

        # Start with feather blend outside the padded overlap ROI to save RAM on huge canvases
        out = img_a.copy()
        only_b = (mask_b > 127) & ~(mask_a > 127)
        out[only_b] = img_b[only_b]

        ys, xs = np.where(overlap)
        pad = 64
        h, w = img_a.shape[:2]
        y0 = max(0, int(np.min(ys)) - pad)
        y1 = min(h, int(np.max(ys)) + pad + 1)
        x0 = max(0, int(np.min(xs)) - pad)
        x1 = min(w, int(np.max(xs)) + pad + 1)

        roi_h = y1 - y0
        roi_w = x1 - x0
        if roi_h < 32 or roi_w < 32:
            return cls._feather_blend(img_a, mask_a, img_b, mask_b)

        sub_a = img_a[y0:y1, x0:x1].astype(np.float32)
        sub_b = img_b[y0:y1, x0:x1].astype(np.float32)
        sub_ma = mask_a[y0:y1, x0:x1]
        sub_mb = mask_b[y0:y1, x0:x1]

        # Replace black unmapped pixels inside ROI with neighbor image so pyramid downsampling doesn't bleed black
        invalid_a = sub_ma <= 127
        invalid_b = sub_mb <= 127
        sub_a_filled = np.where(invalid_a[:, :, None], sub_b, sub_a)
        sub_b_filled = np.where(invalid_b[:, :, None], sub_a, sub_b)

        weight = cls._compute_distance_weight(sub_ma, sub_mb)[:, :, np.newaxis]

        # Build Gaussian pyramids for A, B, and weight
        gp_a = [sub_a_filled]
        gp_b = [sub_b_filled]
        gp_w = [weight]

        actual_levels = 1
        for _ in range(levels):
            if gp_a[-1].shape[0] < 16 or gp_a[-1].shape[1] < 16:
                break
            gp_a.append(cv2.pyrDown(gp_a[-1]))
            gp_b.append(cv2.pyrDown(gp_b[-1]))
            down_w = cv2.pyrDown(gp_w[-1])
            if down_w.ndim == 2:
                down_w = down_w[:, :, np.newaxis]
            gp_w.append(down_w)
            actual_levels += 1

        # Build Laplacian pyramids for A and B
        lp_a = [gp_a[-1]]
        lp_b = [gp_b[-1]]
        for i in range(actual_levels - 1, 0, -1):
            size = (gp_a[i - 1].shape[1], gp_a[i - 1].shape[0])
            up_a = cv2.pyrUp(gp_a[i], dstsize=size)
            up_b = cv2.pyrUp(gp_b[i], dstsize=size)
            lp_a.append(gp_a[i - 1] - up_a)
            lp_b.append(gp_b[i - 1] - up_b)

        # Blend each pyramid level
        lp_blended = []
        for la, lb, gw in zip(lp_a, lp_b, reversed(gp_w)):
            if gw.ndim == 2:
                gw = gw[:, :, np.newaxis]
            lp_blended.append(la * gw + lb * (1.0 - gw))

        # Reconstruct from coarsest to finest
        reconstructed = lp_blended[0]
        for i in range(1, len(lp_blended)):
            size = (lp_blended[i].shape[1], lp_blended[i].shape[0])
            reconstructed = cv2.pyrUp(reconstructed, dstsize=size) + lp_blended[i]

        valid_union = (sub_ma > 127) | (sub_mb > 127)
        roi_out = out[y0:y1, x0:x1]
        clipped = np.clip(reconstructed, 0, 255).astype(np.uint8)
        roi_out[valid_union] = clipped[valid_union]
        out[y0:y1, x0:x1] = roi_out
        return out

    @staticmethod
    def auto_crop_black_borders(bgr: np.ndarray, valid_mask: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Automatically crop outer empty space and perspective black wedges from a stitched panorama.
        """
        if bgr is None or bgr.size == 0:
            return bgr

        h, w = bgr.shape[:2]
        if h < 12 or w < 12:
            return bgr

        if valid_mask is None:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            valid = (gray > 2).astype(np.uint8) * 255
        else:
            valid = (valid_mask > 127).astype(np.uint8) * 255

        if not np.any(valid):
            return bgr

        # Step 1: Tight bounding box of valid pixels
        ys, xs = np.where(valid > 0)
        y0, y1 = int(np.min(ys)), int(np.max(ys)) + 1
        x0, x1 = int(np.min(xs)), int(np.max(xs)) + 1
        bgr = bgr[y0:y1, x0:x1]
        valid = valid[y0:y1, x0:x1]

        # Step 2: Iteratively shave edge rows/columns that have >4% invalid pixels due to slight tilt
        ch, cw = valid.shape[:2]
        top, bottom, left, right = 0, ch, 0, cw
        max_trim_y = int(ch * 0.12)
        max_trim_x = int(cw * 0.12)

        while top < max_trim_y and np.mean(valid[top, left:right] > 0) < 0.97:
            top += 1
        while (ch - bottom) < max_trim_y and bottom > top + 16 and np.mean(valid[bottom - 1, left:right] > 0) < 0.97:
            bottom -= 1
        while left < max_trim_x and np.mean(valid[top:bottom, left] > 0) < 0.97:
            left += 1
        while (cw - right) < max_trim_x and right > left + 16 and np.mean(valid[top:bottom, right - 1] > 0) < 0.97:
            right -= 1

        if bottom - top >= 16 and right - left >= 16:
            return bgr[top:bottom, left:right].copy()
        return bgr


class PanoramaStitchWorker(QThread):
    """Background worker thread for responsive UI during multi-megapixel panorama stitching."""

    progress_changed = Signal(int, str)
    stitch_finished = Signal(object)  # StitchResult

    def __init__(
        self,
        frames: Sequence[PanoramaFrame],
        config: StitchConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.frames = list(frames)
        self.config = config
        self.engine = PanoramaStitcherEngine(config)

    def cancel(self) -> None:
        """Cancel background stitching safely."""
        self.engine.cancel()

    def run(self) -> None:
        result = self.engine.stitch(
            self.frames,
            config=self.config,
            progress_callback=lambda pct, msg: self.progress_changed.emit(pct, msg),
        )
        self.stitch_finished.emit(result)


