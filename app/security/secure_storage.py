"""Sharded encrypted local disk storage ensuring zero plaintext image persistence."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.security.encryption import AuthenticationError, decrypt_aes_gcm, encrypt_aes_gcm
from app.security.kdf import Argon2idParams
from app.security.vault_manifest import VaultManifest, decrypt_manifest, encrypt_manifest
from app.utils.logger import logger

OBJECT_AAD_PREFIX = b"OSVAULT_OBJ_V1:"
THUMB_AAD_PREFIX = b"OSVAULT_THUMB_V1:"


class SecureVaultStorage:
    """Manages sharded encrypted files on local disk with atomic updates."""

    def __init__(self, root_dir: Optional[Path | str] = None) -> None:
        if root_dir is None:
            appdata = os.environ.get("APPDATA", str(Path.home() / ".quickglint"))
            primary_dir = Path(appdata) / "Quickglint" / "SecureVault"
            legacy_dir = Path(appdata) / "Quickglint" / "SecureVault"
            if not primary_dir.exists() and legacy_dir.exists():
                self.root = legacy_dir
            else:
                self.root = primary_dir
        else:
            self.root = Path(root_dir)

        self.objects_dir = self.root / "objects"
        self.header_file = self.root / "vault_header.json"
        self.manifest_file = self.root / "manifest.enc"

    def exists(self) -> bool:
        """Returns True if a vault is initialized at this location."""
        return self.header_file.exists() and self.manifest_file.exists()

    def initialize(
        self,
        kdf_params: Argon2idParams,
        wrapped_vault_key_hex: str,
        vault_key: bytes,
    ) -> None:
        """Creates directory structure, writes public header and initial encrypted manifest."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write public header
        self.write_header(kdf_params, wrapped_vault_key_hex)

        # 2. Write empty encrypted manifest
        manifest = VaultManifest()
        self.save_manifest(manifest, vault_key)

    def write_header(self, kdf_params: Argon2idParams, wrapped_vault_key_hex: str) -> None:
        """Writes public header atomically."""
        header_data = {
            "format": "QuickglintSecureVault",
            "version": 1,
            "kdf": kdf_params.to_dict(),
            "wrapped_vault_key": wrapped_vault_key_hex,
        }
        tmp_file = self.root / "vault_header.json.tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(header_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        tmp_file.replace(self.header_file)

    def read_header(self) -> Tuple[Argon2idParams, str]:
        """Reads public KDF params and wrapped vault key."""
        if not self.header_file.exists():
            raise FileNotFoundError("Vault header not found.")

        with open(self.header_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        kdf_dict = data.get("kdf", {})
        params = Argon2idParams.from_dict(kdf_dict)
        wrapped_hex = str(data.get("wrapped_vault_key", ""))
        return params, wrapped_hex

    def save_manifest(self, manifest: VaultManifest, vault_key: bytes) -> None:
        """Encrypts and atomically saves the manifest to disk."""
        encrypted_bytes = encrypt_manifest(manifest, vault_key)
        tmp_file = self.root / "manifest.enc.tmp"
        with open(tmp_file, "wb") as f:
            f.write(encrypted_bytes)
            f.flush()
            os.fsync(f.fileno())

        tmp_file.replace(self.manifest_file)

    def load_manifest(self, vault_key: bytes) -> VaultManifest:
        """Reads, decrypts, and authenticates the manifest from disk."""
        if not self.manifest_file.exists():
            raise FileNotFoundError("Encrypted manifest file not found.")

        with open(self.manifest_file, "rb") as f:
            encrypted_bytes = f.read()

        return decrypt_manifest(encrypted_bytes, vault_key)

    def _get_shard_path(self, object_id: str, is_thumb: bool = False) -> Path:
        """
        Shards objects into a 2-level directory tree:
        objects/a8/71/a87191c8...enc
        """
        clean_id = object_id.replace("-", "")
        p1 = clean_id[:2] if len(clean_id) >= 2 else "00"
        p2 = clean_id[2:4] if len(clean_id) >= 4 else "00"
        suffix = ".thumb.enc" if is_thumb else ".enc"
        shard_dir = self.objects_dir / p1 / p2
        shard_dir.mkdir(parents=True, exist_ok=True)
        return shard_dir / f"{clean_id}{suffix}"

    def write_encrypted_object(
        self,
        object_id: str,
        image_bytes: bytes,
        vault_key: bytes,
        is_thumb: bool = False,
    ) -> int:
        """
        Encrypts image/thumbnail in memory and writes directly to sharded storage.
        Returns size in bytes of written encrypted payload.
        """
        aad_prefix = THUMB_AAD_PREFIX if is_thumb else OBJECT_AAD_PREFIX
        aad = aad_prefix + object_id.encode("utf-8")

        encrypted_payload = encrypt_aes_gcm(vault_key, image_bytes, aad=aad)

        dest_path = self._get_shard_path(object_id, is_thumb=is_thumb)
        tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")

        with open(tmp_path, "wb") as f:
            f.write(encrypted_payload)
            f.flush()
            os.fsync(f.fileno())

        tmp_path.replace(dest_path)
        return len(encrypted_payload)

    def read_encrypted_object(
        self,
        object_id: str,
        vault_key: bytes,
        is_thumb: bool = False,
    ) -> bytes:
        """
        Reads encrypted payload from disk and decrypts directly into memory.
        """
        path = self._get_shard_path(object_id, is_thumb=is_thumb)
        if not path.exists():
            raise FileNotFoundError(f"Encrypted object {object_id} not found on disk.")

        with open(path, "rb") as f:
            encrypted_payload = f.read()

        aad_prefix = THUMB_AAD_PREFIX if is_thumb else OBJECT_AAD_PREFIX
        aad = aad_prefix + object_id.encode("utf-8")

        return decrypt_aes_gcm(vault_key, encrypted_payload, aad=aad)

    def delete_object(self, object_id: str) -> None:
        """Deletes main and thumbnail encrypted files from sharded disk storage."""
        main_path = self._get_shard_path(object_id, is_thumb=False)
        thumb_path = self._get_shard_path(object_id, is_thumb=True)

        if main_path.exists():
            main_path.unlink()
        if thumb_path.exists():
            thumb_path.unlink()

