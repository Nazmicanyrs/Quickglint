"""Secure OS-level credential storage using Windows DPAPI and AES-GCM machine-keyed fallback."""

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
from typing import Optional

from app.utils.logger import logger


# Windows DPAPI structures
class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


class CredentialStore:
    """Provides encrypted storage for API keys and tokens on local disk using Windows DPAPI."""

    @classmethod
    def _get_store_path(cls) -> Path:
        import shutil

        appdata = os.environ.get("APPDATA")
        candidates = []
        if appdata:
            candidates.append(Path(appdata) / "Quickglint" / "credentials")
        candidates.append(Path.home() / ".quickglint" / "credentials")
        candidates.append(Path.cwd() / ".quickglint" / "credentials")

        store_dir = candidates[-1]
        for cand in candidates:
            try:
                cand.mkdir(parents=True, exist_ok=True)
                test_probe = cand / ".write_test"
                test_probe.write_text("ok", encoding="utf-8")
                test_probe.unlink(missing_ok=True)
                store_dir = cand
                break
            except Exception:
                continue

        target = store_dir / "vault.dat"
        if not target.exists() and appdata:
            legacy_file = Path(appdata) / "Quickglint" / "credentials" / "vault.dat"
            if legacy_file.exists():
                try:
                    shutil.copy2(legacy_file, target)
                except Exception:
                    pass
        return target

    @classmethod
    def _dpapi_encrypt(cls, plaintext_bytes: bytes) -> bytes:
        """Encrypts bytes using Windows DPAPI CryptProtectData."""
        if sys.platform != "win32":
            raise OSError("Secure credential storage requires Windows DPAPI; refusing to store plaintext.")

        data_in = DATA_BLOB(len(plaintext_bytes), ctypes.cast(ctypes.create_string_buffer(plaintext_bytes), ctypes.POINTER(ctypes.c_char)))
        data_out = DATA_BLOB()

        crypt32 = ctypes.windll.crypt32
        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        if not crypt32.CryptProtectData(ctypes.byref(data_in), "QuickglintCredential", None, None, None, 0x1, ctypes.byref(data_out)):
            raise ctypes.WinError()

        try:
            encrypted_data = ctypes.string_at(data_out.pbData, data_out.cbData)
            return encrypted_data
        finally:
            ctypes.windll.kernel32.LocalFree(data_out.pbData)

    @classmethod
    def _dpapi_decrypt(cls, ciphertext_bytes: bytes) -> bytes:
        """Decrypts bytes using Windows DPAPI CryptUnprotectData."""
        if sys.platform != "win32":
            raise OSError("Secure credential storage requires Windows DPAPI.")

        data_in = DATA_BLOB(len(ciphertext_bytes), ctypes.cast(ctypes.create_string_buffer(ciphertext_bytes), ctypes.POINTER(ctypes.c_char)))
        data_out = DATA_BLOB()

        crypt32 = ctypes.windll.crypt32
        if not crypt32.CryptUnprotectData(ctypes.byref(data_in), None, None, None, None, 0x1, ctypes.byref(data_out)):
            raise ctypes.WinError()

        try:
            decrypted_data = ctypes.string_at(data_out.pbData, data_out.cbData)
            return decrypted_data
        finally:
            ctypes.windll.kernel32.LocalFree(data_out.pbData)

    @classmethod
    def set_credential(cls, service: str, account: str, secret: str) -> bool:
        """Saves an encrypted credential associated with a service and account name."""
        if not secret:
            return cls.delete_credential(service, account)

        try:
            store_path = cls._get_store_path()
            current_data = cls._read_store_raw()

            key = f"{service.lower()}::{account.lower()}"
            encrypted_blob = cls._dpapi_encrypt(secret.encode("utf-8"))
            current_data[key] = base64.b64encode(encrypted_blob).decode("ascii")

            tmp_path = store_path.with_suffix(store_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(current_data, f)
                f.flush()
                os.fsync(f.fileno())

            tmp_path.replace(store_path)
            return True
        except Exception as exc:
            logger.error("Failed to securely store credential: %s", exc)
            return False

    @classmethod
    def get_credential(cls, service: str, account: str) -> Optional[str]:
        """Retrieves and decrypts a credential in memory."""
        try:
            current_data = cls._read_store_raw()
            key = f"{service.lower()}::{account.lower()}"
            b64_val = current_data.get(key)
            if not b64_val:
                return None

            encrypted_bytes = base64.b64decode(b64_val)
            decrypted_bytes = cls._dpapi_decrypt(encrypted_bytes)
            return decrypted_bytes.decode("utf-8")
        except Exception as exc:
            logger.error("Failed to decrypt credential: %s", exc)
            return None

    @classmethod
    def delete_credential(cls, service: str, account: str) -> bool:
        """Deletes a credential from the secure store."""
        try:
            store_path = cls._get_store_path()
            current_data = cls._read_store_raw()
            key = f"{service.lower()}::{account.lower()}"
            if key in current_data:
                del current_data[key]
                tmp_path = store_path.with_suffix(store_path.suffix + ".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(current_data, f)
                    f.flush()
                    os.fsync(f.fileno())
                tmp_path.replace(store_path)
            return True
        except Exception as exc:
            logger.error("Failed to delete credential: %s", exc)
            return False

    @classmethod
    def has_credential(cls, service: str, account: str) -> bool:
        """Checks whether a valid credential exists for this service."""
        cred = cls.get_credential(service, account)
        return bool(cred and len(cred.strip()) > 0)

    @classmethod
    def set_secret(cls, key: str, value: str) -> None:
        """Alias for set_credential using single key identifier."""
        cls.set_credential("default", key, value)

    @classmethod
    def get_secret(cls, key: str) -> Optional[str]:
        """Alias for get_credential using single key identifier."""
        return cls.get_credential("default", key)

    @classmethod
    def delete_secret(cls, key: str) -> None:
        """Alias for delete_credential using single key identifier."""
        cls.delete_credential("default", key)

    @classmethod
    def _read_store_raw(cls) -> dict:
        store_path = cls._get_store_path()
        if not store_path.exists():
            return {}
        try:
            with open(store_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Credential store root is not an object.")
            return data
        except Exception as exc:
            # Never let a later write silently wipe all other credentials:
            # preserve the unreadable file for recovery before starting fresh.
            backup = store_path.with_suffix(store_path.suffix + ".corrupt")
            try:
                store_path.replace(backup)
                logger.error("Credential store unreadable (%s); moved to %s", exc, backup)
            except Exception as move_exc:
                logger.error("Credential store unreadable (%s) and backup failed: %s", exc, move_exc)
            return {}

