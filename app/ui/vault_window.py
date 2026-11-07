"""Premium PySide6 Secure Vault user interface with upscale glassmorphism aesthetics, large legible typography, and seamless responsive layout."""

import os
from pathlib import Path
import time
from typing import Optional
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.security.encryption import AuthenticationError
from app.security.vault import SecureVault
from app.ui.notifications import NotificationManager
from app.ui.styles import DARK_THEME_QSS, get_icon
from app.utils.logger import logger
from config.config_manager import ConfigManager

VAULT_STYLESHEET = """
QDialog, QWidget#vaultRoot {
    background-color: #0F172A;
    color: #F8FAFC;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

QFrame#centerCard {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 16px;
}

QFrame#topNavBadge {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 6px 12px;
}

QLabel#headingTitle {
    font-size: 24px;
    font-weight: 700;
    color: #F8FAFC;
}

QLabel#subtitleText {
    font-size: 14px;
    line-height: 1.5;
    color: #94A3B8;
}

QLineEdit#vaultInput {
    background-color: #0F172A;
    border: 1.5px solid #334155;
    border-radius: 10px;
    color: #F8FAFC;
    font-size: 15px;
    padding: 10px 16px;
    selection-background-color: #3B82F6;
}

QLineEdit#vaultInput:focus {
    border: 1.5px solid #3B82F6;
    background-color: #131E33;
}

QPushButton#primaryVaultBtn {
    background-color: #2563EB;
    color: #FFFFFF;
    font-size: 15px;
    font-weight: 600;
    border-radius: 10px;
    padding: 10px 24px;
    border: none;
}

QPushButton#primaryVaultBtn:hover {
    background-color: #1D4ED8;
}

QPushButton#primaryVaultBtn:pressed {
    background-color: #1E40AF;
}

QPushButton#secondaryVaultBtn {
    background-color: #334155;
    color: #E2E8F0;
    font-size: 13px;
    font-weight: 600;
    border-radius: 8px;
    padding: 8px 16px;
    border: 1px solid #475569;
}

QPushButton#secondaryVaultBtn:hover {
    background-color: #475569;
    color: #FFFFFF;
}

QPushButton#dangerVaultBtn {
    background-color: #DC2626;
    color: #FFFFFF;
    font-size: 13px;
    font-weight: 600;
    border-radius: 8px;
    padding: 8px 16px;
    border: none;
}

QPushButton#dangerVaultBtn:hover {
    background-color: #B91C1C;
}

QScrollArea {
    background-color: #0F172A;
    border: 1px solid #1E293B;
    border-radius: 12px;
}

QComboBox#vaultCombo {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
    color: #F8FAFC;
    font-size: 13px;
    padding: 6px 12px;
}
"""


def calculate_password_strength(password: str) -> tuple[int, str, str]:
    """Returns (score 0-100, label, hex_color)"""
    if not password:
        return 0, "Boş", "#64748B"
    score = 0
    if len(password) >= 8:
        score += 25
    if len(password) >= 14:
        score += 25
    if any(c.isupper() for c in password) and any(c.islower() for c in password):
        score += 20
    if any(c.isdigit() for c in password):
        score += 15
    if any(not c.isalnum() for c in password):
        score += 15

    score = min(100, score)
    if score < 30:
        return score, "Çok Zayıf (Weak)", "#EF4444"
    elif score < 50:
        return score, "Zayıf (Fair)", "#F97316"
    elif score < 70:
        return score, "İyi (Good)", "#FBBF24"
    elif score < 90:
        return score, "Güçlü (Strong)", "#22C55E"
    else:
        return score, "Çok Güçlü (Very Strong)", "#10B981"


