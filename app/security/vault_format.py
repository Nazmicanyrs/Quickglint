"""Single-file portable .osvault binary container packaging, verification, and extraction."""

import hashlib
import json
import os
from pathlib import Path
import struct
from typing import Optional, Tuple
import uuid

from app.security.encryption import AuthenticationError, decrypt_aes_gcm
from app.security.kdf import Argon2idParams
from app.security.key_manager import KeyManager
from app.security.secure_storage import OBJECT_AAD_PREFIX, SecureVaultStorage, THUMB_AAD_PREFIX
from app.security.vault_manifest import VaultManifest, decrypt_manifest
from app.utils.logger import logger

OSVAULT_MAGIC = b"OSVAULT\x01"


class VaultContainerFormat:
    """Manages serialization, atomic export, and verified import of .osvault files."""

    @classmethod
    def export_container(
        cls,
        storage: SecureVaultStorage,
        vault_key: bytes,
        output_path: Path | str,
    ) -> bool:
        """
        Packs the current vault into an authenticated, self-contained .osvault backup file.
        Uses atomic write with .tmp and pre-commit self-verification.
        """
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = out_file.with_suffix(out_file.suffix + ".tmp")

        try:
            # 1. Read header and manifest
            kdf_params, wrapped_key_hex = storage.read_header()
            manifest = storage.load_manifest(vault_key)

            header_dict = {
                "format": "QuickglintPortableVault",
                "version": 1,
                "kdf": kdf_params.to_dict(),
                "wrapped_vault_key": wrapped_key_hex,
            }
            header_json_bytes = json.dumps(header_dict, ensure_ascii=False).encode("utf-8")

            with open(storage.manifest_file, "rb") as mf:
                manifest_enc_bytes = mf.read()

            with open(tmp_file, "wb") as f:
                # 1. Magic (8 bytes)
                f.write(OSVAULT_MAGIC)

                # 2. Public Header (Length: 4 bytes uint32 + payload)
                f.write(struct.pack(">I", len(header_json_bytes)))
                f.write(header_json_bytes)

                # 3. Encrypted Manifest (Length: 4 bytes uint32 + payload)
                f.write(struct.pack(">I", len(manifest_enc_bytes)))
                f.write(manifest_enc_bytes)

                # 4. Stream Encrypted Objects
                for obj_id, obj_desc in manifest.objects.items():
                    uuid_bytes = uuid.UUID(obj_id).bytes

                    # Main image payload
                    main_shard = storage._get_shard_path(obj_id, is_thumb=False)
                    if main_shard.exists():
                        with open(main_shard, "rb") as sf:
                            main_data = sf.read()
                        # Header: UUID (16B), Type (4B: b"MAIN"), Len (8B uint64)
                        f.write(uuid_bytes)
                        f.write(b"MAIN")
                        f.write(struct.pack(">Q", len(main_data)))
                        f.write(main_data)

                    # Thumbnail payload
                    thumb_shard = storage._get_shard_path(obj_id, is_thumb=True)
                    if thumb_shard.exists():
                        with open(thumb_shard, "rb") as tf:
                            thumb_data = tf.read()
                        f.write(uuid_bytes)
                        f.write(b"THMB")
                        f.write(struct.pack(">Q", len(thumb_data)))
                        f.write(thumb_data)

                f.flush()
                os.fsync(f.fileno())

            # 5. Pre-commit Verification: Self-validate the backup before committing
            is_valid, err_msg = cls.verify_container(tmp_file, vault_key)
            if not is_valid:
                raise AuthenticationError(f"Backup self-verification failed: {err_msg}")

            # 6. Atomic commit
            tmp_file.replace(out_file)
            logger.info("Successfully exported .osvault to %s (Size: %.2f MB)", out_file, out_file.stat().st_size / (1024 * 1024))
            return True

        except Exception as exc:
            logger.error("Failed to export .osvault: %s", exc, exc_info=True)
            if tmp_file.exists():
                tmp_file.unlink()
            raise

    @classmethod
    def verify_container(cls, container_path: Path | str, vault_key: bytes) -> Tuple[bool, str]:
        """
        Validates structure, magic bytes, manifest authentication, and all object tags.
        """
        path = Path(container_path)
        if not path.exists():
            return False, "File does not exist."

        try:
            with open(path, "rb") as f:
                # 1. Check Magic
                magic = f.read(len(OSVAULT_MAGIC))
                if magic != OSVAULT_MAGIC:
                    return False, "Invalid file format (Missing OSVAULT magic header)."

                # 2. Check Header
                hdr_len_bytes = f.read(4)
                if len(hdr_len_bytes) < 4:
                    return False, "Truncated container header length."
                hdr_len = struct.unpack(">I", hdr_len_bytes)[0]
                hdr_bytes = f.read(hdr_len)
                if len(hdr_bytes) < hdr_len:
                    return False, "Truncated container header."
                json.loads(hdr_bytes.decode("utf-8"))

                # 3. Check Manifest
                man_len_bytes = f.read(4)
                if len(man_len_bytes) < 4:
                    return False, "Truncated manifest length."
                man_len = struct.unpack(">I", man_len_bytes)[0]
                man_bytes = f.read(man_len)
                if len(man_bytes) < man_len:
                    return False, "Truncated manifest payload."

                manifest = decrypt_manifest(man_bytes, vault_key)

                # 4. Check Objects
                while True:
                    uuid_b = f.read(16)
                    if not uuid_b:
                        break
                    if len(uuid_b) < 16:
                        return False, "Truncated object UUID."
                    obj_id = str(uuid.UUID(bytes=uuid_b))

                    obj_type = f.read(4)
                    if len(obj_type) < 4:
                        return False, "Truncated object type."

                    plen_b = f.read(8)
                    if len(plen_b) < 8:
                        return False, "Truncated payload length."
                    payload_len = struct.unpack(">Q", plen_b)[0]

                    payload = f.read(payload_len)
                    if len(payload) < payload_len:
                        return False, "Truncated payload data."

                    # Verify authenticated decrypt
                    is_thumb = (obj_type == b"THMB")
                    aad_prefix = THUMB_AAD_PREFIX if is_thumb else OBJECT_AAD_PREFIX
                    aad = aad_prefix + obj_id.encode("utf-8")

                    decrypt_aes_gcm(vault_key, payload, aad=aad)

            return True, "Integrity PASS"

        except Exception as exc:
            return False, str(exc)

    @classmethod
    def import_container(
        cls,
        container_path: Path | str,
        target_storage: SecureVaultStorage,
        master_password: str,
    ) -> bool:
        """
        Unpacks and authenticates a portable .osvault into the target local storage.
        """
        path = Path(container_path)
        if not path.exists():
            raise FileNotFoundError("Backup file not found.")

        # 1. Read Magic and Public Header
        with open(path, "rb") as f:
            magic = f.read(len(OSVAULT_MAGIC))
            if magic != OSVAULT_MAGIC:
                raise AuthenticationError("Invalid .osvault file magic.")

            def _read_exact(n: int) -> bytes:
                data = f.read(n)
                if len(data) != n:
                    raise AuthenticationError("Corrupted or truncated .osvault file.")
                return data

            hdr_len = struct.unpack(">I", _read_exact(4))[0]
            hdr_bytes = _read_exact(hdr_len)
            header_dict = json.loads(hdr_bytes.decode("utf-8"))

            kdf_dict = header_dict.get("kdf", {})
            kdf_params = Argon2idParams.from_dict(kdf_dict)
            wrapped_key_hex = str(header_dict.get("wrapped_vault_key", ""))

            # 2. Authenticate master password and unwrap Vault Key
            vault_key = KeyManager.unlock_vault(master_password, kdf_params, wrapped_key_hex)

            # 3. Read and authenticate manifest
            man_len = struct.unpack(">I", _read_exact(4))[0]
            man_bytes = _read_exact(man_len)
            manifest = decrypt_manifest(man_bytes, vault_key)

            # 4. Stream objects into temporary files; commit only after everything
            # verified so a bad backup can never corrupt an existing vault.
            target_storage.root.mkdir(parents=True, exist_ok=True)
            target_storage.objects_dir.mkdir(parents=True, exist_ok=True)

            staged: list[tuple[Path, Path]] = []
            try:
                while True:
                    uuid_b = f.read(16)
                    if not uuid_b:
                        break
                    if len(uuid_b) != 16:
                        raise AuthenticationError("Corrupted or truncated .osvault file.")
                    try:
                        obj_id = str(uuid.UUID(bytes=uuid_b))
                    except ValueError as exc:
                        raise AuthenticationError(f"Invalid object id in backup: {exc}") from exc
                    obj_type = _read_exact(4)
                    payload_len = struct.unpack(">Q", _read_exact(8))[0]
                    payload = _read_exact(payload_len)

                    # Authenticate payload before writing
                    is_thumb = (obj_type == b"THMB")
                    aad_prefix = THUMB_AAD_PREFIX if is_thumb else OBJECT_AAD_PREFIX
                    aad = aad_prefix + obj_id.encode("utf-8")
                    decrypt_aes_gcm(vault_key, payload, aad=aad)

                    dest_shard = target_storage._get_shard_path(obj_id, is_thumb=is_thumb)
                    tmp_shard = dest_shard.with_suffix(dest_shard.suffix + ".tmp")
                    with open(tmp_shard, "wb") as out_f:
                        out_f.write(payload)
                    staged.append((tmp_shard, dest_shard))

                for tmp_shard, dest_shard in staged:
                    tmp_shard.replace(dest_shard)
                staged.clear()
            finally:
                for tmp_shard, _ in staged:
                    tmp_shard.unlink(missing_ok=True)

            # 5. Write verified header and manifest
            target_storage.write_header(kdf_params, wrapped_key_hex)
            target_storage.save_manifest(manifest, vault_key)

            logger.info("Successfully imported %d objects from %s", len(manifest.objects), path)
            return True

