"""Login interactivo: abre un navegador real y espera a que el usuario entre.

Playwright solo se usa aquí. Una vez extraída la credencial, el refresco
periódico va por httpx puro, sin navegador.

Esperamos a que aparezca la credencial, no a que la URL sea una concreta: el
login de MiniMax pasa por un OAuth con varios saltos y el destino final cambia
según la cuenta. La cookie es la señal de éxito de verdad.

Sobre la detección de automatización: Google rechaza el OAuth ("es posible que
el navegador o la aplicación no sean seguros") cuando detecta un navegador
pilotado. Por eso lanzamos el Chrome del sistema, no el Chromium de prueba de
Playwright, y le quitamos los delatores de automatización. Aun así, el camino
que nunca falla es entrar por email en vez de por Google: ese no pasa por su
detector.
"""

from __future__ import annotations

import time
from pathlib import Path

from .. import config
from ..core.models import AuthRequired
from ..core.provider import Provider

#: Margen para que el usuario escriba correo, contraseña y el código de verificación.
LOGIN_TIMEOUT_SECONDS = 5 * 60
#: Cada cuánto miramos si ya hay credencial.
POLL_SECONDS = 1.0

#: `--enable-automation` pone la barra de "software automatizado" y activa las
#: señales que mira Google; `AutomationControlled` es lo que deja
#: `navigator.webdriver` en true, el delator más usado.
_STEALTH_ARGS = ["--disable-blink-features=AutomationControlled", "--no-first-run"]
_STEALTH_IGNORE = ["--enable-automation"]

#: Canales a probar por orden. `None` es el Chromium que trae Playwright: es el
#: más fácil de detectar, así que va el último.
_CHANNELS = ["chrome", "chromium", None]


def _launch_context(pw, channel: str | None, profile_dir: Path):
    """Abre un contexto persistente con el canal indicado."""
    config.ensure_dirs()
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel=channel,
        headless=False,
        args=_STEALTH_ARGS,
        ignore_default_args=_STEALTH_IGNORE,
        viewport=None,
    )


def _open_browser(pw, profile_dir: Path):
    """Devuelve un contexto usando el mejor navegador disponible.

    Preferimos el Chrome instalado en el sistema: es un navegador de verdad,
    con su historial y sus extensiones, y pasa los controles que tumban al
    Chromium de pruebas.
    """
    errors: list[str] = []
    for channel in _CHANNELS:
        try:
            return _launch_context(pw, channel, profile_dir)
        except Exception as exc:  # canal no instalado o perfil bloqueado
            errors.append(f"{channel or 'chromium incluido'}: {exc}")

    raise AuthRequired(
        "No se pudo abrir ningún navegador para el login.\n" + "\n".join(errors)
    )


def run_login(provider: type[Provider], profile_dir: Path) -> dict:
    """Abre el navegador, espera al login y devuelve la credencial a guardar.

    `profile_dir` es propio de cada cuenta: compartirlo haría que el login de
    la segunda cuenta reutilizara la sesión de la primera.

    Bloquea hasta que el usuario termina. Debe llamarse fuera del hilo de la UI.
    """
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise AuthRequired(
            "Falta Playwright. Instálalo con: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        context = _open_browser(pw, profile_dir)
        try:
            # Un contexto persistente ya viene con una pestaña abierta.
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(provider.login_url)

            deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                try:
                    current_url = page.url
                except PlaywrightError:
                    current_url = ""

                try:
                    return provider.extract_credential(context.cookies(), current_url)
                except AuthRequired:
                    pass  # todavía no ha terminado de entrar

                if not context.pages:
                    raise AuthRequired("Cerraste el navegador antes de completar el login.")

                try:
                    page.wait_for_timeout(POLL_SECONDS * 1000)
                except PlaywrightError:
                    raise AuthRequired("Se cerró el navegador durante el login.") from None

            raise AuthRequired("Se agotó el tiempo de espera del login (5 min) sin completarlo.")
        finally:
            # El navegador ya puede estar cerrado por el usuario: no dejamos que
            # eso tape el error real.
            try:
                context.close()
            except PlaywrightError:
                pass