class CreateVaultDialog(QDialog):
    """Upscale dialog for creating a brand new Secure Vault."""

    def __init__(self, default_dir: Optional[Path | str] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yeni Güvenli Kasa Oluştur")
        self.setMinimumWidth(520)
        self.setStyleSheet(VAULT_STYLESHEET)

        appdata = os.environ.get("APPDATA", str(Path.home() / ".quickglint"))
        primary_dir = Path(appdata) / "Quickglint" / "SecureVault"
        legacy_dir = Path(appdata) / "Quickglint" / "SecureVault"
        default_base = legacy_dir if not primary_dir.exists() and legacy_dir.exists() else primary_dir
        self.selected_dir = Path(default_dir) if default_dir else default_base

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # Title
        title_lbl = QLabel("🔐 Yeni Güvenli Kasa Oluştur", self)
        title_lbl.setObjectName("headingTitle")
        layout.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Tüm fotoğraflarınız <b>AES-256-GCM</b> ve <b>Argon2id</b> ile yerel olarak şifrelenir.<br>"
            "<span style='color: #F87171;'>⚠️ Ana Parolanız kurtarılamaz. Lütfen güçlü bir parola belirleyin.</span>",
            self,
        )
        sub_lbl.setObjectName("subtitleText")
        sub_lbl.setWordWrap(True)
        layout.addWidget(sub_lbl)

        # Location Picker
        loc_label = QLabel("Kasa Klasör Konumu:", self)
        loc_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #CBD5E1;")
        layout.addWidget(loc_label)

        loc_box = QHBoxLayout()
        self.loc_edit = QLineEdit(str(self.selected_dir), self)
        self.loc_edit.setObjectName("vaultInput")
        self.loc_edit.setReadOnly(True)
        loc_box.addWidget(self.loc_edit)

        browse_btn = QPushButton("📁 Klasör Seç", self)
        browse_btn.setObjectName("secondaryVaultBtn")
        browse_btn.setFixedHeight(42)
        browse_btn.clicked.connect(self._on_browse_location)
        loc_box.addWidget(browse_btn)
        layout.addLayout(loc_box)

        # Password
        pass_label = QLabel("Ana Parola (Master Password):", self)
        pass_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #CBD5E1;")
        layout.addWidget(pass_label)

        self.pass1_edit = QLineEdit(self)
        self.pass1_edit.setObjectName("vaultInput")
        self.pass1_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass1_edit.setPlaceholderText("En az 6 karakterlik güçlü bir parola...")
        self.pass1_edit.textChanged.connect(self._on_password_changed)
        layout.addWidget(self.pass1_edit)

        # Strength Bar
        self.strength_bar = QProgressBar(self)
        self.strength_bar.setFixedHeight(6)
        self.strength_bar.setTextVisible(False)
        self.strength_bar.setValue(0)
        layout.addWidget(self.strength_bar)

        self.strength_lbl = QLabel("Parola Gücü: Boş", self)
        self.strength_lbl.setStyleSheet("color: #64748B; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.strength_lbl)

        # Confirm Password
        conf_label = QLabel("Parolayı Onayla:", self)
        conf_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #CBD5E1;")
        layout.addWidget(conf_label)

        self.pass2_edit = QLineEdit(self)
        self.pass2_edit.setObjectName("vaultInput")
        self.pass2_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass2_edit.setPlaceholderText("Parolayı tekrar girin...")
        layout.addWidget(self.pass2_edit)

        layout.addSpacing(10)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        cancel_btn = QPushButton("İptal", self)
        cancel_btn.setObjectName("secondaryVaultBtn")
        cancel_btn.setFixedHeight(42)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        self.create_btn = QPushButton("Kasayı Oluştur 🚀", self)
        self.create_btn.setObjectName("primaryVaultBtn")
        self.create_btn.setFixedHeight(42)
        self.create_btn.clicked.connect(self._on_create_clicked)
        btn_box.addWidget(self.create_btn)

        layout.addLayout(btn_box)
        self.master_password = ""

    def _on_browse_location(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Kasa Klasörünü Seçin", str(self.selected_dir.parent))
        if folder:
            self.selected_dir = Path(folder)
            if not self.selected_dir.name.lower().endswith("vault") and not self.selected_dir.name.lower().endswith("kasa"):
                self.selected_dir = self.selected_dir / "SecureVault"
            self.loc_edit.setText(str(self.selected_dir))

    def _on_password_changed(self, text: str) -> None:
        score, label, color = calculate_password_strength(text)
        self.strength_bar.setValue(score)
        self.strength_bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {color}; border-radius: 3px; }}")
        self.strength_lbl.setText(f"Parola Gücü: {label}")
        self.strength_lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")

    def _on_create_clicked(self) -> None:
        p1 = self.pass1_edit.text()
        p2 = self.pass2_edit.text()
        if len(p1) < 6:
            QMessageBox.warning(self, "Uyarı", "Ana parola en az 6 karakter olmalıdır.")
            return
        if p1 != p2:
            QMessageBox.warning(self, "Uyarı", "Girdiğiniz parolalar birbiriyle eşleşmiyor.")
            return
        self.master_password = p1
        self.accept()


