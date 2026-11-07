"""Key Derivation Function (Argon2id) for Master Password KEK derivation."""

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


@dataclass
class Argon2idParams:
    """Configurable KDF parameters stored in the public vault header."""

    algorithm: str = "Argon2id"
    version: int = 1
    salt_hex: str = ""
    time_cost: int = 3
    memory_cost: int = 65536  # 64 MiB
    parallelism: int = 4
    key_length: int = 32  # 256 bits

    @classmethod
    def create_new(
        cls,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
    ) -> "Argon2idParams":
        salt = os.urandom(16)
        return cls(
            algorithm="Argon2id",
            version=1,
            salt_hex=salt.hex(),
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            key_length=32,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Argon2idParams":
        return cls(
            algorithm=str(data.get("algorithm", "Argon2id")),
            version=int(data.get("version", 1)),
            salt_hex=str(data.get("salt_hex", "")),
            time_cost=int(data.get("time_cost", 3)),
            memory_cost=int(data.get("memory_cost", 65536)),
            parallelism=int(data.get("parallelism", 4)),
            key_length=int(data.get("key_length", 32)),
        )


def derive_kek(password: str, params: Argon2idParams) -> bytes:
    """
    Derives a 256-bit Key Encryption Key (KEK) from the Master Password using Argon2id.
    """
    if not password:
        raise ValueError("Password cannot be empty.")
    if not params.salt_hex:
        raise ValueError("KDF Salt is missing.")

    salt = bytes.fromhex(params.salt_hex)
    kdf = Argon2id(
        salt=salt,
        length=params.key_length,
        iterations=params.time_cost,
        lanes=params.parallelism,
        memory_cost=params.memory_cost,
        ad=None,
        secret=None,
    )
    return kdf.derive(password.encode("utf-8"))

