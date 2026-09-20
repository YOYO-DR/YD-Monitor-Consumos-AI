"""Preferencias de la interfaz, guardadas entre arranques."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from . import config


@dataclass
class Settings:
    #: Si el panel vive clavado en el escritorio en vez de desplegarse y cerrarse.
    pinned: bool = False
    #: Última posición del panel anclado, para reabrirlo donde lo dejaste.
    position: tuple[int, int] | None = None
    #: Cada cuántos segundos se relee el consumo.
    poll_interval: int = config.DEFAULT_POLL_INTERVAL_SECONDS

    def clamped_interval(self) -> int:
        """El intervalo, encajado en los límites que la app admite.

        Se valida al leer, no solo al escribir: el fichero es editable a mano y
        un 0 ahí dentro convertiría el widget en un bucle de peticiones.
        """
        return max(
            config.MIN_POLL_INTERVAL_SECONDS,
            min(config.MAX_POLL_INTERVAL_SECONDS, int(self.poll_interval)),
        )


def load() -> Settings:
    try:
        raw = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return Settings()

    if not isinstance(raw, dict):
        return Settings()

    defaults = Settings()
    position = raw.get("position")
    return Settings(
        pinned=bool(raw.get("pinned", defaults.pinned)),
        position=tuple(position) if isinstance(position, (list, tuple)) and len(position) == 2 else None,
        poll_interval=raw.get("poll_interval", defaults.poll_interval),
    )


def save(settings: Settings) -> None:
    config.ensure_dirs()
    tmp = config.SETTINGS_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(asdict(settings), fh, indent=2)
    os.replace(tmp, config.SETTINGS_FILE)
