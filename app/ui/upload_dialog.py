"""UI Dialogs for Upload Progress, Result Presentation, and Pre-upload Privacy Alerts."""

import os
from typing import List, Optional
import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.privacy.detection_result import DetectionResult
from app.ui.notifications import NotificationManager
from app.upload.models import UploadResult

UPLOAD_DIALOG_QSS = """
QDialog {
    background-color: #0F172A;
    color: #F8FAFC;
    font-family: 'Segoe UI', system-ui, sans-serif;
}

QFrame#card {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 10px;
}

QLineEdit {
    background-color: #0B1120;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    font-family: Consolas, monospace;
}

QLineEdit:focus {
    border-color: #38BDF8;
}

QPushButton#primaryActionBtn {
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 18px;
    border: none;
}

QPushButton#primaryActionBtn:hover {
    background-color: #1D4ED8;
}

QPushButton#successBtn {
    background-color: #059669;
    color: #FFFFFF;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 16px;
    border: none;
}

QPushButton#successBtn:hover {
    background-color: #047857;
}

QPushButton#secondaryBtn {
    background-color: #334155;
    color: #E2E8F0;
    font-weight: 500;
    border-radius: 6px;
    padding: 6px 14px;
    border: 1px solid #475569;
}

QPushButton#secondaryBtn:hover {
    background-color: #475569;
}

QPushButton#dangerBtn {
    background-color: #DC2626;
    color: #FFFFFF;
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 16px;
    border: none;
}

QPushButton#dangerBtn:hover {
    background-color: #B91C1C;
}
"""


class UploadResultDialog(QDialog):
    """Presents uploaded direct image URL and share links with copy buttons."""

    def __init__(self, result: UploadResult, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.result = result
        self.setWindowTitle("Görsel Yüklendi — Quickglint Paylaşım")
        self.resize(600, 360)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(UPLOAD_DIALOG_QSS)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Badge
        hdr = QHBoxLayout()
        icon_lbl = QLabel("☁️", self)
        icon_lbl.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon_lbl)

        title_lbl = QLabel("<b>Görsel Başarıyla Yüklendi!</b>", self)
        title_lbl.setStyleSheet("font-size: 16px; color: #10B981;")
        hdr.addWidget(title_lbl)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Provider Info Card
        card = QFrame(self)
        card.setObjectName("card")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(14, 14, 14, 14)
        c_layout.setSpacing(12)

        # 1. Direct Image URL
        c_layout.addWidget(QLabel("<b>🔗 Doğrudan Resim Bağlantısı (Direct Image URL):</b>", card))
        d_row = QHBoxLayout()
        self.direct_edit = QLineEdit(self.result.direct_url, card)
        self.direct_edit.setReadOnly(True)
        d_row.addWidget(self.direct_edit)

        copy_d_btn = QPushButton("Kopyala", card)
        copy_d_btn.setObjectName("primaryActionBtn")
        copy_d_btn.clicked.connect(self._copy_direct_url)
        d_row.addWidget(copy_d_btn)
        c_layout.addLayout(d_row)

        # 2. Share / Viewer URL
        c_layout.addWidget(QLabel("<b>🌐 Paylaşım Sayfası (Share Page URL):</b>", card))
        s_row = QHBoxLayout()
        self.share_edit = QLineEdit(self.result.share_url, card)
        self.share_edit.setReadOnly(True)
        s_row.addWidget(self.share_edit)

        copy_s_btn = QPushButton("Kopyala", card)
        copy_s_btn.setObjectName("secondaryBtn")
        copy_s_btn.clicked.connect(self._copy_share_url)
        s_row.addWidget(copy_s_btn)
        c_layout.addLayout(s_row)

        layout.addWidget(card)

        # Bottom Buttons
        btn_bar = QHBoxLayout()
        open_browser_btn = QPushButton("🌐 Tarayıcıda Aç", self)
        open_browser_btn.setObjectName("secondaryBtn")
        open_browser_btn.clicked.connect(self._open_browser)
        btn_bar.addWidget(open_browser_btn)

        btn_bar.addStretch()

        close_btn = QPushButton("Kapat", self)
        close_btn.setObjectName("primaryActionBtn")
        close_btn.clicked.connect(self.accept)
        btn_bar.addWidget(close_btn)

        layout.addLayout(btn_bar)

    def _copy_direct_url(self) -> None:
        QApplication.clipboard().setText(self.result.direct_url)
        NotificationManager.show_toast("Panoya Kopyalandı", "Doğrudan görsel bağlantısı panoya kopyalandı.")

    def _copy_share_url(self) -> None:
        QApplication.clipboard().setText(self.result.share_url)
        NotificationManager.show_toast("Panoya Kopyalandı", "Paylaşım sayfası bağlantısı panoya kopyalandı.")

    def _open_browser(self) -> None:
        url = self.result.share_url or self.result.direct_url
        if url:
            webbrowser.open(url)


