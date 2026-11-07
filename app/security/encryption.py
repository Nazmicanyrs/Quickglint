"""Authenticated AES-256-GCM encryption and decryption with AAD and CSPRNG nonces."""

import os
from typing import Optional
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class AuthenticationError(Exception):
    """Raised when ciphertext authentication or tag verification fails."""
    pass


def encrypt_aes_gcm(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """
    Encrypts plaintext using AES-256-GCM.
    Returns: nonce (12 bytes) + ciphertext + tag (16 bytes).
    """
    if len(key) != 32:
        raise ValueError(f"AES-256 requires a 32-byte key (got {len(key)} bytes).")

    nonce = os.urandom(12)  # Cryptographically secure 96-bit random nonce
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, aad)
    return nonce + ciphertext_with_tag


def decrypt_aes_gcm(key: bytes, payload: bytes, aad: bytes = b"") -> bytes:
    """
    Decrypts and authenticates AES-256-GCM payload (12-byte nonce + ciphertext + tag).
    Raises AuthenticationError if data is corrupted, altered, or AAD mismatches.
    """
    if len(key) != 32:
        raise ValueError(f"AES-256 requires a 32-byte key (got {len(key)} bytes).")
    if len(payload) < 12 + 16:
        raise AuthenticationError("Payload is too short to contain valid nonce and GCM tag.")

    nonce = payload[:12]
    ciphertext_with_tag = payload[12:]

    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, aad)
        return plaintext
    except InvalidTag as exc:
        raise AuthenticationError("Authentication failed: data has been modified or incorrect key/AAD provided.") from exc

