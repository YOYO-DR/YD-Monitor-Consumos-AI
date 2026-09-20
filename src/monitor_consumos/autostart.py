"""Arranque automático con la sesión, vía el autostart de XDG.

Cualquier fichero `.desktop` dentro de `~/.config/autostart/` se lanza solo
al iniciar sesión: no hace falta root ni systemd, y lo respetan por igual
GNOME, KDE, XFCE y cualquier otro escritorio que cumpla la especificación
XDG. El estado (activado/desactivado) es justo si el fichero existe o no:
no se duplica en `settings.json`, para que no haya dos sitios que puedan
desincronizarse.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import config

#: `run.py` mete `src/` en `sys.path` él solo, así que lanzarlo directamente
#: funciona tanto si el paquete se instaló (`pip install -e .`) como si no.
_RUN_SCRIPT = Path(__file__).resolve().parents[2] / "run.py"

_ENTRY = """[Desktop Entry]
Type=Application
Name=Monitor de consumos
Comment=Widget de bandeja para vigilar el consumo de cuentas de IA
Exec="{python}" "{run_script}"
Icon=utilities-system-monitor
Terminal=false
X-GNOME-Autostart-enabled=true
"""


def is_enabled() -> bool:
    return config.AUTOSTART_FILE.exists()


def enable() -> None:
    config.AUTOSTART_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = _ENTRY.format(python=sys.executable, run_script=_RUN_SCRIPT)
    config.AUTOSTART_FILE.write_text(content, encoding="utf-8")
    config.AUTOSTART_FILE.chmod(0o700)


def disable() -> None:
    config.AUTOSTART_FILE.unlink(missing_ok=True)
