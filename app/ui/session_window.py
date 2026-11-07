"""Non-modal gallery window for an in-memory screenshot session."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QImage, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.ocr.dialog import TextExtractionDialog
from app.ocr.provider import AutoOCRProvider
from app.session.screenshot_session import ScreenshotSession
from app.session.session_exporter import (
    ExportResult,
    SessionExportWorker,
    build_export_paths,
    sanitize_prefix,
)
from app.session.session_manager import SessionManager
from app.ui.styles import get_icon
from app.utils.logger import logger


class ImageViewer(QGraphicsView):
    """Zoomable and pannable viewer which always preserves aspect ratio."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem()
        self._scene.addItem(self._item)
        self.setScene(self._scene)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._has_image = False

    def set_image(self, image: QImage) -> None:
        self._item.setPixmap(QPixmap.fromImage(image))
        self._scene.setSceneRect(QRectF(self._item.boundingRect()))
        self._has_image = not image.isNull()
        self.fit_image()

    def clear_image(self) -> None:
        self._item.setPixmap(QPixmap())
        self._scene.setSceneRect(QRectF())
        self._has_image = False

    def fit_image(self) -> None:
        if self._has_image and not self._item.pixmap().isNull():
            self.resetTransform()
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event) -> None:
        if self._has_image:
            factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
            self.scale(factor, factor)
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._has_image:
            self.fit_image()


class ThumbnailList(QListWidget):
    """Icon grid that reports its final order after a drag-and-drop move."""

    order_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setIconSize(QSize(124, 82))
        self.setMaximumHeight(142)
        self.setSpacing(8)

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        self.order_changed.emit()


