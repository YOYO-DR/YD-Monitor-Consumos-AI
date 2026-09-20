"""Claude (claude.ai / Claude Code).

No hay endpoint público de consumo distinto del que usa el propio Claude
Code para avisar de los límites de plan. Y a diferencia de MiniMax, no hace
falta ningún login por navegador: Claude Code ya deja una sesión OAuth en
disco la primera vez que se ejecuta `claude`, y reutilizamos esa.

Verificado contra la red real (2026-09-06), usando la sesión ya guardada en
`~/.claude/.credentials.json`:
  - GET https://api.anthropic.com/api/oauth/usage con
    `Authorization: Bearer <accessToken>`, `User-Agent: claude-code/<versión>`
    (sin esta cabecera responde 429, no sirve los datos) y
    `anthropic-beta: oauth-2025-04-20`.
  - La respuesta trae `limits`: una lista de ventanas activas, cada una con
    `kind` (p. ej. "session", "weekly_all"), `percent` (0-100) y `resets_at`
    (ISO 8601 con offset).
  - También trae gasto en dólares (`spend`, `extra_usage`) del "extra usage"
    opcional de los planes Max: no se muestra, es una unidad distinta ($, no
    % de cuota).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import httpx

from .. import config
from ..core.models import AuthRequired, FetchFailed, Quota, UsageSnapshot
from ..core.provider import Provider

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"

#: Versión que Claude Code manda en su User-Agent. Sin esta cabecera (o con
#: una demasiado vieja) el endpoint responde 429 en vez de servir los datos.
#: Si algún día deja de funcionar, lo primero a comprobar es si hace falta
#: subir este número.
_USER_AGENT = "claude-code/2.1.263"

_LABELS = {
    "session": "5 horas",
    "weekly_all": "Semanal",
}


def _parse_resets_at(raw: object) -> float | None:
    """ISO 8601 con offset -> epoch en segundos. None ante cualquier cosa rara."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


class ClaudeProvider(Provider):
    key = "claude"
    display_name = "Claude"
    login_url = "https://claude.ai"
    login_mode = "local"

    def __init__(self, credential: dict) -> None:
        self._token = credential.get("token")
        if not self._token:
            raise AuthRequired("La credencial de Claude no contiene el token de sesión.")

    @classmethod
    def read_local_credential(cls) -> dict:
        """Lee la sesión que ya dejó `claude` en disco. No abre navegador."""
        try:
            raw = CREDENTIALS_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise AuthRequired(
                f"No encontré {CREDENTIALS_PATH}. Ejecuta `claude` e inicia sesión primero."
            ) from None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise AuthRequired("El fichero de credenciales de Claude Code está corrupto.") from None

        oauth = data.get("claudeAiOauth")
        if not isinstance(oauth, dict) or not oauth.get("accessToken"):
            raise AuthRequired("El fichero de credenciales de Claude Code no tiene un token válido.")

        expires_at_ms = oauth.get("expiresAt")
        return {
            "token": oauth["accessToken"],
            "expires_at": expires_at_ms / 1000 if isinstance(expires_at_ms, (int, float)) else 0,
        }

    @classmethod
    def extract_credential(cls, cookies: list[dict], url: str = "") -> dict:
        # Claude no hace login por navegador (login_mode = "local"): esto no
        # debería llamarse nunca, pero el contrato de Provider lo exige.
        raise AuthRequired("Claude no usa login por navegador: ejecuta `claude` para iniciar sesión.")

    def fetch(self) -> UsageSnapshot:
        try:
            response = httpx.get(
                USAGE_URL,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "User-Agent": _USER_AGENT,
                    "anthropic-beta": "oauth-2025-04-20",
                    "accept": "application/json",
                },
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
        except httpx.RequestError as exc:
            raise FetchFailed(f"No se pudo contactar con Claude: {exc}") from exc

        if response.status_code in (401, 403):
            raise AuthRequired("Claude rechazó la sesión guardada.")
        if response.status_code >= 400:
            raise FetchFailed(f"Claude devolvió HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise FetchFailed("Claude devolvió una respuesta que no es JSON.") from exc

        return UsageSnapshot(provider=self.key, quotas=self._build_quotas(payload))

    def _build_quotas(self, payload: dict) -> tuple[Quota, ...]:
        limits = payload.get("limits")
        if not isinstance(limits, list) or not limits:
            raise FetchFailed("Claude no devolvió ninguna ventana de consumo.")

        quotas: list[Quota] = []
        for limit in limits:
            if not isinstance(limit, dict):
                continue

            percent = limit.get("percent")
            if not isinstance(percent, (int, float)):
                continue

            kind = limit.get("kind") or limit.get("group") or "?"
            label = _LABELS.get(kind, str(kind).replace("_", " ").title())
            quotas.append(
                Quota(
                    label=label,
                    used_percent=float(percent),
                    resets_at=_parse_resets_at(limit.get("resets_at")),
                )
            )

        if not quotas:
            raise FetchFailed("Claude no devolvió ninguna ventana de consumo con datos válidos.")
        return tuple(quotas)
