"""Rutas y ajustes de la aplicación."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "monitor-consumos"

#: Respetamos XDG; en su ausencia, el estándar de facto en Linux.
_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

CONFIG_DIR = _CONFIG_HOME / APP_NAME
CREDENTIALS_DIR = CONFIG_DIR / "credentials"

#: Índice de cuentas dadas de alta. No guarda secretos, solo id/proveedor/nombre.
ACCOUNTS_FILE = CONFIG_DIR / "accounts.json"

#: Preferencias de la interfaz (anclado, intervalo, posición).
SETTINGS_FILE = CONFIG_DIR / "settings.json"

#: Un perfil de navegador POR CUENTA. Compartirlo haría que el segundo login
#: reutilizara la sesión del primero y acabarías con la misma cuenta dos veces.
BROWSER_PROFILES_DIR = CONFIG_DIR / "browser-profiles"

#: Autoarranque de la sesión (XDG): cualquier .desktop aquí se lanza solo al
#: iniciar sesión. Vive fuera de CONFIG_DIR porque XDG_CONFIG_HOME/autostart
#: es una carpeta compartida por todas las apps, no solo por esta.
AUTOSTART_DIR = _CONFIG_HOME / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / f"{APP_NAME}.desktop"

#: Cada cuánto se relee el consumo, por defecto. La web usa 5s; 30s sobra para
#: un widget y evita machacar el endpoint todo el día. Ajustable desde la UI.
DEFAULT_POLL_INTERVAL_SECONDS = 30

#: Límites de lo que la interfaz permite elegir.
MIN_POLL_INTERVAL_SECONDS = 5
MAX_POLL_INTERVAL_SECONDS = 3600

#: Tiempo máximo de espera de una petición de consumo.
REQUEST_TIMEOUT_SECONDS = 15

#: Margen antes de la caducidad a partir del cual ya pedimos login de nuevo.
CREDENTIAL_EXPIRY_MARGIN_SECONDS = 60 * 60


def ensure_dirs() -> None:
    """Crea el árbol de configuración con permisos restrictivos."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    BROWSER_PROFILES_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)


def browser_profile_for(account_id: str) -> Path:
    """Directorio de perfil del navegador de una cuenta concreta."""
    return BROWSER_PROFILES_DIR / account_id
