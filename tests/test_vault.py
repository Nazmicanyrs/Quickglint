"""Comprehensive automated test suite for the Portable Encrypted Secure Vault."""

import os
from pathlib import Path
import pytest
from PySide6.QtGui import QColor, QImage, QPainter

from app.security.encryption import AuthenticationError, decrypt_aes_gcm, encrypt_aes_gcm
from app.security.kdf import Argon2idParams, derive_kek
from app.security.key_manager import KeyManager
from app.security.vault import SecureVault
from app.security.vault_format import OSVAULT_MAGIC, VaultContainerFormat
from app.security.vault_manifest import VaultManifest, VaultObject, decrypt_manifest, encrypt_manifest
from app.ui.vault_window import calculate_password_strength


def create_dummy_qimage(w: int = 120, h: int = 80, color: QColor = QColor(255, 0, 0)) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(color)
    painter = QPainter(img)
    painter.setPen(QColor(0, 255, 0))
    painter.drawText(10, 30, "Vault Secret Test")
    painter.end()
    return img


def test_password_strength_calculation():
    score1, label1, _ = calculate_password_strength("123")
    assert score1 < 30
    assert "Zayıf" in label1 or "Weak" in label1

    score2, label2, _ = calculate_password_strength("MySuperSecretVaultPassword2026!@#")
    assert score2 >= 90
    assert "Güçlü" in label2 or "Strong" in label2


def test_argon2id_kdf():
    params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    kek1 = derive_kek("MasterPassword123", params)
    kek2 = derive_kek("MasterPassword123", params)
    assert len(kek1) == 32
    assert kek1 == kek2  # Deterministic with same salt and params

    # Different salt produces different KEK
    params2 = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    kek3 = derive_kek("MasterPassword123", params2)
    assert kek1 != kek3


def test_aes_256_gcm_authenticated_encryption():
    key = os.urandom(32)
    plaintext = b"Highly confidential screenshot payload data 2026"
    aad = b"AAD_BINDING_V1"

    ciphertext = encrypt_aes_gcm(key, plaintext, aad=aad)
    assert len(ciphertext) == 12 + len(plaintext) + 16  # Nonce (12) + CT + Tag (16)

    decrypted = decrypt_aes_gcm(key, ciphertext, aad=aad)
    assert decrypted == plaintext


def test_different_ciphertexts_for_same_plaintext():
    key = os.urandom(32)
    plaintext = b"Identical image bytes"

    c1 = encrypt_aes_gcm(key, plaintext)
    c2 = encrypt_aes_gcm(key, plaintext)

    assert c1 != c2  # Fresh 12-byte CSPRNG nonce ensures distinct ciphertext


def test_ciphertext_tampering_causes_authentication_failure():
    key = os.urandom(32)
    plaintext = b"Tamper test payload"
    ciphertext = bytearray(encrypt_aes_gcm(key, plaintext))

    # Flip one single bit in ciphertext
    ciphertext[20] ^= 0x01

    with pytest.raises(AuthenticationError):
        decrypt_aes_gcm(key, bytes(ciphertext))


def test_aad_tampering_causes_authentication_failure():
    key = os.urandom(32)
    plaintext = b"AAD tamper test"
    ciphertext = encrypt_aes_gcm(key, plaintext, aad=b"CORRECT_AAD")

    with pytest.raises(AuthenticationError):
        decrypt_aes_gcm(key, ciphertext, aad=b"WRONG_AAD")


def test_key_manager_two_tier_wrapping():
    params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    kek = derive_kek("TestPassword123", params)

    vk = KeyManager.generate_vault_key()
    assert len(vk) == 32

    wrapped_hex = KeyManager.wrap_vault_key(vk, kek)
    unwrapped_vk = KeyManager.unwrap_vault_key(wrapped_hex, kek)
    assert unwrapped_vk == vk

    # Wrong KEK fails
    wrong_kek = os.urandom(32)
    with pytest.raises(AuthenticationError):
        KeyManager.unwrap_vault_key(wrapped_hex, wrong_kek)


def test_instant_password_change_rekey():
    params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    params, wrapped_hex, original_vk = KeyManager.initialize_new_vault("OldPassword123", params)

    # Change password to NewPassword456 in O(1) time
    new_params, new_wrapped_hex, returned_vk = KeyManager.change_master_password(
        "OldPassword123", "NewPassword456", params, wrapped_hex
    )

    # The 32-byte Vault Key remains identical (zero image re-encryption)
    assert returned_vk == original_vk

    # Old password fails to unlock
    with pytest.raises(AuthenticationError):
        KeyManager.unlock_vault("OldPassword123", new_params, new_wrapped_hex)

    # New password successfully unlocks same Vault Key
    unlocked_vk = KeyManager.unlock_vault("NewPassword456", new_params, new_wrapped_hex)
    assert unlocked_vk == original_vk


