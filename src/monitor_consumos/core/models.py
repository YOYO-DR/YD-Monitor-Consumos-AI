"""Modelos de dominio, agnósticos del proveedor."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """Franja de consumo. La UI mapea esto a color."""

    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"

    @classmethod
    def from_percent(cls, percent: float) -> "Severity":
        if percent >= 90:
            return cls.CRITICAL
        if percent >= 70:
            return cls.WARN
        return cls.OK


@dataclass(frozen=True)
class Quota:
    """Una ventana de consumo concreta (p. ej. '5 horas' o 'semanal')."""

    label: str
    used_percent: float
    resets_at: float | None = None
    """Epoch en segundos en que la ventana se reinicia. None si no aplica."""

    @property
    def severity(self) -> Severity:
        return Severity.from_percent(self.used_percent)

    @property
    def seconds_to_reset(self) -> float | None:
        if self.resets_at is None:
            return None
        return max(0.0, self.resets_at - time.time())


@dataclass(frozen=True)
class UsageSnapshot:
    """Lectura completa de un proveedor en un instante dado."""

    provider: str
    quotas: tuple[Quota, ...]
    fetched_at: float = field(default_factory=time.time)

    @property
    def peak_percent(self) -> float:
        """El consumo más alto entre todas las ventanas: lo que manda en el icono."""
        return max((q.used_percent for q in self.quotas), default=0.0)

    @property
    def severity(self) -> Severity:
        return Severity.from_percent(self.peak_percent)


class AuthRequired(Exception):
    """La credencial guardada falta, caducó o fue rechazada: hay que volver a iniciar sesión."""


class FetchFailed(Exception):
    """Fallo transitorio (red, 5xx). Merece reintento, no un nuevo login."""