class ChangePasswordDialog(QDialog):
    """Dialog to change master password in O(1) time."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ana Parolayı Değiştir")
        self.setMinimumWidth(480)
        self.setStyleSheet(VAULT_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("🔑 Ana Parolayı Değiştir", self)
        title.setObjectName("headingTitle")
        layout.addWidget(title)

        desc = QLabel(
            "İki kademeli anahtar mimarisi sayesinde fotoğraflarınız bozulmadan parolanız anında güncellenir.",
            self,
        )
        desc.setObjectName("subtitleText")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.old_pass_edit = QLineEdit(self)
        self.old_pass_edit.setObjectName("vaultInput")
        self.old_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_pass_edit.setPlaceholderText("Mevcut Ana Parola")
        layout.addWidget(self.old_pass_edit)

        self.new_pass_edit = QLineEdit(self)
        self.new_pass_edit.setObjectName("vaultInput")
        self.new_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pass_edit.setPlaceholderText("Yeni Ana Parola")
        layout.addWidget(self.new_pass_edit)

        self.confirm_pass_edit = QLineEdit(self)
        self.confirm_pass_edit.setObjectName("vaultInput")
        self.confirm_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_pass_edit.setPlaceholderText("Yeni Parolayı Tekrar Girin")
        layout.addWidget(self.confirm_pass_edit)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        cancel_btn = QPushButton("İptal", self)
        cancel_btn.setObjectName("secondaryVaultBtn")
        cancel_btn.setFixedHeight(40)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("Parolayı Güncelle", self)
        save_btn.setObjectName("primaryVaultBtn")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._on_save_clicked)
        btn_box.addWidget(save_btn)

        layout.addLayout(btn_box)
        self.old_password = ""
        self.new_password = ""

    def _on_save_clicked(self) -> None:
        old_p = self.old_pass_edit.text()
        new_p = self.new_pass_edit.text()
        conf_p = self.confirm_pass_edit.text()

        if not old_p:
            QMessageBox.warning(self, "Uyarı", "Lütfen mevcut parolanızı girin.")
            return
        if len(new_p) < 6:
            QMessageBox.warning(self, "Uyarı", "Yeni parola en az 6 karakter olmalıdır.")
            return
        if new_p != conf_p:
            QMessageBox.warning(self, "Uyarı", "Yeni parolalar eşleşmiyor.")
            return

        self.old_password = old_p
        self.new_password = new_p
        self.accept()


class ImagePreviewDialog(QDialog):
    """High-resolution preview dialog for a single encrypted image."""

    open_in_editor_requested = Signal(QImage)

    def __init__(self, image: QImage, title: str, object_id: str, vault: SecureVault, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.image = image
        self.title_str = title
        self.object_id = object_id
        self.vault = vault

        self.setWindowTitle(f"Şifreli Görsel: {title}")
        self.resize(960, 680)
        self.setStyleSheet(VAULT_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Image view
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)

        self.img_lbl = QLabel(scroll)
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setPixmap(QPixmap.fromImage(image))
        scroll.setWidget(self.img_lbl)
        layout.addWidget(scroll)

        # Action bar
        bar = QHBoxLayout()

        info_lbl = QLabel(f"📐 {image.width()} × {image.height()} px  |  {title}", self)
        info_lbl.setStyleSheet("color: #94A3B8; font-size: 13px; font-weight: 500;")
        bar.addWidget(info_lbl)

        bar.addStretch()

        ocr_btn = QPushButton("Metin Çıkar", self)
        ocr_btn.setIcon(get_icon("ocr", "#38BDF8", 16))
        ocr_btn.setIconSize(QSize(15, 15))
        ocr_btn.setObjectName("secondaryVaultBtn")
        ocr_btn.clicked.connect(self._on_extract_text)
        bar.addWidget(ocr_btn)

        clean_btn = QPushButton("Metadata Temizle", self)
        clean_btn.setIcon(get_icon("privacy", "#38BDF8", 16))
        clean_btn.setIconSize(QSize(15, 15))
        clean_btn.setObjectName("secondaryVaultBtn")
        clean_btn.clicked.connect(self._on_clean_metadata)
        bar.addWidget(clean_btn)

        copy_btn = QPushButton("Kopyala", self)
        copy_btn.setIcon(get_icon("copy", "#F1F5F9", 16))
        copy_btn.setIconSize(QSize(15, 15))
        copy_btn.setObjectName("secondaryVaultBtn")
        copy_btn.clicked.connect(self._on_copy)
        bar.addWidget(copy_btn)

        export_btn = QPushButton("Dışa Aktar (PNG)", self)
        export_btn.setIcon(get_icon("save", "#F1F5F9", 16))
        export_btn.setIconSize(QSize(15, 15))
        export_btn.setObjectName("secondaryVaultBtn")
        export_btn.clicked.connect(self._on_export)
        bar.addWidget(export_btn)

        editor_btn = QPushButton("Editörde Aç", self)
        editor_btn.setIcon(get_icon("pen", "#FFFFFF", 16))
        editor_btn.setIconSize(QSize(15, 15))
        editor_btn.setObjectName("primaryVaultBtn")
        editor_btn.clicked.connect(self._on_open_editor)
        bar.addWidget(editor_btn)

        delete_btn = QPushButton("Kasadan Sil", self)
        delete_btn.setIcon(get_icon("close", "#FDA4AF", 16))
        delete_btn.setIconSize(QSize(15, 15))
        delete_btn.setObjectName("dangerVaultBtn")
        delete_btn.clicked.connect(self._on_delete)
        bar.addWidget(delete_btn)

        layout.addLayout(bar)

    def _on_clean_metadata(self) -> None:
        from app.metacleaner.vault_cleaner import VaultMetadataCleaner
        from app.metacleaner.models import CleanConfig, CleaningPreset

        reply = QMessageBox.question(
            self,
            "Kasada Metadata Temizliği",
            "Bu görselin tüm hassas EXIF/GPS/XMP/IPTC metadata alanları RAM üzerinde temizlenip yeniden şifrelenecek.\n\n"
            "Orijinal kasa kaydı güncellensin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            new_oid, res = VaultMetadataCleaner.clean_vault_object(
                self.vault, self.object_id, config=CleanConfig(preset=CleaningPreset.PRIVACY_CLEAN), replace_in_vault=True
            )
            if res.success and new_oid:
                self.object_id = new_oid
                self.image = self.vault.get_image(new_oid)
                NotificationManager.show_toast("Metadata Temizlendi 🛡️", f"{res.removed_fields_count} alan RAM üzerinde temizlendi.")
                self.accept()
            else:
                QMessageBox.critical(self, "Hata", f"Metadata temizleme başarısız: {res.error_msg}")

    def _on_extract_text(self) -> None:
        from app.ocr.dialog import TextExtractionDialog
        from app.ocr.provider import AutoOCRProvider

        dlg = TextExtractionDialog(
            image=self.image,
            provider=AutoOCRProvider(),
            parent=self,
        )
        dlg.exec()

    def _on_copy(self) -> None:
        QApplication.clipboard().setImage(self.image)
        NotificationManager.show_toast("Panoya Kopyalandı", "Görsel panoya kopyalandı.")

    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Görseli Kaydet", f"{self.title_str}.png", "PNG Görseli (*.png)")
        if path:
            self.image.save(path, "PNG")
            NotificationManager.show_toast("Dışa Aktarıldı", f"Görsel kaydedildi:\n{path}")

    def _on_open_editor(self) -> None:
        self.open_in_editor_requested.emit(self.image)
        self.accept()

    def _on_delete(self) -> None:
        reply = QMessageBox.question(
            self,
            "Görseli Sil",
            "Bu şifreli görsel kasadan kalıcı olarak silinecek. Onaylıyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.vault.delete_image(self.object_id)
            self.accept()


class SecureVaultWindow(QDialog):
    """Main Secure Vault management window with upscale card UI, large fonts, and auto-lock."""

    open_in_editor = Signal(QImage)

    def __init__(self, config_manager: Optional[ConfigManager] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("vaultRoot")
        self.config_manager = config_manager or ConfigManager()

        # Resolve initial vault directory from settings
        custom_loc = self.config_manager.get("general", "vault_location", "")
        self.vault = SecureVault(custom_loc if custom_loc else None)

        self.setWindowTitle("Quickglint — Güvenli Kasa (Secure Vault)")
        self.resize(1040, 720)
        self.setMinimumSize(880, 600)
        self.setStyleSheet(VAULT_STYLESHEET)

        # Auto-lock timer
        self.auto_lock_timer = QTimer(self)
        self.auto_lock_timer.timeout.connect(self._on_auto_lock_timeout)
        self._auto_lock_minutes = 5

        self._init_ui()
        self._refresh_state()

    def _init_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 20, 24, 20)
        self.main_layout.setSpacing(16)

        # 1. TOP HEADER & LOCATION NAV BAR
        top_nav = QHBoxLayout()

        self.loc_badge = QFrame(self)
        self.loc_badge.setObjectName("topNavBadge")
        loc_badge_layout = QHBoxLayout(self.loc_badge)
        loc_badge_layout.setContentsMargins(10, 6, 10, 6)
        loc_badge_layout.setSpacing(8)

        self.loc_info_lbl = QLabel(f"📁 <b>Kasa Konumu:</b> {self.vault.storage.root}", self.loc_badge)
        self.loc_info_lbl.setStyleSheet("color: #E2E8F0; font-size: 13px; font-weight: 500;")
        loc_badge_layout.addWidget(self.loc_info_lbl)
        top_nav.addWidget(self.loc_badge)

        top_nav.addStretch()

        switch_loc_btn = QPushButton("📂 Kasa Klasörünü Değiştir", self)
        switch_loc_btn.setObjectName("secondaryVaultBtn")
        switch_loc_btn.clicked.connect(self._on_switch_location_clicked)
        top_nav.addWidget(switch_loc_btn)

        self.main_layout.addLayout(top_nav)

        # 2. LOCKED VIEW CONTAINER (Card Layout)
        self.locked_widget = QWidget(self)
        locked_layout = QVBoxLayout(self.locked_widget)
        locked_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        locked_layout.setContentsMargins(0, 0, 0, 0)

        # Center Card
        self.card = QFrame(self.locked_widget)
        self.card.setObjectName("centerCard")
        self.card.setFixedWidth(540)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(40, 36, 40, 36)
        card_layout.setSpacing(18)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Lock Icon
        lock_icon_lbl = QLabel("🔐", self.card)
        lock_icon_lbl.setStyleSheet("font-size: 64px;")
        lock_icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(lock_icon_lbl)

        # Titles
        title_lbl = QLabel("Güvenli Kasa (Secure Vault)", self.card)
        title_lbl.setObjectName("headingTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Hassas ekran görüntüleri ve fotoğraflarınız <b>AES-256-GCM</b> ile diskte şifreli tutulur.<br>"
            "Görsellere erişmek için lütfen Ana Parolanızı girin.",
            self.card,
        )
        desc_lbl.setObjectName("subtitleText")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(desc_lbl)

        card_layout.addSpacing(6)

        # Password Input
        self.unlock_pass_edit = QLineEdit(self.card)
        self.unlock_pass_edit.setObjectName("vaultInput")
        self.unlock_pass_edit.setFixedHeight(48)
        self.unlock_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.unlock_pass_edit.setPlaceholderText("Ana Parolanızı Girin...")
        self.unlock_pass_edit.returnPressed.connect(self._on_unlock_clicked)
        card_layout.addWidget(self.unlock_pass_edit)

        # Unlock Button
        self.unlock_btn = QPushButton("Kilidi Aç 🔓", self.card)
        self.unlock_btn.setObjectName("primaryVaultBtn")
        self.unlock_btn.setFixedHeight(46)
        self.unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlock_btn.clicked.connect(self._on_unlock_clicked)
        card_layout.addWidget(self.unlock_btn)

        card_layout.addSpacing(10)

        # Secondary Actions Box
        sec_box = QHBoxLayout()
        sec_box.setSpacing(12)

        self.create_vault_btn = QPushButton("➕ Yeni Kasa Oluştur", self.card)
        self.create_vault_btn.setObjectName("secondaryVaultBtn")
        self.create_vault_btn.setFixedHeight(38)
        self.create_vault_btn.clicked.connect(self._on_create_vault_clicked)
        sec_box.addWidget(self.create_vault_btn)

        self.import_vault_btn = QPushButton("📥 Yedek İçe Aktar (.osvault)", self.card)
        self.import_vault_btn.setObjectName("secondaryVaultBtn")
        self.import_vault_btn.setFixedHeight(38)
        self.import_vault_btn.clicked.connect(self._on_import_osvault_clicked)
        sec_box.addWidget(self.import_vault_btn)

        card_layout.addLayout(sec_box)
        locked_layout.addWidget(self.card)
        self.main_layout.addWidget(self.locked_widget)

        # 3. UNLOCKED VIEW CONTAINER (Gallery Dashboard)
        self.unlocked_widget = QWidget(self)
        unlocked_layout = QVBoxLayout(self.unlocked_widget)
        unlocked_layout.setContentsMargins(0, 0, 0, 0)
        unlocked_layout.setSpacing(14)

        # Top Bar
        dashboard_bar = QHBoxLayout()

        status_lbl = QLabel("🔓 <b>Güvenli Kasa — Açık</b>", self.unlocked_widget)
        status_lbl.setStyleSheet("font-size: 18px; color: #22C55E; font-weight: 700;")
        dashboard_bar.addWidget(status_lbl)

        self.stats_lbl = QLabel("0 Görsel (0 KB)", self.unlocked_widget)
        self.stats_lbl.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: 500;")
        dashboard_bar.addWidget(self.stats_lbl)

        dashboard_bar.addStretch()

        # Auto-lock selector
        autolock_lbl = QLabel("⏱️ Otomatik Kilit:", self.unlocked_widget)
        autolock_lbl.setStyleSheet("color: #CBD5E1; font-size: 13px; font-weight: 600;")
        dashboard_bar.addWidget(autolock_lbl)

        self.autolock_combo = QComboBox(self.unlocked_widget)
        self.autolock_combo.setObjectName("vaultCombo")
        self.autolock_combo.addItems(["1 dakika", "5 dakika", "15 dakika", "30 dakika", "Asla"])
        self.autolock_combo.setCurrentIndex(1)
        self.autolock_combo.currentIndexChanged.connect(self._on_autolock_changed)
        dashboard_bar.addWidget(self.autolock_combo)

        lock_now_btn = QPushButton("🔒 Şimdi Kilitle", self.unlocked_widget)
        lock_now_btn.setObjectName("secondaryVaultBtn")
        lock_now_btn.clicked.connect(self.lock_vault)
        dashboard_bar.addWidget(lock_now_btn)

        unlocked_layout.addLayout(dashboard_bar)

        # Action Toolbar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        add_img_btn = QPushButton("➕ Görsel Ekle", self.unlocked_widget)
        add_img_btn.setObjectName("primaryVaultBtn")
        add_img_btn.setFixedHeight(38)
        add_img_btn.clicked.connect(self._on_add_image_file)
        action_bar.addWidget(add_img_btn)

        export_backup_btn = QPushButton("📤 Yedek Dışa Aktar (.osvault)", self.unlocked_widget)
        export_backup_btn.setObjectName("secondaryVaultBtn")
        export_backup_btn.setFixedHeight(38)
        export_backup_btn.clicked.connect(self._on_export_osvault_clicked)
        action_bar.addWidget(export_backup_btn)

        export_pdf_btn = QPushButton("📄 PDF Olarak Aktar", self.unlocked_widget)
        export_pdf_btn.setObjectName("secondaryVaultBtn")
        export_pdf_btn.setFixedHeight(38)
        export_pdf_btn.clicked.connect(self._on_export_pdf_clicked)
        action_bar.addWidget(export_pdf_btn)

        optimize_vault_btn = QPushButton("⚡ Kasayı Optimize Et", self.unlocked_widget)
        optimize_vault_btn.setObjectName("secondaryVaultBtn")
        optimize_vault_btn.setFixedHeight(38)
        optimize_vault_btn.clicked.connect(self._on_optimize_vault_clicked)
        action_bar.addWidget(optimize_vault_btn)

        upload_vault_btn = QPushButton("☁️ ImgBB'ye Yükle", self.unlocked_widget)
        upload_vault_btn.setObjectName("secondaryVaultBtn")
        upload_vault_btn.setFixedHeight(38)
        upload_vault_btn.clicked.connect(self._on_upload_vault_image)
        action_bar.addWidget(upload_vault_btn)

        import_backup_btn = QPushButton("📥 Yedek İçe Aktar", self.unlocked_widget)
        import_backup_btn.setObjectName("secondaryVaultBtn")
        import_backup_btn.setFixedHeight(38)
        import_backup_btn.clicked.connect(self._on_import_osvault_clicked)
        action_bar.addWidget(import_backup_btn)

        change_pass_btn = QPushButton("🔑 Parola Değiştir", self.unlocked_widget)
        change_pass_btn.setObjectName("secondaryVaultBtn")
        change_pass_btn.setFixedHeight(38)
        change_pass_btn.clicked.connect(self._on_change_password_clicked)
        action_bar.addWidget(change_pass_btn)

        action_bar.addStretch()
        unlocked_layout.addLayout(action_bar)

        # Gallery Scroll Area
        self.gallery_scroll = QScrollArea(self.unlocked_widget)
        self.gallery_scroll.setWidgetResizable(True)

        self.gallery_container = QWidget(self.gallery_scroll)
        self.gallery_grid = QGridLayout(self.gallery_container)
        self.gallery_grid.setContentsMargins(16, 16, 16, 16)
        self.gallery_grid.setSpacing(20)
        self.gallery_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.gallery_scroll.setWidget(self.gallery_container)

        unlocked_layout.addWidget(self.gallery_scroll)
        self.main_layout.addWidget(self.unlocked_widget)

    def _refresh_state(self) -> None:
        """Toggles between locked and unlocked views and updates UI text."""
        self.loc_info_lbl.setText(f"📁 <b>Kasa Konumu:</b> {self.vault.storage.root}")

        if not self.vault.is_initialized:
            self.locked_widget.setVisible(True)
            self.unlocked_widget.setVisible(False)
            self.create_vault_btn.setVisible(True)
            self.unlock_pass_edit.setEnabled(False)
            self.unlock_pass_edit.setPlaceholderText("Bu konumda kasa yok. 'Yeni Kasa Oluştur'a basın.")
            self.unlock_btn.setEnabled(False)
        elif self.vault.is_unlocked:
            self.locked_widget.setVisible(False)
            self.unlocked_widget.setVisible(True)
            self._load_gallery()
            self._reset_autolock_timer()
        else:
            self.locked_widget.setVisible(True)
            self.unlocked_widget.setVisible(False)
            self.create_vault_btn.setVisible(False)
            self.unlock_pass_edit.setEnabled(True)
            self.unlock_pass_edit.setPlaceholderText("Ana Parolanızı Girin...")
            self.unlock_btn.setEnabled(True)
            self.unlock_pass_edit.clear()
            self.unlock_pass_edit.setFocus()
            self.auto_lock_timer.stop()

    def _on_switch_location_clicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Açmak veya Oluşturmak İstediğiniz Kasa Klasörünü Seçin",
            str(self.vault.storage.root.parent),
        )
        if not folder:
            return

        target_dir = Path(folder)
        self.vault = SecureVault(target_dir)

        # Save to config
        self.config_manager.set("general", "vault_location", str(target_dir))
        self.config_manager.save()

        NotificationManager.show_toast("Konum Değiştirildi", f"Aktif kasa konumu:\n{target_dir}")
        self._refresh_state()

    def _on_unlock_clicked(self) -> None:
        pwd = self.unlock_pass_edit.text()
        if not pwd:
            return
        try:
            self.vault.unlock(pwd)
            NotificationManager.show_toast("Kasa Açıldı", "Güvenli Kasa başarıyla açıldı.")
            self._refresh_state()
        except AuthenticationError:
            QMessageBox.critical(self, "Hata", "Hatalı ana parola veya bozuk kasa verisi.")
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Kasa açılamadı:\n{exc}")

    def lock_vault(self) -> None:
        self.vault.lock()
        self._refresh_state()
        NotificationManager.show_toast("Kasa Kilitlendi", "Güvenli Kasa kilitlendi.")

    def _on_create_vault_clicked(self) -> None:
        dlg = CreateVaultDialog(default_dir=self.vault.storage.root, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.master_password:
            try:
                self.vault = SecureVault(dlg.selected_dir)
                self.vault.create_vault(dlg.master_password)

                self.config_manager.set("general", "vault_location", str(dlg.selected_dir))
                self.config_manager.save()

                NotificationManager.show_toast("Kasa Oluşturuldu", f"Güvenli Kasa oluşturuldu:\n{dlg.selected_dir}")
                self._refresh_state()
            except Exception as exc:
                QMessageBox.critical(self, "Hata", f"Kasa oluşturulamadı:\n{exc}")

    def _on_change_password_clicked(self) -> None:
        dlg = ChangePasswordDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                self.vault.change_master_password(dlg.old_password, dlg.new_password)
                NotificationManager.show_toast("Parola Güncellendi", "Ana parola başarıyla değiştirildi (O(1) rekey).")
            except AuthenticationError:
                QMessageBox.critical(self, "Hata", "Mevcut parolanız hatalı.")
            except Exception as exc:
                QMessageBox.critical(self, "Hata", f"Parola değiştirilemedi:\n{exc}")

    def _on_export_osvault_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Taşınabilir Kasa Yedeği Oluştur (.osvault)",
            f"QuickglintVault_Backup_{time.strftime('%Y%m%d')}.osvault",
            "Quickglint Portable Vault (*.osvault);;Quickglint Eski Portable Vault (*.osvault)",
        )
        if path:
            try:
                self.vault.export_osvault(path)
                NotificationManager.show_toast("Yedek Oluşturuldu", f"Kasa yedeği başarıyla dışa aktarıldı:\n{path}")
            except Exception as exc:
                QMessageBox.critical(self, "Hata", f"Yedek dışa aktarılamadı:\n{exc}")

    def _on_export_pdf_clicked(self) -> None:
        """Exports unlocked vault images into a PDF with memory-only decryption."""
        if not self.vault.is_unlocked or not self.vault.manifest:
            return

        all_items = self.vault.manifest.get_all()
        if not all_items:
            QMessageBox.information(self, "Bilgi", "Kasada dışa aktarılacak görsel bulunmuyor.")
            return

        from app.pdf.image_loader import PDFSourceItem
        from app.ui.pdf_export_dialog import PDFExportDialog

        source_items = []
        for meta in all_items:
            # Memory-only decryption closure
            def make_decrypt_fn(oid=meta.object_id):
                return lambda: self.vault.get_image(oid)

            source_items.append(
                PDFSourceItem(
                    title=meta.title,
                    vault_decrypt_fn=make_decrypt_fn(),
                )
            )

        dlg = PDFExportDialog(items=source_items, parent=self)
        dlg.exec()

    def _on_optimize_vault_clicked(self) -> None:
        """Optimizes all images in vault entirely in memory with AES-256-GCM re-encryption."""
        if not self.vault.is_unlocked or not self.vault.manifest:
            return

        all_items = self.vault.manifest.get_all()
        if not all_items:
            QMessageBox.information(self, "Bilgi", "Kasada optimize edilecek görsel bulunmuyor.")
            return

        reply = QMessageBox.question(
            self,
            "Kasayı Optimize Et",
            f"Kasada bulunan {len(all_items)} adet görsel bellekte (RAM) kayıpsız olarak sıkıştırılıp yeniden şifrelenecek.\n\nDevam etmek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from app.optimizer.models import OptimizerConfig, QualityPreset
        from app.optimizer.vault_optimizer import VaultImageOptimizer

        cfg = OptimizerConfig(is_lossless=True)
        total_saved = 0
        success_count = 0

        for meta in all_items:
            try:
                new_oid, orig_sz, opt_sz = VaultImageOptimizer.optimize_vault_object(
                    self.vault, meta.object_id, cfg
                )
                if new_oid:
                    success_count += 1
                    total_saved += max(0, orig_sz - opt_sz)
            except Exception as exc:
                logger.error("Failed to optimize vault object %s: %s", meta.object_id, exc)

        self._load_gallery()
        NotificationManager.show_toast(
            "Kasa Optimize Edildi ⚡",
            f"{success_count} görsel optimize edildi. Toplam {total_saved / 1024.0:.1f} KB alan kazanıldı.",
        )

    def _on_upload_vault_image(self) -> None:
        """Decrypts in memory and uploads selected/first vault image to ImgBB with user confirmation."""
        if not self.vault.is_unlocked or not self.vault.manifest:
            return

        all_items = self.vault.manifest.get_all()
        if not all_items:
            QMessageBox.information(self, "Bilgi", "Kasada yüklenecek görsel bulunmuyor.")
            return

        from app.security.credential_store import CredentialStore
        from app.ui.upload_dialog import ApiKeyPromptDialog
        api_key = CredentialStore.get_credential("imgbb", "user") or ""
        if not api_key.strip():
            key_dlg = ApiKeyPromptDialog(parent=self)
            if key_dlg.exec() != QDialog.DialogCode.Accepted or not key_dlg.entered_key.strip():
                return
            api_key = key_dlg.entered_key.strip()


        # Select first or target object
        target_meta = all_items[0]

        reply = QMessageBox.question(
            self,
            "Görseli ImgBB'ye Yükle",
            f"'{target_meta.title}' kasadan bellekte çözülüp ImgBB'ye yüklenecek ve paylaşılabilir bir link oluşturulacak.\n\nDevam etmek istiyor musunuz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        from app.ui.upload_dialog import UploadResultDialog
        from app.upload.imgbb import ImgBBProvider

        qimg = self.vault.get_image(target_meta.object_id)
        if not qimg or qimg.isNull():
            QMessageBox.critical(self, "Hata", "Görsel kasadan çözülemedi.")
            return

        qba = QByteArray()
        buf = QBuffer(qba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")

        provider = ImgBBProvider()
        res = provider.upload(bytes(qba.data()), file_name=f"{target_meta.title}.png", api_key=api_key)

        if res.success:
            import time
            from app.upload.history_manager import ShareHistoryManager
            from app.upload.models import ShareHistoryItem
            if self.config_manager.get("upload", "save_history", True):
                ShareHistoryManager.add_item(
                    ShareHistoryItem(
                        timestamp=time.time(),
                        provider=provider.name,
                        direct_url=res.direct_url,
                        share_url=res.share_url,
                        delete_url=res.delete_url,
                        title=res.file_name,
                        size_bytes=res.size_bytes,
                    )
                )
            res_dlg = UploadResultDialog(res, parent=self)
            res_dlg.exec()
        else:
            QMessageBox.critical(self, "Yükleme Başarısız", f"ImgBB Yükleme Hatası:\n{res.error_msg}")

    def _on_import_osvault_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Kasa Yedeğini Seç (.osvault)",
            "",
            "Quickglint Portable Vault (*.osvault);;Quickglint Eski Portable Vault (*.osvault);;Tüm Dosyalar (*)",
        )
        if not path:
            return

        from PySide6.QtWidgets import QInputDialog
        pwd, ok = QInputDialog.getText(
            self,
            "Yedek Parolası",
            "Bu yedek dosyasının Ana Parolasını girin:",
            QLineEdit.EchoMode.Password,
        )
        if ok and pwd:
            try:
                self.vault.import_osvault(path, pwd)
                NotificationManager.show_toast("Yedek İçe Aktarıldı", "Kasa yedeği başarıyla içe aktarıldı ve açıldı.")
                self._refresh_state()
            except AuthenticationError:
                QMessageBox.critical(self, "Hata", "Yedek dosyası parolası hatalı veya dosya bütünlüğü bozulmuş.")
            except Exception as exc:
                QMessageBox.critical(self, "Hata", f"Yedek içe aktarılamadı:\n{exc}")

    def _on_add_image_file(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Kasaya Eklenecek Görselleri Seç", "", "Görseller (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if paths:
            for p in paths:
                img = QImage(p)
                if not img.isNull():
                    self.vault.add_image(img, title=Path(p).stem)
            self._load_gallery()
            NotificationManager.show_toast("Görseller Eklendi", f"{len(paths)} adet görsel şifrelenerek kasaya eklendi.")

    def _load_gallery(self) -> None:
        # Clear grid
        while self.gallery_grid.count():
            item = self.gallery_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.vault.is_unlocked or not self.vault.manifest:
            return

        stats = self.vault.get_stats()
        kb_size = stats['total_size_bytes'] / 1024
        mb_size = kb_size / 1024
        size_str = f"{mb_size:.2f} MB" if mb_size >= 1.0 else f"{kb_size:.1f} KB"
        self.stats_lbl.setText(f"{stats['item_count']} Şifreli Görsel  •  {size_str}")

        objects = list(self.vault.manifest.objects.values())
        objects.sort(key=lambda o: o.created_at, reverse=True)

        cols = 4
        for idx, obj in enumerate(objects):
            card = self._create_card(obj)
            row = idx // cols
            col = idx % cols
            self.gallery_grid.addWidget(card, row, col)

    def _create_card(self, obj) -> QFrame:
        card = QFrame(self.gallery_container)
        card.setFixedSize(210, 220)
        card.setStyleSheet(
            "QFrame { background-color: #1E293B; border: 1px solid #334155; border-radius: 12px; }"
            "QFrame:hover { border: 1.5px solid #3B82F6; background-color: #243048; }"
        )
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Thumbnail
        thumb_lbl = QLabel(card)
        thumb_lbl.setFixedSize(192, 148)
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_lbl.setStyleSheet("background-color: #0F172A; border-radius: 8px;")

        try:
            thumb_qimg = self.vault.get_thumbnail(obj.object_id)
            thumb_pixmap = QPixmap.fromImage(thumb_qimg).scaled(
                192, 148, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            thumb_lbl.setPixmap(thumb_pixmap)
        except Exception:
            thumb_lbl.setText("🔒 [Şifreli]")
            thumb_lbl.setStyleSheet("color: #64748B; font-size: 14px; background-color: #0F172A; border-radius: 8px;")

        layout.addWidget(thumb_lbl)

        # Title
        title_lbl = QLabel(obj.title, card)
        title_lbl.setStyleSheet("color: #F8FAFC; font-weight: 600; font-size: 12px; padding: 2px 4px;")
        layout.addWidget(title_lbl)

        card.mousePressEvent = lambda e: self._on_card_clicked(obj)
        return card

    def _on_card_clicked(self, obj) -> None:
        try:
            full_img = self.vault.get_image(obj.object_id)
            dlg = ImagePreviewDialog(full_img, obj.title, obj.object_id, self.vault, self)
            dlg.open_in_editor_requested.connect(self._on_open_in_editor_requested)
            dlg.exec()
            self._load_gallery()
        except Exception as exc:
            QMessageBox.critical(self, "Hata", f"Görsel açılamadı:\n{exc}")

    def _on_open_in_editor_requested(self, img: QImage) -> None:
        self.open_in_editor.emit(img)
        self.accept()

    def _on_autolock_changed(self, idx: int) -> None:
        mins_map = [1, 5, 15, 30, 0]
        self._auto_lock_minutes = mins_map[idx]
        self._reset_autolock_timer()

    def _reset_autolock_timer(self) -> None:
        if self._auto_lock_minutes > 0 and self.vault.is_unlocked:
            self.auto_lock_timer.start(self._auto_lock_minutes * 60 * 1000)
        else:
            self.auto_lock_timer.stop()

    def _on_auto_lock_timeout(self) -> None:
        if self.vault.is_unlocked:
            self.lock_vault()
            NotificationManager.show_toast("Otomatik Kilitlendi", "Güvenli Kasa süre dolduğu için kilitlendi.")

