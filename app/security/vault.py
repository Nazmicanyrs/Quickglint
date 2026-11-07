"""High-level SecureVault interface managing lifecycle, gallery objects, and portable backup operations."""

import hashlib
import io
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from PIL import Image
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

from app.security.encryption import AuthenticationError
from app.security.kdf import Argon2idParams
from app.security.key_manager import KeyManager
from app.security.secure_storage import SecureVaultStorage
from app.security.vault_format import VaultContainerFormat
from app.security.vault_manifest import VaultManifest, VaultObject
from app.utils.logger import logger


class SecureVault:
    """Master controller for the Quickglint Portable Encrypted Secure Vault."""

    def __init__(self, custom_storage_dir: Optional[Path | str] = None) -> None:
        self.storage = SecureVaultStorage(custom_storage_dir)
        self.vault_key: Optional[bytes] = None
        self.manifest: Optional[VaultManifest] = None
        self.kdf_params: Optional[Argon2idParams] = None
        self.wrapped_vault_key_hex: str = ""

    @property
    def is_initialized(self) -> bool:
        """Returns True if a vault exists on disk."""
        return self.storage.exists()

    @property
    def is_unlocked(self) -> bool:
        """Returns True if the vault is unlocked with a valid Vault Key in memory."""
        return (self.vault_key is not None) and (self.manifest is not None)

    def create_vault(self, master_password: str, kdf_params: Optional[Argon2idParams] = None) -> None:
        """Creates and initializes a new secure vault with the given master password."""
        if self.is_initialized:
            raise RuntimeError("Vault is already initialized at this location.")

        params, wrapped_hex, vk = KeyManager.initialize_new_vault(master_password, kdf_params)
        self.storage.initialize(params, wrapped_hex, vk)

        self.kdf_params = params
        self.wrapped_vault_key_hex = wrapped_hex
        self.vault_key = vk
        self.manifest = VaultManifest()
        logger.info("Secure Vault successfully initialized and unlocked.")

    def unlock(self, master_password: str) -> bool:
        """
        Unlocks the vault using the Master Password.
        Raises AuthenticationError if password is wrong or vault is corrupted.
        """
        params, wrapped_hex = self.storage.read_header()
        vk = KeyManager.unlock_vault(master_password, params, wrapped_hex)
        manifest = self.storage.load_manifest(vk)

        self.kdf_params = params
        self.wrapped_vault_key_hex = wrapped_hex
        self.vault_key = vk
        self.manifest = manifest
        logger.info("Secure Vault unlocked with %d items.", len(manifest.objects))
        return True

    def lock(self) -> None:
        """Wipes the Vault Key from memory and locks the vault."""
        self.vault_key = None
        self.manifest = None
        logger.info("Secure Vault locked.")

    def _require_unlocked(self) -> bytes:
        if not self.is_unlocked or self.vault_key is None or self.manifest is None:
            raise PermissionError("Vault is locked. Please unlock the vault first.")
        return self.vault_key

    def add_image(self, image: QImage | Image.Image, title: str = "") -> str:
        """
        Encrypts an image and its thumbnail into the vault.
        Returns the unique random object_id (UUID4).
        """
        vk = self._require_unlocked()

        # Convert QImage to PNG bytes in memory
        if isinstance(image, QImage):
            qbyte_array = QByteArray()
            buffer = QBuffer(qbyte_array)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            img_bytes = bytes(qbyte_array.data())
            w, h = image.width(), image.height()

            # Create thumbnail QImage (max 256x256)
            thumb_qimg = image.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            thumb_byte_array = QByteArray()
            thumb_buffer = QBuffer(thumb_byte_array)
            thumb_buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            thumb_qimg.save(thumb_buffer, "PNG")
            thumb_bytes = bytes(thumb_byte_array.data())
        else:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            w, h = image.size

            thumb_img = image.copy()
            thumb_img.thumbnail((256, 256))
            thumb_buf = io.BytesIO()
            thumb_img.save(thumb_buf, format="PNG")
            thumb_bytes = thumb_buf.getvalue()

        object_id = str(uuid.uuid4())
        obj_title = title.strip() or f"Screenshot {time.strftime('%Y-%m-%d %H:%M:%S')}"

        # Write encrypted main image
        enc_size = self.storage.write_encrypted_object(object_id, img_bytes, vk, is_thumb=False)
        # Write encrypted thumbnail
        thumb_enc_size = self.storage.write_encrypted_object(object_id, thumb_bytes, vk, is_thumb=True)

        sha256_hash = hashlib.sha256(img_bytes).hexdigest()

        obj_descriptor = VaultObject(
            object_id=object_id,
            title=obj_title,
            created_at=time.time(),
            width=w,
            height=h,
            encrypted_size=enc_size,
            thumbnail_encrypted_size=thumb_enc_size,
            sha256_ciphertext=sha256_hash,
        )

        self.manifest.add_object(obj_descriptor)
        self.storage.save_manifest(self.manifest, vk)

        logger.info("Added encrypted object %s (%s, %d bytes) to vault.", object_id, obj_title, enc_size)
        return object_id

    def get_image(self, object_id: str) -> QImage:
        """Decrypts and returns the full resolution QImage directly in memory."""
        vk = self._require_unlocked()
        img_bytes = self.storage.read_encrypted_object(object_id, vk, is_thumb=False)

        qimg = QImage()
        qimg.loadFromData(img_bytes, "PNG")
        return qimg

    def get_thumbnail(self, object_id: str) -> QImage:
        """Decrypts and returns the thumbnail QImage directly in memory."""
        vk = self._require_unlocked()
        try:
            thumb_bytes = self.storage.read_encrypted_object(object_id, vk, is_thumb=True)
            qimg = QImage()
            qimg.loadFromData(thumb_bytes, "PNG")
            return qimg
        except FileNotFoundError:
            # Fallback to full image if thumbnail not found
            return self.get_image(object_id).scaled(
                256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )

    def delete_image(self, object_id: str) -> bool:
        """Deletes object from disk and manifest."""
        vk = self._require_unlocked()
        if object_id not in self.manifest.objects:
            return False

        # Persist the manifest first, then delete files: a crash in between leaves
        # a harmless orphan file instead of a manifest entry pointing to nothing.
        self.manifest.remove_object(object_id)
        self.storage.save_manifest(self.manifest, vk)
        self.storage.delete_object(object_id)
        logger.info("Deleted object %s from vault.", object_id)
        return True

    def change_master_password(self, old_password: str, new_password: str) -> bool:
        """
        Changes Master Password in O(1) time without re-encrypting any images.
        """
        params, wrapped_hex = self.storage.read_header()
        new_params, new_wrapped_hex, vk = KeyManager.change_master_password(
            old_password, new_password, params, wrapped_hex
        )

        self.storage.write_header(new_params, new_wrapped_hex)
        self.kdf_params = new_params
        self.wrapped_vault_key_hex = new_wrapped_hex
        self.vault_key = vk
        logger.info("Master password successfully changed (O(1) rekey).")
        return True

    def export_osvault(self, target_path: Path | str) -> bool:
        """Packs the vault into a single .osvault portable file."""
        vk = self._require_unlocked()
        return VaultContainerFormat.export_container(self.storage, vk, target_path)

    def import_osvault(self, source_path: Path | str, master_password: str) -> bool:
        """Imports an external .osvault backup into this local storage."""
        success = VaultContainerFormat.import_container(source_path, self.storage, master_password)
        if success:
            self.unlock(master_password)
        return success

    def verify_vault(self) -> Tuple[bool, List[str]]:
        """Verifies integrity of all encrypted objects in the vault."""
        vk = self._require_unlocked()
        errors = []

        for obj_id, obj_desc in self.manifest.objects.items():
            try:
                self.storage.read_encrypted_object(obj_id, vk, is_thumb=False)
            except Exception as exc:
                errors.append(f"Object {obj_id} error: {exc}")

        return (len(errors) == 0), errors

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics for the vault."""
        if not self.is_unlocked or self.manifest is None:
            return {"item_count": 0, "total_size_bytes": 0, "status": "LOCKED"}

        total_bytes = sum(o.encrypted_size + o.thumbnail_encrypted_size for o in self.manifest.objects.values())
        return {
            "item_count": len(self.manifest.objects),
            "total_size_bytes": total_bytes,
            "created_at": self.manifest.created_at,
            "modified_at": self.manifest.modified_at,
            "status": "UNLOCKED",
        }

