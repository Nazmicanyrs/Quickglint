"""Modern, Stitch-inspired Settings Dialog with sidebar navigation, top category quick cards, elevated glass cards, and iOS-style toggle switches."""

from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from config.config_manager import ConfigManager
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QIcon, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.services.autostart_service import AutostartService
from app.ui.hotkey_edit import HotkeyRecorderEdit
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.ui.widgets import SettingToggleRow, SettingsCard, SettingsToggleSwitch
from app.utils.constants import (
    APP_AUTHOR,
    APP_AUTHOR_URL,
    APP_DESCRIPTION,
    APP_LICENSE,
    APP_NAME,
    APP_VERSION,
    DEFAULT_PALETTE,
    STROKE_WIDTH_OPTIONS,
    SUPPORTED_IMAGE_FORMATS,
)
from app.utils.helpers import get_app_icon
from app.utils.i18n import get_language, set_language, tr


class SidebarNavButton(QPushButton):
    """Left sidebar category button with active gradient state."""

    def __init__(self, icon_name: str, text: str, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.index = index
        self.icon_name = icon_name
        self.label_text = text
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self._update_style(False)

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self._update_style(active)

    def _update_style(self, active: bool) -> None:
        if active:
            self.setIcon(get_icon(self.icon_name, "#FFFFFF", 18))
            self.setIconSize(QSize(18, 18))
            self.setText(f"  {self.label_text}")
            self.setStyleSheet(
                """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4F46E5, stop:1 #6366F1);
                    color: #FFFFFF;
                    border: none;
                    border-radius: 10px;
                    font-weight: 700;
                    font-size: 13px;
                    text-align: left;
                    padding-left: 14px;
                }
                """
            )
        else:
            self.setIcon(get_icon(self.icon_name, "#94A3B8", 18))
            self.setIconSize(QSize(18, 18))
            self.setText(f"  {self.label_text}")
            self.setStyleSheet(
                """
                QPushButton {
                    background: transparent;
                    color: #94A3B8;
                    border: none;
                    border-radius: 10px;
                    font-weight: 600;
                    font-size: 13px;
                    text-align: left;
                    padding-left: 14px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.06);
                    color: #F1F5F9;
                }
                """
            )


class TopCategoryCard(QPushButton):
    """Top horizontal quick navigation category card."""

    def __init__(self, icon_name: str, title: str, index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.index = index
        self.icon_name = icon_name
        self.card_title = title
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(92, 58)
        self.setMaximumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Internal clean vertical layout separating Icon and Label cleanly
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(6, 6, 6, 6)
        card_layout.setSpacing(3)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon_lbl = QLabel(self)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        card_layout.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(self.card_title, self)
        self._text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        card_layout.addWidget(self._text_lbl)

        self._update_style(False)

    def set_active(self, active: bool) -> None:
        self.setChecked(active)
        self._update_style(active)

    def _update_style(self, active: bool) -> None:
        if active:
            self._icon_lbl.setPixmap(get_icon(self.icon_name, "#818CF8", 20).pixmap(20, 20))
            self._text_lbl.setStyleSheet("color: #818CF8; font-weight: 700; font-size: 11px; background: transparent;")
            self.setStyleSheet(
                """
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(79, 70, 229, 0.35), stop:1 rgba(99, 102, 241, 0.18));
                    border: 1.5px solid #6366F1;
                    border-radius: 10px;
                }
                """
            )
        else:
            self._icon_lbl.setPixmap(get_icon(self.icon_name, "#94A3B8", 20).pixmap(20, 20))
            self._text_lbl.setStyleSheet("color: #94A3B8; font-weight: 500; font-size: 11px; background: transparent;")
            self.setStyleSheet(
                """
                QPushButton {
                    background: rgba(18, 24, 38, 0.60);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 10px;
                }
                QPushButton:hover {
                    background: rgba(30, 41, 59, 0.85);
                    border-color: rgba(255, 255, 255, 0.18);
                }
                """
            )


class SettingsDialog(QDialog):
    """Ultra-modern Stitch-grade configuration dialog window."""

    settings_saved = Signal()

    def __init__(self, config_manager: ConfigManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle(tr("settings_window_title"))

        # Screen-aware responsive sizing (adapts gracefully from 1366x768 up to 4K displays)
        screen = QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            diag_w = min(1120, max(840, int(avail.width() * 0.80)))
            diag_h = min(740, max(560, int(avail.height() * 0.82)))
            self.resize(diag_w, diag_h)
            self.setMinimumSize(min(800, avail.width() - 40), min(500, avail.height() - 60))
        else:
            self.resize(1060, 720)
            self.setMinimumSize(820, 520)

        self.setStyleSheet(
            DARK_THEME_QSS
            + """
            QDialog {
                background-color: #0B0F19;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.18);
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.32);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 6px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(255, 255, 255, 0.16);
                min-width: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:horizontal:hover {
                background: rgba(255, 255, 255, 0.28);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            """
        )

        self._hotkey_editors: Dict[str, HotkeyRecorderEdit] = {}
        self.sidebar_buttons: List[SidebarNavButton] = []
        self.top_cards: List[TopCategoryCard] = []

        self._setup_ui()
        self._load_values()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # -------------------------------------------------------------
        # 1. Custom Title Bar
        # -------------------------------------------------------------
        self.title_bar = QFrame(self)
        self.title_bar.setFixedHeight(46)
        self.title_bar.setStyleSheet(
            """
            QFrame {
                background-color: #0B0F19;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            }
            """
        )
        tb_layout = QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(18, 0, 14, 0)
        tb_layout.setSpacing(10)

        # App Logo & Title
        logo_lbl = QLabel(self.title_bar)
        logo_lbl.setPixmap(get_app_icon().pixmap(22, 22))
        tb_layout.addWidget(logo_lbl)

        win_title = QLabel(f"{APP_NAME} - Ayarlar", self.title_bar)
        win_title.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 13.5px;")
        tb_layout.addWidget(win_title)

        tb_layout.addStretch()

        root_layout.addWidget(self.title_bar)

        # -------------------------------------------------------------
        # 2. Main Body (Sidebar + Content Stack)
        # -------------------------------------------------------------
        body_widget = QWidget(self)
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # --- Left Sidebar ---
        self.sidebar = QFrame(body_widget)
        self.sidebar.setFixedWidth(220)
        self.sidebar.setStyleSheet(
            """
            QFrame {
                background-color: #0D1220;
                border-right: 1px solid rgba(255, 255, 255, 0.08);
            }
            """
        )
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(14, 16, 14, 16)
        sidebar_layout.setSpacing(6)

        categories = [
            ("settings", "Genel"),
            ("keyboard", "Kısayollar"),
            ("privacy", "Smart Privacy"),
            ("ocr", "OCR / Metin"),
            ("qr_code", "QR Kod"),
            ("gif", "Scrolling GIF"),
            ("camera", "Görüntü"),
            ("pen", "Editör"),
            ("cloud_upload", "Yükle / Paylaş"),
            ("panorama", "Panorama"),
            ("info", "Hakkında"),
        ]

        for i, (icon_name, cat_title) in enumerate(categories):
            btn = SidebarNavButton(icon_name, cat_title, i, self.sidebar)
            btn.clicked.connect(lambda checked=False, idx=i: self._switch_tab(idx))
            self.sidebar_buttons.append(btn)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # Reset to Defaults button at bottom of sidebar
        self.reset_btn = QPushButton("  Varsayılanlara Sıfırla", self.sidebar)
        self.reset_btn.setIcon(get_icon("reset", "#94A3B8", 16))
        self.reset_btn.setIconSize(QSize(16, 16))
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(255, 255, 255, 0.04);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 9px 12px;
                font-weight: 500;
                font-size: 12px;
                text-align: left;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #F1F5F9;
                border-color: rgba(255, 255, 255, 0.16);
            }
            """
        )
        self.reset_btn.clicked.connect(self._on_reset_defaults)
        sidebar_layout.addWidget(self.reset_btn)

        body_layout.addWidget(self.sidebar)

        # --- Right Main Content Area ---
        content_area = QWidget(body_widget)
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(20, 16, 20, 16)
        content_layout.setSpacing(14)

        # 1. Top Horizontal Quick Category Cards Ribbon (Scrollable and Adaptive)
        top_scroll = QScrollArea(content_area)
        top_scroll.setWidgetResizable(True)
        top_scroll.setFixedHeight(74)
        top_scroll.setFrameShape(QFrame.Shape.NoFrame)
        top_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        top_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        top_scroll.setStyleSheet("background: transparent; border: none;")

        top_cards_container = QWidget()
        top_cards_container.setStyleSheet("background: transparent;")
        top_cards_layout = QHBoxLayout(top_cards_container)
        top_cards_layout.setContentsMargins(0, 0, 0, 4)
        top_cards_layout.setSpacing(8)

        for i, (icon_name, cat_title) in enumerate(categories):
            tcard = TopCategoryCard(icon_name, cat_title, i, top_cards_container)
            tcard.clicked.connect(lambda checked=False, idx=i: self._switch_tab(idx))
            self.top_cards.append(tcard)
            top_cards_layout.addWidget(tcard)

        top_scroll.setWidget(top_cards_container)
        content_layout.addWidget(top_scroll)

        # 2. Scrollable Tab Pages (QStackedWidget)
        self.stack = QStackedWidget(content_area)

        # Build each tab page
        self._build_general_tab()
        self._build_hotkeys_tab()
        self._build_privacy_tab()
        self._build_ocr_tab()
        self._build_qr_tab()
        self._build_scrolling_gif_tab()
        self._build_image_tab()
        self._build_editor_tab()
        self._build_upload_tab()
        self._build_panorama_tab()
        self._build_about_tab()

        content_layout.addWidget(self.stack)

        # 3. Bottom Action Bar (İptal + Kaydet)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(12)

        footer_layout.addStretch()

        self.cancel_btn = QPushButton(tr("btn_cancel"), content_area)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 8px;
                padding: 8px 24px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.14);
                border-color: rgba(255, 255, 255, 0.24);
                color: #FFFFFF;
            }
            """
        )
        self.cancel_btn.clicked.connect(self.reject)
        footer_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("✓  " + tr("btn_save_settings"), content_area)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3B82F6, stop:1 #4F46E5);
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 28px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #60A5FA, stop:1 #6366F1);
            }
            QPushButton:pressed {
                background: #1E40AF;
            }
            """
        )
        self.save_btn.clicked.connect(self._on_save)
        footer_layout.addWidget(self.save_btn)

        content_layout.addLayout(footer_layout)

        body_layout.addWidget(content_area)
        root_layout.addWidget(body_widget)

        # Set default active tab
        self._switch_tab(0)

    def _switch_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for btn in self.sidebar_buttons:
            btn.set_active(btn.index == index)
        for card in self.top_cards:
            card.set_active(card.index == index)

    def _create_scrollable_page(self) -> Tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 4, 10, 4)
        layout.setSpacing(14)

        scroll.setWidget(container)
        return scroll, layout

    # =========================================================================
    # Tab 1: General (Genel)
    # =========================================================================
    def _build_general_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        # Card 1: Uygulama Dili / Language
        lang_card = SettingsCard("globe", "Uygulama Dili / Language", f"{APP_NAME} arayüz dili.")
        self.lang_combo = QComboBox(lang_card)
        self.lang_combo.addItem("Türkçe (Turkish)", "tr")
        self.lang_combo.addItem("English (İngilizce)", "en")
        self.lang_combo.setStyleSheet(
            """
            QComboBox {
                background-color: rgba(10, 14, 23, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 8px 14px;
                color: #FFFFFF;
                font-size: 13px;
            }
            QComboBox:hover {
                border-color: #6366F1;
            }
            """
        )
        lang_card.add_widget(self.lang_combo)
        page_layout.addWidget(lang_card)

        # Card 2: Başlangıç ve Davranış
        startup_card = SettingsCard("rocket", "Başlangıç ve Davranış", "")
        self.autostart_cb = SettingsToggleSwitch(startup_card)
        self.minimize_tray_cb = SettingsToggleSwitch(startup_card)
        self.show_notif_cb = SettingsToggleSwitch(startup_card)

        startup_card.add_widget(
            SettingToggleRow(
                "monitor",
                "Windows açılışında otomatik başlat",
                f"Bilgisayar açıldığında {APP_NAME}'i otomatik olarak başlat.",
                self.autostart_cb,
                startup_card,
            )
        )
        startup_card.add_widget(
            SettingToggleRow(
                "inbox",
                "Kapatıldığında sistem tepsisine küçült",
                "Uygulamayı kapatmak yerine sistem tepsisine küçült.",
                self.minimize_tray_cb,
                startup_card,
            )
        )
        startup_card.add_widget(
            SettingToggleRow(
                "bell",
                "Kopyalama / kaydetme bildirimlerini göster",
                "Kopyalama veya kaydetme işlemlerinden sonra bildirim göster.",
                self.show_notif_cb,
                startup_card,
            )
        )
        page_layout.addWidget(startup_card)

        # Card 3: Varsayılan Kayıt Klasörü
        folder_card = SettingsCard("folder", "Varsayılan Kayıt Klasörü", "Ekran görüntülerinin varsayılan olarak kaydedileceği klasör.")
        f_row = QHBoxLayout()
        f_row.setSpacing(10)

        self.folder_edit = QLineEdit(folder_card)
        self.folder_edit.setStyleSheet(
            """
            QLineEdit {
                background-color: rgba(10, 14, 23, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 8px 12px;
                color: #FFFFFF;
                font-size: 13px;
            }
            """
        )
        f_row.addWidget(self.folder_edit)

        self.browse_btn = QPushButton("  " + tr("btn_browse"), folder_card)
        self.browse_btn.setIcon(get_icon("folder", "#FFFFFF", 16))
        self.browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_btn.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3B82F6, stop:1 #4F46E5);
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #60A5FA, stop:1 #6366F1);
            }
            """
        )
        self.browse_btn.clicked.connect(self._on_browse_folder)
        f_row.addWidget(self.browse_btn)

        folder_card.add_layout(f_row)
        page_layout.addWidget(folder_card)

        # Card 3.5: Akıllı Dosya Adlandırma (Smart File Naming)
        from app.services.naming_service import AVAILABLE_NAMING_VARIABLES, DEFAULT_NAMING_TEMPLATE

        naming_card = SettingsCard(
            "pen",
            "Akıllı Dosya Adlandırma (Şablon)",
            "Kayıt edilen dosyaların adını dinamik değişkenlerle özelleştirin. Hatalı şablonda varsayılana düşülür.",
        )
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(8)

        self.naming_template_edit = QLineEdit(naming_card)
        self.naming_template_edit.setPlaceholderText(DEFAULT_NAMING_TEMPLATE)
        self.naming_template_edit.setStyleSheet(
            """
            QLineEdit {
                background-color: rgba(10, 14, 23, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 8px 12px;
                color: #FFFFFF;
                font-size: 13px;
                font-family: 'Consolas', monospace;
            }
            """
        )
        self.naming_template_edit.textChanged.connect(self._update_naming_preview)
        tpl_row.addWidget(self.naming_template_edit, stretch=1)

        self.btn_reset_naming = QPushButton("Varsayılan", naming_card)
        self.btn_reset_naming.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_naming.setStyleSheet(
            "QPushButton { background-color: rgba(255, 255, 255, 0.08); color: #E2E8F0; padding: 7px 12px; border-radius: 6px; font-size: 12px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.16); }"
        )
        self.btn_reset_naming.clicked.connect(lambda: self.naming_template_edit.setText(DEFAULT_NAMING_TEMPLATE))
        tpl_row.addWidget(self.btn_reset_naming)
        naming_card.add_layout(tpl_row)

        # Variable chips row
        vars_row = QHBoxLayout()
        vars_row.setSpacing(6)
        for token, desc in AVAILABLE_NAMING_VARIABLES:
            chip_btn = QPushButton(token, naming_card)
            chip_btn.setToolTip(f"{token} — {desc} (Eklemek için tıklayın)")
            chip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            chip_btn.setStyleSheet(
                "QPushButton { background-color: rgba(56, 189, 248, 0.12); color: #38BDF8; border: 1px solid rgba(56, 189, 248, 0.3); "
                "border-radius: 5px; padding: 3px 7px; font-size: 11px; font-family: 'Consolas', monospace; }"
                "QPushButton:hover { background-color: rgba(56, 189, 248, 0.25); color: #FFFFFF; }"
            )
            chip_btn.clicked.connect(lambda checked=False, t=token: self._insert_naming_token(t))
            vars_row.addWidget(chip_btn)
        vars_row.addStretch()
        naming_card.add_layout(vars_row)

        vars_desc = QLabel(
            "Değişkenler: {date} Tarih • {time} Saat • {datetime} Tarih+Saat • {n} Sayaç • "
            "{window} Pencere Başlığı • {app} Süreç Adı • {mode} Mod • {ocr} OCR İlk Satır (yalnızca OCR çalıştıysa)",
            naming_card,
        )
        vars_desc.setWordWrap(True)
        vars_desc.setStyleSheet("color: #94A3B8; font-size: 11.5px;")
        naming_card.add_widget(vars_desc)

        self.naming_preview_lbl = QLabel("", naming_card)
        self.naming_preview_lbl.setStyleSheet(
            "color: #4ADE80; font-size: 12px; font-weight: 600; font-family: 'Consolas', monospace; "
            "background-color: rgba(15, 23, 42, 0.8); padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(74, 222, 128, 0.25);"
        )
        naming_card.add_widget(self.naming_preview_lbl)
        page_layout.addWidget(naming_card)

        # Card 4: Ayarları içe / dışa aktar
        io_card = SettingsCard(
            "inbox",
            "Ayarları Yedekle / Taşı",
            "Tüm ayarlarınızı bir dosyaya aktarın veya başka bir bilgisayardan içe aktarın. "
            "API anahtarları ve Google oturum bilgileri güvenlik için dosyaya yazılmaz.",
        )
        io_row = QHBoxLayout()
        io_row.setSpacing(10)
        io_btn_style = (
            "QPushButton { background-color: rgba(255, 255, 255, 0.08); color: #FFF; padding: 8px 16px; "
            "border-radius: 8px; font-weight: 600; border: 1px solid rgba(255, 255, 255, 0.14); }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.14); }"
        )
        self.btn_export_settings = QPushButton("Ayarları Dışa Aktar...", io_card)
        self.btn_export_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_settings.setStyleSheet(io_btn_style)
        self.btn_export_settings.clicked.connect(self._on_export_settings)
        io_row.addWidget(self.btn_export_settings)

        self.btn_import_settings = QPushButton("Ayarları İçe Aktar...", io_card)
        self.btn_import_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_settings.setStyleSheet(io_btn_style)
        self.btn_import_settings.clicked.connect(self._on_import_settings)
        io_row.addWidget(self.btn_import_settings)
        io_row.addStretch()
        io_card.add_layout(io_row)
        page_layout.addWidget(io_card)

        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 2: Hotkeys (Kısayollar)
    # =========================================================================
    def _build_hotkeys_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        # 1. Ekran Yakalama Kısayolları (Capture Shortcuts)
        cap_card = SettingsCard("camera", "Ekran Yakalama Kısayolları", "Tüm ekran, pencere, bölge, panorama ve kaydırmalı ekran yakalama kısayolları.")
        cap_layout = QFormLayout()
        cap_layout.setSpacing(12)

        capture_keys = [
            ("capture_hotkey", "Ana Ekran Yakalama (Bölge / Tam Ekran)", "PrintScreen"),
            ("action_smart_window", "Akıllı Pencere / Web Yakalama", "Alt+PrintScreen"),
            ("action_panorama", "Panorama & Çoklu Ekran Birleştirme", "Ctrl+Shift+M"),
            ("action_scrolling", "Kaydırmalı Ekran Yakalama (Scrolling)", "Ctrl+Shift+L"),
            ("action_gif", "Ekran GIF Kaydedici", "Ctrl+Shift+G"),
        ]
        for key_name, key_label, default_val in capture_keys:
            ed = HotkeyRecorderEdit(default_val, cap_card)
            self._hotkey_editors[key_name] = ed
            lbl = QLabel(key_label)
            lbl.setStyleSheet("color: #FFFFFF; font-weight: 500; font-size: 12.5px;")
            cap_layout.addRow(lbl, ed)

        cap_card.add_layout(cap_layout)
        page_layout.addWidget(cap_card)

        # 2. Çizim ve Anotasyon Araçları (Drawing & Annotation Tools)
        tool_card = SettingsCard("pen", "Çizim ve Anotasyon Araçları", "Ekran görüntüsü düzenleme ve işaretleme araç kısayolları.")
        tool_layout = QFormLayout()
        tool_layout.setSpacing(12)

        drawing_keys = [
            ("tool_select", "Seç ve Taşı / İmleç Aracı", "Esc"),
            ("tool_pen", "Serbest Çizim Kalemi", "P"),
            ("tool_highlighter", "Fosforlu Kalem (Highlighter)", "H"),
            ("tool_line", "Düz Çizgi Aracı", "L"),
            ("tool_arrow", "Yön Oku Aracı", "A"),
            ("tool_rectangle", "Dikdörtgen Kutusu", "R"),
            ("tool_ellipse", "Elips ve Daire Aracı", "E"),
            ("tool_text", "Metin Ekleme Aracı", "T"),
            ("tool_blur", "Bulanıklaştırma (Blur) Aracı", "B"),
            ("tool_pixelate", "Mozaik / Pikselleştirme (Pixelate)", "M"),
            ("tool_magnifier", "Büyüteç (Magnifier) Aracı", "Z"),
        ]
        for key_name, key_label, default_val in drawing_keys:
            ed = HotkeyRecorderEdit(default_val, tool_card)
            self._hotkey_editors[key_name] = ed
            lbl = QLabel(key_label)
            lbl.setStyleSheet("color: #FFFFFF; font-weight: 500; font-size: 12.5px;")
            tool_layout.addRow(lbl, ed)

        tool_card.add_layout(tool_layout)
        page_layout.addWidget(tool_card)

        # 3. İşlem ve Düzenleme Eylemleri (Actions & Workflow)
        action_card = SettingsCard("check", "İşlem ve Stüdyo Eylemleri", "Kaydetme, kopyalama, geri alma, gizlilik ve OCR kısayolları.")
        action_layout = QFormLayout()
        action_layout.setSpacing(12)

        action_keys = [
            ("action_copy", "Panoya Kopyala", "Ctrl+C"),
            ("action_save", "Dosyaya Kaydet", "Ctrl+S"),
            ("action_undo", "Son İşlemi Geri Al", "Ctrl+Z"),
            ("action_redo", "İşlemi İleri Al", "Ctrl+Y"),
            ("action_privacy", "Akıllı Gizlilik / Hassas Veri Maskeleme", "Ctrl+Shift+P"),
            ("action_ocr", "Metin Tanıma ve Çıkarma (OCR)", "Ctrl+Shift+O"),
            ("action_copy_ocr", "OCR Metnini Panoya Kopyala", "Ctrl+Shift+C"),
            ("action_favorite", "Favorilere Ekle / Aç", "Ctrl+Shift+F"),
        ]
        for key_name, key_label, default_val in action_keys:
            ed = HotkeyRecorderEdit(default_val, action_card)
            self._hotkey_editors[key_name] = ed
            lbl = QLabel(key_label)
            lbl.setStyleSheet("color: #FFFFFF; font-weight: 500; font-size: 12.5px;")
            action_layout.addRow(lbl, ed)

        action_card.add_layout(action_layout)
        page_layout.addWidget(action_card)

        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 3: Smart Privacy
    # =========================================================================
    def _build_privacy_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        gen_card = SettingsCard("privacy", "Smart Privacy Genel Yapılandırması", "Hassas bilgileri otomatik gizleme.")
        self.priv_enabled_cb = SettingsToggleSwitch(gen_card)
        gen_card.add_widget(
            SettingToggleRow(
                "privacy",
                "Smart Privacy Özelliğini Etkinleştir",
                "Ekran görüntüsü alındığında hassas verileri otomatik tara.",
                self.priv_enabled_cb,
                gen_card,
            )
        )

        self.priv_auto_redact_cb = SettingsToggleSwitch(gen_card)
        gen_card.add_widget(
            SettingToggleRow(
                "privacy",
                "Kaydetmeden / Kopyalamadan Önce Otomatik Gizle",
                "Hassas veriler OCR ile bulunup görüntü kaydedilmeden veya kopyalanmadan önce otomatik maskelenir. "
                "Aşağıdaki veri türü seçimleri ve efekt kullanılır.",
                self.priv_auto_redact_cb,
                gen_card,
            )
        )

        eff_row = QHBoxLayout()
        eff_lbl = QLabel("Varsayılan Maskeleme Efekti:", gen_card)
        eff_lbl.setStyleSheet("color: #FFFFFF; font-weight: 600;")
        eff_row.addWidget(eff_lbl)

        self.priv_effect_combo = QComboBox(gen_card)
        self.priv_effect_combo.addItem("Mozaikleme (Pixelate)", "pixelate")
        self.priv_effect_combo.addItem("Bulanıklaştırma (Blur)", "blur")
        self.priv_effect_combo.addItem("Siyah Bant (Blackout)", "blackout")
        self.priv_effect_combo.setStyleSheet(
            """
            QComboBox {
                background-color: rgba(10, 14, 23, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                color: #FFFFFF;
            }
            """
        )
        eff_row.addWidget(self.priv_effect_combo)
        gen_card.add_layout(eff_row)

        ocr_row = QHBoxLayout()
        ocr_lbl = QLabel("OCR Motoru:", gen_card)
        ocr_lbl.setStyleSheet("color: #FFFFFF; font-weight: 600;")
        ocr_row.addWidget(ocr_lbl)

        self.priv_ocr_combo = QComboBox(gen_card)
        self.priv_ocr_combo.addItem("Otomatik (En Uygun)", "auto")
        self.priv_ocr_combo.addItem("Windows Media OCR", "windows_ocr")
        self.priv_ocr_combo.addItem("Tesseract OCR", "tesseract")
        self.priv_ocr_combo.setStyleSheet(
            """
            QComboBox {
                background-color: rgba(10, 14, 23, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                color: #FFFFFF;
            }
            """
        )
        ocr_row.addWidget(self.priv_ocr_combo)
        gen_card.add_layout(ocr_row)

        page_layout.addWidget(gen_card)

        # Detect Types Card
        types_card = SettingsCard("privacy", "Algılanacak Hassas Veri Türleri", "Otomatik gizlenecek kalıp ve desenler.")
        self.cb_det_email = SettingsToggleSwitch(types_card)
        self.cb_det_phone = SettingsToggleSwitch(types_card)
        self.cb_det_ip = SettingsToggleSwitch(types_card)
        self.cb_det_url = SettingsToggleSwitch(types_card)
        self.cb_det_api = SettingsToggleSwitch(types_card)
        self.cb_det_card = SettingsToggleSwitch(types_card)
        self.cb_det_iban = SettingsToggleSwitch(types_card)
        self.cb_det_path = SettingsToggleSwitch(types_card)

        types_card.add_widget(SettingToggleRow("", "E-posta Adresleri", "user@domain.com kalıpları", self.cb_det_email, types_card))
        types_card.add_widget(SettingToggleRow("", "Telefon Numaraları", "Uluslararası ve yerel numaralar", self.cb_det_phone, types_card))
        types_card.add_widget(SettingToggleRow("", "IP Adresleri", "IPv4 ve IPv6 adresleri", self.cb_det_ip, types_card))
        types_card.add_widget(SettingToggleRow("", "URL ve Bağlantılar", "Web bağlantıları ve parametreler", self.cb_det_url, types_card))
        types_card.add_widget(SettingToggleRow("", "API Anahtarları & Token'lar", "AWS, Stripe, OpenAI, GitHub tokenları", self.cb_det_api, types_card))
        types_card.add_widget(SettingToggleRow("", "Kredi Kartı Numaraları", "Luhn algoritması doğrulamalı kartlar", self.cb_det_card, types_card))
        types_card.add_widget(SettingToggleRow("", "IBAN ve Banka Hesapları", "Uluslararası banka hesap numaraları", self.cb_det_iban, types_card))
        types_card.add_widget(SettingToggleRow("", "Dosya ve Dizin Yolları", "C:\\Users, /home vb. sistem yolları", self.cb_det_path, types_card))

        page_layout.addWidget(types_card)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 4: OCR / Metin
    # =========================================================================
    def _build_ocr_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        ocr_card = SettingsCard("ocr", "Optik Karakter Tanıma (OCR)", "Görsellerdeki metinleri algılama ve ayıklama.")
        
        eng_row = QHBoxLayout()
        eng_lbl = QLabel("Tercih Edilen OCR Motoru:", ocr_card)
        eng_lbl.setStyleSheet("color: #FFFFFF; font-weight: 600;")
        eng_row.addWidget(eng_lbl)

        self.ocr_engine_combo = QComboBox(ocr_card)
        self.ocr_engine_combo.addItem("Otomatik (En Hızlı ve Doğru)", "auto")
        self.ocr_engine_combo.addItem("Windows Media OCR", "windows_ocr")
        self.ocr_engine_combo.addItem("Tesseract OCR", "tesseract")
        self.ocr_engine_combo.setStyleSheet(
            """
            QComboBox {
                background-color: rgba(10, 14, 23, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                color: #FFFFFF;
            }
            """
        )
        eng_row.addWidget(self.ocr_engine_combo)
        ocr_card.add_layout(eng_row)

        langs_label = QLabel("Desteklenen Diller:", ocr_card)
        langs_label.setStyleSheet("color: #FFFFFF; font-weight: 600; margin-top: 6px;")
        ocr_card.add_widget(langs_label)

        langs_grid = QHBoxLayout()
        self.ocr_lang_tr = QCheckBox("Türkçe (tr)", ocr_card)
        self.ocr_lang_en = QCheckBox("İngilizce (en)", ocr_card)
        self.ocr_lang_de = QCheckBox("Almanca (de)", ocr_card)
        self.ocr_lang_fr = QCheckBox("Fransızca (fr)", ocr_card)
        self.ocr_lang_es = QCheckBox("İspanyolca (es)", ocr_card)
        self.ocr_lang_it = QCheckBox("İtalyanca (it)", ocr_card)

        for cb in (self.ocr_lang_tr, self.ocr_lang_en, self.ocr_lang_de, self.ocr_lang_fr, self.ocr_lang_es, self.ocr_lang_it):
            cb.setStyleSheet("color: #E2E8F0; font-size: 12px;")
            langs_grid.addWidget(cb)

        ocr_card.add_layout(langs_grid)

        self.ocr_auto_detect_cb = SettingsToggleSwitch(ocr_card)
        self.ocr_enhance_contrast_cb = SettingsToggleSwitch(ocr_card)
        self.ocr_upscale_small_cb = SettingsToggleSwitch(ocr_card)

        ocr_card.add_widget(SettingToggleRow("", "Yakalama Sonrası Otomatik Metin Tara", "Seçim bitince metinleri tara", self.ocr_auto_detect_cb, ocr_card))
        ocr_card.add_widget(SettingToggleRow("", "Kontrastı Otomatik İyileştir", "Metin doğruluğunu artırmak için kontrast uygula", self.ocr_enhance_contrast_cb, ocr_card))
        ocr_card.add_widget(SettingToggleRow("", "Küçük Metinleri Büyüt", "Düşük çözünürlüklü metinleri 2x ölçekle", self.ocr_upscale_small_cb, ocr_card))

        page_layout.addWidget(ocr_card)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 5: QR Code (QR Kod)
    # =========================================================================
    def _build_qr_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        qr_card = SettingsCard("qr_code", "QR Kod Algılama ve Çözümleme", "Ekran görüntüsü içindeki QR kodları yerel ve çevrimdışı tespit et.")
        self.qr_enabled_cb = SettingsToggleSwitch(qr_card)
        self.qr_show_panel_cb = SettingsToggleSwitch(qr_card)
        self.qr_highlight_cb = SettingsToggleSwitch(qr_card)

        qr_card.add_widget(
            SettingToggleRow(
                "qr_code",
                "QR Kod Algılamayı Etkinleştir",
                "Ekran görüntüsü alındığında arka planda QR kodları tara.",
                self.qr_enabled_cb,
                qr_card,
            )
        )
        qr_card.add_widget(
            SettingToggleRow(
                "bell",
                "Sonuç Bildirim Kartını Otomatik Göster",
                "QR kod bulunduğunda floating bilgi kartını otomatik aç.",
                self.qr_show_panel_cb,
                qr_card,
            )
        )
        qr_card.add_widget(
            SettingToggleRow(
                "select",
                "QR Kodlarını Görsel Üzerinde Neon Vurgula",
                "Görüntü üzerinde QR kodların etrafına parlayan çerçeve çiz.",
                self.qr_highlight_cb,
                qr_card,
            )
        )

        page_layout.addWidget(qr_card)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 6: Scrolling GIF (Scrolling & GIF)
    # =========================================================================
    def _build_scrolling_gif_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        scroll_card = SettingsCard("scroll", "Kaydırmalı Ekran Görüntüsü (Scrolling Capture)", "Uzun web sayfaları ve belgeleri dikey birleştirme.")
        s_form = QFormLayout()
        s_form.setSpacing(12)

        self.max_captures_spin = QSpinBox(scroll_card)
        self.max_captures_spin.setRange(5, 200)
        self.max_captures_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px;")
        lbl1 = QLabel("Maksimum Kare Sayısı:")
        lbl1.setStyleSheet("color: #FFF; font-weight: 500;")
        s_form.addRow(lbl1, self.max_captures_spin)

        self.max_height_spin = QSpinBox(scroll_card)
        self.max_height_spin.setRange(1000, 100000)
        self.max_height_spin.setSingleStep(1000)
        self.max_height_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px;")
        lbl2 = QLabel("Maksimum Yükseklik (px):")
        lbl2.setStyleSheet("color: #FFF; font-weight: 500;")
        s_form.addRow(lbl2, self.max_height_spin)

        scroll_card.add_layout(s_form)
        page_layout.addWidget(scroll_card)

        gif_card = SettingsCard("gif", "GIF Ekran Kaydedici", "Seçili alandan animasyonlu GIF üretimi.")
        g_form = QFormLayout()
        g_form.setSpacing(12)

        self.gif_fps_combo = QComboBox(gif_card)
        for fps in (10, 15, 20, 24, 30):
            self.gif_fps_combo.addItem(f"{fps} FPS")
        self.gif_fps_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px;")
        lbl3 = QLabel("Kare Hızı (FPS):")
        lbl3.setStyleSheet("color: #FFF; font-weight: 500;")
        g_form.addRow(lbl3, self.gif_fps_combo)

        self.gif_duration_spin = QSpinBox(gif_card)
        self.gif_duration_spin.setRange(5, 300)
        self.gif_duration_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px;")
        lbl4 = QLabel("Maksimum Süre (Saniye):")
        lbl4.setStyleSheet("color: #FFF; font-weight: 500;")
        g_form.addRow(lbl4, self.gif_duration_spin)

        gif_card.add_layout(g_form)

        self.gif_cursor_cb = SettingsToggleSwitch(gif_card)
        self.gif_halo_cb = SettingsToggleSwitch(gif_card)
        self.gif_clicks_cb = SettingsToggleSwitch(gif_card)

        gif_card.add_widget(SettingToggleRow("", "Fare İmlecini Kaydet", "İmleç hareketlerini GIF'e dahil et", self.gif_cursor_cb, gif_card))
        gif_card.add_widget(SettingToggleRow("", "İmleç Etrafında Halka Göster", "İmleç konumunu belirginleştir", self.gif_halo_cb, gif_card))
        gif_card.add_widget(SettingToggleRow("", "Tıklama Efektlerini Göster", "Fare tıklandığında dalgalanma efekti ekle", self.gif_clicks_cb, gif_card))

        page_layout.addWidget(gif_card)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 7: Image (Görüntü)
    # =========================================================================
    def _build_image_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        img_card = SettingsCard("camera", "Görüntü Formatı ve Kalite Ayarları", "Kaydedilen ekran görüntüsü nitelikleri.")
        
        fmt_row = QHBoxLayout()
        fmt_lbl = QLabel("Varsayılan Kayıt Formatı:", img_card)
        fmt_lbl.setStyleSheet("color: #FFFFFF; font-weight: 600;")
        fmt_row.addWidget(fmt_lbl)

        self.format_combo = QComboBox(img_card)
        for fmt in SUPPORTED_IMAGE_FORMATS:
            self.format_combo.addItem(fmt)
        self.format_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 6px 12px;")
        fmt_row.addWidget(self.format_combo)
        img_card.add_layout(fmt_row)

        q_layout = QVBoxLayout()
        q_layout.setSpacing(6)
        q_hdr = QHBoxLayout()
        q_lbl = QLabel("JPEG / WEBP Kalitesi:", img_card)
        q_lbl.setStyleSheet("color: #FFFFFF; font-weight: 600;")
        q_hdr.addWidget(q_lbl)
        self.quality_label = QLabel("95%", img_card)
        self.quality_label.setStyleSheet("color: #818CF8; font-weight: 700;")
        q_hdr.addWidget(self.quality_label)
        q_layout.addLayout(q_hdr)

        self.quality_slider = QSlider(Qt.Orientation.Horizontal, img_card)
        self.quality_slider.setRange(10, 100)
        self.quality_slider.setValue(95)
        self.quality_slider.valueChanged.connect(lambda v: self.quality_label.setText(f"{v}%"))
        q_layout.addWidget(self.quality_slider)
        img_card.add_layout(q_layout)

        self.cursor_cb = SettingsToggleSwitch(img_card)
        img_card.add_widget(SettingToggleRow("", "Ekran Görüntüsüne Fare İmlecini Dahil Et", "Yakalama anında imleci çiz", self.cursor_cb, img_card))

        page_layout.addWidget(img_card)

        # -----------------------------------------------------------------
        # Card 2: Filigran (Watermark) & Profiller
        # -----------------------------------------------------------------
        from app.services.watermark_service import GRID_POSITIONS

        wm_card = SettingsCard(
            "sparkles",
            "Filigran (Watermark) ve Profiller",
            "Metin veya PNG görsel filigranı. Orijinal görüntü korunur (non-destructive), yalnızca çıktıya işlenir.",
        )

        # Profile selector row
        prof_row = QHBoxLayout()
        prof_lbl = QLabel("Filigran Profili:", wm_card)
        prof_lbl.setStyleSheet("color: #FFFFFF; font-weight: 600;")
        prof_row.addWidget(prof_lbl)

        self.wm_profile_combo = QComboBox(wm_card)
        self.wm_profile_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 10px; border-radius: 6px;")
        self.wm_profile_combo.currentTextChanged.connect(self._on_wm_profile_selected)
        prof_row.addWidget(self.wm_profile_combo, stretch=1)

        self.wm_profile_name_edit = QLineEdit(wm_card)
        self.wm_profile_name_edit.setPlaceholderText("Yeni profil adı...")
        self.wm_profile_name_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 10px; border-radius: 6px;")
        prof_row.addWidget(self.wm_profile_name_edit)

        self.btn_wm_save_profile = QPushButton("Profil Kaydet", wm_card)
        self.btn_wm_save_profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_wm_save_profile.setStyleSheet("background-color: rgba(56, 189, 248, 0.2); color: #38BDF8; padding: 5px 10px; border-radius: 6px; font-weight: 600;")
        self.btn_wm_save_profile.clicked.connect(self._on_save_wm_profile)
        prof_row.addWidget(self.btn_wm_save_profile)

        self.btn_wm_del_profile = QPushButton("Sil", wm_card)
        self.btn_wm_del_profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_wm_del_profile.setStyleSheet("background-color: rgba(239, 68, 68, 0.2); color: #FCA5A5; padding: 5px 10px; border-radius: 6px;")
        self.btn_wm_del_profile.clicked.connect(self._on_delete_wm_profile)
        prof_row.addWidget(self.btn_wm_del_profile)
        wm_card.add_layout(prof_row)

        self.wm_enabled_cb = SettingsToggleSwitch(wm_card)
        self.wm_auto_save_cb = SettingsToggleSwitch(wm_card)
        self.wm_auto_copy_cb = SettingsToggleSwitch(wm_card)
        self.wm_export_cb = SettingsToggleSwitch(wm_card)

        wm_card.add_widget(SettingToggleRow("", "Filigranı Etkinleştir (Tek Tıkla Aç/Kapat & Canlı Önizleme)", "Seçim ekranında canlı önizleme gösterir ve çıktıda aktif eder.", self.wm_enabled_cb, wm_card))
        wm_card.add_widget(SettingToggleRow("", "Kaydederken Otomatik Uygula", "Dosyaya kaydedilen görüntülere filigranı otomatik işle.", self.wm_auto_save_cb, wm_card))
        wm_card.add_widget(SettingToggleRow("", "Panoya Kopyalarken Otomatik Uygula", "Panoya kopyalanan görüntülere filigranı otomatik işle.", self.wm_auto_copy_cb, wm_card))
        wm_card.add_widget(SettingToggleRow("", "Dışa Aktar / PDF ve Toplu İşlemde Uygula", "PDF dışa aktarım ve görüntü sıkıştırma çıktılarında uygula.", self.wm_export_cb, wm_card))

        wm_form = QFormLayout()
        wm_form.setSpacing(10)

        self.wm_type_combo = QComboBox(wm_card)
        self.wm_type_combo.addItem("Metin Filigranı", "text")
        self.wm_type_combo.addItem("Görsel (PNG) Filigran", "image")
        self.wm_type_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 10px;")
        wm_form.addRow(self._make_form_label("Filigran Türü:"), self.wm_type_combo)

        self.wm_text_edit = QLineEdit(wm_card)
        self.wm_text_edit.setPlaceholderText(f"Filigran metni (örn. © {APP_NAME})")
        self.wm_text_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 6px 10px; border-radius: 6px;")
        wm_form.addRow(self._make_form_label("Filigran Metni:"), self.wm_text_edit)

        img_pick_row = QHBoxLayout()
        self.wm_image_edit = QLineEdit(wm_card)
        self.wm_image_edit.setPlaceholderText("Saydam PNG dosya yolu...")
        self.wm_image_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 6px 10px; border-radius: 6px;")
        img_pick_row.addWidget(self.wm_image_edit, stretch=1)
        self.btn_wm_browse_img = QPushButton("PNG Seç...", wm_card)
        self.btn_wm_browse_img.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); color: #FFF; padding: 6px 12px; border-radius: 6px;")
        self.btn_wm_browse_img.clicked.connect(self._on_browse_wm_image)
        img_pick_row.addWidget(self.btn_wm_browse_img)
        wm_form.addRow(self._make_form_label("Görsel (PNG):"), img_pick_row)

        self.wm_pos_combo = QComboBox(wm_card)
        for pos_code, pos_label in GRID_POSITIONS:
            self.wm_pos_combo.addItem(pos_label, pos_code)
        self.wm_pos_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 10px;")
        wm_form.addRow(self._make_form_label("Konum (9 Nokta Izgarası):"), self.wm_pos_combo)

        self.wm_margin_spin = QSpinBox(wm_card)
        self.wm_margin_spin.setRange(0, 300)
        self.wm_margin_spin.setSuffix(" px")
        self.wm_margin_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 8px;")
        wm_form.addRow(self._make_form_label("Kenar Boşluğu:"), self.wm_margin_spin)

        self.wm_opacity_spin = QSpinBox(wm_card)
        self.wm_opacity_spin.setRange(0, 100)
        self.wm_opacity_spin.setSuffix(" %")
        self.wm_opacity_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 8px;")
        wm_form.addRow(self._make_form_label("Saydamlık (%0–100):"), self.wm_opacity_spin)

        self.wm_scale_spin = QSpinBox(wm_card)
        self.wm_scale_spin.setRange(5, 80)
        self.wm_scale_spin.setSuffix(" %")
        self.wm_scale_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 8px;")
        wm_form.addRow(self._make_form_label("Boyut (Genişliğe Oranla):"), self.wm_scale_spin)

        self.wm_rotation_spin = QSpinBox(wm_card)
        self.wm_rotation_spin.setRange(-180, 180)
        self.wm_rotation_spin.setSuffix(" °")
        self.wm_rotation_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 8px;")
        wm_form.addRow(self._make_form_label("Döndürme Açısı:"), self.wm_rotation_spin)

        font_color_row = QHBoxLayout()
        self.wm_font_edit = QLineEdit(wm_card)
        self.wm_font_edit.setPlaceholderText("Segoe UI")
        self.wm_font_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 8px; border-radius: 6px;")
        font_color_row.addWidget(self.wm_font_edit)

        self.wm_color_edit = QLineEdit(wm_card)
        self.wm_color_edit.setPlaceholderText("#FFFFFF")
        self.wm_color_edit.setFixedWidth(90)
        self.wm_color_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 8px; border-radius: 6px; font-family: monospace;")
        font_color_row.addWidget(self.wm_color_edit)

        self.btn_wm_color = QPushButton("Renk...", wm_card)
        self.btn_wm_color.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); color: #FFF; padding: 5px 10px; border-radius: 6px;")
        self.btn_wm_color.clicked.connect(self._on_choose_wm_color)
        font_color_row.addWidget(self.btn_wm_color)

        self.wm_shadow_cb = QCheckBox("Gölge", wm_card)
        self.wm_shadow_cb.setStyleSheet("color: #E2E8F0;")
        font_color_row.addWidget(self.wm_shadow_cb)
        wm_form.addRow(self._make_form_label("Yazı Tipi / Renk / Gölge:"), font_color_row)

        tile_row = QHBoxLayout()
        self.wm_diagonal_cb = QCheckBox("Kitap / Film Tarzı Köşeden Köşeye Çapraz", wm_card)
        self.wm_diagonal_cb.setStyleSheet("color: #38BDF8; font-weight: 600;")
        self.wm_diagonal_cb.setToolTip(
            "Filigranı kitap/belge veya film önizlemelerindeki gibi köşeden köşeye büyük çapraz olarak yerleştirir."
        )
        tile_row.addWidget(self.wm_diagonal_cb)

        self.wm_tiled_cb = QCheckBox("Çapraz Döşeme (Tile Tekrar)", wm_card)
        self.wm_tiled_cb.setStyleSheet("color: #E2E8F0;")
        self.wm_tiled_cb.setToolTip(
            "Filigranı tüm görüntü boyunca çapraz açıyla (-35°) tekrarlayarak döşer."
        )
        tile_row.addWidget(self.wm_tiled_cb)

        self.wm_tile_spacing_spin = QSpinBox(wm_card)
        self.wm_tile_spacing_spin.setRange(10, 100)
        self.wm_tile_spacing_spin.setSuffix(" % aralık")
        self.wm_tile_spacing_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 8px;")
        tile_row.addWidget(self.wm_tile_spacing_spin)
        tile_row.addStretch()
        wm_form.addRow(self._make_form_label("Çapraz & Döşeme Modu:"), tile_row)

        wm_card.add_layout(wm_form)

        # Live Preview Box for Watermark & Info Banner
        prev_title = QLabel("Canlı Önizleme (Filigran & Alt Bilgi Bandı):", wm_card)
        prev_title.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 600; margin-top: 6px;")
        wm_card.add_widget(prev_title)

        self.wm_live_preview_lbl = QLabel(wm_card)
        self.wm_live_preview_lbl.setFixedHeight(150)
        self.wm_live_preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wm_live_preview_lbl.setStyleSheet("background-color: #090D16; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px;")
        wm_card.add_widget(self.wm_live_preview_lbl)

        page_layout.addWidget(wm_card)

        # -----------------------------------------------------------------
        # Card 3: Görüntü Altına Bilgi Bandı (Bottom Info Banner)
        # -----------------------------------------------------------------
        ib_card = SettingsCard(
            "info",
            "Görüntü Altına Bilgi Bandı",
            "Görüntünün hiçbir yerini kapatmadan altına ek bilgi şeridi ekler (görüntü yüksekliği uzar).",
        )

        self.ib_enabled_cb = SettingsToggleSwitch(ib_card)
        self.ib_auto_save_cb = SettingsToggleSwitch(ib_card)
        self.ib_auto_copy_cb = SettingsToggleSwitch(ib_card)
        self.ib_export_cb = SettingsToggleSwitch(ib_card)

        ib_card.add_widget(SettingToggleRow("", "Görüntü Altına Bilgi Bandını Etkinleştir", "Çıktı görüntüsünün altına bilgi bandı ekler.", self.ib_enabled_cb, ib_card))
        ib_card.add_widget(SettingToggleRow("", "Kaydederken Otomatik Uygula", "Dosyaya kaydedilen görüntülere bilgi bandı ekle.", self.ib_auto_save_cb, ib_card))
        ib_card.add_widget(SettingToggleRow("", "Panoya Kopyalarken Otomatik Uygula", "Panoya kopyalanan görüntülere bilgi bandı ekle.", self.ib_auto_copy_cb, ib_card))
        ib_card.add_widget(SettingToggleRow("", "Dışa Aktarmada Uygula", "PDF ve dışa aktarılan görüntülere bilgi bandı ekle.", self.ib_export_cb, ib_card))

        fields_lbl = QLabel("Gösterilecek Alanlar (Hassas alanlar varsayılan olarak kapalıdır):", ib_card)
        fields_lbl.setStyleSheet("color: #FFFFFF; font-weight: 600; margin-top: 6px;")
        ib_card.add_widget(fields_lbl)

        fields_row1 = QHBoxLayout()
        self.ib_dt_cb = QCheckBox("Tarih / Saat", ib_card)
        self.ib_win_cb = QCheckBox("Pencere Başlığı", ib_card)
        self.ib_app_cb = QCheckBox("Uygulama Adı", ib_card)
        self.ib_url_cb = QCheckBox("Varsa URL", ib_card)
        self.ib_res_cb = QCheckBox("Çözünürlük", ib_card)
        for cb in (self.ib_dt_cb, self.ib_win_cb, self.ib_app_cb, self.ib_url_cb, self.ib_res_cb):
            cb.setStyleSheet("color: #E2E8F0; font-size: 12px;")
            fields_row1.addWidget(cb)
        ib_card.add_layout(fields_row1)

        fields_row2 = QHBoxLayout()
        self.ib_comp_cb = QCheckBox("Bilgisayar Adı (Hassas)", ib_card)
        self.ib_user_cb = QCheckBox("Kullanıcı Adı (Hassas)", ib_card)
        self.ib_custom_cb = QCheckBox("Özel Metin:", ib_card)
        for cb in (self.ib_comp_cb, self.ib_user_cb, self.ib_custom_cb):
            cb.setStyleSheet("color: #FCD34D; font-size: 12px;" if "Hassas" in cb.text() else "color: #E2E8F0; font-size: 12px;")
            fields_row2.addWidget(cb)

        self.ib_custom_edit = QLineEdit(ib_card)
        self.ib_custom_edit.setPlaceholderText("Alt banda eklenecek özel not...")
        self.ib_custom_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 8px; border-radius: 6px;")
        fields_row2.addWidget(self.ib_custom_edit, stretch=1)
        ib_card.add_layout(fields_row2)

        ib_form = QFormLayout()
        ib_form.setSpacing(10)

        self.ib_theme_combo = QComboBox(ib_card)
        self.ib_theme_combo.addItem("Koyu Tema (Dark)", "dark")
        self.ib_theme_combo.addItem("Açık Tema (Light)", "light")
        self.ib_theme_combo.addItem("Özel Renkler (Custom)", "custom")
        self.ib_theme_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 10px;")
        ib_form.addRow(self._make_form_label("Hazır Tema:"), self.ib_theme_combo)

        ib_colors_row = QHBoxLayout()
        self.ib_bg_edit = QLineEdit(ib_card)
        self.ib_bg_edit.setPlaceholderText("#0F172A (Arka Plan)")
        self.ib_bg_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 8px; border-radius: 6px; font-family: monospace;")
        ib_colors_row.addWidget(self.ib_bg_edit)

        self.ib_fg_edit = QLineEdit(ib_card)
        self.ib_fg_edit.setPlaceholderText("#F8FAFC (Yazı Rengi)")
        self.ib_fg_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 8px; border-radius: 6px; font-family: monospace;")
        ib_colors_row.addWidget(self.ib_fg_edit)

        self.ib_sep_cb = QCheckBox("İnce Ayırıcı Çizgi", ib_card)
        self.ib_sep_cb.setStyleSheet("color: #E2E8F0;")
        ib_colors_row.addWidget(self.ib_sep_cb)
        ib_form.addRow(self._make_form_label("Arka Plan / Yazı Rengi:"), ib_colors_row)

        ib_style_row = QHBoxLayout()
        self.ib_font_spin = QSpinBox(ib_card)
        self.ib_font_spin.setRange(8, 32)
        self.ib_font_spin.setSuffix(" px")
        self.ib_font_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 8px;")
        ib_style_row.addWidget(self.ib_font_spin)

        self.ib_align_combo = QComboBox(ib_card)
        self.ib_align_combo.addItem("Sola Hizalı", "left")
        self.ib_align_combo.addItem("Ortalanmış", "center")
        self.ib_align_combo.addItem("Sağa Hizalı", "right")
        self.ib_align_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 10px;")
        ib_style_row.addWidget(self.ib_align_combo)

        self.ib_wrap_cb = QCheckBox("Taşan metni alt satıra böl (Kapalıysa kısalt)", ib_card)
        self.ib_wrap_cb.setStyleSheet("color: #E2E8F0;")
        ib_style_row.addWidget(self.ib_wrap_cb)
        ib_style_row.addStretch()
        ib_form.addRow(self._make_form_label("Yazı Boyutu & Hizalama:"), ib_style_row)

        ib_card.add_layout(ib_form)
        page_layout.addWidget(ib_card)

        # Wire live preview updates
        for w_sig in (
            self.wm_enabled_cb.toggled,
            self.wm_type_combo.currentIndexChanged,
            self.wm_text_edit.textChanged,
            self.wm_image_edit.textChanged,
            self.wm_pos_combo.currentIndexChanged,
            self.wm_margin_spin.valueChanged,
            self.wm_opacity_spin.valueChanged,
            self.wm_scale_spin.valueChanged,
            self.wm_rotation_spin.valueChanged,
            self.wm_font_edit.textChanged,
            self.wm_color_edit.textChanged,
            self.wm_shadow_cb.toggled,
            self.wm_diagonal_cb.toggled,
            self.wm_tiled_cb.toggled,
            self.wm_tile_spacing_spin.valueChanged,
            self.ib_enabled_cb.toggled,
            self.ib_dt_cb.toggled,
            self.ib_win_cb.toggled,
            self.ib_app_cb.toggled,
            self.ib_url_cb.toggled,
            self.ib_res_cb.toggled,
            self.ib_comp_cb.toggled,
            self.ib_user_cb.toggled,
            self.ib_custom_cb.toggled,
            self.ib_custom_edit.textChanged,
            self.ib_theme_combo.currentIndexChanged,
            self.ib_bg_edit.textChanged,
            self.ib_fg_edit.textChanged,
            self.ib_sep_cb.toggled,
            self.ib_font_spin.valueChanged,
            self.ib_align_combo.currentIndexChanged,
            self.ib_wrap_cb.toggled,
        ):
            w_sig.connect(self._update_watermark_live_preview)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 8: Editor (Editör)
    # =========================================================================
    def _build_editor_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        ed_card = SettingsCard("pen", "Çizim ve Anotasyon Editörü", "Varsayılan çizim renkleri ve fırça boyutları.")

        c_row = QHBoxLayout()
        c_lbl = QLabel("Varsayılan Çizim Rengi:", ed_card)
        c_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        c_row.addWidget(c_lbl)

        self.color_preview = QLabel(ed_card)
        self.color_preview.setFixedSize(28, 28)
        c_row.addWidget(self.color_preview)

        self.color_hex_label = QLabel("#FF0000", ed_card)
        self.color_hex_label.setStyleSheet("color: #CBD5E0; font-family: monospace;")
        c_row.addWidget(self.color_hex_label)

        self.btn_choose_color = QPushButton("Renk Seç...", ed_card)
        self.btn_choose_color.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); color: #FFF; padding: 4px 10px; border-radius: 6px;")
        self.btn_choose_color.clicked.connect(self._on_choose_color)
        c_row.addWidget(self.btn_choose_color)
        c_row.addStretch()
        ed_card.add_layout(c_row)

        b_row = QHBoxLayout()
        b_lbl = QLabel("Varsayılan Çizgi Kalınlığı:", ed_card)
        b_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        b_row.addWidget(b_lbl)

        self.brush_size_combo = QComboBox(ed_card)
        for w in STROKE_WIDTH_OPTIONS:
            self.brush_size_combo.addItem(f"{w} px", w)
        self.brush_size_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 10px;")
        b_row.addWidget(self.brush_size_combo)
        ed_card.add_layout(b_row)

        f_row = QHBoxLayout()
        f_lbl = QLabel("Varsayılan Metin Boyutu:", ed_card)
        f_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        f_row.addWidget(f_lbl)

        self.font_size_spin = QSpinBox(ed_card)
        self.font_size_spin.setRange(8, 72)
        self.font_size_spin.setValue(18)
        self.font_size_spin.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 10px;")
        f_row.addWidget(self.font_size_spin)
        ed_card.add_layout(f_row)

        page_layout.addWidget(ed_card)

        # Blur / Pixelate Card
        blur_card = SettingsCard("blur", "Bulanıklaştırma ve Mozaikleme", "Gizleme araçlarının yoğunluk değerleri.")
        
        blr_layout = QVBoxLayout()
        blr_hdr = QHBoxLayout()
        blr_lbl = QLabel("Bulanıklık Yarıçapı (Blur):", blur_card)
        blr_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        blr_hdr.addWidget(blr_lbl)
        self.blur_radius_label = QLabel("15 px", blur_card)
        self.blur_radius_label.setStyleSheet("color: #818CF8; font-weight: 700;")
        blr_hdr.addWidget(self.blur_radius_label)
        blr_layout.addLayout(blr_hdr)

        self.blur_radius_slider = QSlider(Qt.Orientation.Horizontal, blur_card)
        self.blur_radius_slider.setRange(3, 50)
        self.blur_radius_slider.setValue(15)
        self.blur_radius_slider.valueChanged.connect(lambda v: self.blur_radius_label.setText(f"{v} px"))
        blr_layout.addWidget(self.blur_radius_slider)
        blur_card.add_layout(blr_layout)

        pix_layout = QVBoxLayout()
        pix_hdr = QHBoxLayout()
        pix_lbl = QLabel("Mozaik Blok Boyutu (Pixelate):", blur_card)
        pix_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        pix_hdr.addWidget(pix_lbl)
        self.pixel_size_label = QLabel("12 px", blur_card)
        self.pixel_size_label.setStyleSheet("color: #818CF8; font-weight: 700;")
        pix_hdr.addWidget(self.pixel_size_label)
        pix_layout.addLayout(pix_hdr)

        self.pixel_size_slider = QSlider(Qt.Orientation.Horizontal, blur_card)
        self.pixel_size_slider.setRange(4, 40)
        self.pixel_size_slider.setValue(12)
        self.pixel_size_slider.valueChanged.connect(lambda v: self.pixel_size_label.setText(f"{v} px"))
        pix_layout.addWidget(self.pixel_size_slider)
        blur_card.add_layout(pix_layout)

        # Tint
        t_row = QHBoxLayout()
        t_lbl = QLabel("Bulanıklık Renk Tonu:", blur_card)
        t_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        t_row.addWidget(t_lbl)

        self.tint_preview = QLabel(blur_card)
        self.tint_preview.setFixedSize(24, 24)
        t_row.addWidget(self.tint_preview)

        self.tint_hex_label = QLabel("Ton Yok", blur_card)
        self.tint_hex_label.setStyleSheet("color: #CBD5E0;")
        t_row.addWidget(self.tint_hex_label)

        self.btn_choose_tint = QPushButton("Ton Seç...", blur_card)
        self.btn_choose_tint.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); color: #FFF; padding: 4px 10px; border-radius: 6px;")
        self.btn_choose_tint.clicked.connect(self._on_choose_tint)
        t_row.addWidget(self.btn_choose_tint)

        self.btn_clear_tint = QPushButton("Temizle", blur_card)
        self.btn_clear_tint.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); color: #FFF; padding: 4px 10px; border-radius: 6px;")
        self.btn_clear_tint.clicked.connect(self._on_clear_tint)
        t_row.addWidget(self.btn_clear_tint)
        t_row.addStretch()
        blur_card.add_layout(t_row)

        top_layout = QVBoxLayout()
        top_hdr = QHBoxLayout()
        top_lbl = QLabel("Ton Opaklığı:", blur_card)
        top_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        top_hdr.addWidget(top_lbl)
        self.tint_opacity_label = QLabel("%20", blur_card)
        self.tint_opacity_label.setStyleSheet("color: #818CF8; font-weight: 700;")
        top_hdr.addWidget(self.tint_opacity_label)
        top_layout.addLayout(top_hdr)

        self.tint_opacity_slider = QSlider(Qt.Orientation.Horizontal, blur_card)
        self.tint_opacity_slider.setRange(0, 100)
        self.tint_opacity_slider.setValue(20)
        self.tint_opacity_slider.valueChanged.connect(lambda v: self.tint_opacity_label.setText(f"%{v}"))
        top_layout.addWidget(self.tint_opacity_slider)
        blur_card.add_layout(top_layout)

        page_layout.addWidget(blur_card)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 9: Upload & Share (Yükle / Paylaş)
    # =========================================================================
    def _build_upload_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        up_card = SettingsCard("cloud_upload", "Bulut Yükleme ve Paylaşım", "Ekran görüntülerini tek tıkla buluta yükleyip bağlantı alma.")

        # API Key
        key_row = QHBoxLayout()
        k_lbl = QLabel("ImgBB API Anahtarı:", up_card)
        k_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        key_row.addWidget(k_lbl)

        self.imgbb_key_edit = QLineEdit(up_card)
        self.imgbb_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.imgbb_key_edit.setPlaceholderText("ImgBB API key girin...")
        self.imgbb_key_edit.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 6px 10px; border-radius: 6px;")
        key_row.addWidget(self.imgbb_key_edit)

        self.btn_show_key = QPushButton("👁️", up_card)
        self.btn_show_key.setFixedSize(32, 32)
        self.btn_show_key.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.btn_show_key)

        self.btn_test_conn = QPushButton("Bağlantıyı Test Et", up_card)
        self.btn_test_conn.setStyleSheet("background-color: rgba(79, 70, 229, 0.4); color: #FFF; padding: 6px 12px; border-radius: 6px;")
        self.btn_test_conn.clicked.connect(self._on_test_upload_connection)
        key_row.addWidget(self.btn_test_conn)

        self.btn_clear_key = QPushButton("Sil", up_card)
        self.btn_clear_key.setStyleSheet("background-color: rgba(239, 68, 68, 0.3); color: #FFF; padding: 6px 12px; border-radius: 6px;")
        self.btn_clear_key.clicked.connect(self._on_clear_api_key)
        key_row.addWidget(self.btn_clear_key)

        up_card.add_layout(key_row)

        self.lbl_conn_status = QLabel("Durum: Kontrol edilmedi", up_card)
        self.lbl_conn_status.setStyleSheet("color: #94A3B8; font-size: 12px; margin-top: 4px;")
        up_card.add_widget(self.lbl_conn_status)

        exp_row = QHBoxLayout()
        exp_lbl = QLabel("Görsel Son Kullanma Süresi:", up_card)
        exp_lbl.setStyleSheet("color: #FFF; font-weight: 600;")
        exp_row.addWidget(exp_lbl)

        self.upload_expiration_combo = QComboBox(up_card)
        self.upload_expiration_combo.addItem("Süresiz (Kalıcı)", None)
        self.upload_expiration_combo.addItem("5 Dakika", 300)
        self.upload_expiration_combo.addItem("15 Dakika", 900)
        self.upload_expiration_combo.addItem("1 Saat", 3600)
        self.upload_expiration_combo.addItem("1 Gün", 86400)
        self.upload_expiration_combo.addItem("1 Hafta", 604800)
        self.upload_expiration_combo.addItem("1 Ay", 2592000)
        self.upload_expiration_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 4px 10px;")
        exp_row.addWidget(self.upload_expiration_combo)
        up_card.add_layout(exp_row)

        self.cb_upload_privacy_check = SettingsToggleSwitch(up_card)
        self.cb_upload_clean_metadata = SettingsToggleSwitch(up_card)
        self.cb_upload_copy_share = SettingsToggleSwitch(up_card)
        self.cb_upload_copy_direct = SettingsToggleSwitch(up_card)
        self.cb_upload_save_history = SettingsToggleSwitch(up_card)

        up_card.add_widget(SettingToggleRow("", "Yükleme Öncesi Gizlilik Taraması", "Hassas bilgi varsa onay iste", self.cb_upload_privacy_check, up_card))
        up_card.add_widget(SettingToggleRow("", "EXIF ve Metadata'yı Temizle", "Konum ve cihaz bilgilerini sil", self.cb_upload_clean_metadata, up_card))
        up_card.add_widget(SettingToggleRow("", "Paylaşım Bağlantısını Panoya Kopyala", "Yükleme bitince URL kopyala", self.cb_upload_copy_share, up_card))
        up_card.add_widget(SettingToggleRow("", "Doğrudan Resim Linkini Kopyala (i.ibb.co)", "Direkt CDN linkini al", self.cb_upload_copy_direct, up_card))
        up_card.add_widget(SettingToggleRow("", "Yükleme Geçmişini Kaydet", "Paylaşılan görsel linklerini yerel olarak sakla", self.cb_upload_save_history, up_card))

        page_layout.addWidget(up_card)

        # History card with Path & Action Controls
        hist_card = SettingsCard("inbox", "Paylaşım Geçmişi ve Kayıt Dosyası", "Buluta yüklenen görsellerin yerel geçmişi ve bağlantı listesi.")
        
        # 1. Path display row
        path_box = QFrame(hist_card)
        path_box.setStyleSheet("background-color: rgba(10, 14, 23, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 6px 10px;")
        path_layout = QHBoxLayout(path_box)
        path_layout.setContentsMargins(8, 4, 8, 4)
        path_layout.setSpacing(8)

        f_icon = QLabel(path_box)
        f_icon.setPixmap(get_icon("folder", "#FCD34D", 16).pixmap(16, 16))
        path_layout.addWidget(f_icon)

        from app.upload.history_manager import ShareHistoryManager
        hist_file_path = ShareHistoryManager.get_history_file_path()
        self.lbl_history_path = QLabel(str(hist_file_path), path_box)
        self.lbl_history_path.setStyleSheet("color: #94A3B8; font-size: 11.5px; font-family: 'Consolas', monospace;")
        self.lbl_history_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_layout.addWidget(self.lbl_history_path, stretch=1)

        btn_open_hist_dir = QPushButton(" Klasörde Göster", path_box)
        btn_open_hist_dir.setIcon(get_icon("folder", "#FCD34D", 14))
        btn_open_hist_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open_hist_dir.setStyleSheet("background-color: rgba(255, 255, 255, 0.06); color: #FFF; padding: 4px 10px; border-radius: 6px; font-size: 11.5px;")
        btn_open_hist_dir.clicked.connect(self._on_open_share_history_folder)
        path_layout.addWidget(btn_open_hist_dir)

        hist_card.add_widget(path_box)

        # 2. Status and action buttons row
        h_row = QHBoxLayout()
        h_row.setContentsMargins(0, 4, 0, 0)
        h_row.setSpacing(10)

        self.lbl_history_info = QLabel("Geçmiş yüklemeleri kontrol ediliyor...", hist_card)
        self.lbl_history_info.setStyleSheet("color: #E2E8F0; font-size: 12.5px; font-weight: 500;")
        h_row.addWidget(self.lbl_history_info, stretch=1)

        self.btn_view_history = QPushButton("  Paylaşım Geçmişini Görüntüle", hist_card)
        self.btn_view_history.setIcon(get_icon("external_link", "#38BDF8", 14))
        self.btn_view_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_history.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1D4ED8); color: #FFF; padding: 7px 16px; border-radius: 6px; font-weight: 600; font-size: 12px;")
        self.btn_view_history.clicked.connect(self._on_open_share_history_dialog)
        h_row.addWidget(self.btn_view_history)

        self.btn_clear_history = QPushButton("Geçmişi Temizle", hist_card)
        self.btn_clear_history.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_history.setStyleSheet("background-color: rgba(239, 68, 68, 0.12); color: #FCA5A5; border: 1px solid rgba(239, 68, 68, 0.25); padding: 7px 14px; border-radius: 6px; font-size: 12px;")
        self.btn_clear_history.clicked.connect(self._on_clear_share_history)
        h_row.addWidget(self.btn_clear_history)

        hist_card.add_layout(h_row)

        page_layout.addWidget(hist_card)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # ------------------------------------------------------------------
    # Settings import / export
    # ------------------------------------------------------------------
    def _on_export_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Ayarları Dışa Aktar", "quickglint_settings.json", "Quickglint Ayarları (*.json)"
        )
        if not path:
            return
        try:
            self.config_manager.export_to_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Dışa Aktarma Başarısız", f"Ayarlar yazılamadı:\n{exc}")
            return
        QMessageBox.information(
            self,
            "Dışa Aktarıldı",
            f"Ayarlar kaydedildi:\n{path}\n\nNot: Henüz 'Kaydet'e basılmamış değişiklikler dosyaya dahil edilmez.",
        )

    def _on_import_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Ayarları İçe Aktar", "", "Quickglint Ayarları (*.json);;Quickglint Eski Ayarları (*.json);;Tüm Dosyalar (*.*)"
        )
        if not path:
            return
        reply = QMessageBox.question(
            self,
            "Ayarları İçe Aktar",
            "Mevcut ayarlarınızın üzerine yazılacak. Devam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            applied = self.config_manager.import_from_file(path)
        except ValueError as exc:
            QMessageBox.warning(self, "İçe Aktarma Başarısız", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "İçe Aktarma Başarısız", f"Beklenmeyen hata:\n{exc}")
            return

        set_language(self.config_manager.get("general", "language", "tr"))
        self._load_values()
        self.settings_saved.emit()
        QMessageBox.information(self, "İçe Aktarıldı", f"{applied} ayar başarıyla içe aktarıldı ve uygulandı.")

    # =========================================================================
    # Tab 10: Panorama Capture
    # =========================================================================
    def _build_panorama_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        # Panorama Capture & Multi-Monitor Stitching
        pano_card = SettingsCard(
            "panorama",
            "Panorama Capture – Çoklu Ekran ve Panoramik Birleştirme",
            "Çoklu monitör yakalama, OpenCV özellik eşleştirme (ORB/SIFT), dikişsiz harmanlama ve otomatik kırpma ayarları.",
        )
        p_form = QFormLayout()
        p_form.setSpacing(10)

        self.pano_detector_combo = QComboBox(pano_card)
        self.pano_detector_combo.addItem("Otomatik (SIFT / ORB)", "auto")
        self.pano_detector_combo.addItem("ORB (Hızlı Özellik Çıkarma)", "orb")
        self.pano_detector_combo.addItem("SIFT (Yüksek Hassasiyetli Eşleştirme)", "sift")
        self.pano_detector_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 10px;")
        p_form.addRow(self._make_form_label("Özellik Çıkarma Algoritması:"), self.pano_detector_combo)

        self.pano_blend_combo = QComboBox(pano_card)
        self.pano_blend_combo.addItem("Multi-Band (Laplacian Piramit Dikişsiz)", "multiband")
        self.pano_blend_combo.addItem("Feather (Yumuşak Geçişli)", "feather")
        self.pano_blend_combo.addItem("Kapalı (Keskin)", "none")
        self.pano_blend_combo.setStyleSheet("background-color: rgba(10, 14, 23, 0.85); color: #FFF; padding: 5px 10px;")
        p_form.addRow(self._make_form_label("Dikiş Harmanlama (Blending):"), self.pano_blend_combo)

        pano_card.add_layout(p_form)

        self.pano_exposure_cb = SettingsToggleSwitch(pano_card)
        self.pano_dpi_cb = SettingsToggleSwitch(pano_card)
        self.pano_autocrop_cb = SettingsToggleSwitch(pano_card)

        pano_card.add_widget(
            SettingToggleRow(
                "",
                "Renk ve Parlaklık Farklarını Otomatik Dengele",
                "Monitörler veya kareler arasındaki pozlama farklarını düzelt.",
                self.pano_exposure_cb,
                pano_card,
            )
        )
        pano_card.add_widget(
            SettingToggleRow(
                "",
                "Farklı DPI ve Ölçeklendirme Oranlarını Eşitle",
                "Yüksek DPI monitörlerin tam çözünürlüğünü koruyarak hizala.",
                self.pano_dpi_cb,
                pano_card,
            )
        )
        pano_card.add_widget(
            SettingToggleRow(
                "",
                "Otomatik Kırpma ve Boş Alan Temizleme",
                "Birleştirme sonrası siyah kenar boşluklarını otomatik temizle.",
                self.pano_autocrop_cb,
                pano_card,
            )
        )
        page_layout.addWidget(pano_card)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Tab 11: About (Hakkında)
    # =========================================================================
    def _build_about_tab(self) -> None:
        scroll, page_layout = self._create_scrollable_page()

        about_card = SettingsCard("info", f"{APP_NAME} Hakkında", "Açık kaynaklı, modern ve güvenli ekran yakalama aracı.")

        header_row = QHBoxLayout()
        header_row.setSpacing(14)

        icon_lbl = QLabel(about_card)
        icon_lbl.setPixmap(get_app_icon().pixmap(56, 56))
        icon_lbl.setFixedSize(56, 56)
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        app_title = QLabel(f"<b>{APP_NAME}</b>  •  v{APP_VERSION}", about_card)
        app_title.setStyleSheet("color: #818CF8; font-size: 19px; font-weight: 700;")
        title_col.addWidget(app_title)

        tagline = QLabel(APP_DESCRIPTION, about_card)
        tagline.setStyleSheet("color: #E2E8F0; font-size: 13px;")
        title_col.addWidget(tagline)

        header_row.addLayout(title_col, stretch=1)
        about_card.add_layout(header_row)

        auth = QLabel(f"Geliştirici: {APP_AUTHOR} ({APP_AUTHOR_URL})  •  Lisans: {APP_LICENSE}", about_card)
        auth.setStyleSheet("color: #94A3B8; font-size: 12px; margin-top: 10px;")
        about_card.add_widget(auth)

        page_layout.addWidget(about_card)
        page_layout.addStretch()
        self.stack.addWidget(scroll)

    # =========================================================================
    # Load & Save Logic
    # =========================================================================
    def _load_values(self) -> None:
        """Populate widgets with current config values."""
        # Language
        current_lang = self.config_manager.get("general", "language", "tr")
        l_idx = self.lang_combo.findData(current_lang)
        if l_idx >= 0:
            self.lang_combo.setCurrentIndex(l_idx)

        # General
        self.autostart_cb.setChecked(self.config_manager.get("general", "start_with_windows", False))
        self.minimize_tray_cb.setChecked(self.config_manager.get("general", "minimize_to_tray", True))
        self.show_notif_cb.setChecked(self.config_manager.get("general", "show_notifications", True))
        self.folder_edit.setText(self.config_manager.get("general", "default_save_dir", ""))

        # Smart File Naming
        from app.services.naming_service import DEFAULT_NAMING_TEMPLATE

        self.naming_template_edit.setText(
            self.config_manager.get("naming", "template", DEFAULT_NAMING_TEMPLATE)
        )
        self._update_naming_preview()

        # Hotkeys
        hk_section = self.config_manager.get_section("hotkeys")
        for key, editor in self._hotkey_editors.items():
            editor.set_hotkey(hk_section.get(key, ""))

        # Smart Privacy
        self.priv_enabled_cb.setChecked(self.config_manager.get("privacy", "enabled", True))
        self.priv_auto_redact_cb.setChecked(self.config_manager.get("privacy", "auto_redact_on_save", False))
        priv_eff = self.config_manager.get("privacy", "default_effect", "pixelate")
        pe_idx = self.priv_effect_combo.findData(priv_eff)
        if pe_idx >= 0:
            self.priv_effect_combo.setCurrentIndex(pe_idx)

        priv_ocr = self.config_manager.get("privacy", "ocr_engine", "auto")
        po_idx = self.priv_ocr_combo.findData(priv_ocr)
        if po_idx >= 0:
            self.priv_ocr_combo.setCurrentIndex(po_idx)

        self.cb_det_email.setChecked(self.config_manager.get("privacy", "detect_emails", True))
        self.cb_det_phone.setChecked(self.config_manager.get("privacy", "detect_phones", True))
        self.cb_det_ip.setChecked(self.config_manager.get("privacy", "detect_ips", True))
        self.cb_det_url.setChecked(self.config_manager.get("privacy", "detect_urls", True))
        self.cb_det_api.setChecked(self.config_manager.get("privacy", "detect_api_keys", True))
        self.cb_det_card.setChecked(self.config_manager.get("privacy", "detect_credit_cards", True))
        self.cb_det_iban.setChecked(self.config_manager.get("privacy", "detect_iban", True))
        self.cb_det_path.setChecked(self.config_manager.get("privacy", "detect_file_paths", True))

        # OCR
        ocr_eng = self.config_manager.get("ocr", "engine", "auto")
        oe_idx = self.ocr_engine_combo.findData(ocr_eng)
        if oe_idx >= 0:
            self.ocr_engine_combo.setCurrentIndex(oe_idx)

        ocr_langs = self.config_manager.get("ocr", "languages", ["tr", "en"])
        self.ocr_lang_tr.setChecked("tr" in ocr_langs)
        self.ocr_lang_en.setChecked("en" in ocr_langs)
        self.ocr_lang_de.setChecked("de" in ocr_langs)
        self.ocr_lang_fr.setChecked("fr" in ocr_langs)
        self.ocr_lang_es.setChecked("es" in ocr_langs)
        self.ocr_lang_it.setChecked("it" in ocr_langs)

        self.ocr_auto_detect_cb.setChecked(self.config_manager.get("ocr", "auto_detect_after_capture", False))
        self.ocr_enhance_contrast_cb.setChecked(self.config_manager.get("ocr", "enhance_contrast", False))
        self.ocr_upscale_small_cb.setChecked(self.config_manager.get("ocr", "upscale_small", True))

        # QR Code
        self.qr_enabled_cb.setChecked(self.config_manager.get("qr", "enabled", True))
        self.qr_show_panel_cb.setChecked(self.config_manager.get("qr", "show_panel_automatically", True))
        self.qr_highlight_cb.setChecked(self.config_manager.get("qr", "highlight_detected", True))

        # Scrolling
        self.max_captures_spin.setValue(self.config_manager.get("scrolling", "max_captures", 40))
        self.max_height_spin.setValue(self.config_manager.get("scrolling", "max_height", 40000))

        # GIF Recorder
        fps_val = self.config_manager.get("recorder", "fps", 15)
        self.gif_fps_combo.setCurrentText(f"{fps_val} FPS")
        self.gif_duration_spin.setValue(int(self.config_manager.get("recorder", "max_duration", 60.0)))
        self.gif_cursor_cb.setChecked(self.config_manager.get("recorder", "show_cursor", True))
        self.gif_halo_cb.setChecked(self.config_manager.get("recorder", "highlight_cursor", True))
        self.gif_clicks_cb.setChecked(self.config_manager.get("recorder", "show_click_effects", True))

        # Image
        fmt = self.config_manager.get("image", "default_format", "PNG")
        idx = self.format_combo.findText(fmt)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        quality = self.config_manager.get("image", "jpeg_quality", 95)
        self.quality_slider.setValue(quality)
        self.quality_label.setText(f"{quality}%")
        self.cursor_cb.setChecked(self.config_manager.get("image", "include_cursor", False))

        # Watermark & Profiles
        self._refresh_wm_profile_combo()
        self._apply_wm_dict_to_ui(self.config_manager.get_section("watermark"))

        # Bottom Info Banner
        ib = self.config_manager.get_section("info_banner")
        self.ib_enabled_cb.setChecked(bool(ib.get("enabled", False)))
        self.ib_auto_save_cb.setChecked(bool(ib.get("auto_apply_on_save", False)))
        self.ib_auto_copy_cb.setChecked(bool(ib.get("auto_apply_on_copy", False)))
        self.ib_export_cb.setChecked(bool(ib.get("apply_on_export", False)))
        self.ib_dt_cb.setChecked(bool(ib.get("show_datetime", True)))
        self.ib_win_cb.setChecked(bool(ib.get("show_window_title", True)))
        self.ib_app_cb.setChecked(bool(ib.get("show_app_name", True)))
        self.ib_url_cb.setChecked(bool(ib.get("show_url", False)))
        self.ib_res_cb.setChecked(bool(ib.get("show_resolution", True)))
        self.ib_comp_cb.setChecked(bool(ib.get("show_computer_name", False)))
        self.ib_user_cb.setChecked(bool(ib.get("show_user_name", False)))
        self.ib_custom_cb.setChecked(bool(ib.get("show_custom_text", False)))
        self.ib_custom_edit.setText(str(ib.get("custom_text", "")))
        ib_t_idx = self.ib_theme_combo.findData(str(ib.get("theme", "dark")))
        if ib_t_idx >= 0:
            self.ib_theme_combo.setCurrentIndex(ib_t_idx)
        self.ib_bg_edit.setText(str(ib.get("bg_color", "#0F172A")))
        self.ib_fg_edit.setText(str(ib.get("text_color", "#F8FAFC")))
        self.ib_sep_cb.setChecked(bool(ib.get("show_separator", True)))
        self.ib_font_spin.setValue(int(ib.get("font_size", 12)))
        ib_a_idx = self.ib_align_combo.findData(str(ib.get("alignment", "left")))
        if ib_a_idx >= 0:
            self.ib_align_combo.setCurrentIndex(ib_a_idx)
        self.ib_wrap_cb.setChecked(bool(ib.get("wrap_long_text", True)))
        self._update_watermark_live_preview()

        # Editor
        self._current_color = self.config_manager.get("editor", "default_color", "#FF0000")
        self._update_color_preview(self._current_color)

        brush_size = self.config_manager.get("editor", "default_brush_size", 3)
        b_idx = self.brush_size_combo.findData(brush_size)
        if b_idx >= 0:
            self.brush_size_combo.setCurrentIndex(b_idx)

        self.font_size_spin.setValue(self.config_manager.get("editor", "default_font_size", 18))

        # Blur & Pixelate
        blur_rad = self.config_manager.get("editor", "blur_radius", 15)
        self.blur_radius_slider.setValue(blur_rad)
        self.blur_radius_label.setText(f"{blur_rad} px")

        pix_sz = self.config_manager.get("editor", "pixel_size", 12)
        self.pixel_size_slider.setValue(pix_sz)
        self.pixel_size_label.setText(f"{pix_sz} px")

        self._current_tint = self.config_manager.get("editor", "blur_tint", "")
        self._update_tint_preview(self._current_tint)

        tint_op = int(self.config_manager.get("editor", "blur_tint_opacity", 0.2) * 100)
        self.tint_opacity_slider.setValue(tint_op)
        self.tint_opacity_label.setText(f"%{tint_op}")

        # Upload & Share
        from app.security.credential_store import CredentialStore
        stored_key = CredentialStore.get_credential("imgbb", "user") or ""
        self.imgbb_key_edit.setText(stored_key)
        if stored_key:
            self.lbl_conn_status.setText("Durum: ● Yapılandırıldı (Şifreli Depoda Saklanıyor)")
            self.lbl_conn_status.setStyleSheet("color: #48BB78; font-size: 12px; font-weight: 600;")
        else:
            self.lbl_conn_status.setText("Durum: ● Yapılandırılmadı (API Anahtarı Gerekli)")
            self.lbl_conn_status.setStyleSheet("color: #ECC94B; font-size: 12px; font-weight: 500;")

        self.cb_upload_privacy_check.setChecked(self.config_manager.get("upload", "privacy_check", True))
        self.cb_upload_clean_metadata.setChecked(self.config_manager.get("upload", "clean_metadata", True))
        self.cb_upload_copy_share.setChecked(self.config_manager.get("upload", "copy_share_url", True))
        self.cb_upload_copy_direct.setChecked(self.config_manager.get("upload", "copy_direct_url", False))
        self.cb_upload_save_history.setChecked(self.config_manager.get("upload", "save_history", True))

        saved_exp = self.config_manager.get("upload", "expiration", None)
        idx = self.upload_expiration_combo.findData(saved_exp)
        if idx >= 0:
            self.upload_expiration_combo.setCurrentIndex(idx)

        self._refresh_share_history_info()

        # Panorama Capture
        p_det = self.config_manager.get("panorama", "detector", "auto")
        pd_idx = self.pano_detector_combo.findData(p_det)
        if pd_idx >= 0:
            self.pano_detector_combo.setCurrentIndex(pd_idx)

        p_blend = self.config_manager.get("panorama", "blending", "multiband")
        pb_idx = self.pano_blend_combo.findData(p_blend)
        if pb_idx >= 0:
            self.pano_blend_combo.setCurrentIndex(pb_idx)

        self.pano_exposure_cb.setChecked(bool(self.config_manager.get("panorama", "exposure_compensation", True)))
        self.pano_dpi_cb.setChecked(bool(self.config_manager.get("panorama", "normalize_dpi", True)))
        self.pano_autocrop_cb.setChecked(bool(self.config_manager.get("panorama", "auto_crop", True)))

    def _on_clear_api_key(self) -> None:
        from app.security.credential_store import CredentialStore
        CredentialStore.delete_credential("imgbb", "user")
        self.imgbb_key_edit.clear()
        self.lbl_conn_status.setText("Durum: ● Yapılandırılmadı (API Anahtarı Silindi)")
        self.lbl_conn_status.setStyleSheet("color: #ECC94B; font-size: 12px; font-weight: 500;")

    def _toggle_key_visibility(self) -> None:
        if self.imgbb_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.imgbb_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_show_key.setText("🔒")
        else:
            self.imgbb_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_show_key.setText("👁️")

    def _on_test_upload_connection(self) -> None:
        api_key = self.imgbb_key_edit.text().strip()
        if not api_key:
            self.lbl_conn_status.setText("❌ Lütfen önce geçerli bir ImgBB API anahtarı girin.")
            self.lbl_conn_status.setStyleSheet("color: #FC8181; font-size: 12px; font-weight: 600;")
            return

        self.lbl_conn_status.setText("🔄 ImgBB sunucusuyla bağlantı test ediliyor...")
        self.lbl_conn_status.setStyleSheet("color: #63B3ED; font-size: 12px;")
        QApplication.processEvents()

        from app.upload.imgbb import ImgBBProvider
        provider = ImgBBProvider()
        ok, msg = provider.validate_api_key(api_key)
        self.lbl_conn_status.setText(msg)
        if ok:
            self.lbl_conn_status.setStyleSheet("color: #48BB78; font-size: 12px; font-weight: 600;")
        else:
            self.lbl_conn_status.setStyleSheet("color: #FC8181; font-size: 12px; font-weight: 600;")

    def _refresh_share_history_info(self) -> None:
        from app.upload.history_manager import ShareHistoryManager
        items = ShareHistoryManager.get_items()
        count = len(items)
        if count == 0:
            self.lbl_history_info.setText("Henüz kayıtlı paylaşım geçmişi bulunmuyor.")
            self.lbl_history_info.setStyleSheet("color: #94A3B8; font-size: 12.5px;")
            self.btn_clear_history.setEnabled(False)
        else:
            self.lbl_history_info.setText(f"Toplam {count} paylaşılan görsel kaydı mevcut.")
            self.lbl_history_info.setStyleSheet("color: #4ADE80; font-size: 12.5px; font-weight: 600;")
            self.btn_clear_history.setEnabled(True)

    def _on_open_share_history_dialog(self) -> None:
        from app.ui.share_history_dialog import ShareHistoryDialog
        dlg = ShareHistoryDialog(parent=self)
        dlg.exec()
        self._refresh_share_history_info()

    def _on_open_share_history_folder(self) -> None:
        from app.upload.history_manager import ShareHistoryManager
        from app.utils.helpers import open_folder_in_file_manager
        p = ShareHistoryManager.get_history_file_path()
        open_folder_in_file_manager(str(p.parent))

    def _on_clear_share_history(self) -> None:
        reply = QMessageBox.question(
            self,
            "Geçmişi Temizle",
            "Tüm yerel paylaşım geçmişi silinecektir. Devam etmek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from app.upload.history_manager import ShareHistoryManager
            ShareHistoryManager.clear_history()
            self._refresh_share_history_info()

    def _update_color_preview(self, color_hex: str) -> None:
        self._current_color = color_hex
        self.color_preview.setStyleSheet(f"background-color: {color_hex}; border: 1px solid #CBD5E0; border-radius: 6px;")
        self.color_hex_label.setText(color_hex)

    def _on_choose_color(self) -> None:
        c = QColorDialog.getColor(self._current_color, self, tr("dialog_select_color"))
        if c.isValid():
            self._update_color_preview(c.name().upper())

    def _update_tint_preview(self, tint_hex: str) -> None:
        self._current_tint = tint_hex
        if tint_hex:
            self.tint_preview.setStyleSheet(f"background-color: {tint_hex}; border: 1px solid #CBD5E0; border-radius: 6px;")
            self.tint_hex_label.setText(tint_hex)
        else:
            self.tint_preview.setStyleSheet("background-color: transparent; border: 1px dashed #718096; border-radius: 6px;")
            self.tint_hex_label.setText(tr("opt_no_tint"))

    def _on_choose_tint(self) -> None:
        init_c = self._current_tint or "#000000"
        c = QColorDialog.getColor(init_c, self, tr("lbl_blur_tint"))
        if c.isValid():
            self._update_tint_preview(c.name().upper())

    def _on_clear_tint(self) -> None:
        self._update_tint_preview("")

    def _make_form_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #FFFFFF; font-weight: 500;")
        return lbl

    def _insert_naming_token(self, token: str) -> None:
        cur = self.naming_template_edit.text()
        if cur and not cur.endswith("_") and not cur.endswith("-"):
            self.naming_template_edit.setText(f"{cur}_{token}")
        else:
            self.naming_template_edit.setText(f"{cur}{token}")

    def _update_naming_preview(self) -> None:
        from app.services.naming_service import DEFAULT_NAMING_TEMPLATE, SmartNamingService

        raw_tpl = self.naming_template_edit.text().strip()
        fmt_ext = self.format_combo.currentText().lower() if hasattr(self, "format_combo") else "png"
        counter_val = int(self.config_manager.get("naming", "counter", 1))
        is_valid = SmartNamingService.is_template_valid(raw_tpl)
        sample_name = SmartNamingService.preview_filename(raw_tpl, ext=fmt_ext, counter=counter_val)
        if is_valid:
            self.naming_preview_lbl.setText(f"✓ Canlı Önizleme: {sample_name}")
            self.naming_preview_lbl.setStyleSheet(
                "color: #4ADE80; font-size: 12px; font-weight: 600; font-family: 'Consolas', monospace; "
                "background-color: rgba(15, 23, 42, 0.8); padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(74, 222, 128, 0.25);"
            )
        else:
            self.naming_preview_lbl.setText(
                f"⚠ Geçersiz şablon (Varsayılan '{DEFAULT_NAMING_TEMPLATE}' kullanılacak): {sample_name}"
            )
            self.naming_preview_lbl.setStyleSheet(
                "color: #FBBF24; font-size: 12px; font-weight: 600; font-family: 'Consolas', monospace; "
                "background-color: rgba(15, 23, 42, 0.8); padding: 6px 10px; border-radius: 6px; border: 1px solid rgba(251, 191, 36, 0.3);"
            )

    def _collect_ui_wm_dict(self) -> Dict[str, object]:
        return {
            "enabled": self.wm_enabled_cb.isChecked(),
            "auto_apply_on_save": self.wm_auto_save_cb.isChecked(),
            "auto_apply_on_copy": self.wm_auto_copy_cb.isChecked(),
            "apply_on_export": self.wm_export_cb.isChecked(),
            "watermark_type": self.wm_type_combo.currentData() or "text",
            "text": self.wm_text_edit.text().strip() or "Quickglint",
            "image_path": self.wm_image_edit.text().strip(),
            "position": self.wm_pos_combo.currentData() or "bottom_right",
            "margin": self.wm_margin_spin.value(),
            "opacity": self.wm_opacity_spin.value(),
            "scale_percent": self.wm_scale_spin.value(),
            "rotation": self.wm_rotation_spin.value(),
            "font_family": self.wm_font_edit.text().strip() or "Segoe UI",
            "text_color": self.wm_color_edit.text().strip() or "#FFFFFF",
            "shadow_enabled": self.wm_shadow_cb.isChecked(),
            "tiled": self.wm_tiled_cb.isChecked(),
            "tile_spacing": self.wm_tile_spacing_spin.value(),
            "diagonal_banner": self.wm_diagonal_cb.isChecked(),
        }

    def _apply_wm_dict_to_ui(self, wm: Dict[str, object]) -> None:
        self.wm_enabled_cb.setChecked(bool(wm.get("enabled", False)))
        self.wm_auto_save_cb.setChecked(bool(wm.get("auto_apply_on_save", False)))
        self.wm_auto_copy_cb.setChecked(bool(wm.get("auto_apply_on_copy", False)))
        self.wm_export_cb.setChecked(bool(wm.get("apply_on_export", False)))
        t_idx = self.wm_type_combo.findData(str(wm.get("watermark_type", "text")))
        if t_idx >= 0:
            self.wm_type_combo.setCurrentIndex(t_idx)
        self.wm_text_edit.setText(str(wm.get("text", "Quickglint")))
        self.wm_image_edit.setText(str(wm.get("image_path", "")))
        p_idx = self.wm_pos_combo.findData(str(wm.get("position", "bottom_right")))
        if p_idx >= 0:
            self.wm_pos_combo.setCurrentIndex(p_idx)
        self.wm_margin_spin.setValue(int(wm.get("margin", 20)))
        self.wm_opacity_spin.setValue(int(wm.get("opacity", 65)))
        self.wm_scale_spin.setValue(int(wm.get("scale_percent", 18)))
        self.wm_rotation_spin.setValue(int(wm.get("rotation", 0)))
        self.wm_font_edit.setText(str(wm.get("font_family", "Segoe UI")))
        self.wm_color_edit.setText(str(wm.get("text_color", "#FFFFFF")))
        self.wm_shadow_cb.setChecked(bool(wm.get("shadow_enabled", True)))
        self.wm_tiled_cb.setChecked(bool(wm.get("tiled", False)))
        self.wm_tile_spacing_spin.setValue(int(wm.get("tile_spacing", 25)))
        self.wm_diagonal_cb.setChecked(bool(wm.get("diagonal_banner", False)))

    def _refresh_wm_profile_combo(self) -> None:
        if not hasattr(self, "wm_profile_combo"):
            return
        self.wm_profile_combo.blockSignals(True)
        self.wm_profile_combo.clear()
        self.wm_profile_combo.addItem("Varsayılan")
        profiles = self.config_manager.get("watermark", "profiles", {}) or {}
        for p_name in sorted(profiles.keys()):
            if p_name != "Varsayılan":
                self.wm_profile_combo.addItem(p_name)
        active = str(self.config_manager.get("watermark", "active_profile", "Varsayılan"))
        idx = self.wm_profile_combo.findText(active)
        if idx >= 0:
            self.wm_profile_combo.setCurrentIndex(idx)
        self.wm_profile_combo.blockSignals(False)

    def _on_wm_profile_selected(self, name: str) -> None:
        if not name:
            return
        profiles = self.config_manager.get("watermark", "profiles", {}) or {}
        if name in profiles and isinstance(profiles[name], dict):
            self._apply_wm_dict_to_ui(profiles[name])
            self._update_watermark_live_preview()

    def _on_save_wm_profile(self) -> None:
        from app.services.watermark_service import WatermarkService, WatermarkSettings

        name = self.wm_profile_name_edit.text().strip() or self.wm_profile_combo.currentText().strip()
        if not name:
            return
        settings = WatermarkSettings.from_dict(self._collect_ui_wm_dict())
        WatermarkService.save_profile(self.config_manager, name, settings)
        self.wm_profile_name_edit.clear()
        self._refresh_wm_profile_combo()

    def _on_delete_wm_profile(self) -> None:
        from app.services.watermark_service import WatermarkService

        name = self.wm_profile_combo.currentText().strip()
        if not name or name == "Varsayılan":
            return
        WatermarkService.delete_profile(self.config_manager, name)
        self._refresh_wm_profile_combo()

    def _on_browse_wm_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Filigran Görseli Seç (PNG)", "", "PNG Görselleri (*.png);;Tüm Görseller (*.png *.webp)"
        )
        if path:
            self.wm_image_edit.setText(path)

    def _on_choose_wm_color(self) -> None:
        cur = self.wm_color_edit.text().strip() or "#FFFFFF"
        c = QColorDialog.getColor(QColor(cur), self, "Filigran Metin Rengi")
        if c.isValid():
            self.wm_color_edit.setText(c.name().upper())

    def _collect_ui_ib_dict(self) -> Dict[str, object]:
        return {
            "enabled": self.ib_enabled_cb.isChecked(),
            "auto_apply_on_save": self.ib_auto_save_cb.isChecked(),
            "auto_apply_on_copy": self.ib_auto_copy_cb.isChecked(),
            "apply_on_export": self.ib_export_cb.isChecked(),
            "show_datetime": self.ib_dt_cb.isChecked(),
            "show_window_title": self.ib_win_cb.isChecked(),
            "show_app_name": self.ib_app_cb.isChecked(),
            "show_url": self.ib_url_cb.isChecked(),
            "show_resolution": self.ib_res_cb.isChecked(),
            "show_computer_name": self.ib_comp_cb.isChecked(),
            "show_user_name": self.ib_user_cb.isChecked(),
            "show_custom_text": self.ib_custom_cb.isChecked(),
            "custom_text": self.ib_custom_edit.text().strip(),
            "theme": self.ib_theme_combo.currentData() or "dark",
            "bg_color": self.ib_bg_edit.text().strip() or "#0F172A",
            "text_color": self.ib_fg_edit.text().strip() or "#F8FAFC",
            "separator_color": "#334155",
            "show_separator": self.ib_sep_cb.isChecked(),
            "font_size": self.ib_font_spin.value(),
            "alignment": self.ib_align_combo.currentData() or "left",
            "wrap_long_text": self.ib_wrap_cb.isChecked(),
        }

    def _update_watermark_live_preview(self) -> None:
        if not hasattr(self, "wm_live_preview_lbl"):
            return
        from PySide6.QtGui import QImage
        from app.services.info_banner_service import InfoBannerService, InfoBannerSettings
        from app.services.naming_service import CaptureMetadata
        from app.services.watermark_service import WatermarkService, WatermarkSettings

        sample = QImage(460, 115, QImage.Format.Format_RGBA8888)
        sample.fill(QColor("#1E293B"))
        p = QPainter(sample)
        p.setPen(QColor("#475569"))
        p.drawRect(0, 0, 459, 114)
        p.setPen(QColor("#94A3B8"))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(sample.rect(), Qt.AlignmentFlag.AlignCenter, "Örnek Ekran Görüntüsü Alanı")
        p.end()

        wm_cfg = WatermarkSettings.from_dict(self._collect_ui_wm_dict())
        sample = WatermarkService.apply_watermark(sample, settings=wm_cfg)

        ib_cfg = InfoBannerSettings.from_dict(self._collect_ui_ib_dict())
        if ib_cfg.enabled:
            meta = CaptureMetadata(
                window_title="Quickglint — Örnek Pencere",
                app_name="quickglint",
                url="https://quickglint.example",
                resolution="1920 × 1080 px",
            )
            sample = InfoBannerService.apply_info_banner(sample, settings=ib_cfg, metadata=meta)

        pix = QPixmap.fromImage(sample).scaled(
            460,
            142,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.wm_live_preview_lbl.setPixmap(pix)

    def _on_browse_folder(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, tr("dialog_select_folder"), self.folder_edit.text())
        if dir_path:
            self.folder_edit.setText(dir_path)

    def _on_reset_defaults(self) -> None:
        self.config_manager.reset_to_defaults()
        try:
            from app.security.credential_store import CredentialStore
            CredentialStore.delete_credential("imgbb", "user")
        except Exception as e:
            logger.warning(f"Failed to clear stored API key on reset: {e}")
        self._load_values()
        if hasattr(self, "imgbb_key_edit"):
            self.imgbb_key_edit.clear()
        if hasattr(self, "imgbb_status_label"):
            self.imgbb_status_label.setText(tr("settings_cloud_api_key_not_configured") if tr("settings_cloud_api_key_not_configured") != "settings_cloud_api_key_not_configured" else "Yapılandırılmadı (İsteğe Bağlı)")
            self.imgbb_status_label.setStyleSheet("color: #64748b; font-size: 11px;")

    def _on_save(self) -> None:
        selected_lang = self.lang_combo.currentData()
        self.config_manager.set("general", "language", selected_lang)
        set_language(selected_lang)

        autostart = self.autostart_cb.isChecked()
        self.config_manager.set("general", "start_with_windows", autostart)
        self.config_manager.set("general", "minimize_to_tray", self.minimize_tray_cb.isChecked())
        self.config_manager.set("general", "show_notifications", self.show_notif_cb.isChecked())
        self.config_manager.set("general", "default_save_dir", self.folder_edit.text())

        if AutostartService.is_supported():
            if autostart:
                AutostartService.enable()
            else:
                AutostartService.disable()

        # Save all hotkeys
        for key, editor in self._hotkey_editors.items():
            self.config_manager.set("hotkeys", key, editor.get_hotkey())

        # Smart Privacy
        self.config_manager.set("privacy", "enabled", self.priv_enabled_cb.isChecked())
        self.config_manager.set("privacy", "auto_redact_on_save", self.priv_auto_redact_cb.isChecked())
        self.config_manager.set("privacy", "default_effect", self.priv_effect_combo.currentData())
        self.config_manager.set("privacy", "ocr_engine", self.priv_ocr_combo.currentData())
        self.config_manager.set("privacy", "detect_emails", self.cb_det_email.isChecked())
        self.config_manager.set("privacy", "detect_phones", self.cb_det_phone.isChecked())
        self.config_manager.set("privacy", "detect_ips", self.cb_det_ip.isChecked())
        self.config_manager.set("privacy", "detect_urls", self.cb_det_url.isChecked())
        self.config_manager.set("privacy", "detect_api_keys", self.cb_det_api.isChecked())
        self.config_manager.set("privacy", "detect_credit_cards", self.cb_det_card.isChecked())
        self.config_manager.set("privacy", "detect_iban", self.cb_det_iban.isChecked())
        self.config_manager.set("privacy", "detect_file_paths", self.cb_det_path.isChecked())

        # OCR
        self.config_manager.set("ocr", "engine", self.ocr_engine_combo.currentData())
        selected_ocr_langs = []
        if self.ocr_lang_tr.isChecked():
            selected_ocr_langs.append("tr")
        if self.ocr_lang_en.isChecked():
            selected_ocr_langs.append("en")
        if self.ocr_lang_de.isChecked():
            selected_ocr_langs.append("de")
        if self.ocr_lang_fr.isChecked():
            selected_ocr_langs.append("fr")
        if self.ocr_lang_es.isChecked():
            selected_ocr_langs.append("es")
        if self.ocr_lang_it.isChecked():
            selected_ocr_langs.append("it")
        if not selected_ocr_langs:
            selected_ocr_langs = ["tr", "en"]
        self.config_manager.set("ocr", "languages", selected_ocr_langs)
        self.config_manager.set("ocr", "auto_detect_after_capture", self.ocr_auto_detect_cb.isChecked())
        self.config_manager.set("ocr", "enhance_contrast", self.ocr_enhance_contrast_cb.isChecked())
        self.config_manager.set("ocr", "upscale_small", self.ocr_upscale_small_cb.isChecked())

        # QR Code
        self.config_manager.set("qr", "enabled", self.qr_enabled_cb.isChecked())
        self.config_manager.set("qr", "show_panel_automatically", self.qr_show_panel_cb.isChecked())
        self.config_manager.set("qr", "highlight_detected", self.qr_highlight_cb.isChecked())

        # Scrolling
        self.config_manager.set("scrolling", "max_captures", self.max_captures_spin.value())
        self.config_manager.set("scrolling", "max_height", self.max_height_spin.value())

        # Recorder
        try:
            fps_val = int(self.gif_fps_combo.currentText().split()[0])
            self.config_manager.set("recorder", "fps", fps_val)
        except Exception:
            pass
        self.config_manager.set("recorder", "max_duration", float(self.gif_duration_spin.value()))
        self.config_manager.set("recorder", "show_cursor", self.gif_cursor_cb.isChecked())
        self.config_manager.set("recorder", "highlight_cursor", self.gif_halo_cb.isChecked())
        self.config_manager.set("recorder", "show_click_effects", self.gif_clicks_cb.isChecked())

        # Image
        self.config_manager.set("image", "default_format", self.format_combo.currentText())
        self.config_manager.set("image", "jpeg_quality", self.quality_slider.value())
        self.config_manager.set("image", "include_cursor", self.cursor_cb.isChecked())

        # Smart File Naming
        from app.services.naming_service import DEFAULT_NAMING_TEMPLATE, SmartNamingService

        raw_tpl = self.naming_template_edit.text().strip()
        final_tpl = raw_tpl if SmartNamingService.is_template_valid(raw_tpl) else DEFAULT_NAMING_TEMPLATE
        self.config_manager.set("naming", "template", final_tpl)

        # Watermark
        wm_values = self._collect_ui_wm_dict()
        wm_values["active_profile"] = self.wm_profile_combo.currentText() or "Varsayılan"
        self.config_manager.update_section("watermark", wm_values)

        # Info Banner
        ib_values = self._collect_ui_ib_dict()
        self.config_manager.update_section("info_banner", ib_values)

        # Editor
        self.config_manager.set("editor", "default_color", self._current_color)
        brush_data = self.brush_size_combo.currentData()
        if brush_data is not None:
            self.config_manager.set("editor", "default_brush_size", int(brush_data))
        self.config_manager.set("editor", "default_font_size", self.font_size_spin.value())

        # Blur & Pixelate
        self.config_manager.set("editor", "blur_radius", self.blur_radius_slider.value())
        self.config_manager.set("editor", "pixel_size", self.pixel_size_slider.value())
        self.config_manager.set("editor", "blur_tint", self._current_tint)
        self.config_manager.set("editor", "blur_tint_opacity", self.tint_opacity_slider.value() / 100.0)

        # Upload & Share (DPAPI)
        from app.security.credential_store import CredentialStore
        entered_key = self.imgbb_key_edit.text().strip()
        if entered_key:
            CredentialStore.set_credential("imgbb", "user", entered_key)
        else:
            CredentialStore.delete_credential("imgbb", "user")

        self.config_manager.set("upload", "privacy_check", self.cb_upload_privacy_check.isChecked())
        self.config_manager.set("upload", "clean_metadata", self.cb_upload_clean_metadata.isChecked())
        self.config_manager.set("upload", "copy_share_url", self.cb_upload_copy_share.isChecked())
        self.config_manager.set("upload", "copy_direct_url", self.cb_upload_copy_direct.isChecked())
        self.config_manager.set("upload", "save_history", self.cb_upload_save_history.isChecked())
        self.config_manager.set("upload", "expiration", self.upload_expiration_combo.currentData())

        # Panorama Capture
        self.config_manager.set("panorama", "detector", self.pano_detector_combo.currentData() or "auto")
        self.config_manager.set("panorama", "blending", self.pano_blend_combo.currentData() or "multiband")
        self.config_manager.set("panorama", "exposure_compensation", self.pano_exposure_cb.isChecked())
        self.config_manager.set("panorama", "normalize_dpi", self.pano_dpi_cb.isChecked())
        self.config_manager.set("panorama", "auto_crop", self.pano_autocrop_cb.isChecked())

        self.settings_saved.emit()
        self.accept()

