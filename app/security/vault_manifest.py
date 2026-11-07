"""Encrypted vault manifest containing metadata, object descriptors, and authenticated state."""

from dataclasses import asdict, dataclass, field
import json
import time
from typing import Any, Dict, List, Optional
import uuid

from app.security.encryption import decrypt_aes_gcm, encrypt_aes_gcm

MANIFEST_AAD = b"OSVAULT_MANIFEST_V1"


@dataclass
class VaultObject:
    """Descriptor for a single encrypted image object."""

    object_id: str
    title: str
    created_at: float
    width: int
    height: int
    encrypted_size: int
    thumbnail_encrypted_size: int
    sha256_ciphertext: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VaultObject":
        return cls(
            object_id=str(d.get("object_id", "")),
            title=str(d.get("title", "Untitled Image")),
            created_at=float(d.get("created_at", time.time())),
            width=int(d.get("width", 0)),
            height=int(d.get("height", 0)),
            encrypted_size=int(d.get("encrypted_size", 0)),
            thumbnail_encrypted_size=int(d.get("thumbnail_encrypted_size", 0)),
            sha256_ciphertext=str(d.get("sha256_ciphertext", "")),
        )


@dataclass
class VaultManifest:
    """Master encrypted manifest mapping opaque object IDs to encrypted metadata."""

    version: int = 1
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    objects: Dict[str, VaultObject] = field(default_factory=dict)

    def add_object(self, obj: VaultObject) -> None:
        self.objects[obj.object_id] = obj
        self.modified_at = time.time()

    def remove_object(self, object_id: str) -> Optional[VaultObject]:
        obj = self.objects.pop(object_id, None)
        if obj:
            self.modified_at = time.time()
        return obj

    def to_json(self) -> str:
        data = {
            "version": self.version,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "objects": {k: v.to_dict() for k, v in self.objects.items()},
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "VaultManifest":
        data = json.loads(json_str)
        manifest = cls(
            version=int(data.get("version", 1)),
            created_at=float(data.get("created_at", time.time())),
            modified_at=float(data.get("modified_at", time.time())),
        )
        objs = data.get("objects", {})
        for k, v in objs.items():
            manifest.objects[k] = VaultObject.from_dict(v)
        return manifest


def encrypt_manifest(manifest: VaultManifest, vault_key: bytes) -> bytes:
    """Encrypts the full manifest JSON with the Vault Key and AAD."""
    json_bytes = manifest.to_json().encode("utf-8")
    return encrypt_aes_gcm(vault_key, json_bytes, aad=MANIFEST_AAD)


def decrypt_manifest(payload: bytes, vault_key: bytes) -> VaultManifest:
    """Decrypts and authenticates the manifest with the Vault Key and AAD."""
    json_bytes = decrypt_aes_gcm(vault_key, payload, aad=MANIFEST_AAD)
    return VaultManifest.from_json(json_bytes.decode("utf-8"))