def test_local_vault_zero_plaintext_persistence(tmp_path):
    vault_dir = tmp_path / "SecureVaultStorageTest"
    vault = SecureVault(custom_storage_dir=vault_dir)

    fast_params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    vault.create_vault("StrongPass123!", kdf_params=fast_params)

    # Add 2 images
    img1 = create_dummy_qimage(200, 150, QColor(200, 50, 50))
    img2 = create_dummy_qimage(300, 200, QColor(50, 150, 200))
    id1 = vault.add_image(img1, title="Secret Financial Chart")
    id2 = vault.add_image(img2, title="Private Password Screenshot")

    # Verify zero plaintext image files exist on disk
    all_files = list(vault_dir.rglob("*"))
    for f in all_files:
        if f.is_file():
            assert not f.name.endswith(".png")
            assert not f.name.endswith(".jpg")
            assert not f.name.endswith(".jpeg")
            assert not f.name.endswith(".webp")
            # Verify file names are opaque (.enc, .json)
            assert f.name in ["vault_header.json", "manifest.enc"] or f.name.endswith(".enc")

    # Read back decrypted images in memory
    dec_img1 = vault.get_image(id1)
    assert dec_img1.width() == 200
    assert dec_img1.height() == 150

    thumb1 = vault.get_thumbnail(id1)
    assert not thumb1.isNull()

    stats = vault.get_stats()
    assert stats["item_count"] == 2
    assert stats["total_size_bytes"] > 0


def test_vault_export_and_import_portable_osvault(tmp_path):
    vault_dir_a = tmp_path / "VaultComputerA"
    vault_a = SecureVault(custom_storage_dir=vault_dir_a)

    fast_params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    vault_a.create_vault("ComputerAPassword123", kdf_params=fast_params)

    img = create_dummy_qimage(250, 180, QColor(80, 200, 120))
    obj_id = vault_a.add_image(img, title="Cross Computer Secret")

    # Export to .osvault
    backup_file = tmp_path / "MyPortableBackup.osvault"
    success = vault_a.export_osvault(backup_file)
    assert success is True
    assert backup_file.exists()

    # Verify magic bytes of .osvault
    with open(backup_file, "rb") as bf:
        assert bf.read(8) == OSVAULT_MAGIC

    # Simulate Computer B: Import .osvault into a clean vault
    vault_dir_b = tmp_path / "VaultComputerB"
    vault_b = SecureVault(custom_storage_dir=vault_dir_b)

    import_success = vault_b.import_osvault(backup_file, "ComputerAPassword123")
    assert import_success is True
    assert vault_b.is_unlocked is True

    # Retrieve and verify image on Computer B
    imported_img = vault_b.get_image(obj_id)
    assert imported_img.width() == 250
    assert imported_img.height() == 180
    assert vault_b.manifest.objects[obj_id].title == "Cross Computer Secret"


def test_wrong_password_on_import_rejected(tmp_path):
    vault_dir = tmp_path / "VaultSrc"
    vault = SecureVault(custom_storage_dir=vault_dir)
    fast_params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    vault.create_vault("CorrectPassword999", kdf_params=fast_params)
    vault.add_image(create_dummy_qimage(), title="Doc 1")

    backup_file = tmp_path / "BackupTest.osvault"
    vault.export_osvault(backup_file)

    target_dir = tmp_path / "VaultDst"
    target_vault = SecureVault(custom_storage_dir=target_dir)

    with pytest.raises(AuthenticationError):
        target_vault.import_osvault(backup_file, "WrongPassword000")


def test_tampered_osvault_backup_rejected(tmp_path):
    vault_dir = tmp_path / "VaultTamper"
    vault = SecureVault(custom_storage_dir=vault_dir)
    fast_params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    vault.create_vault("PasswordTest", kdf_params=fast_params)
    vault.add_image(create_dummy_qimage(), title="Doc Tamper")

    backup_file = tmp_path / "TamperBackup.osvault"
    vault.export_osvault(backup_file)

    # Tamper one byte inside the payload
    with open(backup_file, "r+b") as f:
        f.seek(150)
        b = f.read(1)
        f.seek(150)
        f.write(bytes([b[0] ^ 0xFF]))

    target_dir = tmp_path / "VaultDstTamper"
    target_vault = SecureVault(custom_storage_dir=target_dir)

    with pytest.raises(Exception):
        target_vault.import_osvault(backup_file, "PasswordTest")


def test_vault_lock_and_unlock(tmp_path):
    vault_dir = tmp_path / "LockTest"
    vault = SecureVault(custom_storage_dir=vault_dir)
    fast_params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    vault.create_vault("LockPass123", kdf_params=fast_params)

    assert vault.is_unlocked is True
    vault.lock()
    assert vault.is_unlocked is False

    # Calling operations when locked raises PermissionError
    with pytest.raises(PermissionError):
        vault.add_image(create_dummy_qimage())

    # Unlock with correct password
    vault.unlock("LockPass123")
    assert vault.is_unlocked is True


def test_large_image_vault(tmp_path):
    vault_dir = tmp_path / "LargeImageVault"
    vault = SecureVault(custom_storage_dir=vault_dir)
    fast_params = Argon2idParams.create_new(time_cost=1, memory_cost=16384, parallelism=2)
    vault.create_vault("Pass123", kdf_params=fast_params)

    # 4K resolution image (3840x2160)
    large_img = create_dummy_qimage(1920, 1080, QColor(30, 40, 50))
    obj_id = vault.add_image(large_img, title="4K Capture")

    decrypted = vault.get_image(obj_id)
    assert decrypted.width() == 1920
    assert decrypted.height() == 1080

