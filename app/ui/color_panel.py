"""Advanced Color Picker, Palettes, Custom Colors, and Eyedropper UI module."""

from typing import List, Optional
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.editor.tools import ToolManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.constants import DEFAULT_PALETTE, EXTENDED_PALETTES
from app.utils.i18n import tr
from app.utils.logger import logger


class ColorSwatchButton(QPushButton):
    """Circular or rounded swatch button with active selection ring."""

    color_clicked = Signal(str)

    def __init__(
        self,
        color_hex: str,
        size: int = 22,
        is_selected: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._color_hex = color_hex.upper()
        self._size = size
        self._is_selected = is_selected

        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._color_hex)
        self.clicked.connect(lambda: self.color_clicked.emit(self._color_hex))
        self._update_appearance()

    @property
    def color_hex(self) -> str:
        return self._color_hex

    def set_color(self, color_hex: str) -> None:
        self._color_hex = color_hex.upper()
        self.setToolTip(self._color_hex)
        self._update_appearance()

    def set_selected(self, selected: bool) -> None:
        if self._is_selected != selected:
            self._is_selected = selected
            self._update_appearance()

    def _update_appearance(self) -> None:
        # Generate custom pixmap with border and active ring
        s = self._size
        pix = QPixmap(s, s)
        pix.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        c = QColor(self._color_hex)
        if not c.isValid():
            c = QColor("#FF0000")

        if self._is_selected:
            # Outer active indicator ring
            painter.setPen(QColor("#38BDF8"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(1, 1, s - 2, s - 2)

            # Inner color circle
            painter.setPen(QColor("#FFFFFF"))
            painter.setBrush(c)
            painter.drawEllipse(3, 3, s - 6, s - 6)
        else:
            # Subtle border
            border_color = QColor("#475569") if c.lightness() < 200 else QColor("#94A3B8")
            painter.setPen(border_color)
            painter.setBrush(c)
            painter.drawEllipse(1, 1, s - 2, s - 2)

        painter.end()
        self.setIcon(QIcon(pix))
        self.setIconSize(QSize(s, s))
        self.setStyleSheet("QPushButton { background: transparent; border: none; padding: 0; }")


class AdvancedColorPopup(QFrame):
    """Modern floating color palette and custom picker popup."""

    color_selected = Signal(str)
    eyedropper_requested = Signal()

    # Saved custom colors in memory/session
    _custom_colors: List[str] = ["#FF5500", "#00E5FF", "#A855F7", "#F43F5E", "#10B981", "#F59E0B"]

    def __init__(
        self,
        tool_manager: ToolManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.tool_manager = tool_manager

        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(DARK_THEME_QSS)

        self._swatch_buttons: List[ColorSwatchButton] = []
        self._custom_swatches: List[ColorSwatchButton] = []

        self._setup_ui()
        self._update_selection(self.tool_manager.color)

    def _setup_ui(self) -> None:
        self.setObjectName("advancedColorPopupFrame")
        self.setStyleSheet(
            "QFrame#advancedColorPopupFrame { "
            "background-color: rgba(15, 23, 42, 0.98); "
            "border: 1px solid rgba(56, 189, 248, 0.35); "
            "border-radius: 12px; padding: 12px; } "
            "QLabel { font-size: 11.5px; font-weight: 600; color: #94A3B8; margin-top: 4px; } "
            "QLineEdit { background: #0B0F17; border: 1px solid #334155; border-radius: 6px; "
            "color: #F8FAFC; font-weight: 600; font-family: monospace; font-size: 12.5px; padding: 4px 8px; }"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # 1. Header: Active Color & Hex Input Box
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.preview_swatch = QLabel(self)
        self.preview_swatch.setFixedSize(30, 30)
        self.preview_swatch.setStyleSheet(
            f"background-color: {self.tool_manager.color}; border: 2px solid #FFFFFF; border-radius: 6px;"
        )
        header_layout.addWidget(self.preview_swatch)

        self.hex_input = QLineEdit(self)
        self.hex_input.setText(self.tool_manager.color.upper())
        self.hex_input.setMaxLength(7)
        self.hex_input.setPlaceholderText(tr("color_hex_placeholder"))
        self.hex_input.textEdited.connect(self._on_hex_edited)
        header_layout.addWidget(self.hex_input, 1)

        copy_btn = QToolButton(self)
        copy_btn.setIcon(get_icon("copy", "#38BDF8", 16))
        copy_btn.setIconSize(QSize(16, 16))
        copy_btn.setToolTip("HEX Kodunu Kopyala")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(self._copy_hex_to_clipboard)
        header_layout.addWidget(copy_btn)

        main_layout.addLayout(header_layout)

        # 2. Section: Canlı ve Temel Renkler (Vibrant Palette)
        lbl_vibrant = QLabel(tr("color_vibrant_title"), self)
        main_layout.addWidget(lbl_vibrant)

        vibrant_grid = QGridLayout()
        vibrant_grid.setSpacing(4)
        vibrant_colors = EXTENDED_PALETTES.get("vibrant", DEFAULT_PALETTE)
        cols = 8
        for i, c in enumerate(vibrant_colors):
            btn = ColorSwatchButton(c, size=20, parent=self)
            btn.color_clicked.connect(self._select_color)
            self._swatch_buttons.append(btn)
            vibrant_grid.addWidget(btn, i // cols, i % cols)
        main_layout.addLayout(vibrant_grid)

        # 3. Section: Pastel ve Monokrom
        lbl_pastel = QLabel(tr("color_pastel_title") + " & " + tr("color_mono_title"), self)
        main_layout.addWidget(lbl_pastel)

        pm_grid = QGridLayout()
        pm_grid.setSpacing(4)
        pm_colors = EXTENDED_PALETTES.get("pastel", []) + EXTENDED_PALETTES.get("monochrome", [])
        for i, c in enumerate(pm_colors):
            btn = ColorSwatchButton(c, size=20, parent=self)
            btn.color_clicked.connect(self._select_color)
            self._swatch_buttons.append(btn)
            pm_grid.addWidget(btn, i // cols, i % cols)
        main_layout.addLayout(pm_grid)

        # 4. Section: Özel ve Kayıtlı Renkler
        custom_header = QHBoxLayout()
        lbl_custom = QLabel(tr("color_custom_title"), self)
        custom_header.addWidget(lbl_custom)
        custom_header.addStretch()

        add_custom_btn = QToolButton(self)
        add_custom_btn.setIcon(get_icon("plus", "#38BDF8", 14))
        add_custom_btn.setIconSize(QSize(14, 14))
        add_custom_btn.setToolTip(tr("color_add_custom"))
        add_custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_custom_btn.clicked.connect(self._save_current_to_custom)
        custom_header.addWidget(add_custom_btn)
        main_layout.addLayout(custom_header)

        self.custom_grid = QHBoxLayout()
        self.custom_grid.setSpacing(4)
        self._rebuild_custom_swatches()
        main_layout.addLayout(self.custom_grid)

        # 5. Action Buttons (Full Color Wheel & Eyedropper)
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(6)

        self.wheel_btn = QPushButton(tr("color_wheel_btn"), self)
        self.wheel_btn.setIcon(get_icon("palette", "#F59E0B", 16))
        self.wheel_btn.setIconSize(QSize(16, 16))
        self.wheel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.wheel_btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 6px; padding: 6px 10px; font-weight: 600; font-size: 11.5px; } "
            "QPushButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: #38BDF8; color: #FFFFFF; }"
        )
        self.wheel_btn.clicked.connect(self._open_full_color_dialog)
        actions_layout.addWidget(self.wheel_btn, 1)

        self.eyedropper_btn = QPushButton(self)
        self.eyedropper_btn.setIcon(get_icon("pipette", "#38BDF8", 16))
        self.eyedropper_btn.setIconSize(QSize(16, 16))
        self.eyedropper_btn.setToolTip(tr("color_eyedropper_btn"))
        self.eyedropper_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.eyedropper_btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 6px; padding: 6px 8px; } QPushButton:hover { background-color: rgba(56, 189, 248, 0.25); border-color: #38BDF8; }"
        )
        self.eyedropper_btn.clicked.connect(self._on_eyedropper_clicked)
        actions_layout.addWidget(self.eyedropper_btn)

        main_layout.addLayout(actions_layout)

    def _rebuild_custom_swatches(self) -> None:
        # Clear existing
        while self.custom_grid.count():
            item = self.custom_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._custom_swatches.clear()

        for c in self._custom_colors:
            btn = ColorSwatchButton(c, size=22, parent=self)
            btn.color_clicked.connect(self._select_color)
            self._custom_swatches.append(btn)
            self.custom_grid.addWidget(btn)

        self.custom_grid.addStretch()

    def _select_color(self, color_hex: str) -> None:
        hex_str = color_hex.upper()
        if not hex_str.startswith("#"):
            hex_str = f"#{hex_str}"

        self.tool_manager.color = hex_str
        self._update_selection(hex_str)
        self.color_selected.emit(hex_str)

    def _update_selection(self, color_hex: str) -> None:
        hex_norm = color_hex.upper()
        self.preview_swatch.setStyleSheet(
            f"background-color: {hex_norm}; border: 2px solid #FFFFFF; border-radius: 6px;"
        )
        if self.hex_input.text().upper() != hex_norm:
            self.hex_input.setText(hex_norm)

        for btn in self._swatch_buttons + self._custom_swatches:
            btn.set_selected(btn.color_hex == hex_norm)

    def _on_hex_edited(self, text: str) -> None:
        txt = text.strip().upper()
        if not txt.startswith("#"):
            txt = f"#{txt}"

        if len(txt) == 7 and QColor(txt).isValid():
            self._select_color(txt)

    def _copy_hex_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.tool_manager.color.upper())

    def _save_current_to_custom(self) -> None:
        cur = self.tool_manager.color.upper()
        if cur in self._custom_colors:
            self._custom_colors.remove(cur)
        self._custom_colors.insert(0, cur)
        if len(self._custom_colors) > 8:
            self._custom_colors.pop()
        self._rebuild_custom_swatches()
        self._update_selection(cur)

    def _open_full_color_dialog(self) -> None:
        c = QColorDialog.getColor(QColor(self.tool_manager.color), self, tr("dialog_select_color"))
        if c.isValid():
            hex_str = c.name().upper()
            self._select_color(hex_str)
            self._save_current_to_custom()

    def _on_eyedropper_clicked(self) -> None:
        self.hide()
        self.eyedropper_requested.emit()

    def show_above_or_below(self, target_rect: QRect, screen_rect: QRect) -> None:
        """Position popup nicely near the target widget."""
        self.adjustSize()
        pw = self.sizeHint().width()
        ph = self.sizeHint().height()

        x = target_rect.center().x() - (pw // 2)
        x = max(screen_rect.left() + 10, min(x, screen_rect.right() - pw - 10))

        # Try below
        y = target_rect.bottom() + 6
        if y + ph > screen_rect.bottom() - 10:
            # Place above
            y = target_rect.top() - ph - 6

        self.move(x, y)
        self._update_selection(self.tool_manager.color)
        self.show()
        self.raise_()
        self.activateWindow()

