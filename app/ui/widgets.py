"""Reusable modern UI components: ToggleSwitch, SettingToggleRow, SettingsCard, and navigation items."""

from typing import Optional
from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.styles import get_icon


class SettingsToggleSwitch(QCheckBox):
    """Custom painted iOS/Fluent-style sliding toggle switch."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        checked = self.isChecked()
        width = 46
        height = 24
        radius = height / 2.0

        # Background track
        track_rect = QRectF(0, 1, width, height)
        path = QPainterPath()
        path.addRoundedRect(track_rect, radius, radius)

        if checked:
            # Active Gradient (Indigo/Purple)
            grad = QLinearGradient(0, 0, width, 0)
            grad.setColorAt(0.0, QColor("#4F46E5"))
            grad.setColorAt(1.0, QColor("#6366F1"))
            painter.fillPath(path, QBrush(grad))
            painter.strokePath(path, QPen(QColor("#818CF8"), 1))
        else:
            # Inactive Track
            painter.fillPath(path, QBrush(QColor("#1E293B")))
            painter.strokePath(path, QPen(QColor("#334155"), 1.2))

        # Knob (Slider circle)
        knob_size = 18.0
        knob_y = 4.0
        knob_x = (width - knob_size - 3.0) if checked else 3.0

        knob_rect = QRectF(knob_x, knob_y, knob_size, knob_size)
        knob_path = QPainterPath()
        knob_path.addEllipse(knob_rect)

        if checked:
            painter.fillPath(knob_path, QBrush(QColor("#FFFFFF")))
        else:
            painter.fillPath(knob_path, QBrush(QColor("#94A3B8")))

        painter.end()


class SettingToggleRow(QWidget):
    """Setting row with an icon, title, description, and a ToggleSwitch."""

    def __init__(
        self,
        icon_name: str,
        title: str,
        description: str,
        toggle_switch: Optional[SettingsToggleSwitch] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.toggle = toggle_switch if toggle_switch else SettingsToggleSwitch(self)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui(icon_name, title, description)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle.toggle()
            event.accept()
        else:
            super().mousePressEvent(event)

    def _setup_ui(self, icon_name: str, title: str, description: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(14)

        if icon_name:
            icon_lbl = QLabel(self)
            icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            icon_lbl.setPixmap(get_icon(icon_name, "#818CF8", 20).pixmap(20, 20))
            icon_lbl.setFixedSize(24, 24)
            layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title_lbl = QLabel(title, self)
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        title_lbl.setStyleSheet("color: #FFFFFF; font-weight: 600; font-size: 13px;")
        text_layout.addWidget(title_lbl)

        if description:
            desc_lbl = QLabel(description, self)
            desc_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            desc_lbl.setStyleSheet("color: #94A3B8; font-size: 11.5px;")
            desc_lbl.setWordWrap(True)
            text_layout.addWidget(desc_lbl)

        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addWidget(self.toggle, alignment=Qt.AlignmentFlag.AlignVCenter)


class SettingsCard(QFrame):
    """Elevated dark glassmorphic card container with header icon and title."""

    def __init__(
        self,
        icon_name: str,
        title: str,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("settingsCard")
        self.setStyleSheet(
            """
            QFrame#settingsCard {
                background-color: rgba(18, 24, 38, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 14px 16px;
            }
            """
        )

        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(14, 14, 14, 14)
        self.card_layout.setSpacing(10)

        # Header
        hdr_layout = QHBoxLayout()
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(10)

        if icon_name:
            icon_lbl = QLabel(self)
            icon_lbl.setPixmap(get_icon(icon_name, "#818CF8", 20).pixmap(20, 20))
            hdr_layout.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)

        title_lbl = QLabel(title, self)
        title_lbl.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 14.5px;")
        title_box.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle, self)
            sub_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
            title_box.addWidget(sub_lbl)

        hdr_layout.addLayout(title_box)
        hdr_layout.addStretch()
        self.card_layout.addLayout(hdr_layout)

    def add_widget(self, widget: QWidget) -> None:
        self.card_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self.card_layout.addLayout(layout)

