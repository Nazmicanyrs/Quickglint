"""Ultra-modern, Google Stitch-inspired floating QR detection panel with glassmorphism and drag-to-move support."""

from typing import List, Optional
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDesktopServices,
    QFont,
    QIcon,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.qr.qr_result import QRDataType, QRResult
from app.services.clipboard_service import ClipboardService
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.i18n import tr


class QRItemWidget(QFrame):
    """Modern Stitch-styled card representing a single detected QR code."""

    locate_clicked = Signal(object)  # QRResult

    def __init__(self, result: QRResult, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.result = result
        self.setObjectName("stitchQrItemCard")
        self.setStyleSheet(
            """
            QFrame#stitchQrItemCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(30, 41, 59, 0.75), stop:1 rgba(15, 23, 42, 0.85));
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 10px;
                padding: 10px;
            }
            QFrame#stitchQrItemCard:hover {
                border: 1px solid rgba(56, 189, 248, 0.45);
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(30, 41, 59, 0.90), stop:1 rgba(15, 23, 42, 0.95));
            }
            """
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 1. Header Row: Semantic Type Badge + Locate Icon Button
        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(6)

        # Type Badge (Pill style)
        type_title = self.result.get_display_title()
        badge_bg = "rgba(56, 189, 248, 0.14)"
        badge_border = "rgba(56, 189, 248, 0.35)"
        badge_color = "#38BDF8"

        if self.result.type == QRDataType.URL:
            badge_bg = "rgba(59, 130, 246, 0.16)"
            badge_border = "rgba(96, 165, 250, 0.40)"
            badge_color = "#60A5FA"
        elif self.result.type == QRDataType.WIFI:
            badge_bg = "rgba(16, 185, 129, 0.16)"
            badge_border = "rgba(52, 211, 153, 0.40)"
            badge_color = "#34D399"
        elif self.result.type == QRDataType.OTP:
            badge_bg = "rgba(245, 158, 11, 0.16)"
            badge_border = "rgba(251, 191, 36, 0.40)"
            badge_color = "#FBBF24"

        badge_lbl = QLabel(f"#{self.result.index}  •  {type_title}", self)
        badge_lbl.setStyleSheet(
            f"""
            background-color: {badge_bg};
            border: 1px solid {badge_border};
            border-radius: 10px;
            color: {badge_color};
            font-weight: 700;
            font-size: 11px;
            padding: 3px 9px;
            """
        )
        hdr_layout.addWidget(badge_lbl)

        hdr_layout.addStretch()

        # Locate Button
        self.locate_btn = QToolButton(self)
        self.locate_btn.setIcon(get_icon("select", "#94A3B8", 14))
        self.locate_btn.setIconSize(QSize(14, 14))
        self.locate_btn.setToolTip("Görsel üzerinde bu QR kodun konumuna odaklan (Locate QR)")
        self.locate_btn.setStyleSheet(
            """
            QToolButton {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
                padding: 4px;
                min-width: 22px;
                min-height: 22px;
            }
            QToolButton:hover {
                background-color: rgba(56, 189, 248, 0.20);
                border-color: rgba(56, 189, 248, 0.40);
            }
            """
        )
        self.locate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.locate_btn.clicked.connect(lambda: self.locate_clicked.emit(self.result))
        hdr_layout.addWidget(self.locate_btn)

        layout.addLayout(hdr_layout)

        # 2. Content Well (Structured preview)
        content_frame = QFrame(self)
        content_frame.setStyleSheet(
            """
            background-color: rgba(10, 15, 26, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            padding: 8px 10px;
            """
        )
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(4, 4, 4, 4)
        content_layout.setSpacing(4)

        preview_text = self.result.get_display_preview()
        self.preview_lbl = QLabel(preview_text, content_frame)
        self.preview_lbl.setWordWrap(True)
        self.preview_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview_lbl.setStyleSheet(
            """
            color: #F8FAFC;
            font-size: 12px;
            font-family: 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
            line-height: 1.4;
            background: transparent;
            border: none;
            """
        )
        content_layout.addWidget(self.preview_lbl)
        layout.addWidget(content_frame)

        # 3. Action Buttons Row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
        btn_layout.setSpacing(8)

        # Open Link (Only for validated safe http/https URLs)
        if self.result.is_url and self.result.normalized_url:
            self.open_btn = QPushButton("Bağlantıyı Aç", self)
            self.open_btn.setIcon(get_icon("share", "#FFFFFF", 14))
            self.open_btn.setIconSize(QSize(14, 14))
            self.open_btn.setStyleSheet(
                """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3B82F6, stop:1 #1D4ED8);
                    color: #FFFFFF;
                    border: 1px solid rgba(96, 165, 250, 0.6);
                    border-radius: 7px;
                    padding: 6px 14px;
                    font-weight: 600;
                    font-size: 11.5px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #60A5FA, stop:1 #2563EB);
                    border-color: #93C5FD;
                }
                QPushButton:pressed {
                    background: #1E40AF;
                }
                """
            )
            self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.open_btn.clicked.connect(self._on_open_link)
            btn_layout.addWidget(self.open_btn)

        # Copy Button
        self.copy_btn = QPushButton("Kopyala", self)
        self.copy_btn.setIcon(get_icon("copy", "#E2E8F0", 14))
        self.copy_btn.setIconSize(QSize(14, 14))
        self.copy_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #F1F5F9;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 7px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 11.5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                border-color: rgba(255, 255, 255, 0.28);
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 0.3);
            }
            """
        )
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._on_copy_data)
        btn_layout.addWidget(self.copy_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _on_open_link(self) -> None:
        """Safely open normalized web URL in user's default browser."""
        if self.result.is_url and self.result.normalized_url:
            url = QUrl(self.result.normalized_url)
            if url.isValid() and url.scheme() in ("http", "https"):
                QDesktopServices.openUrl(url)

    def _on_copy_data(self) -> None:
        """Copy QR data to clipboard and give visual feedback."""
        text_to_copy = (
            self.result.normalized_url
            if (self.result.is_url and self.result.normalized_url)
            else self.result.data
        )
        ClipboardService.copy_text(text_to_copy)

        # Visual feedback with emerald glow
        self.copy_btn.setText("✓ Kopyalandı")
        self.copy_btn.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                border: 1px solid #34D399;
                border-radius: 7px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 11.5px;
            }
            """
        )
        QTimer.singleShot(1800, self._reset_copy_btn)

    def _reset_copy_btn(self) -> None:
        self.copy_btn.setText("Kopyala")
        self.copy_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #F1F5F9;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 7px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 11.5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                border-color: rgba(255, 255, 255, 0.28);
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: rgba(0, 0, 0, 0.3);
            }
            """
        )


