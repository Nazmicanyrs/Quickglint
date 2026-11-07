"""Smart Privacy scanning dialog, background worker, and preview masking UI."""

from typing import List, Optional
from PySide6.QtCore import QRect, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.privacy.detection_result import DetectionResult, PrivacyAction, SensitiveType
from app.privacy.detector import SensitiveDataDetector
from app.privacy.ocr import OCRProvider, OCRResult
from app.privacy.providers import AutoOCRProvider
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.i18n import tr
from app.utils.logger import logger


class PrivacyScanWorker(QThread):
    """Background worker executing OCR and sensitive pattern detection."""

    scan_finished = Signal(list)  # List[DetectionResult]
    scan_error = Signal(str)

    def __init__(
        self,
        image: QImage,
        ocr_provider: Optional[OCRProvider] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.image = image.copy() if (image is not None and not image.isNull()) else QImage()
        self.ocr_provider = ocr_provider or AutoOCRProvider()
        self.detector = SensitiveDataDetector()
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        try:
            if self._is_cancelled or self.image.isNull():
                self.scan_finished.emit([])
                return

            # 1. Run OCR
            ocr_results = self.ocr_provider.detect_text(self.image)
            if self._is_cancelled:
                return

            # 2. Run pattern detection
            detections = self.detector.scan(ocr_results)
            if self._is_cancelled:
                return

            self.scan_finished.emit(detections)
        except Exception as exc:
            logger.error("PrivacyScanWorker failed: %s", exc)
            if not self._is_cancelled:
                self.scan_error.emit(str(exc))


class PrivacyResultDialog(QDialog):
    """Smart Privacy review dialog for selecting and masking detected sensitive areas."""

    apply_privacy = Signal(list)  # List[DetectionResult]

    def __init__(
        self,
        image: Optional[QImage] = None,
        ocr_provider: Optional[OCRProvider] = None,
        default_action: PrivacyAction = PrivacyAction.PIXELATE,
        parent: Optional[QWidget] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent)
        # Handle alternate parameter names like screenshot_image
        self.image = image or kwargs.get("screenshot_image")
        if self.image is None:
            self.image = QImage()
        self.ocr_provider = ocr_provider or AutoOCRProvider()
        self.default_action = default_action
        self.detections: List[DetectionResult] = []
        self._item_checkboxes: List[tuple[QCheckBox, DetectionResult]] = []
        self.worker: Optional[PrivacyScanWorker] = None

        self.setWindowTitle("Quickglint — Smart Privacy")
        self.setMinimumSize(540, 480)
        self.setStyleSheet(DARK_THEME_QSS)

        self._setup_ui()
        self._start_scan()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(18, 18, 18, 18)
        self.main_layout.setSpacing(14)

        # Header Title & Icon
        header_layout = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(get_icon("shield", "#63B3ED", 28).pixmap(28, 28))
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_lbl = QLabel("<b>Smart Privacy — Hassas Bilgi Koruma</b>", self)
        title_lbl.setStyleSheet("font-size: 16px; color: #63B3ED;")
        subtitle_lbl = QLabel(
            "Ekrandaki e-posta, telefon, API token, şifre ve kredi kartı gibi hassas verileri algılar ve gizler.",
            self,
        )
        subtitle_lbl.setStyleSheet("color: #A0AEC0; font-size: 11px;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(subtitle_lbl)
        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        self.main_layout.addLayout(header_layout)

        # Progress / Status Section
        self.status_frame = QFrame(self)
        self.status_frame.setStyleSheet(
            "background-color: #1A202C; border: 1px solid #334155; border-radius: 8px; padding: 12px;"
        )
        status_vbox = QVBoxLayout(self.status_frame)
        self.status_lbl = QLabel("Ekran taranıyor ve hassas veriler aranıyor...", self.status_frame)
        self.status_lbl.setStyleSheet("color: #E2E8F0; font-weight: bold;")
        self.progress_bar = QProgressBar(self.status_frame)
        self.progress_bar.setRange(0, 0)  # Indeterminate spinner
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(
            "QProgressBar { background-color: #2D3748; border-radius: 3px; } "
            "QProgressBar::chunk { background-color: #3182CE; border-radius: 3px; }"
        )
        status_vbox.addWidget(self.status_lbl)
        status_vbox.addWidget(self.progress_bar)
        self.main_layout.addWidget(self.status_frame)

        # Scroll area for detected items
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background: transparent;")
        self.items_layout = QVBoxLayout(self.scroll_widget)
        self.items_layout.setSpacing(8)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.hide()
        self.main_layout.addWidget(self.scroll_area)

        # Masking Effect Selector
        self.effect_group = QGroupBox("Gizleme Yöntemi (Masking Effect)", self)
        self.effect_group.hide()
        effect_layout = QHBoxLayout(self.effect_group)
        self.radio_pixelate = QRadioButton("Mozaik (Pixelate)", self.effect_group)
        self.radio_blur = QRadioButton("Bulanıklaştır (Blur)", self.effect_group)
        self.radio_blackout = QRadioButton("Siyah Kutu (Blackout)", self.effect_group)
        self.radio_pixelate.setChecked(True)
        effect_layout.addWidget(self.radio_pixelate)
        effect_layout.addWidget(self.radio_blur)
        effect_layout.addWidget(self.radio_blackout)
        self.main_layout.addWidget(self.effect_group)

        # Action Buttons
        self.btn_layout = QHBoxLayout()

        self.select_all_cb = QCheckBox("Tümünü Seç / Kaldır", self)
        self.select_all_cb.setChecked(True)
        self.select_all_cb.stateChanged.connect(self._on_toggle_all)
        self.select_all_cb.hide()
        self.btn_layout.addWidget(self.select_all_cb)

        self.btn_layout.addStretch()

        self.apply_btn = QPushButton("Gizle (Hide Selected)", self)
        self.apply_btn.setObjectName("primaryActionBtn")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._on_apply)
        self.btn_layout.addWidget(self.apply_btn)

        self.cancel_btn = QPushButton("İptal", self)
        self.cancel_btn.clicked.connect(self.reject)
        self.btn_layout.addWidget(self.cancel_btn)

        self.main_layout.addLayout(self.btn_layout)

    def _start_scan(self) -> None:
        self.worker = PrivacyScanWorker(self.image, self.ocr_provider, self)
        self.worker.scan_finished.connect(self._on_scan_finished)
        self.worker.scan_error.connect(self._on_scan_error)
        self.worker.start()

    def _on_scan_error(self, err: str) -> None:
        self.progress_bar.hide()
        self.status_lbl.setText(f"Tarama sırasında hata oluştu: {err}")
        self.status_lbl.setStyleSheet("color: #FEB2B2; font-weight: bold;")

    def _on_scan_finished(self, detections: List[DetectionResult]) -> None:
        self.detections = detections
        self.progress_bar.hide()

        if not detections:
            self.status_lbl.setText("✓ Taramada herhangi bir hassas veri tespit edilmedi.")
            self.status_lbl.setStyleSheet("color: #68D391; font-weight: bold;")
            return

        self.status_lbl.setText(f"✓ {len(detections)} adet potansiyel hassas veri tespit edildi:")
        self.status_lbl.setStyleSheet("color: #63B3ED; font-weight: bold;")

        self.scroll_area.show()
        self.effect_group.show()
        self.select_all_cb.show()
        self.apply_btn.setEnabled(True)

        for det in detections:
            item_frame = QFrame(self.scroll_widget)
            item_frame.setStyleSheet(
                "background-color: #1E293B; border: 1px solid #334155; border-radius: 6px; padding: 6px;"
            )
            item_h = QHBoxLayout(item_frame)
            item_h.setContentsMargins(8, 4, 8, 4)

            cb = QCheckBox(item_frame)
            cb.setChecked(True)
            self._item_checkboxes.append((cb, det))

            # Masked preview text (e.g. j***@domain.com or sk-***)
            masked_label = self._mask_text_preview(det.text, det.type)
            type_name = det.reason

            lbl = QLabel(f"<b>[{type_name}]</b> <span style='color:#E2E8F0;'>{masked_label}</span>", item_frame)
            lbl.setStyleSheet("font-size: 12px;")

            item_h.addWidget(cb)
            item_h.addWidget(lbl)
            item_h.addStretch()

            self.items_layout.addWidget(item_frame)

    def _mask_text_preview(self, text: str, s_type: SensitiveType) -> str:
        """Create a safe preview without exposing full credential in UI."""
        if len(text) <= 4:
            return "****"
        if s_type == SensitiveType.EMAIL:
            parts = text.split("@")
            if len(parts) == 2:
                name, domain = parts
                return f"{name[0]}***@{domain}"
        if s_type == SensitiveType.CREDIT_CARD:
            clean = text.replace(" ", "").replace("-", "")
            return f"****-****-****-{clean[-4:]}"
        return f"{text[:3]}...{text[-3:]}"

    def _on_toggle_all(self, state: int) -> None:
        is_checked = (state == Qt.CheckState.Checked.value or state == 2)
        for cb, _ in self._item_checkboxes:
            cb.setChecked(is_checked)

    def _cleanup_worker(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)

    def closeEvent(self, event) -> None:
        self._cleanup_worker()
        super().closeEvent(event)

    def reject(self) -> None:
        self._cleanup_worker()
        super().reject()

    def accept(self) -> None:
        self._cleanup_worker()
        super().accept()

    def _on_apply(self) -> None:
        selected_action = PrivacyAction.PIXELATE
        if self.radio_blur.isChecked():
            selected_action = PrivacyAction.BLUR
        elif self.radio_blackout.isChecked():
            selected_action = PrivacyAction.BLACKOUT

        active_detections: List[DetectionResult] = []
        for cb, det in self._item_checkboxes:
            if cb.isChecked():
                det.action = selected_action
                active_detections.append(det)

        self.apply_privacy.emit(active_detections)
        self.accept()


