"""Registro de proveedores disponibles.

Para añadir una cuenta nueva: implementa `Provider` en un módulo de este
paquete y añádelo aquí.
"""

from __future__ import annotations

from ..core.provider import Provider
from .claude import ClaudeProvider
from .minimax import MiniMaxProvider
from .opencode import OpenCodeProvider

#: key -> clase. El orden fija el de la interfaz.
REGISTRY: dict[str, type[Provider]] = {
    MiniMaxProvider.key: MiniMaxProvider,
    ClaudeProvider.key: ClaudeProvider,
    OpenCodeProvider.key: OpenCodeProvider,
}


def get(key: str) -> type[Provider]:
    try:
        return REGISTRY[key]
    except KeyError:
        raise KeyError(f"Proveedor desconocido: {key!r}. Disponibles: {sorted(REGISTRY)}") from None


__all__ = ["REGISTRY", "get", "ClaudeProvider", "MiniMaxProvider", "OpenCodeProvider", "Provider"]
