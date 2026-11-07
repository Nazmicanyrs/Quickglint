"""Floating annotation and action toolbars with Smart Privacy, Scrolling, and GIF recording buttons."""

from typing import List, Optional
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.editor.history import HistoryManager
from app.editor.tools import ToolManager
from app.ui.color_panel import AdvancedColorPopup, ColorSwatchButton
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.constants import DEFAULT_PALETTE, FONT_SIZE_OPTIONS, STROKE_WIDTH_OPTIONS, ToolType
from app.utils.i18n import tr
from app.utils.logger import logger


class FloatingToolbar(QWidget):
    """Container holding drawing tools and advanced action dropdown menus anchored to selection."""

    # Core signals
    copy_requested = Signal()
    save_requested = Signal()
    cancel_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()

    # Session signals
    new_session_requested = Signal()
    add_to_session_requested = Signal()
    open_session_requested = Signal()

    # Advanced feature signals
    privacy_requested = Signal()
    scrolling_requested = Signal()
    record_gif_requested = Signal()
    save_to_vault_requested = Signal()
    export_pdf_requested = Signal()
    optimize_requested = Signal()
    upload_requested = Signal()
    open_share_history_requested = Signal()
    measure_requested = Signal()
    favorite_toggled = Signal()
    open_favorites_gallery_requested = Signal()
    extract_text_requested = Signal()
    qr_scan_requested = Signal()
    panorama_requested = Signal()
    eyedropper_requested = Signal()
    watermark_toggled = Signal(bool)
    info_banner_toggled = Signal(bool)

    def __init__(
        self,
        tool_manager: ToolManager,
        history_manager: HistoryManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.tool_manager = tool_manager
        self.history_manager = history_manager

        if parent is None:
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(DARK_THEME_QSS)

        self.color_chips: List[ColorSwatchButton] = []
        self.color_popup = AdvancedColorPopup(self.tool_manager, self)
        self.color_popup.color_selected.connect(self._set_color)
        self.color_popup.eyedropper_requested.connect(self.eyedropper_requested.emit)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # 1. Top/Horizontal Toolbar for Drawing Tools & Colors
        self.tools_frame = QFrame(self)
        self.tools_frame.setObjectName("floatingToolbar")
        tools_layout = QHBoxLayout(self.tools_frame)
        tools_layout.setContentsMargins(6, 4, 6, 4)
        tools_layout.setSpacing(4)

        self.tool_button_group = QButtonGroup(self)
        self.tool_button_group.setExclusive(True)
        self.tool_buttons = {}

        def _add_tool_btn(tool_type: ToolType, icon_name: str, tooltip: str) -> QToolButton:
            btn = QToolButton(self.tools_frame)
            btn.setIcon(get_icon(icon_name, "#E2E8F0"))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tool_button_group.addButton(btn)
            tools_layout.addWidget(btn)
            self.tool_buttons[tool_type] = btn
            btn.clicked.connect(lambda checked, t=tool_type: self._select_tool(t))
            return btn

        # Group 1: Temel Çizim ve Şekiller (Drawing & Shapes)
        drawing_tools = [
            (ToolType.SELECT, "select", tr("tool_select")),
            (ToolType.PEN, "pen", tr("tool_pen")),
            (ToolType.HIGHLIGHTER, "highlighter", tr("tool_highlighter")),
            (ToolType.ARROW, "arrow", tr("tool_arrow")),
            (ToolType.LINE, "line", tr("tool_line")),
            (ToolType.RECTANGLE, "rect", tr("tool_rectangle")),
            (ToolType.ELLIPSE, "ellipse", tr("tool_ellipse")),
            (ToolType.TEXT, "text", tr("tool_text")),
        ]
        for t_type, icon_n, tip in drawing_tools:
            _add_tool_btn(t_type, icon_n, tip)

        # Divider 1: Ölçüm Araçları
        tools_layout.addWidget(self._create_divider())

        # Group 2: Hassas Ölçüm ve İnceleme Araçları (Measurement & Inspection)
        _add_tool_btn(ToolType.RULER, "ruler", "Mesafe ve Boyut Cetveli (Measurement Ruler)")
        _add_tool_btn(ToolType.MAGNIFIER, "magnifier", tr("tool_magnifier"))

        # Divider 2: Gizlilik ve Sansür
        tools_layout.addWidget(self._create_divider())

        # Group 3: Gizlilik ve Sansür (Privacy & Redaction)
        _add_tool_btn(ToolType.BLUR, "blur", tr("tool_blur"))
        _add_tool_btn(ToolType.PIXELATE, "pixelate", tr("tool_pixelate"))

        if self.tool_manager.active_tool in self.tool_buttons:
            self.tool_buttons[self.tool_manager.active_tool].setChecked(True)
        elif ToolType.SELECT in self.tool_buttons:
            self.tool_buttons[ToolType.SELECT].setChecked(True)

        # Divider 3: Renk Paleti
        tools_layout.addWidget(self._create_divider())

        # Curated Quick Color Palette Chips (10 Colors)
        self.color_chips.clear()
        for color_hex in DEFAULT_PALETTE:
            chip = ColorSwatchButton(
                color_hex=color_hex,
                size=20,
                is_selected=(color_hex.upper() == self.tool_manager.color.upper()),
                parent=self.tools_frame,
            )
            chip.color_clicked.connect(self._set_color)
            tools_layout.addWidget(chip)
            self.color_chips.append(chip)

        # Advanced Color Palette / More Colors Button
        self.palette_btn = QToolButton(self.tools_frame)
        self.palette_btn.setIcon(get_icon("palette", "#F59E0B", 18))
        self.palette_btn.setIconSize(QSize(18, 18))
        self.palette_btn.setToolTip(tr("tool_color_palette"))
        self.palette_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.palette_btn.clicked.connect(self._toggle_color_popup)
        tools_layout.addWidget(self.palette_btn)

        # Divider 4: Nitelik Seçiciler
        tools_layout.addWidget(self._create_divider())

        # Stroke Width Combo
        self.stroke_combo = QComboBox(self.tools_frame)
        for w in STROKE_WIDTH_OPTIONS:
            self.stroke_combo.addItem(f"{w}px", w)
        self.stroke_combo.setCurrentIndex(2)  # 3px
        self.stroke_combo.setToolTip(tr("tool_stroke_width"))
        self.stroke_combo.currentIndexChanged.connect(self._on_stroke_changed)
        tools_layout.addWidget(self.stroke_combo)

        # Font Size Combo (px)
        self.font_size_combo = QComboBox(self.tools_frame)
        for fs in FONT_SIZE_OPTIONS:
            self.font_size_combo.addItem(f"{fs}px", fs)
        fs_idx = self.font_size_combo.findData(self.tool_manager.font_size)
        if fs_idx >= 0:
            self.font_size_combo.setCurrentIndex(fs_idx)
        else:
            self.font_size_combo.setCurrentIndex(4)  # 18px default
        self.font_size_combo.setToolTip(tr("tool_font_size"))
        self.font_size_combo.currentIndexChanged.connect(self._on_font_size_changed)
        tools_layout.addWidget(self.font_size_combo)

        # Quick Blur Intensity Combo
        self.blur_combo = QComboBox(self.tools_frame)
        self.blur_combo.addItem(tr("blur_level_low"), 8)
        self.blur_combo.addItem(tr("blur_level_medium"), 15)
        self.blur_combo.addItem(tr("blur_level_high"), 25)
        self.blur_combo.addItem(tr("blur_level_max"), 40)
        self.blur_combo.setToolTip(tr("tool_blur_intensity"))
        b_idx = self.blur_combo.findData(self.tool_manager.blur_radius)
        if b_idx >= 0:
            self.blur_combo.setCurrentIndex(b_idx)
        else:
            self.blur_combo.setCurrentIndex(1)
        self.blur_combo.currentIndexChanged.connect(self._on_blur_changed)
        tools_layout.addWidget(self.blur_combo)

        main_layout.addWidget(self.tools_frame)

        # 2. Bottom/Actions Bar (Dropdown Menus, Undo/Redo, Copy, Save, Close)
        self.actions_frame = QFrame(self)
        self.actions_frame.setObjectName("floatingToolbar")
        actions_layout = QHBoxLayout(self.actions_frame)
        actions_layout.setContentsMargins(6, 4, 6, 4)
        actions_layout.setSpacing(5)

        menu_stylesheet = (
            "QMenu { background-color: #0F172A; color: #F8FAFC; border: 1px solid rgba(255, 255, 255, 0.15); "
            "border-radius: 10px; padding: 6px; font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; "
            "font-weight: 500; font-size: 13px; } "
            "QMenu::item { background-color: transparent; color: #F1F5F9; padding: 8px 26px 8px 12px; margin: 2px 4px; border-radius: 6px; } "
            "QMenu::item:selected { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #4F46E5); color: #FFFFFF; font-weight: 600; } "
            "QMenu::item:disabled { color: #64748B; } "
            "QMenu::separator { height: 1px; background-color: rgba(255, 255, 255, 0.12); margin: 4px 6px; }"
        )

        dropdown_btn_style = (
            "QToolButton { background-color: rgba(30, 41, 59, 0.92); color: #F1F5F9; border: 1px solid rgba(255, 255, 255, 0.14); "
            "border-radius: 7px; padding: 5px 11px; font-weight: 600; font-size: 12px; } "
            "QToolButton:hover { background-color: rgba(51, 65, 85, 0.95); border-color: rgba(255, 255, 255, 0.28); color: #FFFFFF; } "
            "QToolButton:pressed { background-color: #0F172A; } "
            "QToolButton::menu-indicator { image: none; width: 0px; }"
        )

        # Dropdown 1: Seri Çekim (Multi-Shot / Screenshot Session)
        self.session_btn = QToolButton(self.actions_frame)
        self.session_btn.setText("Seri Çekim ▾")
        self.session_btn.setIcon(get_icon("camera", "#34D399", 16))
        self.session_btn.setIconSize(QSize(16, 16))
        self.session_btn.setStyleSheet(dropdown_btn_style)
        self.session_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.session_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.session_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.session_btn.setToolTip("Seri Ekran Görüntüsü Oturumu İşlemleri")

        session_menu = QMenu(self.session_btn)
        session_menu.setStyleSheet(menu_stylesheet)

        act_new_sess = session_menu.addAction(get_icon("camera", "#34D399", 16), "Yeni Seri Ekran Görüntüsü Başlat")
        act_new_sess.triggered.connect(self.new_session_requested.emit)

        act_add_sess = session_menu.addAction(get_icon("camera", "#38BDF8", 16), "Mevcut Seri Oturuma Ekle")
        act_add_sess.triggered.connect(self.add_to_session_requested.emit)

        session_menu.addSeparator()
        act_open_sess = session_menu.addAction(get_icon("folder", "#A5B4FC", 16), "Seri Oturum Galerisini Aç")
        act_open_sess.triggered.connect(self.open_session_requested.emit)

        self.session_btn.setMenu(session_menu)
        actions_layout.addWidget(self.session_btn)

        # Dropdown 2: Akıllı Analiz & Araçlar (OCR, QR, Privacy, Scrolling, GIF)
        self.tools_btn = QToolButton(self.actions_frame)
        self.tools_btn.setText("Akıllı Araçlar ▾")
        self.tools_btn.setIcon(get_icon("sparkles", "#38BDF8", 16))
        self.tools_btn.setIconSize(QSize(16, 16))
        self.tools_btn.setStyleSheet(dropdown_btn_style)
        self.tools_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.tools_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tools_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tools_btn.setToolTip("Akıllı Metin (OCR), QR Kod, Otomatik Gizlilik ve GIF Araçları")

        tools_menu = QMenu(self.tools_btn)
        tools_menu.setStyleSheet(menu_stylesheet)

        act_ocr = tools_menu.addAction(get_icon("ocr", "#38BDF8", 16), "Metin Çıkar (OCR)  [Ctrl+Shift+O]")
        act_ocr.triggered.connect(self.extract_text_requested.emit)

        act_qr = tools_menu.addAction(get_icon("qr_code", "#38BDF8", 16), "QR Kod Algıla & Çözümle")
        act_qr.triggered.connect(self.qr_scan_requested.emit)

        act_privacy = tools_menu.addAction(get_icon("privacy", "#38BDF8", 16), "Smart Privacy (Gizlilik Maskesi)  [Ctrl+Shift+P]")
        act_privacy.triggered.connect(self.privacy_requested.emit)

        tools_menu.addSeparator()

        act_panorama = tools_menu.addAction(get_icon("panorama", "#34D399", 16), tr("action_panorama"))
        act_panorama.triggered.connect(self.panorama_requested.emit)

        act_scroll = tools_menu.addAction(get_icon("scroll", "#A5B4FC", 16), "Kayan Ekran Yakalama (Scrolling)")
        act_scroll.triggered.connect(self.scrolling_requested.emit)

        act_gif = tools_menu.addAction(get_icon("gif", "#F472B6", 16), "Ekran GIF Kaydet")
        act_gif.triggered.connect(self.record_gif_requested.emit)

        self.tools_btn.setMenu(tools_menu)
        actions_layout.addWidget(self.tools_btn)

        # Dropdown 3: Ölçüm & Stüdyo (Measurement Studio)
        self.measure_btn = QToolButton(self.actions_frame)
        self.measure_btn.setText("Ölçüm & Stüdyo ▾")
        self.measure_btn.setIcon(get_icon("ruler", "#38BDF8", 16))
        self.measure_btn.setIconSize(QSize(16, 16))
        self.measure_btn.setStyleSheet(dropdown_btn_style)
        self.measure_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.measure_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.measure_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.measure_btn.setToolTip("Profesyonel Piksel, Açı ve Koordinat Ölçüm Stüdyosu")

        measure_menu = QMenu(self.measure_btn)
        measure_menu.setStyleSheet(menu_stylesheet)

        act_measure_studio = measure_menu.addAction(get_icon("ruler", "#38BDF8", 16), "Ölçüm Stüdyosunda Aç (Measurement Studio)")
        act_measure_studio.triggered.connect(self.measure_requested.emit)

        self.measure_btn.setMenu(measure_menu)
        actions_layout.addWidget(self.measure_btn)

        # Dropdown 4: Paylaşım & Favoriler (Favorites, Upload, History, Vault, PDF, Optimizer)
        self.export_btn = QToolButton(self.actions_frame)
        self.export_btn.setText("Paylaşım & Dışa Aktar ▾")
        self.export_btn.setIcon(get_icon("share", "#818CF8", 16))
        self.export_btn.setIconSize(QSize(16, 16))
        self.export_btn.setStyleSheet(dropdown_btn_style)
        self.export_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.export_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setToolTip("Favoriler, Bulut Paylaşımı, Geçmiş, Kasa ve Dışa Aktarım")

        export_menu = QMenu(self.export_btn)
        export_menu.setStyleSheet(menu_stylesheet)

        act_toggle_fav = export_menu.addAction(get_icon("star_filled", "#FBBF24", 16), "Favorilere Ekle / Çıkar  [Ctrl+Shift+F]")
        act_toggle_fav.triggered.connect(self.favorite_toggled.emit)

        act_open_favs = export_menu.addAction(get_icon("star", "#FBBF24", 16), "Favoriler Galerisini Aç...")
        act_open_favs.triggered.connect(self.open_favorites_gallery_requested.emit)

        export_menu.addSeparator()

        act_upload = export_menu.addAction(get_icon("cloud_upload", "#34D399", 16), "ImgBB'ye Yükle ve Paylaş")
        act_upload.triggered.connect(self.upload_requested.emit)

        act_history = export_menu.addAction(get_icon("cloud_upload", "#38BDF8", 16), "Paylaşım Geçmişi (Upload History)")
        act_history.triggered.connect(self.open_share_history_requested.emit)

        export_menu.addSeparator()

        act_vault = export_menu.addAction(get_icon("vault", "#FBBF24", 16), "Şifreli Kasaya Kaydet (Secure Vault)")
        act_vault.triggered.connect(self.save_to_vault_requested.emit)

        act_pdf = export_menu.addAction(get_icon("pdf", "#94A3B8", 16), "PDF Olarak Dışa Aktar / Yazdır")
        act_pdf.triggered.connect(self.export_pdf_requested.emit)

        act_opt = export_menu.addAction(get_icon("optimize", "#38BDF8", 16), "Görseli Optimize Et (Sıkıştır)")
        act_opt.triggered.connect(self.optimize_requested.emit)

        export_menu.addSeparator()

        self.act_watermark = export_menu.addAction("Filigranı Etkinleştir (Canlı Önizleme)")
        self.act_watermark.setCheckable(True)
        self.act_watermark.toggled.connect(self.watermark_toggled.emit)

        self.act_info_banner = export_menu.addAction("Görüntü Altına Bilgi Bandı Ekle")
        self.act_info_banner.setCheckable(True)
        self.act_info_banner.toggled.connect(self.info_banner_toggled.emit)

        self.export_btn.setMenu(export_menu)
        actions_layout.addWidget(self.export_btn)

        actions_layout.addWidget(self._create_divider())

        # Undo / Redo
        self.undo_btn = QToolButton(self.actions_frame)
        self.undo_btn.setIcon(get_icon("undo", "#E2E8F0", 18))
        self.undo_btn.setIconSize(QSize(18, 18))
        self.undo_btn.setToolTip(tr("tool_undo"))
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo_requested.emit)
        actions_layout.addWidget(self.undo_btn)

        self.redo_btn = QToolButton(self.actions_frame)
        self.redo_btn.setIcon(get_icon("redo", "#E2E8F0", 18))
        self.redo_btn.setIconSize(QSize(18, 18))
        self.redo_btn.setToolTip(tr("tool_redo"))
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.redo_requested.emit)
        actions_layout.addWidget(self.redo_btn)

        actions_layout.addWidget(self._create_divider())

        # Quick Favorite Toggle button
        self.favorite_btn = QToolButton(self.actions_frame)
        self.favorite_btn.setIcon(get_icon("star", "#94A3B8", 18))
        self.favorite_btn.setIconSize(QSize(18, 18))
        self.favorite_btn.setToolTip(tr("tool_favorite"))
        self.favorite_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.favorite_btn.clicked.connect(self.favorite_toggled.emit)
        actions_layout.addWidget(self.favorite_btn)

        # Copy button (Primary Action)
        self.copy_btn = QPushButton(tr("action_copy"), self.actions_frame)
        self.copy_btn.setObjectName("primaryActionBtn")
        self.copy_btn.setIcon(get_icon("copy", "#FFFFFF", 16))
        self.copy_btn.setIconSize(QSize(16, 16))
        self.copy_btn.setToolTip(tr("action_copy_tooltip"))
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self.copy_requested.emit)
        actions_layout.addWidget(self.copy_btn)

        # Save button
        self.save_btn = QPushButton(tr("action_save"), self.actions_frame)
        self.save_btn.setObjectName("primaryActionBtn")
        self.save_btn.setIcon(get_icon("save", "#FFFFFF", 16))
        self.save_btn.setIconSize(QSize(16, 16))
        self.save_btn.setToolTip(tr("action_save_tooltip"))
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self.save_requested.emit)
        actions_layout.addWidget(self.save_btn)

        # Cancel / Close button
        self.cancel_btn = QPushButton(tr("action_cancel"), self.actions_frame)
        self.cancel_btn.setObjectName("cancelActionBtn")
        self.cancel_btn.setIcon(get_icon("close", "#FDA4AF", 16))
        self.cancel_btn.setIconSize(QSize(16, 16))
        self.cancel_btn.setToolTip(tr("action_cancel_tooltip"))
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        actions_layout.addWidget(self.cancel_btn)

        main_layout.addWidget(self.actions_frame)

    def set_is_favorite(self, is_fav: bool) -> None:
        """Updates favorite button visual state and tooltip."""
        if is_fav:
            self.favorite_btn.setIcon(get_icon("star_filled", "#FBBF24", 18))
            self.favorite_btn.setToolTip(tr("fav_remove"))
        else:
            self.favorite_btn.setIcon(get_icon("star", "#94A3B8", 18))
            self.favorite_btn.setToolTip(tr("tool_favorite"))

    def _create_divider(self) -> QFrame:
        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("background-color: #4A5568; max-width: 1px; margin: 2px 4px;")
        return divider

    def _connect_signals(self) -> None:
        self.history_manager.history_changed.connect(self._on_history_changed)
        self.tool_manager.tool_changed.connect(self._on_tool_changed_externally)
        self.tool_manager.font_size_changed.connect(self._on_font_size_changed_externally)
        self.tool_manager.color_changed.connect(self._on_color_changed_externally)

    def _select_tool(self, tool_type: ToolType) -> None:
        if self.tool_manager.active_tool == tool_type and tool_type != ToolType.SELECT:
            self.tool_manager.active_tool = ToolType.SELECT
        else:
            self.tool_manager.active_tool = tool_type

    def _set_color(self, color_hex: str) -> None:
        hex_norm = color_hex.upper()
        self.tool_manager.color = hex_norm
        self._update_color_chips(hex_norm)

    def _on_color_changed_externally(self, color_hex: str) -> None:
        self._update_color_chips(color_hex.upper())

    def _update_color_chips(self, color_hex: str) -> None:
        norm = color_hex.upper()
        for chip in self.color_chips:
            chip.set_selected(chip.color_hex == norm)

    def _toggle_color_popup(self) -> None:
        if self.color_popup.isVisible():
            self.color_popup.hide()
        else:
            parent_w = self.parentWidget()
            screen_rect = parent_w.rect() if parent_w else QRect(0, 0, 1920, 1080)
            btn_rect = self.palette_btn.rect()
            global_pt = self.palette_btn.mapToGlobal(QPoint(0, 0))
            target_rect = QRect(global_pt, btn_rect.size())
            self.color_popup.show_above_or_below(target_rect, screen_rect)

    def _on_stroke_changed(self, index: int) -> None:
        val = self.stroke_combo.currentData()
        if val is not None:
            self.tool_manager.stroke_width = int(val)


    def _on_font_size_changed(self, index: int) -> None:
        val = self.font_size_combo.currentData()
        if val is not None:
            self.tool_manager.font_size = int(val)

    def _on_blur_changed(self, index: int) -> None:
        val = self.blur_combo.currentData()
        if val is not None:
            self.tool_manager.blur_radius = int(val)

    def _on_history_changed(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_btn.setEnabled(can_undo)
        self.redo_btn.setEnabled(can_redo)

    def _on_tool_changed_externally(self, tool_type: ToolType) -> None:
        for t, btn in self.tool_buttons.items():
            btn.setChecked(t == tool_type)

    def _on_font_size_changed_externally(self, size: int) -> None:
        idx = self.font_size_combo.findData(size)
        if idx >= 0 and self.font_size_combo.currentIndex() != idx:
            self.font_size_combo.setCurrentIndex(idx)

    def set_output_toggles(self, watermark_enabled: bool, banner_enabled: bool) -> None:
        """Sync toolbar checkable actions with current config state."""
        if hasattr(self, "act_watermark"):
            self.act_watermark.blockSignals(True)
            self.act_watermark.setChecked(bool(watermark_enabled))
            self.act_watermark.blockSignals(False)
        if hasattr(self, "act_info_banner"):
            self.act_info_banner.blockSignals(True)
            self.act_info_banner.setChecked(bool(banner_enabled))
            self.act_info_banner.blockSignals(False)

    def position_near_selection(self, sel_rect: QRect, screen_rect: QRect) -> None:
        """Position the toolbar dynamically around the selection rectangle without clipping."""
        self.adjustSize()
        tb_w = self.width()
        tb_h = self.height()
        margin = 8

        x = sel_rect.right() - tb_w
        if x < screen_rect.left() + margin:
            x = sel_rect.left()
        if x + tb_w > screen_rect.right() - margin:
            x = screen_rect.right() - tb_w - margin

        y = sel_rect.bottom() + margin
        if y + tb_h > screen_rect.bottom() - margin:
            y = sel_rect.top() - tb_h - margin
            if y < screen_rect.top() + margin:
                y = sel_rect.bottom() - tb_h - margin

        self.move(max(screen_rect.left() + margin, x), max(screen_rect.top() + margin, y))
        self.show()
        self.raise_()