class SmartPrivacyUploadWarningDialog(QDialog):
    """Alerts user when sensitive information is detected before uploading to external cloud."""

    ACTION_REVIEW = 1
    ACTION_AUTO_REDACT = 2
    ACTION_UPLOAD_ANYWAY = 3
    ACTION_CANCEL = 0

    def __init__(self, detections: List[DetectionResult], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.detections = detections
        self.selected_action = self.ACTION_CANCEL
        self.setWindowTitle("⚠️ Hassas Bilgi Uyarısı — Quickglint")
        self.resize(520, 360)
        self.setStyleSheet(UPLOAD_DIALOG_QSS)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon_lbl = QLabel("🛡️", self)
        icon_lbl.setStyleSheet("font-size: 32px;")
        hdr.addWidget(icon_lbl)

        hdr_v = QVBoxLayout()
        title_lbl = QLabel("<b>Hassas Bilgiler Tespit Edildi!</b>", self)
        title_lbl.setStyleSheet("font-size: 16px; color: #F59E0B;")
        hdr_v.addWidget(title_lbl)

        sub_lbl = QLabel("Bu görseli üçüncü taraf servise (ImgBB) yüklemek üzeresiniz.", self)
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        hdr_v.addWidget(sub_lbl)
        hdr.addLayout(hdr_v)
        layout.addLayout(hdr)

        # Card listing detected types
        card = QFrame(self)
        card.setObjectName("card")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(14, 14, 14, 14)
        c_layout.setSpacing(8)

        # Group counts
        counts = {}
        for d in self.detections:
            cat_name = d.category.name if hasattr(d.category, "name") else str(d.category)
            counts[cat_name] = counts.get(cat_name, 0) + 1

        c_layout.addWidget(QLabel("<b>Tespit Edilen Veriler:</b>", card))
        for cat, cnt in counts.items():
            row = QLabel(f"• <b>{cat}:</b> {cnt} adet tespit edildi", card)
            row.setStyleSheet("color: #E2E8F0; font-size: 13px;")
            c_layout.addWidget(row)

        layout.addWidget(card)

        # Action Buttons
        layout.addWidget(QLabel("Ne yapmak istersiniz?", self))
        btn_box = QVBoxLayout()
        btn_box.setSpacing(8)

        btn_review = QPushButton("🔍 Gizlilik Editöründe İncele", self)
        btn_review.setObjectName("primaryActionBtn")
        btn_review.clicked.connect(self._on_review)
        btn_box.addWidget(btn_review)

        btn_auto_blur = QPushButton("🪄 Otomatik Sansürle (Blur) ve Yükle", self)
        btn_auto_blur.setObjectName("successBtn")
        btn_auto_blur.clicked.connect(self._on_auto_blur)
        btn_box.addWidget(btn_auto_blur)

        btn_anyway = QPushButton("⚠️ Yine de Yükle (Olduğu Gibi Paylaş)", self)
        btn_anyway.setObjectName("dangerBtn")
        btn_anyway.clicked.connect(self._on_upload_anyway)
        btn_box.addWidget(btn_anyway)

        btn_cancel = QPushButton("İptal", self)
        btn_cancel.setObjectName("secondaryBtn")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        layout.addLayout(btn_box)

    def _on_review(self) -> None:
        self.selected_action = self.ACTION_REVIEW
        self.accept()

    def _on_auto_blur(self) -> None:
        self.selected_action = self.ACTION_AUTO_REDACT
        self.accept()

    def _on_upload_anyway(self) -> None:
        self.selected_action = self.ACTION_UPLOAD_ANYWAY
        self.accept()


class ApiKeyPromptDialog(QDialog):
    """Prompts user to enter their ImgBB API key with instant save and get-key link."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.entered_key: str = ""
        self.setWindowTitle("ImgBB API Anahtarı — Quickglint")
        self.resize(520, 240)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(UPLOAD_DIALOG_QSS)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        hdr = QHBoxLayout()
        icon_lbl = QLabel("☁️", self)
        icon_lbl.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon_lbl)

        hdr_v = QVBoxLayout()
        title_lbl = QLabel("<b>ImgBB API Anahtarı Gerekli</b>", self)
        title_lbl.setStyleSheet("font-size: 15px; color: #38BDF8;")
        hdr_v.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Görsellerinizi doğrudan ImgBB'ye yükleyip bağlantı alabilmek için ücretsiz API anahtarınızı girin.",
            self,
        )
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        sub_lbl.setWordWrap(True)
        hdr_v.addWidget(sub_lbl)
        hdr.addLayout(hdr_v)
        layout.addLayout(hdr)

        self.key_edit = QLineEdit(self)
        self.key_edit.setPlaceholderText("ImgBB API Anahtarınızı buraya yapıştırın...")
        layout.addWidget(self.key_edit)

        btn_bar = QHBoxLayout()
        get_key_btn = QPushButton("🔑 Anahtar Al (api.imgbb.com)", self)
        get_key_btn.setObjectName("secondaryBtn")
        get_key_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        get_key_btn.clicked.connect(lambda: webbrowser.open("https://api.imgbb.com/"))
        btn_bar.addWidget(get_key_btn)

        btn_bar.addStretch()

        cancel_btn = QPushButton("İptal", self)
        cancel_btn.setObjectName("secondaryBtn")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_bar.addWidget(cancel_btn)

        save_btn = QPushButton("Kaydet ve Yükle", self)
        save_btn.setObjectName("primaryActionBtn")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        btn_bar.addWidget(save_btn)

        layout.addLayout(btn_bar)

    def _on_save(self) -> None:
        key = self.key_edit.text().strip()
        if not key:
            self.key_edit.setFocus()
            return
        from app.security.credential_store import CredentialStore
        CredentialStore.set_credential("imgbb", "user", key)
        self.entered_key = key
        self.accept()