class QRNotificationPanel(QWidget):
    """Floating top-level Stitch-grade glassmorphic card displaying detected QR codes with drag-to-move support."""

    closed = Signal()
    locate_requested = Signal(object)  # QRResult

    def __init__(self, results: List[QRResult], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.results = results
        self._is_dragging = False
        self._drag_offset = QPoint()
        if parent is None:
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(DARK_THEME_QSS)

        self._setup_ui()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Outer Glassmorphic Container Frame
        self.card_frame = QFrame(self)
        self.card_frame.setObjectName("stitchQrNotificationShell")
        self.card_frame.setStyleSheet(
            """
            QFrame#stitchQrNotificationShell {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(15, 23, 42, 0.97), stop:1 rgba(11, 17, 32, 0.99));
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 14px;
                padding: 10px;
            }
            """
        )
        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.setSpacing(10)

        # 1. Header Bar: Stitch Drag Grip + Glowing Icon + Title Badge + Close Button
        self.header_frame = QFrame(self.card_frame)
        self.header_frame.setCursor(Qt.CursorShape.SizeAllCursor)
        self.header_frame.setToolTip("Sürükleyerek istediğiniz yere taşıyabilirsiniz (Drag to move)")
        self.header_frame.setStyleSheet("background: transparent; border: none;")

        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # 6-dot drag handle
        grip_lbl = QLabel("⠿", self.header_frame)
        grip_lbl.setStyleSheet("color: #64748B; font-weight: bold; font-size: 16px;")
        header_layout.addWidget(grip_lbl)

        icon_lbl = QLabel(self.header_frame)
        icon_lbl.setPixmap(get_icon("qr_code", "#38BDF8", 18).pixmap(18, 18))
        header_layout.addWidget(icon_lbl)

        count = len(self.results)
        title_text = "QR Kod Algılandı" if count == 1 else f"{count} QR Kod Algılandı"
        title_lbl = QLabel(title_text, self.header_frame)
        title_lbl.setStyleSheet(
            """
            color: #FFFFFF;
            font-weight: 700;
            font-size: 13px;
            letter-spacing: 0.3px;
            """
        )
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        # Stitch-styled circular close button
        close_btn = QToolButton(self.header_frame)
        close_btn.setIcon(get_icon("close", "#94A3B8", 14))
        close_btn.setIconSize(QSize(14, 14))
        close_btn.setToolTip("Kapat")
        close_btn.setStyleSheet(
            """
            QToolButton {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 12px;
                padding: 4px;
                min-width: 22px;
                min-height: 22px;
            }
            QToolButton:hover {
                background-color: rgba(239, 68, 68, 0.25);
                border-color: rgba(239, 68, 68, 0.50);
            }
            """
        )
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self._on_close)
        header_layout.addWidget(close_btn)

        card_layout.addWidget(self.header_frame)

        # 2. Items Area (Single or Scrollable List)
        if count == 1:
            item_widget = QRItemWidget(self.results[0], self)
            item_widget.locate_clicked.connect(self.locate_requested.emit)
            card_layout.addWidget(item_widget)
            self.setFixedWidth(350)
        else:
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("background: transparent; border: none;")
            scroll.setMaximumHeight(340)

            scroll_content = QWidget()
            scroll_content.setStyleSheet("background: transparent;")
            scroll_layout = QVBoxLayout(scroll_content)
            scroll_layout.setContentsMargins(0, 0, 0, 0)
            scroll_layout.setSpacing(8)

            for res in self.results:
                item_w = QRItemWidget(res, scroll_content)
                item_w.locate_clicked.connect(self.locate_requested.emit)
                scroll_layout.addWidget(item_w)

            scroll_layout.addStretch()
            scroll.setWidget(scroll_content)
            card_layout.addWidget(scroll)
            self.setFixedWidth(390)

        main_layout.addWidget(self.card_frame)

    def _on_close(self) -> None:
        self.hide()
        self.closed.emit()
        self.deleteLater()

    def position_smart(self, selection_rect: QRect, parent_bounds: QRect) -> None:
        """Position the panel cleanly near the selection without going off-screen."""
        card_w = self.sizeHint().width() or self.width()
        card_h = self.sizeHint().height() or self.height()

        x = selection_rect.right() - card_w
        y = selection_rect.top() + 10

        if x < parent_bounds.left() + 10:
            x = parent_bounds.left() + 10

        if x + card_w > parent_bounds.right() - 10:
            x = parent_bounds.right() - card_w - 10

        if y < parent_bounds.top() + 10:
            y = parent_bounds.top() + 10

        if y + card_h > parent_bounds.bottom() - 10:
            y = parent_bounds.bottom() - card_h - 10

        self.move(x, y)
        self.show()
        self.raise_()

