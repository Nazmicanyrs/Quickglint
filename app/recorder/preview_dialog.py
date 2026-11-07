"""Interactive GIF preview editor, timeline trimmer, and background export dialog."""

from pathlib import Path
from typing import List, Optional
from PySide6.QtCore import QPoint, QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.recorder.cursor import CursorRenderer
from app.recorder.frame import RecordedFrame
from app.recorder.gif_encoder import GifEncodingWorker
from app.services.storage_service import StorageService
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.i18n import tr
from app.utils.logger import logger


class GifPreviewDialog(QDialog):
    """Interactive editor for reviewing, trimming, and exporting recorded GIF frames."""

    gif_saved = Signal(str)

    def __init__(
        self,
        frames: List[RecordedFrame],
        initial_fps: int = 15,
        default_save_dir: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.raw_frames = list(frames)
        self.active_frames = list(frames)
        self.fps = initial_fps
        self.default_save_dir = default_save_dir

        self.current_frame_idx = 0
        self.is_playing = False

        self.setWindowTitle("Quickglint — GIF Editör ve Dışa Aktarma")
        self.setMinimumSize(800, 640)
        self.setStyleSheet(DARK_THEME_QSS)

        # Playback timer
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(int(1000 / max(1, self.fps)))
        self.play_timer.timeout.connect(self._on_play_tick)

        self._setup_ui()
        self._update_display_frame()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # 1. Main Video/Frame Preview Viewport
        self.preview_frame = QFrame(self)
        self.preview_frame.setStyleSheet(
            "background-color: #0F172A; border: 1px solid #334155; border-radius: 8px;"
        )
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_label = QLabel(self.preview_frame)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(480, 280)
        preview_layout.addWidget(self.preview_label)
        main_layout.addWidget(self.preview_frame, stretch=1)

        # 2. Timeline & Transport Controls
        timeline_card = QFrame(self)
        timeline_card.setStyleSheet(
            "background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 8px;"
        )
        timeline_layout = QVBoxLayout(timeline_card)
        timeline_layout.setSpacing(8)

        # Scrubber Slider + Time
        scrub_row = QHBoxLayout()
        self.time_lbl = QLabel("0.0s / 0.0s", timeline_card)
        self.time_lbl.setStyleSheet("color: #63B3ED; font-size: 11px; font-weight: bold;")
        self.frame_num_lbl = QLabel(f"Kare: 1 / {len(self.active_frames)}", timeline_card)
        self.frame_num_lbl.setStyleSheet("color: #CBD5E1; font-size: 11px;")

        self.timeline_slider = QSlider(Qt.Orientation.Horizontal, timeline_card)
        self.timeline_slider.setRange(0, max(0, len(self.active_frames) - 1))
        self.timeline_slider.valueChanged.connect(self._on_slider_moved)

        scrub_row.addWidget(self.time_lbl)
        scrub_row.addWidget(self.timeline_slider, stretch=1)
        scrub_row.addWidget(self.frame_num_lbl)
        timeline_layout.addLayout(scrub_row)

        # Transport Buttons
        controls_row = QHBoxLayout()
        self.play_btn = QPushButton("▶ Oynat", timeline_card)
        self.play_btn.setFixedSize(80, 28)
        self.play_btn.clicked.connect(self._toggle_playback)

        self.prev_btn = QPushButton("⏮ Önceki", timeline_card)
        self.prev_btn.setFixedSize(70, 28)
        self.prev_btn.clicked.connect(self._step_prev)

        self.next_btn = QPushButton("Sonraki ⏭", timeline_card)
        self.next_btn.setFixedSize(70, 28)
        self.next_btn.clicked.connect(self._step_next)

        self.del_frame_btn = QPushButton("🗑 Bu Kareyi Sil", timeline_card)
        self.del_frame_btn.setObjectName("cancelActionBtn")
        self.del_frame_btn.setFixedHeight(28)
        self.del_frame_btn.clicked.connect(self._delete_current_frame)

        self.reverse_btn = QPushButton("⇄ Tersine Çevir", timeline_card)
        self.reverse_btn.setFixedHeight(28)
        self.reverse_btn.clicked.connect(self._reverse_frames)

        controls_row.addWidget(self.play_btn)
        controls_row.addWidget(self.prev_btn)
        controls_row.addWidget(self.next_btn)
        controls_row.addWidget(self.del_frame_btn)
        controls_row.addWidget(self.reverse_btn)
        controls_row.addStretch()
        timeline_layout.addLayout(controls_row)

        # Trimming Sliders (Start & End)
        trim_group = QGroupBox("Kırpma / Kesme (Trim Start & End)", timeline_card)
        trim_layout = QHBoxLayout(trim_group)

        trim_layout.addWidget(QLabel("Başlangıç:", trim_group))
        self.trim_start_slider = QSlider(Qt.Orientation.Horizontal, trim_group)
        self.trim_start_slider.setRange(0, max(0, len(self.active_frames) - 1))
        self.trim_start_slider.setValue(0)
        self.trim_start_slider.valueChanged.connect(self._on_trim_changed)
        trim_layout.addWidget(self.trim_start_slider)

        trim_layout.addWidget(QLabel("Bitiş:", trim_group))
        self.trim_end_slider = QSlider(Qt.Orientation.Horizontal, trim_group)
        self.trim_end_slider.setRange(0, max(0, len(self.active_frames) - 1))
        self.trim_end_slider.setValue(max(0, len(self.active_frames) - 1))
        self.trim_end_slider.valueChanged.connect(self._on_trim_changed)
        trim_layout.addWidget(self.trim_end_slider)

        timeline_layout.addWidget(trim_group)
        main_layout.addWidget(timeline_card)

        # 3. Export Options Bar (FPS, Quality, Cursor, Click effects)
        opt_card = QFrame(self)
        opt_card.setStyleSheet(
            "background-color: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 6px;"
        )
        opt_layout = QHBoxLayout(opt_card)
        opt_layout.setSpacing(12)

        # FPS
        opt_layout.addWidget(QLabel("FPS:", opt_card))
        self.fps_combo = QComboBox(opt_card)
        self.fps_combo.addItems(["10 FPS", "15 FPS", "20 FPS", "24 FPS", "30 FPS"])
        self.fps_combo.setCurrentText(f"{self.fps} FPS")
        self.fps_combo.currentTextChanged.connect(self._on_fps_changed)
        opt_layout.addWidget(self.fps_combo)

        # Quality
        opt_layout.addWidget(QLabel("Kalite:", opt_card))
        self.quality_combo = QComboBox(opt_card)
        self.quality_combo.addItem("Maksimum (256 Renk)", 256)
        self.quality_combo.addItem("Yüksek (128 Renk)", 128)
        self.quality_combo.addItem("Orta (64 Renk)", 64)
        self.quality_combo.addItem("Düşük / Hızlı (32 Renk)", 32)
        opt_layout.addWidget(self.quality_combo)

        # Cursor Options
        self.show_cursor_cb = QCheckBox("İmleç", opt_card)
        self.show_cursor_cb.setChecked(True)
        self.show_cursor_cb.stateChanged.connect(lambda: self._update_display_frame())
        opt_layout.addWidget(self.show_cursor_cb)

        self.halo_cb = QCheckBox("Vurgu Halkası", opt_card)
        self.halo_cb.setChecked(True)
        self.halo_cb.stateChanged.connect(lambda: self._update_display_frame())
        opt_layout.addWidget(self.halo_cb)

        self.click_fx_cb = QCheckBox("Tıklama Efekti", opt_card)
        self.click_fx_cb.setChecked(True)
        self.click_fx_cb.stateChanged.connect(lambda: self._update_display_frame())
        opt_layout.addWidget(self.click_fx_cb)

        opt_layout.addStretch()
        main_layout.addWidget(opt_card)

        # Progress bar for encoding
        self.export_progress = QProgressBar(self)
        self.export_progress.setFixedHeight(8)
        self.export_progress.setStyleSheet(
            "QProgressBar { background-color: #2D3748; border-radius: 4px; } "
            "QProgressBar::chunk { background-color: #38A169; border-radius: 4px; }"
        )
        self.export_progress.hide()
        main_layout.addWidget(self.export_progress)

        # 4. Bottom Export / Cancel Actions
        btn_layout = QHBoxLayout()
        self.status_export_lbl = QLabel("", self)
        self.status_export_lbl.setStyleSheet("color: #68D391; font-weight: bold;")
        btn_layout.addWidget(self.status_export_lbl)

        btn_layout.addStretch()

        self.export_btn = QPushButton("💾 GIF Olarak Kaydet (Export GIF)", self)
        self.export_btn.setObjectName("primaryActionBtn")
        self.export_btn.setStyleSheet(
            "QPushButton { background-color: #2563EB; color: #FFFFFF; font-weight: bold; "
            "border-radius: 6px; padding: 6px 16px; font-size: 13px; } "
            "QPushButton:hover { background-color: #1D4ED8; }"
        )
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.clicked.connect(self._on_export)

        self.close_btn = QPushButton("Kapat", self)
        self.close_btn.clicked.connect(self.reject)

        btn_layout.addWidget(self.export_btn)
        btn_layout.addWidget(self.close_btn)
        main_layout.addLayout(btn_layout)

    def _toggle_playback(self) -> None:
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.play_btn.setText("⏸ Duraklat")
            self.play_timer.start()
        else:
            self.play_btn.setText("▶ Oynat")
            self.play_timer.stop()

    def _on_play_tick(self) -> None:
        if not self.active_frames:
            return
        self.current_frame_idx = (self.current_frame_idx + 1) % len(self.active_frames)
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setValue(self.current_frame_idx)
        self.timeline_slider.blockSignals(False)
        self._update_display_frame()

    def _step_prev(self) -> None:
        if self.active_frames:
            self.current_frame_idx = (self.current_frame_idx - 1) % len(self.active_frames)
            self.timeline_slider.setValue(self.current_frame_idx)

    def _step_next(self) -> None:
        if self.active_frames:
            self.current_frame_idx = (self.current_frame_idx + 1) % len(self.active_frames)
            self.timeline_slider.setValue(self.current_frame_idx)

    def _on_slider_moved(self, val: int) -> None:
        self.current_frame_idx = val
        self._update_display_frame()

    def _on_trim_changed(self) -> None:
        s = min(self.trim_start_slider.value(), self.trim_end_slider.value())
        e = max(self.trim_start_slider.value(), self.trim_end_slider.value())
        self.active_frames = self.raw_frames[s : e + 1]

        if not self.active_frames:
            self.active_frames = list(self.raw_frames)

        self.timeline_slider.setRange(0, len(self.active_frames) - 1)
        self.current_frame_idx = min(self.current_frame_idx, len(self.active_frames) - 1)
        self._update_display_frame()

    def _delete_current_frame(self) -> None:
        if len(self.active_frames) > 1:
            del self.active_frames[self.current_frame_idx]
            self.current_frame_idx = min(self.current_frame_idx, len(self.active_frames) - 1)
            self.timeline_slider.setRange(0, len(self.active_frames) - 1)
            self._update_display_frame()

    def _reverse_frames(self) -> None:
        self.active_frames.reverse()
        self._update_display_frame()

    def _on_fps_changed(self, text: str) -> None:
        try:
            fps_val = int(text.split()[0])
            self.fps = fps_val
            self.play_timer.setInterval(int(1000 / max(1, self.fps)))
        except Exception:
            pass

    def _update_display_frame(self) -> None:
        if not self.active_frames:
            return

        idx = min(self.current_frame_idx, len(self.active_frames) - 1)
        frame = self.active_frames[idx]

        # Render cursor on preview
        renderer = CursorRenderer(
            show_cursor=self.show_cursor_cb.isChecked(),
            highlight_cursor=self.halo_cb.isChecked(),
            show_click_effects=self.click_fx_cb.isChecked(),
        )
        rendered_img = renderer.render_to_frame(frame.image, frame.cursor_pos)

        pix = QPixmap.fromImage(rendered_img)
        scaled_pix = pix.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled_pix)

        # Update labels
        current_sec = idx / max(1, self.fps)
        total_sec = len(self.active_frames) / max(1, self.fps)
        self.time_lbl.setText(f"{current_sec:.1f}s / {total_sec:.1f}s")
        self.frame_num_lbl.setText(f"Kare: {idx + 1} / {len(self.active_frames)}")

    def _on_export(self) -> None:
        default_path = StorageService.get_quick_save_path(self.default_save_dir, "GIF")
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "GIF Olarak Kaydet",
            str(default_path),
            "GIF Animation (*.gif)",
        )

        if not filepath:
            return

        if not filepath.lower().endswith(".gif"):
            filepath += ".gif"

        self.export_progress.show()
        self.export_progress.setValue(0)
        self.export_btn.setEnabled(False)
        self.status_export_lbl.setText("GIF oluşturuluyor ve kaydediliyor...")
        self.status_export_lbl.setStyleSheet("color: #63B3ED;")

        renderer = CursorRenderer(
            show_cursor=self.show_cursor_cb.isChecked(),
            highlight_cursor=self.halo_cb.isChecked(),
            show_click_effects=self.click_fx_cb.isChecked(),
        )

        colors = int(self.quality_combo.currentData() or 256)

        self.worker = GifEncodingWorker(
            frames=self.active_frames,
            output_path=filepath,
            fps=self.fps,
            loop=0,
            cursor_renderer=renderer,
            deduplicate=True,
            max_colors=colors,
            parent=self,
        )

        self.worker.progress_updated.connect(self.export_progress.setValue)
        self.worker.encoding_finished.connect(self._on_export_finished)
        self.worker.encoding_failed.connect(self._on_export_failed)
        self.worker.start()

    def _on_export_finished(self, out_path: str) -> None:
        self.export_progress.hide()
        self.export_btn.setEnabled(True)
        self.status_export_lbl.setText("✓ GIF başarıyla kaydedildi!")
        self.status_export_lbl.setStyleSheet("color: #68D391;")

        # Display system-wide Toast notification
        from app.ui.notifications import NotificationManager
        NotificationManager.show_toast(
            "GIF Kaydedildi",
            f"GIF animasyonu başarıyla kaydedildi:\n{Path(out_path).name}",
            "save",
            3500,
        )

        self.gif_saved.emit(out_path)
        QTimer.singleShot(500, self.accept)

    def _on_export_failed(self, err_msg: str) -> None:
        self.export_progress.hide()
        self.export_btn.setEnabled(True)
        self.status_export_lbl.setText("Hata oluştu.")
        self.status_export_lbl.setStyleSheet("color: #FEB2B2;")
        logger.error("GIF export failed: %s", err_msg)