class ExportOptionsDialog(QDialog):
    """Collects batch export settings before a worker is started."""

    def __init__(self, default_prefix: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Seri Ekran Görüntüsü Dışa Aktar")
        self.setModal(True)
        self.setMinimumWidth(430)
        self.setStyleSheet(
            "QDialog { background-color: #0F172A; color: #F8FAFC; font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; }"
            "QLabel { color: #E2E8F0; font-size: 13px; }"
            "QLineEdit { background: #1E293B; color: #F8FAFC; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; padding: 7px 12px; font-size: 13px; }"
            "QLineEdit:focus { border: 1px solid #6366F1; background: #0F172A; }"
            "QComboBox { background: #1E293B; color: #F8FAFC; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; padding: 7px 12px; font-size: 13px; }"
            "QComboBox:focus { border: 1px solid #6366F1; }"
            "QComboBox::drop-down { border: none; width: 24px; }"
            "QComboBox QAbstractItemView { background-color: #0F172A; color: #F8FAFC; selection-background-color: #4F46E5; selection-color: #FFFFFF; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 4px; }"
            "QSlider::groove:horizontal { height: 6px; background: #334155; border-radius: 3px; }"
            "QSlider::sub-page:horizontal { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3B82F6, stop:1 #6366F1); border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #F8FAFC; border: 2px solid #6366F1; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }"
            "QPushButton { background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; color: #E2E8F0; padding: 8px 18px; font-weight: 500; font-size: 13px; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 0.12); color: #FFFFFF; }"
            "QPushButton#save_btn { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #4F46E5); border: none; color: #FFFFFF; font-weight: 700; }"
            "QPushButton#save_btn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1D4ED8, stop:1 #4338CA); }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        self.prefix_edit = QLineEdit(sanitize_prefix(default_prefix))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPEG", "WEBP"])
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(95)
        self.quality_label = QLabel("95%")
        self.quality_label.setStyleSheet("color: #818CF8; font-weight: 700; min-width: 38px;")
        quality_row = QHBoxLayout()
        quality_row.addWidget(self.quality_slider, 1)
        quality_row.addWidget(self.quality_label)

        form.addRow("Dosya Öneki:", self.prefix_edit)
        form.addRow("Format:", self.format_combo)
        form.addRow("Kalite (JPEG/WebP):", quality_row)
        layout.addLayout(form)

        self.note = QLabel("ℹ️ PNG kayıpsızdır; kalite ayarı PNG için uygulanmaz.")
        self.note.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(self.note)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("İptal")
        save = QPushButton("Dışa Aktar")
        save.setObjectName("save_btn")
        save.setDefault(True)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self.quality_slider.valueChanged.connect(lambda value: self.quality_label.setText(f"{value}%"))
        self.format_combo.currentTextChanged.connect(self._update_quality_state)
        self._update_quality_state(self.format_combo.currentText())

    def _update_quality_state(self, format_name: str) -> None:
        enabled = format_name != "PNG"
        self.quality_slider.setEnabled(enabled)
        self.quality_label.setEnabled(enabled)

    @property
    def extension(self) -> str:
        return {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[self.format_combo.currentText()]


class ScreenshotSessionWindow(QDialog):
    """Gallery, navigation, selection and batch-export UI for one session."""

    open_editor_requested = Signal(QImage)

    def __init__(self, session: ScreenshotSession, manager: SessionManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.session = session
        self.manager = manager
        self._loading_thumbnails = False
        self._export_worker: Optional[SessionExportWorker] = None
        self._progress_dialog = None
        self.setWindowTitle("Seri Ekran Görüntüsü")
        self.setWindowIcon(get_icon("camera", "#6366F1", 24))
        self.setMinimumSize(780, 620)
        self.resize(960, 730)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setStyleSheet(
            "QDialog { background-color: #0B0F19; color: #F8FAFC; font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; }"
            "QPushButton { background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; color: #E2E8F0; font-size: 12px; font-weight: 500; padding: 7px 14px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.12); border-color: rgba(255, 255, 255, 0.2); color: #FFFFFF; }"
            "QPushButton:pressed { background-color: rgba(255, 255, 255, 0.08); }"
            "QPushButton:disabled { background-color: rgba(255, 255, 255, 0.02); border-color: rgba(255, 255, 255, 0.04); color: #475569; }"
            "QPushButton#primary_save_btn { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563EB, stop:1 #4F46E5); border: none; color: #FFFFFF; font-weight: 700; padding: 8px 18px; }"
            "QPushButton#primary_save_btn:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1D4ED8, stop:1 #4338CA); }"
            "QPushButton#delete_btn:hover { background-color: rgba(239, 68, 68, 0.15); border-color: rgba(248, 113, 113, 0.4); color: #F87171; }"
            "QPushButton#action_accent_btn:hover { background-color: rgba(99, 102, 241, 0.2); border-color: #6366F1; color: #A5B4FC; }"
        )
        self._build_ui()
        self.manager.session_changed.connect(self._on_session_changed)
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header card with dark glass styling
        header_card = QFrame(self)
        header_card.setStyleSheet(
            "QFrame { background-color: rgba(17, 24, 39, 0.85); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 4px; }"
        )
        header = QHBoxLayout(header_card)
        header.setContentsMargins(14, 10, 14, 10)
        header.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("camera", "#818CF8", 22).pixmap(22, 22))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        header.addWidget(icon_lbl)

        title = QLabel("Seri Ekran Görüntüsü")
        title.setStyleSheet("color: #F8FAFC; font-size: 16px; font-weight: 700; border: none; background: transparent;")
        header.addWidget(title)

        self.name_edit = QLineEdit(self.session.name)
        self.name_edit.setPlaceholderText("Oturum Adı")
        self.name_edit.setStyleSheet(
            "QLineEdit { background: #131B2E; color: #F8FAFC; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 8px; padding: 6px 12px; font-size: 13px; font-weight: 500; }"
            "QLineEdit:focus { border: 1px solid #6366F1; background: #0B0F19; }"
        )
        self.name_edit.editingFinished.connect(self._rename_session)
        header.addWidget(self.name_edit, 1)

        self.counter = QLabel("0 / 0")
        self.counter.setStyleSheet(
            "QLabel { background: rgba(99, 102, 241, 0.15); border: 1px solid #6366F1; border-radius: 12px; color: #A5B4FC; font-weight: 700; font-size: 13px; padding: 4px 14px; }"
        )
        header.addWidget(self.counter)
        layout.addWidget(header_card)

        self.empty_label = QLabel("Bu oturumda henüz ekran görüntüsü yok.\nEkran görüntüsü alarak (Ctrl+X) bu seri oturuma otomatik ekleyebilirsiniz.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            "QLabel { color: #94A3B8; background: rgba(15, 23, 42, 0.4); border: 2px dashed rgba(255, 255, 255, 0.12); border-radius: 12px; padding: 40px; font-size: 14px; line-height: 1.5; }"
        )
        layout.addWidget(self.empty_label, 1)

        self.viewer = ImageViewer(self)
        self.viewer.setStyleSheet("border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; background: #070B14;")
        layout.addWidget(self.viewer, 1)

        # Mid navigation toolbar
        nav = QHBoxLayout()
        nav.setSpacing(8)
        self.previous_button = QPushButton("‹ Önceki")
        self.next_button = QPushButton("Sonraki ›")
        self.fit_button = QPushButton("⛶ Ekrana Sığdır")
        self.duplicate_button = QPushButton("❐ Çoğalt")
        self.delete_button = QPushButton("🗑 Sil")
        self.delete_button.setObjectName("delete_btn")

        for button in (self.previous_button, self.next_button, self.fit_button, self.duplicate_button, self.delete_button):
            nav.addWidget(button)
        nav.addStretch()

        self.copy_button = QPushButton("📋 Kopyala")
        self.ocr_button = QPushButton("🔤 OCR Metin")
        self.ocr_button.setObjectName("action_accent_btn")
        self.edit_button = QPushButton("✏️ Düzenle")
        self.edit_button.setObjectName("action_accent_btn")

        nav.addWidget(self.copy_button)
        nav.addWidget(self.ocr_button)
        nav.addWidget(self.edit_button)
        layout.addLayout(nav)

        # Thumbnail strip
        self.thumbnails = ThumbnailList(self)
        self.thumbnails.setStyleSheet(
            "QListWidget { background-color: #0F172A; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 8px; }"
            "QListWidget::item { color: #CBD5E1; border: 1px solid transparent; border-radius: 8px; padding: 4px; margin: 2px; }"
            "QListWidget::item:hover { background-color: rgba(255, 255, 255, 0.06); border-color: rgba(255, 255, 255, 0.12); }"
            "QListWidget::item:selected { border: 2px solid #6366F1; background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(99, 102, 241, 0.28), stop:1 rgba(79, 70, 229, 0.15)); color: #FFFFFF; font-weight: 600; }"
        )
        layout.addWidget(self.thumbnails)

        # Bottom action bar
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.add_button = QPushButton("+ Görsel Ekle")
        self.select_all_button = QPushButton("Tümünü Seç")
        self.clear_selection_button = QPushButton("Seçimi Kaldır")
        self.save_selected_button = QPushButton("💾 Seçilenleri Kaydet")
        self.save_all_button = QPushButton("✓ Tümünü Kaydet")
        self.save_all_button.setObjectName("primary_save_btn")

        for button in (self.add_button, self.select_all_button, self.clear_selection_button):
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(self.save_selected_button)
        actions.addWidget(self.save_all_button)
        layout.addLayout(actions)

        self.previous_button.clicked.connect(lambda: self._navigate(-1))
        self.next_button.clicked.connect(lambda: self._navigate(1))
        self.fit_button.clicked.connect(self.viewer.fit_image)
        self.duplicate_button.clicked.connect(self._duplicate_current)
        self.delete_button.clicked.connect(self._delete_current)
        self.copy_button.clicked.connect(self._copy_current)
        self.ocr_button.clicked.connect(self._open_ocr)
        self.edit_button.clicked.connect(self._open_editor)
        self.add_button.clicked.connect(self._add_existing_images)
        self.select_all_button.clicked.connect(lambda: self._select_all(True))
        self.clear_selection_button.clicked.connect(lambda: self._select_all(False))
        self.save_selected_button.clicked.connect(lambda: self._export(selected_only=True))
        self.save_all_button.clicked.connect(lambda: self._export(selected_only=False))
        self.thumbnails.currentRowChanged.connect(self._set_current)
        self.thumbnails.itemChanged.connect(self._thumbnail_checked)
        self.thumbnails.order_changed.connect(self._apply_thumbnail_order)
        self.thumbnails.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self._add_context_actions()

    def _add_context_actions(self) -> None:
        actions = [
            ("Aç", lambda: self._set_current(self.thumbnails.currentRow())),
            ("Çoğalt", self._duplicate_current),
            ("Yeniden Adlandır", self._rename_current),
            ("Sola Taşı", lambda: self._move_current(-1)),
            ("Sağa Taşı", lambda: self._move_current(1)),
            ("Sil", self._delete_current),
        ]
        for text, handler in actions:
            action = QAction(text, self)
            action.triggered.connect(handler)
            self.thumbnails.addAction(action)

    def _refresh(self) -> None:
        self._loading_thumbnails = True
        self.name_edit.setText(self.session.name)
        self.thumbnails.clear()
        for index, item in enumerate(self.session.items, start=1):
            thumb = QPixmap.fromImage(item.image).scaled(
                124, 82, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            list_item = QListWidgetItem(QIcon(thumb), f"{index:02d}")
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            list_item.setCheckState(Qt.CheckState.Checked if item.selected else Qt.CheckState.Unchecked)
            list_item.setToolTip(item.title)
            self.thumbnails.addItem(list_item)
        self._loading_thumbnails = False
        has_items = bool(self.session.items)
        self.empty_label.setVisible(not has_items)
        self.viewer.setVisible(has_items)
        for widget in (self.previous_button, self.next_button, self.fit_button, self.duplicate_button, self.delete_button, self.copy_button, self.ocr_button, self.edit_button, self.select_all_button, self.clear_selection_button, self.save_selected_button, self.save_all_button):
            widget.setEnabled(has_items)
        if has_items:
            current = max(0, min(self.session.current_index, len(self.session.items) - 1))
            self.session.set_current(current)
            self.thumbnails.setCurrentRow(current)
            self._show_current()
        else:
            self.viewer.clear_image()
            self.counter.setText("0 / 0")

    def _on_session_changed(self, changed: ScreenshotSession) -> None:
        if changed is self.session:
            self._refresh()

    def _rename_session(self) -> None:
        self.session.rename(self.name_edit.text())
        self.manager.notify_changed(self.session)

    def _set_current(self, index: int) -> None:
        if self.session.set_current(index):
            self._show_current()

    def _show_current(self) -> None:
        item = self.session.current_item
        if item is None:
            return
        self.viewer.set_image(item.image)
        self.counter.setText(f"{self.session.current_index + 1} / {len(self.session.items)}")

    def _navigate(self, amount: int) -> None:
        if not self.session.items:
            return
        self._set_current((self.session.current_index + amount) % len(self.session.items))
        self.thumbnails.setCurrentRow(self.session.current_index)

    def _thumbnail_checked(self, list_item: QListWidgetItem) -> None:
        if self._loading_thumbnails:
            return
        index = self.thumbnails.row(list_item)
        self.session.set_selected(index, list_item.checkState() == Qt.CheckState.Checked)
        self.manager.notify_changed(self.session)

    def _apply_thumbnail_order(self) -> None:
        item_ids = [self.thumbnails.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.thumbnails.count())]
        if self.session.apply_order(item_ids):
            self.manager.notify_changed(self.session)

    def _move_current(self, offset: int) -> None:
        old_index = self.session.current_index
        new_index = old_index + offset
        if self.session.reorder(old_index, new_index):
            self.manager.notify_changed(self.session)

    def _duplicate_current(self) -> None:
        if self.session.duplicate(self.session.current_index):
            self.manager.notify_changed(self.session)

    def _delete_current(self) -> None:
        index = self.session.current_index
        if index < 0:
            return
        reply = QMessageBox.question(self, "Screenshot Sil", "Seçili ekran görüntüsü session'dan silinsin mi?")
        if reply == QMessageBox.StandardButton.Yes and self.session.remove(index):
            self.manager.notify_changed(self.session)

    def _rename_current(self) -> None:
        item = self.session.current_item
        if item is None:
            return
        value, ok = QInputDialog.getText(self, "Screenshot Adı", "Ad:", text=item.title)
        if ok and value.strip():
            item.title = value.strip()
            self.session.is_dirty = True
            self.manager.notify_changed(self.session)

    def _select_all(self, selected: bool) -> None:
        self.session.select_all(selected)
        self.manager.notify_changed(self.session)

    def _copy_current(self) -> None:
        item = self.session.current_item
        if item:
            QApplication.clipboard().setImage(item.image)

    def _open_ocr(self) -> None:
        item = self.session.current_item
        if item is None:
            return
        dialog = TextExtractionDialog(image=item.image, provider=AutoOCRProvider(), languages=["tr", "en"], parent=self)
        dialog.exec()

    def _open_editor(self) -> None:
        item = self.session.current_item
        if item:
            self.open_editor_requested.emit(item.image.copy())

    def _add_existing_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Session'a Görsel Ekle", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff)"
        )
        added = False
        for raw_path in paths:
            image = QImage(raw_path)
            if not image.isNull():
                self.session.add_image(image, Path(raw_path).stem)
                added = True
        if added:
            self.manager.notify_changed(self.session)

    def _export(self, selected_only: bool) -> None:
        indexed_items = [(index, item) for index, item in enumerate(self.session.items, start=1) if not selected_only or item.selected]
        if not indexed_items:
            QMessageBox.information(self, "Dışa Aktar", "Kaydedilecek ekran görüntüsü seçilmedi.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Dışa aktarma klasörünü seçin")
        if not directory:
            return
        options = ExportOptionsDialog(self.session.name, self)
        if options.exec() != QDialog.DialogCode.Accepted:
            return
        plan = build_export_paths(Path(directory), options.prefix_edit.text(), options.extension, indexed_items)
        policy = self._ask_collision_policy([path for _, path in plan if path.exists()])
        if policy is None:
            return
        self._start_export(plan, options.quality_slider.value(), policy)

    def _ask_collision_policy(self, existing: list[Path]) -> Optional[str]:
        if not existing:
            return "rename"
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Dosya zaten var")
        dialog.setText(f"{len(existing)} dosya zaten mevcut. Nasıl devam edilsin?")
        replace = dialog.addButton("Değiştir", QMessageBox.ButtonRole.DestructiveRole)
        skip = dialog.addButton("Atla", QMessageBox.ButtonRole.ActionRole)
        rename = dialog.addButton("Otomatik Yeniden Adlandır", QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton("İptal", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked == replace:
            return "replace"
        if clicked == skip:
            return "skip"
        if clicked == rename:
            return "rename"
        return None

    def _start_export(self, plan, quality: int, collision_policy: str) -> None:
        self._export_worker = SessionExportWorker(plan, quality=quality, collision_policy=collision_policy)
        self._progress_dialog = QProgressDialog("Ekran görüntüleri dışa aktarılıyor...", "İptal", 0, len(plan), self)
        self._progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress_dialog.setAutoClose(False)
        self._progress_dialog.canceled.connect(self._export_worker.cancel)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.completed.connect(self._on_export_complete)
        self._progress_dialog.show()
        self._export_worker.start()

    def _on_export_progress(self, current: int, total: int, filename: str) -> None:
        if self._progress_dialog:
            self._progress_dialog.setMaximum(total)
            self._progress_dialog.setValue(current)
            self._progress_dialog.setLabelText(f"Dışa aktarılıyor: {filename} ({current}/{total})")

    def _on_export_complete(self, result: ExportResult) -> None:
        if self._progress_dialog:
            self._progress_dialog.close()
        self._export_worker = None
        if result.error:
            QMessageBox.critical(self, "Dışa Aktarma Hatası", result.error)
            return
        if result.written:
            self.session.mark_exported()
            self.manager.notify_changed(self.session)
        suffix = " (iptal edildi)" if result.cancelled else ""
        QMessageBox.information(self, "Dışa Aktarma Tamamlandı", f"{len(result.written)} dosya kaydedildi, {len(result.skipped)} dosya atlandı.{suffix}")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_Left:
            self._navigate(-1)
        elif key == Qt.Key.Key_Right:
            self._navigate(1)
        elif key == Qt.Key.Key_Home:
            self._set_current(0)
        elif key == Qt.Key.Key_End:
            self._set_current(len(self.session.items) - 1)
        elif key == Qt.Key.Key_Delete:
            self._delete_current()
        elif modifiers & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_A:
            self._select_all(True)
        elif modifiers & Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_S:
            self._export(selected_only=True)
        elif modifiers & Qt.KeyboardModifier.ControlModifier and modifiers & Qt.KeyboardModifier.ShiftModifier and key == Qt.Key.Key_S:
            self._export(selected_only=False)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._export_worker and self._export_worker.isRunning():
            self._export_worker.cancel()
            event.ignore()
            return
        if self.session.is_dirty and self.session.items:
            reply = QMessageBox.question(
                self,
                "Session'ı Kapat",
                f"Kaydedilmemiş {len(self.session.items)} ekran görüntüsü var. Session kapatılsın mı?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Discard:
                event.ignore()
                return
        self.manager.close_session(self.session)
        super().closeEvent(event)

