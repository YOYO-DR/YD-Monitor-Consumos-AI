"""Persistencia de credenciales en disco, solo legibles por el usuario.

Una credencial por cuenta: dos cuentas del mismo proveedor tienen ficheros
distintos y sesiones independientes.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .. import config
from ..core.models import AuthRequired


def _path_for(account_id: str) -> Path:
    return config.CREDENTIALS_DIR / f"{account_id}.json"


def save(account_id: str, credential: dict) -> None:
    """Guarda la credencial con permisos 0600.

    Escribimos en un temporal y renombramos para que un fallo a media
    escritura no deje un fichero corrupto en su lugar.
    """
    config.ensure_dirs()
    path = _path_for(account_id)
    tmp = path.with_suffix(".tmp")

    # Creamos ya con 0600: nunca existe un instante en que sea legible por otros.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(credential, fh)
    os.replace(tmp, path)


def load(account_id: str) -> dict:
    """Devuelve la credencial guardada.

    Lanza `AuthRequired` si no existe, está corrupta o ya caducó.
    """
    path = _path_for(account_id)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise AuthRequired("No hay sesión guardada.") from None

    try:
        credential = json.loads(raw)
    except json.JSONDecodeError:
        raise AuthRequired("La sesión guardada está corrupta.") from None

    if not isinstance(credential, dict):
        raise AuthRequired("La sesión guardada no tiene el formato esperado.")

    expires_at = credential.get("expires_at")
    if isinstance(expires_at, (int, float)) and expires_at > 0:
        if time.time() >= expires_at - config.CREDENTIAL_EXPIRY_MARGIN_SECONDS:
            raise AuthRequired("La sesión ha caducado.")

    return credential


def clear(account_id: str) -> None:
    _path_for(account_id).unlink(missing_ok=True)


def exists(account_id: str) -> bool:
    return _path_for(account_id).exists()
