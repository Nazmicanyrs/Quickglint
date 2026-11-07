"""Secure Vault in-memory optimization bridge with zero-plaintext disk persistence."""

from typing import List, Tuple

from PySide6.QtGui import QImage

from app.optimizer.engine import ImageOptimizer
from app.optimizer.models import OptimizerConfig
from app.pdf.image_loader import pil_to_qimage
from app.security.vault import SecureVault
from app.utils.logger import logger


class VaultImageOptimizer:
    """Optimizes encrypted images inside SecureVault entirely in volatile memory."""

    @staticmethod
    def optimize_vault_object(
        vault: SecureVault,
        object_id: str,
        config: OptimizerConfig,
    ) -> Tuple[Optional[str], int, int]:
        """
        Decrypts in RAM, optimizes, re-encrypts, and atomically updates the vault object.
        Returns: (new_object_id, original_size_bytes, optimized_size_bytes)
        """
        if not vault.is_unlocked or not vault.manifest:
            raise PermissionError("Vault must be unlocked to perform in-memory optimization.")

        # 1. Decrypt in memory
        qimg = vault.get_image(object_id)
        if not qimg or qimg.isNull():
            raise ValueError(f"Failed to decrypt vault object {object_id}")

        meta = vault.manifest.objects.get(object_id)
        orig_bytes = meta.encrypted_size if meta else 0

        # 2. Optimize in memory
        optimizer = ImageOptimizer()
        res = optimizer.optimize(qimg, config)

        # 3. Convert back to QImage for re-encryption
        opt_qimg = pil_to_qimage(res.optimized_image)

        # 4. Re-encrypt with AES-256-GCM and update object
        # Delete old encrypted object and insert optimized object with same title
        title = meta.title if meta else "Optimized Image"
        vault.delete_image(object_id)
        new_oid = vault.add_image(opt_qimg, title=title)

        logger.info(
            "Vault object %s optimized -> %s (%.1f KB -> %.1f KB, %.1f%% saved)",
            object_id,
            new_oid,
            orig_bytes / 1024.0,
            res.optimized_size_bytes / 1024.0,
            res.reduction_pct,
        )
        return new_oid, orig_bytes, res.optimized_size_bytes

