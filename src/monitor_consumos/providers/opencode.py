"""OpenCode Zen (el plan de pago "Go" de opencode.ai).

A diferencia de MiniMax y Claude, aquí no hay ni endpoint JSON ni API key de
autoservicio: el consumo solo se ve en la página web de tu workspace, y el
dato llega **embebido en el HTML** que sirve el propio servidor (no en una
petición aparte). Verificado contra la red real (2026-09-06): al pedir
`https://opencode.ai/workspace/<id>/go` con la cookie de sesión, el HTML trae
un bloque de estado inicial con, entre otras cosas:

    rollingUsage: { status: "ok", resetInSec: 18000, usagePercent: 0, ... }
    weeklyUsage:  { status: "ok", resetInSec: 62160, usagePercent: 96.4, ... }
    monthlyUsage: { status: "rate-limited", resetInSec: 1501288, usagePercent: 100, ... }

Como no es JSON (el script mezcla esas claves con variables `$R[n]` propias
del framework de la web), en vez de `response.json()` se busca cada bloque
`nombreVentana: { ... }` por su clave y se extraen `usagePercent` /
`resetInSec` con regex. Es más frágil que un contrato JSON: si opencode.ai
cambia el nombre de estas claves o cómo serializa el estado, esto deja de
funcionar y hay que volver a inspeccionar la página con las devtools.

No sabemos cuál cookie exacta hace falta (la web no expone una API con
API key para esto), así que se guardan todas las del dominio `opencode.ai`.

Tampoco hay una ruta "/workspace" genérica que redirija al workspace por
defecto (responde 404): el id de workspace solo aparece en la URL a la que
aterriza el propio login, así que se captura ahí, no se "descubre" después.
"""

from __future__ import annotations

import re
import time

import httpx

from .. import config
from ..core.models import AuthRequired, FetchFailed, Quota, UsageSnapshot
from ..core.provider import Provider

#: clave del bloque embebido en el HTML -> etiqueta visible.
_WINDOWS = (
    ("rollingUsage", "5 horas"),
    ("weeklyUsage", "Semanal"),
    ("monthlyUsage", "Mensual"),
)

_WORKSPACE_ID_RE = re.compile(r"/workspace/(wrk_[A-Za-z0-9]+)")


def _extract_block(html: str, key: str) -> str | None:
    """Aísla el objeto `{...}` que sigue a `key:`, contando llaves.

    No es JSON: hay que recorrer carácter a carácter para saber dónde
    cierra, en vez de asumir un formato con el que `json.loads` pueda.
    """
    marker_index = html.find(f"{key}:")
    if marker_index == -1:
        return None
    start = html.find("{", marker_index)
    if start == -1:
        return None

    depth = 0
    for index in range(start, len(html)):
        char = html[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return html[start : index + 1]
    return None


def _extract_number(block: str, field: str) -> float | None:
    match = re.search(rf"{field}:\s*(-?[\d.]+)", block)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


class OpenCodeProvider(Provider):
    key = "opencode"
    display_name = "OpenCode Zen"
    login_url = "https://opencode.ai/auth"

    def __init__(self, credential: dict) -> None:
        self._cookies = credential.get("cookies")
        self._workspace_id = credential.get("workspace_id")
        if not self._cookies or not self._workspace_id:
            raise AuthRequired("La credencial de OpenCode no contiene cookies de sesión o workspace.")

    @classmethod
    def extract_credential(cls, cookies: list[dict], url: str = "") -> dict:
        # opencode.ai deja cookies de sesión (anónima) nada más cargar la
        # pantalla de login, antes de autenticarse: no bastan por sí solas,
        # o el login se daría por completado al instante sin haber entrado
        # de verdad. Solo lo aceptamos cuando el navegador ya aterrizó en un
        # workspace real (fin del login), no mientras sigue en /auth.
        #
        # Además, no existe una ruta genérica "/workspace" que redirija al
        # workspace por defecto (un GET ahí devuelve 404): el id solo
        # aparece en la URL a la que aterriza el propio login, así que lo
        # capturamos aquí en vez de intentar "descubrirlo" después.
        match = _WORKSPACE_ID_RE.search(url)
        if match is None:
            raise AuthRequired("Todavía no has terminado de iniciar sesión en OpenCode.")
        workspace_id = match.group(1)

        # No hay una única cookie de sesión documentada (a diferencia del
        # `_token` de MiniMax): guardamos todas las del dominio para no tener
        # que adivinar cuál es la que importa.
        session_cookies = {
            cookie["name"]: cookie["value"]
            for cookie in cookies
            if isinstance(cookie, dict)
            and cookie.get("name")
            and cookie.get("value")
            and str(cookie.get("domain", "")).endswith("opencode.ai")
        }
        if not session_cookies:
            raise AuthRequired(
                "El login terminó pero no encontré ninguna cookie de opencode.ai. "
                "¿Se completó la sesión?"
            )
        return {"cookies": session_cookies, "workspace_id": workspace_id}

    def _get(self, url: str) -> httpx.Response:
        try:
            response = httpx.get(
                url,
                cookies=self._cookies,
                headers={"accept": "text/html"},
                timeout=config.REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except httpx.RequestError as exc:
            raise FetchFailed(f"No se pudo contactar con OpenCode: {exc}") from exc

        # Sesión muerta: la web redirige a /auth en vez de servir el workspace.
        if "/auth" in str(response.url) or response.status_code in (401, 403):
            raise AuthRequired("OpenCode redirigió al login: la sesión ya no vale.")
        if response.status_code >= 400:
            raise FetchFailed(f"OpenCode devolvió HTTP {response.status_code}.")
        return response

    def fetch(self) -> UsageSnapshot:
        go_response = self._get(f"https://opencode.ai/workspace/{self._workspace_id}/go")
        return UsageSnapshot(provider=self.key, quotas=self._build_quotas(go_response.text))

    def _build_quotas(self, html: str) -> tuple[Quota, ...]:
        quotas: list[Quota] = []
        for key, label in _WINDOWS:
            block = _extract_block(html, key)
            if block is None:
                continue

            percent = _extract_number(block, "usagePercent")
            if percent is None:
                continue

            reset_in_sec = _extract_number(block, "resetInSec")
            resets_at = time.time() + reset_in_sec if reset_in_sec and reset_in_sec > 0 else None
            quotas.append(Quota(label=label, used_percent=percent, resets_at=resets_at))

        if not quotas:
            raise FetchFailed(
                "OpenCode no devolvió ninguna ventana de consumo reconocible "
                "(¿cambió el formato de la página?)."
            )
        return tuple(quotas)
