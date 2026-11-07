"""In-memory metadata cleaner for AES-256-GCM Secure Vault objects."""

import io
from typing import Optional, Tuple
from PySide6.QtGui import QImage
from PIL import Image

from app.metacleaner.cleaner import MetadataCleaner
from app.metacleaner.models import CleanConfig, CleanResult
from app.utils.logger import logger


class VaultMetadataCleaner:
    """Performs RAM-only metadata stripping on decrypted Secure Vault objects without plaintext disk leaks."""

    @classmethod
    def clean_vault_object(
        cls,
        vault,
        object_id: str,
        config: Optional[CleanConfig] = None,
        replace_in_vault: bool = True,
    ) -> Tuple[Optional[str], CleanResult]:
        """Decrypts in memory, cleans metadata in RAM, and replaces or creates vault object."""
        cfg = config or CleanConfig()

        if not vault.is_unlocked:
            res = CleanResult(success=False, error_msg="Güvenli Kasa kilitli. Lütfen önce kasanın kilidini açın.")
            return None, res

        try:
            # 1. Authenticated in-memory decryption
            qimg: Optional[QImage] = vault.get_image(object_id)
            if not qimg or qimg.isNull():
                res = CleanResult(success=False, error_msg="Görsel kasadan çözülemedi.")
                return None, res

            meta = vault.manifest.objects.get(object_id) if (vault.manifest and hasattr(vault.manifest, "objects")) else None
            title = meta.title if meta else "vault_image"

            # 2. Convert QImage to PIL via in-memory PNG buffer
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            qba = QByteArray()
            buf = QBuffer(qba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            qimg.save(buf, "PNG")
            img_bytes = bytes(qba.data())

            # 3. Clean in memory
            cleaned_bytes, clean_res = MetadataCleaner.clean_bytes(img_bytes, config=cfg, target_format="PNG")

            if not clean_res.success:
                return None, clean_res

            # 4. Load cleaned QImage from RAM
            cleaned_qimg = QImage()
            cleaned_qimg.loadFromData(cleaned_bytes, "PNG")

            # 5. Atomic vault update/insertion
            if replace_in_vault:
                vault.delete_image(object_id)
                new_oid = vault.add_image(cleaned_qimg, title=title)
            else:
                new_oid = vault.add_image(cleaned_qimg, title=f"{title}_clean")

            clean_res.output_bytes = cleaned_bytes
            return new_oid, clean_res
        except Exception as exc:
            logger.error("Failed to clean metadata in vault: %s", exc)
            return None, CleanResult(success=False, error_msg=str(exc))

