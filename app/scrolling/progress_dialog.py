"""Smartphone-style floating Scroll Capture HUD with Live Thumbnail, Step Scroll, Auto Scroll, and Done."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.styles import get_icon


class ScrollingProgressDialog(QDialog):
    """Smartphone-like floating HUD showing live thumbnail and Scroll / Done controls."""

    step_scroll_requested = Signal()
    toggle_auto_scroll_requested = Signal()
    finish_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scroll Capture")
        self.setFixedSize(360, 180)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self.is_auto_scrolling = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame(self)
        card.setObjectName("smartScrollCard")
        card.setStyleSheet(
            "#smartScrollCard { background-color: #0F172A; border: 2px solid #3B82F6; border-radius: 14px; }"
        )
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(12)

        # 1. Left: Live Thumbnail preview of stitched document (Smartphone Style)
        self.thumb_frame = QFrame(card)
        self.thumb_frame.setFixedSize(50, 150)
        self.thumb_frame.setStyleSheet(
            "background-color: #1E293B; border: 1px solid #475569; border-radius: 6px;"
        )
        thumb_layout = QVBoxLayout(self.thumb_frame)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.thumb_label = QLabel(self.thumb_frame)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("border: none; background: transparent;")
        thumb_layout.addWidget(self.thumb_label)
        card_layout.addWidget(self.thumb_frame)

        # 2. Right: Info & Controls
        controls_col = QVBoxLayout()
        controls_col.setSpacing(8)

        # Title & Stats
        title_lbl = QLabel("Kaydırmalı Ekran Yakalama", card)
        title_lbl.setStyleSheet(
            "border: none; background: transparent; color: #FFFFFF; font-size: 13px; font-weight: bold;"
        )
        controls_col.addWidget(title_lbl)

        stats_row = QHBoxLayout()
        self.frame_lbl = QLabel("Kare: 1", card)
        self.frame_lbl.setStyleSheet(
            "border: none; background: #1E293B; color: #F8FAFC; font-size: 11px; font-weight: bold; "
            "border-radius: 4px; padding: 2px 6px;"
        )
        self.height_lbl = QLabel("Yükseklik: 0 px", card)
        self.height_lbl.setStyleSheet(
            "border: none; background: #1E293B; color: #60A5FA; font-size: 11px; font-weight: bold; "
            "border-radius: 4px; padding: 2px 6px;"
        )
        stats_row.addWidget(self.frame_lbl)
        stats_row.addWidget(self.height_lbl)
        stats_row.addStretch()
        controls_col.addLayout(stats_row)

        # Scroll Action Buttons Row (Smartphone Style: Scroll More & Auto Scroll)
        scroll_btn_row = QHBoxLayout()
        scroll_btn_row.setSpacing(6)

        self.scroll_more_btn = QPushButton("⬇ Daha Fazla Kaydır", card)
        self.scroll_more_btn.setFixedHeight(28)
        self.scroll_more_btn.setStyleSheet(
            "QPushButton { background-color: #0284C7; color: #FFFFFF; font-weight: bold; "
            "border: none; border-radius: 6px; font-size: 11px; padding: 0 8px; } "
            "QPushButton:hover { background-color: #0369A1; }"
        )
        self.scroll_more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scroll_more_btn.clicked.connect(self.step_scroll_requested.emit)
        scroll_btn_row.addWidget(self.scroll_more_btn)

        self.auto_scroll_btn = QPushButton("▶ Otomatik", card)
        self.auto_scroll_btn.setFixedHeight(28)
        self.auto_scroll_btn.setStyleSheet(
            "QPushButton { background-color: #334155; color: #F8FAFC; font-weight: bold; "
            "border: 1px solid #475569; border-radius: 6px; font-size: 11px; padding: 0 8px; } "
            "QPushButton:hover { background-color: #475569; }"
        )
        self.auto_scroll_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_scroll_btn.clicked.connect(self.toggle_auto_scroll_requested.emit)
        scroll_btn_row.addWidget(self.auto_scroll_btn)

        controls_col.addLayout(scroll_btn_row)

        # Finish & Cancel Row
        finish_row = QHBoxLayout()
        finish_row.setSpacing(6)

        self.finish_btn = QPushButton("✓ Bitir ve Düzenle", card)
        self.finish_btn.setFixedHeight(30)
        self.finish_btn.setStyleSheet(
            "QPushButton { background-color: #2563EB; color: #FFFFFF; font-weight: bold; "
            "border: none; border-radius: 6px; font-size: 11px; } "
            "QPushButton:hover { background-color: #1D4ED8; }"
        )
        self.finish_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.finish_btn.clicked.connect(self.finish_requested.emit)
        finish_row.addWidget(self.finish_btn, stretch=3)

        self.cancel_btn = QPushButton("İptal", card)
        self.cancel_btn.setFixedHeight(30)
        self.cancel_btn.setStyleSheet(
            "QPushButton { background-color: #475569; color: #F8FAFC; "
            "border: none; border-radius: 6px; font-size: 11px; } "
            "QPushButton:hover { background-color: #64748B; }"
        )
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        finish_row.addWidget(self.cancel_btn, stretch=2)

        controls_col.addLayout(finish_row)
        card_layout.addLayout(controls_col)

        main_layout.addWidget(card)

    def update_stats(self, frame_count: int, total_height: int, preview_img: Optional[QImage] = None) -> None:
        self.frame_lbl.setText(f"Kare: {frame_count}")
        self.height_lbl.setText(f"Yükseklik: {total_height:,} px")

        if preview_img and not preview_img.isNull():
            pix = QPixmap.fromImage(preview_img)
            scaled = pix.scaled(
                self.thumb_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.thumb_label.setPixmap(scaled)

    def set_auto_scroll_state(self, is_running: bool) -> None:
        self.is_auto_scrolling = is_running
        if is_running:
            self.auto_scroll_btn.setText("⏸ Durdur")
            self.auto_scroll_btn.setStyleSheet(
                "QPushButton { background-color: #DC2626; color: #FFFFFF; font-weight: bold; "
                "border: none; border-radius: 6px; font-size: 11px; } "
                "QPushButton:hover { background-color: #B91C1C; }"
            )
        else:
            self.auto_scroll_btn.setText("▶ Otomatik")
            self.auto_scroll_btn.setStyleSheet(
                "QPushButton { background-color: #334155; color: #F8FAFC; font-weight: bold; "
                "border: 1px solid #475569; border-radius: 6px; font-size: 11px; } "
                "QPushButton:hover { background-color: #475569; }"
            )

