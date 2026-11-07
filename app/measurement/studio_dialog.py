"""Full-featured standalone window for Quickglint Professional Measurement Studio."""

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.measurement.canvas import MeasurementCanvas
from app.measurement.models import ColorInfo, MeasurementItem, MeasurementType, SnapMode
from app.services.clipboard_service import ClipboardService
from app.services.storage_service import StorageService
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.constants import APP_NAME, APP_VERSION
from app.utils.helpers import open_folder_in_file_manager
from app.utils.logger import logger


class MeasurementStudioWindow(QDialog):
    """Complete Professional Measurement Studio application window."""

    def __init__(
        self,
        image: Optional[QImage] = None,
        image_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.image_path = image_path
        if image is not None:
            self.image = image
        elif image_path and Path(image_path).exists():
            self.image = QImage(image_path)
        else:
            # Fallback blank template image (1920x1080)
            self.image = QImage(1920, 1080, QImage.Format.Format_ARGB32)
            self.image.fill(QColor("#1E293B"))

        # Setup standard window flags
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setWindowTitle(
            f"Quickglint — Measurement Studio ({self.image.width()} × {self.image.height()} px)"
        )
        self.resize(1340, 860)
        self.setMinimumSize(960, 620)
        self.setStyleSheet(DARK_THEME_QSS)

        self._setup_ui()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 8)
        main_layout.setSpacing(8)

        # Initialize Canvas first so toolbars can connect to it safely
        self.canvas = MeasurementCanvas(self.image)
        self.canvas.measurement_added.connect(self._on_measurement_added)
        self.canvas.mouse_moved_pixel.connect(self._on_mouse_moved_pixel)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)

        # 1. Top Unified Header & Tools Ribbon
        top_bar = self._create_top_toolbar()
        main_layout.addWidget(top_bar)

        # 2. Central Splitter (Canvas + Sidebar)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setStyleSheet(
            """
            QSplitter::handle {
                background-color: rgba(255, 255, 255, 0.08);
                width: 2px;
            }
            """
        )

        self.canvas.setParent(splitter)
        splitter.addWidget(self.canvas)

        # Right Sidebar Panel (Measurement List & Property Inspector)
        sidebar = self._create_sidebar()
        splitter.addWidget(sidebar)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, stretch=1)

        # 3. Bottom Status Bar
        status_bar = self._create_status_bar()
        main_layout.addWidget(status_bar)

        # Initial zoom fit
        self.canvas.fit_to_view()

    def _create_top_toolbar(self) -> QFrame:
        top_bar = QFrame(self)
        top_bar.setStyleSheet(
            """
            QFrame {
                background-color: #0F172A;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                padding: 4px 8px;
            }
            """
        )
        bar_layout = QHBoxLayout(top_bar)
        bar_layout.setContentsMargins(6, 4, 6, 4)
        bar_layout.setSpacing(8)

        # Title / Brand Icon
        brand_icon = QLabel(top_bar)
        brand_icon.setPixmap(get_icon("line", "#38BDF8", 20).pixmap(20, 20))
        bar_layout.addWidget(brand_icon)

        brand_lbl = QLabel("Measurement Studio", top_bar)
        brand_lbl.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 13.5px;")
        bar_layout.addWidget(brand_lbl)

        sep0 = QFrame()
        sep0.setFrameShape(QFrame.Shape.VLine)
        sep0.setStyleSheet("color: rgba(255, 255, 255, 0.15);")
        bar_layout.addWidget(sep0)

        # Tool Buttons Group
        self.tool_btn_group = QButtonGroup(self)
        self.tool_btn_group.setExclusive(True)

        tools = [
            (MeasurementType.DISTANCE, "Mesafe (Distance)", "line", "#38BDF8"),
            (MeasurementType.HORIZONTAL, "Yatay (Horizontal)", "arrow", "#60A5FA"),
            (MeasurementType.VERTICAL, "Dikey (Vertical)", "scroll", "#818CF8"),
            (MeasurementType.RECTANGLE, "Dikdörtgen (Rectangle)", "rect", "#34D399"),
            (MeasurementType.ANGLE, "Açı (Angle)", "sparkles", "#A78BFA"),
            (MeasurementType.POINT, "Nokta & Renk (Point)", "pipette", "#FBBF24"),
        ]

        for mtype, label, icon_name, color in tools:
            btn = QToolButton(top_bar)
            btn.setCheckable(True)
            btn.setIcon(get_icon(icon_name, color, 16))
            btn.setText(f" {label}")
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._tool_btn_qss())
            if mtype == MeasurementType.DISTANCE:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, t=mtype: self._select_tool(t))
            self.tool_btn_group.addButton(btn)
            bar_layout.addWidget(btn)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: rgba(255, 255, 255, 0.15);")
        bar_layout.addWidget(sep1)

        # Snap Selector
        snap_lbl = QLabel("Snap:", top_bar)
        snap_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        bar_layout.addWidget(snap_lbl)

        self.snap_combo = QComboBox(top_bar)
        self.snap_combo.addItem("Kapalı (None)", SnapMode.NONE)
        self.snap_combo.addItem("Piksel (Pixel)", SnapMode.PIXEL)
        self.snap_combo.addItem("Grid (Grid)", SnapMode.GRID)
        self.snap_combo.addItem("Kenar (Edge)", SnapMode.EDGE)
        self.snap_combo.addItem("Merkez (Center)", SnapMode.CENTER)
        self.snap_combo.setStyleSheet(self._combo_qss())
        self.snap_combo.currentIndexChanged.connect(self._on_snap_mode_changed)
        bar_layout.addWidget(self.snap_combo)

        # Grid Toggle & Size
        self.cb_grid = QCheckBox("Grid", top_bar)
        self.cb_grid.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        self.cb_grid.toggled.connect(self._on_grid_toggled)
        bar_layout.addWidget(self.cb_grid)

        self.grid_size_combo = QComboBox(top_bar)
        for sz in (8, 16, 24, 32, 64):
            self.grid_size_combo.addItem(f"{sz} px", sz)
        self.grid_size_combo.setCurrentIndex(1)  # 16 px default
        self.grid_size_combo.setStyleSheet(self._combo_qss())
        self.grid_size_combo.currentIndexChanged.connect(self._on_grid_size_changed)
        bar_layout.addWidget(self.grid_size_combo)

        # Center Guides Toggle
        self.cb_center_guides = QCheckBox("Merkez Kılavuzu", top_bar)
        self.cb_center_guides.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        self.cb_center_guides.toggled.connect(self._on_center_guides_toggled)
        bar_layout.addWidget(self.cb_center_guides)

        bar_layout.addStretch()

        # Zoom Buttons
        btn_zoom_out = QToolButton(top_bar)
        btn_zoom_out.setText("－")
        btn_zoom_out.setToolTip("Uzaklaştır (Ctrl+-)")
        btn_zoom_out.setStyleSheet(self._action_tool_btn_qss())
        btn_zoom_out.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.zoom_factor / 1.25))
        bar_layout.addWidget(btn_zoom_out)

        self.lbl_zoom = QLabel("100%", top_bar)
        self.lbl_zoom.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 12px; min-width: 45px; text-align: center;")
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self.lbl_zoom)

        btn_zoom_in = QToolButton(top_bar)
        btn_zoom_in.setText("＋")
        btn_zoom_in.setToolTip("Yakınlaştır (Ctrl++)")
        btn_zoom_in.setStyleSheet(self._action_tool_btn_qss())
        btn_zoom_in.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.zoom_factor * 1.25))
        bar_layout.addWidget(btn_zoom_in)

        btn_fit = QPushButton("Sığdır", top_bar)
        btn_fit.setToolTip("Görseli Ekrana Sığdır (Ctrl+0)")
        btn_fit.setStyleSheet(self._btn_secondary_qss())
        btn_fit.clicked.connect(self.canvas.fit_to_view)
        bar_layout.addWidget(btn_fit)

        btn_100 = QPushButton("1:1", top_bar)
        btn_100.setToolTip("100% Gerçek Boyut")
        btn_100.setStyleSheet(self._btn_secondary_qss())
        btn_100.clicked.connect(self.canvas.zoom_100)
        bar_layout.addWidget(btn_100)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: rgba(255, 255, 255, 0.15);")
        bar_layout.addWidget(sep2)

        # Load / Save Actions
        btn_open = QPushButton("Görsel Yükle...", top_bar)
        btn_open.setIcon(get_icon("folder", "#FCD34D", 14))
        btn_open.setStyleSheet(self._btn_secondary_qss())
        btn_open.clicked.connect(self._on_load_image_clicked)
        bar_layout.addWidget(btn_open)

        btn_copy_img = QPushButton("Panoya Kopyala", top_bar)
        btn_copy_img.setIcon(get_icon("copy", "#FFFFFF", 14))
        btn_copy_img.setStyleSheet(self._btn_primary_qss())
        btn_copy_img.clicked.connect(self._on_copy_with_overlays)
        bar_layout.addWidget(btn_copy_img)

        btn_save = QPushButton("Kaydet...", top_bar)
        btn_save.setIcon(get_icon("save", "#FFFFFF", 14))
        btn_save.setStyleSheet(self._btn_primary_green_qss())
        btn_save.clicked.connect(self._on_save_with_overlays)
        bar_layout.addWidget(btn_save)

        return top_bar

    def _create_sidebar(self) -> QFrame:
        sidebar = QFrame(self)
        sidebar.setStyleSheet(
            """
            QFrame {
                background-color: #0F172A;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                padding: 8px;
            }
            """
        )
        s_layout = QVBoxLayout(sidebar)
        s_layout.setContentsMargins(8, 8, 8, 8)
        s_layout.setSpacing(10)

        # Header with Counter Badge
        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel("Ölçümler (Measurements)", sidebar)
        hdr_lbl.setStyleSheet("color: #FFFFFF; font-weight: 700; font-size: 13.5px;")
        hdr_row.addWidget(hdr_lbl)

        self.list_badge = QLabel("0", sidebar)
        self.list_badge.setStyleSheet(
            """
            background-color: rgba(56, 189, 248, 0.2);
            color: #38BDF8;
            border: 1px solid rgba(56, 189, 248, 0.35);
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 600;
            """
        )
        hdr_row.addWidget(self.list_badge)
        hdr_row.addStretch()

        btn_clear = QPushButton("Temizle", sidebar)
        btn_clear.setIcon(get_icon("trash", "#F87171", 12))
        btn_clear.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(239, 68, 68, 0.12);
                color: #FCA5A5;
                border: 1px solid rgba(239, 68, 68, 0.25);
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.25);
            }
            """
        )
        btn_clear.clicked.connect(self._on_clear_all_measurements)
        hdr_row.addWidget(btn_clear)
        s_layout.addLayout(hdr_row)

        # Measurement List Widget
        self.items_list = QListWidget(sidebar)
        self.items_list.setStyleSheet(
            """
            QListWidget {
                background-color: rgba(15, 23, 42, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                color: #F1F5F9;
                font-size: 12.5px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 6px;
                margin-bottom: 3px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.06);
            }
            QListWidget::item:selected {
                background-color: rgba(56, 189, 248, 0.18);
                border: 1px solid rgba(56, 189, 248, 0.4);
                color: #FFFFFF;
                font-weight: 600;
            }
            """
        )
        self.items_list.itemClicked.connect(self._on_list_item_clicked)
        s_layout.addWidget(self.items_list, stretch=2)

        # Inspector Card (Properties for selected measurement)
        self.inspector_card = QFrame(sidebar)
        self.inspector_card.setStyleSheet(
            """
            QFrame {
                background-color: rgba(30, 41, 59, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 8px;
            }
            """
        )
        insp_layout = QVBoxLayout(self.inspector_card)
        insp_layout.setContentsMargins(8, 8, 8, 8)
        insp_layout.setSpacing(6)

        insp_title = QLabel("Seçili Ölçüm Detayı", self.inspector_card)
        insp_title.setStyleSheet("color: #38BDF8; font-weight: 700; font-size: 12px;")
        insp_layout.addWidget(insp_title)

        self.lbl_insp_details = QLabel("Bir ölçüm seçin veya çizin.", self.inspector_card)
        self.lbl_insp_details.setStyleSheet("color: #CBD5E1; font-size: 11.5px; font-family: 'Consolas', monospace;")
        self.lbl_insp_details.setWordWrap(True)
        self.lbl_insp_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        insp_layout.addWidget(self.lbl_insp_details)

        # Action Buttons for selected measurement
        act_row = QHBoxLayout()
        act_row.setContentsMargins(0, 4, 0, 0)
        act_row.setSpacing(6)

        self.btn_copy_val = QPushButton("Kopyala", self.inspector_card)
        self.btn_copy_val.setIcon(get_icon("copy", "#38BDF8", 12))
        self.btn_copy_val.setStyleSheet(self._btn_secondary_qss())
        self.btn_copy_val.clicked.connect(self._on_copy_selected_value)
        act_row.addWidget(self.btn_copy_val)

        self.btn_copy_css = QPushButton("CSS", self.inspector_card)
        self.btn_copy_css.setStyleSheet(self._btn_secondary_qss())
        self.btn_copy_css.clicked.connect(self._on_copy_selected_css)
        act_row.addWidget(self.btn_copy_css)

        self.btn_copy_json = QPushButton("JSON", self.inspector_card)
        self.btn_copy_json.setStyleSheet(self._btn_secondary_qss())
        self.btn_copy_json.clicked.connect(self._on_copy_selected_json)
        act_row.addWidget(self.btn_copy_json)

        self.btn_rename = QPushButton("İsim", self.inspector_card)
        self.btn_rename.setStyleSheet(self._btn_secondary_qss())
        self.btn_rename.clicked.connect(self._on_rename_selected)
        act_row.addWidget(self.btn_rename)

        self.btn_del_item = QPushButton(self.inspector_card)
        self.btn_del_item.setIcon(get_icon("trash", "#F87171", 14))
        self.btn_del_item.setStyleSheet(
            "background-color: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 5px;"
        )
        self.btn_del_item.setFixedSize(28, 28)
        self.btn_del_item.clicked.connect(self._on_delete_selected_item)
        act_row.addWidget(self.btn_del_item)

        insp_layout.addLayout(act_row)
        s_layout.addWidget(self.inspector_card, stretch=1)

        return sidebar

    def _create_status_bar(self) -> QFrame:
        status_bar = QFrame(self)
        status_bar.setStyleSheet(
            """
            QFrame {
                background-color: #0F172A;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 4px 12px;
            }
            """
        )
        st_layout = QHBoxLayout(status_bar)
        st_layout.setContentsMargins(8, 2, 8, 2)
        st_layout.setSpacing(16)

        # 1. Live Coordinates
        self.lbl_coord = QLabel("X: 0 px  •  Y: 0 px", status_bar)
        self.lbl_coord.setStyleSheet("color: #F8FAFC; font-weight: 600; font-size: 12px; font-family: 'Consolas', monospace;")
        st_layout.addWidget(self.lbl_coord)

        # 2. Live Color Swatch & Value
        self.color_swatch = QLabel(status_bar)
        self.color_swatch.setFixedSize(14, 14)
        self.color_swatch.setStyleSheet("background-color: #000000; border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 3px;")
        st_layout.addWidget(self.color_swatch)

        self.lbl_color_val = QLabel("HEX: #000000", status_bar)
        self.lbl_color_val.setStyleSheet("color: #94A3B8; font-size: 12px; font-family: 'Consolas', monospace;")
        st_layout.addWidget(self.lbl_color_val)

        st_layout.addStretch()

        # 3. Image Resolution
        self.lbl_resolution = QLabel(f"Çözünürlük: {self.image.width()} × {self.image.height()} px", status_bar)
        self.lbl_resolution.setStyleSheet("color: #94A3B8; font-size: 12px;")
        st_layout.addWidget(self.lbl_resolution)

        return status_bar

    # =========================================================================
    # Slot Handlers
    # =========================================================================
    def _select_tool(self, mtype: MeasurementType) -> None:
        self.canvas.active_tool = mtype

    def _on_snap_mode_changed(self, idx: int) -> None:
        mode = self.snap_combo.currentData()
        self.canvas.snap_mode = mode if mode else SnapMode.NONE
        self.canvas.update()

    def _on_grid_toggled(self, checked: bool) -> None:
        self.canvas.show_grid = checked
        self.canvas.update()

    def _on_grid_size_changed(self, idx: int) -> None:
        sz = self.grid_size_combo.currentData()
        self.canvas.grid_size = sz if sz else 16
        self.canvas.update()

    def _on_center_guides_toggled(self, checked: bool) -> None:
        self.canvas.show_center_guides = checked
        self.canvas.update()

    def _on_zoom_changed(self, zoom: float) -> None:
        self.lbl_zoom.setText(f"{int(round(zoom * 100))}%")

    def _on_mouse_moved_pixel(self, x: int, y: int, col_info: ColorInfo) -> None:
        self.lbl_coord.setText(f"X: {x} px  •  Y: {y} px")
        self.color_swatch.setStyleSheet(f"background-color: {col_info.hex_value}; border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 3px;")
        self.lbl_color_val.setText(f"HEX: {col_info.hex_value}  •  {col_info.rgb_str}")

    def _on_measurement_added(self, item: MeasurementItem) -> None:
        self._refresh_measurements_list()
        self._select_item_by_id(item.id)

    def _refresh_measurements_list(self) -> None:
        self.items_list.clear()
        count = len(self.canvas.measurements)
        self.list_badge.setText(str(count))

        for it in self.canvas.measurements:
            summary = it.to_summary_text()
            list_item = QListWidgetItem(f"{it.name}\n  ↳ {summary}")
            list_item.setData(Qt.ItemDataRole.UserRole, it.id)
            self.items_list.addItem(list_item)

    def _select_item_by_id(self, item_id: str) -> None:
        self.canvas.selected_item_id = item_id
        for i in range(self.items_list.count()):
            li = self.items_list.item(i)
            if li.data(Qt.ItemDataRole.UserRole) == item_id:
                self.items_list.setCurrentItem(li)
                break
        self._update_inspector(item_id)

    def _on_list_item_clicked(self, list_item: QListWidgetItem) -> None:
        item_id = list_item.data(Qt.ItemDataRole.UserRole)
        self.canvas.selected_item_id = item_id
        self.canvas.update()
        self._update_inspector(item_id)

    def _update_inspector(self, item_id: Optional[str]) -> None:
        item = next((it for it in self.canvas.measurements if it.id == item_id), None)
        if not item:
            self.lbl_insp_details.setText("Bir ölçüm seçin veya çizin.")
            return

        lines = [f"<b>{item.name}</b>", f"Tür: {item.mtype.value}"]
        for k, v in item.data.items():
            if isinstance(v, float):
                lines.append(f"• {k}: <b>{v:.2f}</b>")
            else:
                lines.append(f"• {k}: <b>{v}</b>")

        self.lbl_insp_details.setText("<br>".join(lines))

    def _on_copy_selected_value(self) -> None:
        item = self._get_selected_item()
        if item:
            val = item.to_summary_text()
            QApplication.clipboard().setText(val)
            NotificationManager.show_toast("Kopyalandı", f"Ölçüm değeri panoya kopyalandı:\n{val}", "copy", 2000)

    def _on_copy_selected_css(self) -> None:
        item = self._get_selected_item()
        if item:
            css_text = item.to_css()
            QApplication.clipboard().setText(css_text)
            NotificationManager.show_toast("CSS Kopyalandı", f"CSS kuralları panoya kopyalandı:\n{css_text}", "code", 2000)

    def _on_copy_selected_json(self) -> None:
        item = self._get_selected_item()
        if item:
            json_text = item.to_json()
            QApplication.clipboard().setText(json_text)
            NotificationManager.show_toast("JSON Kopyalandı", "JSON verisi panoya kopyalandı.", "copy", 2000)

    def _on_rename_selected(self) -> None:
        item = self._get_selected_item()
        if not item:
            return
        new_name, ok = QInputDialog.getText(self, "Ölçümü Yeniden Adlandır", "Yeni isim:", text=item.name)
        if ok and new_name.strip():
            item.name = new_name.strip()
            self._refresh_measurements_list()
            self._select_item_by_id(item.id)

    def _on_delete_selected_item(self) -> None:
        item = self._get_selected_item()
        if not item:
            return
        self.canvas.measurements = [it for it in self.canvas.measurements if it.id != item.id]
        self.canvas.selected_item_id = None
        self._refresh_measurements_list()
        self.canvas.update()
        self._update_inspector(None)

    def _on_clear_all_measurements(self) -> None:
        if not self.canvas.measurements:
            return
        self.canvas.measurements.clear()
        self.canvas.selected_item_id = None
        self._refresh_measurements_list()
        self.canvas.update()
        self._update_inspector(None)

    def _get_selected_item(self) -> Optional[MeasurementItem]:
        item_id = self.canvas.selected_item_id
        return next((it for it in self.canvas.measurements if it.id == item_id), None)

    # =========================================================================
    # Load & Export Handlers
    # =========================================================================
    def _on_load_image_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Ölçülecek Görseli Seçin",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff);;All Files (*)",
        )
        if path and Path(path).exists():
            loaded = QImage(path)
            if not loaded.isNull():
                self.image = loaded
                self.image_path = path
                self.canvas.image = loaded
                self.canvas.measurements.clear()
                self._refresh_measurements_list()
                self.canvas.fit_to_view()
                self.lbl_resolution.setText(f"Çözünürlük: {self.image.width()} × {self.image.height()} px")
                self.setWindowTitle(f"Quickglint — Measurement Studio ({self.image.width()} × {self.image.height()} px)")
                NotificationManager.show_toast("Görsel Yüklendi", f"{Path(path).name} başarıyla açıldı.", "folder", 2000)

    def _on_copy_with_overlays(self) -> None:
        out_img = self.canvas.export_image_with_overlays()
        if not out_img.isNull():
            ClipboardService.copy_image(out_img)
            NotificationManager.show_toast("Görsel Panoya Kopyalandı", "Ölçüm çizgileriyle birlikte görsel panoya kopyalandı.", "copy", 2500)

    def _on_save_with_overlays(self) -> None:
        out_img = self.canvas.export_image_with_overlays()
        if out_img.isNull():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Ölçümlü Görseli Kaydet",
            "measurement_export.png",
            "PNG Image (*.png);;JPEG Image (*.jpg);;WebP Image (*.webp)",
        )
        if path:
            out_img.save(path)
            NotificationManager.show_toast("Kaydedildi", f"Ölçümlü görsel kaydedildi:\n{Path(path).name}", "save", 3000)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+0"), self, self.canvas.fit_to_view)
        QShortcut(QKeySequence("Ctrl+1"), self, self.canvas.zoom_100)
        QShortcut(QKeySequence("Ctrl+="), self, lambda: self.canvas.set_zoom(self.canvas.zoom_factor * 1.25))
        QShortcut(QKeySequence("Ctrl+-"), self, lambda: self.canvas.set_zoom(self.canvas.zoom_factor / 1.25))
        QShortcut(QKeySequence("Ctrl+C"), self, self._on_copy_selected_value)

    @staticmethod
    def _tool_btn_qss() -> str:
        return """
            QToolButton {
                background-color: rgba(255, 255, 255, 0.05);
                color: #CBD5E1;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 500;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
            }
            QToolButton:checked {
                background-color: rgba(56, 189, 248, 0.22);
                border: 1px solid #38BDF8;
                color: #FFFFFF;
                font-weight: 600;
            }
        """

    @staticmethod
    def _combo_qss() -> str:
        return """
            QComboBox {
                background-color: rgba(15, 23, 42, 0.9);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11.5px;
            }
        """

    @staticmethod
    def _action_tool_btn_qss() -> str:
        return """
            QToolButton {
                background-color: rgba(255, 255, 255, 0.06);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 13px;
                font-weight: 700;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
        """

    @staticmethod
    def _btn_secondary_qss() -> str:
        return """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.15);
                color: #FFFFFF;
            }
        """

    @staticmethod
    def _btn_primary_qss() -> str:
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0284C7, stop:1 #0369A1);
                color: #FFFFFF;
                font-weight: 600;
                font-size: 12px;
                border: 1px solid #38BDF8;
                border-radius: 6px;
                padding: 5px 14px;
            }
            QPushButton:hover {
                background: #0284C7;
            }
        """

    @staticmethod
    def _btn_primary_green_qss() -> str:
        return """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #059669, stop:1 #047857);
                color: #FFFFFF;
                font-weight: 600;
                font-size: 12px;
                border: 1px solid #34D399;
                border-radius: 6px;
                padding: 5px 14px;
            }
            QPushButton:hover {
                background: #059669;
            }
        """

