"""Two-Tier Key Lifecycle Manager: KEK derivation, CSPRNG Vault Key wrapping, and O(1) rekey."""

import os
from typing import Optional, Tuple

from app.security.encryption import AuthenticationError, decrypt_aes_gcm, encrypt_aes_gcm
from app.security.kdf import Argon2idParams, derive_kek

VAULT_KEY_WRAP_AAD = b"OSVAULT_KEY_WRAP_V1"


class KeyManager:
    """Manages generation, wrapping, unwrapping, and instant re-keying of the 256-bit Vault Key."""

    @staticmethod
    def generate_vault_key() -> bytes:
        """Generates a cryptographically random 256-bit (32-byte) master Vault Key."""
        return os.urandom(32)

    @staticmethod
    def wrap_vault_key(vault_key: bytes, kek: bytes) -> str:
        """Encrypts the Vault Key using the KEK with AES-256-GCM and AAD binding."""
        wrapped_bytes = encrypt_aes_gcm(kek, vault_key, aad=VAULT_KEY_WRAP_AAD)
        return wrapped_bytes.hex()

    @staticmethod
    def unwrap_vault_key(wrapped_hex: str, kek: bytes) -> bytes:
        """Decrypts and authenticates the wrapped Vault Key using the KEK."""
        wrapped_bytes = bytes.fromhex(wrapped_hex)
        vault_key = decrypt_aes_gcm(kek, wrapped_bytes, aad=VAULT_KEY_WRAP_AAD)
        if len(vault_key) != 32:
            raise AuthenticationError("Unwrapped Vault Key has invalid length.")
        return vault_key

    @classmethod
    def initialize_new_vault(
        cls,
        master_password: str,
        kdf_params: Optional[Argon2idParams] = None,
    ) -> Tuple[Argon2idParams, str, bytes]:
        """
        Initializes a fresh vault key bundle.
        Returns: (kdf_params, wrapped_vault_key_hex, raw_vault_key)
        """
        params = kdf_params or Argon2idParams.create_new()
        kek = derive_kek(master_password, params)
        vault_key = cls.generate_vault_key()
        wrapped_hex = cls.wrap_vault_key(vault_key, kek)
        return params, wrapped_hex, vault_key

    @classmethod
    def unlock_vault(
        cls,
        master_password: str,
        kdf_params: Argon2idParams,
        wrapped_hex: str,
    ) -> bytes:
        """
        Derives KEK from master password and unwraps the Vault Key.
        Raises AuthenticationError if password is wrong or wrapped key was tampered.
        """
        kek = derive_kek(master_password, kdf_params)
        return cls.unwrap_vault_key(wrapped_hex, kek)

    @classmethod
    def change_master_password(
        cls,
        old_password: str,
        new_password: str,
        current_params: Argon2idParams,
        current_wrapped_hex: str,
    ) -> Tuple[Argon2idParams, str, bytes]:
        """
        Atomically changes master password by unwrapping existing Vault Key and re-wrapping with new KEK.
        Executes in O(1) time without re-encrypting any images.
        """
        # 1. Authenticate and retrieve existing Vault Key
        vault_key = cls.unlock_vault(old_password, current_params, current_wrapped_hex)

        # 2. Derive new KEK with a fresh unique salt
        new_params = Argon2idParams.create_new(
            time_cost=current_params.time_cost,
            memory_cost=current_params.memory_cost,
            parallelism=current_params.parallelism,
        )
        new_kek = derive_kek(new_password, new_params)

        # 3. Re-wrap the SAME Vault Key with new KEK
        new_wrapped_hex = cls.wrap_vault_key(vault_key, new_kek)

        # 4. Verify that new password can unlock the new bundle
        test_key = cls.unlock_vault(new_password, new_params, new_wrapped_hex)
        if test_key != vault_key:
            raise AuthenticationError("Rekey self-verification failed.")

        return new_params, new_wrapped_hex, vault_key

