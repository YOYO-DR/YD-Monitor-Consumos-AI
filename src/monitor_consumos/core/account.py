"""Una cuenta dada de alta en el monitor."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    """Identidad concreta dentro de un proveedor.

    Puede haber varias del mismo proveedor: dos cuentas de MiniMax son dos
    `Account` con el mismo `provider` y distinto `id`.
    """

    id: str
    provider: str
    label: str

    @staticmethod
    def new_id() -> str:
        # Corto pero sin colisiones realistas, y válido como nombre de fichero.
        return uuid.uuid4().hex[:12]

    def to_dict(self) -> dict:
        return {"id": self.id, "provider": self.provider, "label": self.label}

    @classmethod
    def from_dict(cls, raw: dict) -> "Account":
        return cls(id=raw["id"], provider=raw["provider"], label=raw.get("label", raw["id"]))
