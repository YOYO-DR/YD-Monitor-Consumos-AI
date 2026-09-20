"""MiniMax.

No hay endpoint público de consumo: reutilizamos el que usa la propia consola
web, `/backend/account/token_plan/remains_percent`.

Verificado contra la red real:
  - La única credencial necesaria es la cookie `_token` (JWT, HttpOnly) del
    dominio platform.minimax.io. Dura unos 40 días.
  - La cabecera `x-group-id` que manda la web NO es obligatoria: la respuesta
    es 200 igual sin ella.
  - Sin cookie responde 200 con `base_resp.status_code = 1016` ("invalid api
    key"), no con un 401. Por eso hay que mirar el cuerpo, no solo el estado.
"""

from __future__ import annotations

import httpx

from .. import config
from ..core.models import AuthRequired, FetchFailed, Quota, UsageSnapshot
from ..core.provider import Provider

USAGE_URL = "https://platform.minimax.io/backend/account/token_plan/remains_percent"

#: Códigos de `base_resp.status_code` que significan "tu sesión no vale".
_AUTH_ERROR_CODES = {1004, 1016, 1008}

#: `current_interval_status`/`current_weekly_status` == 3 en modelos sin plan
#: contratado. Sus porcentajes son siempre 0 y solo ensucian la vista.
_STATUS_INACTIVE = 3


def _parse_percent(raw: object) -> float:
    """'38%' -> 38.0. Devuelve 0.0 ante cualquier cosa inesperada."""
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return 0.0
    try:
        return float(raw.strip().rstrip("%"))
    except ValueError:
        return 0.0


def _parse_epoch_ms(raw: object) -> float | None:
    """La API da milisegundos; el resto de la app trabaja en segundos."""
    if not isinstance(raw, (int, float)) or raw <= 0:
        return None
    return float(raw) / 1000.0


class MiniMaxProvider(Provider):
    key = "minimax"
    display_name = "MiniMax"
    login_url = "https://platform.minimax.io/login"

    def __init__(self, credential: dict) -> None:
        self._token = credential.get("token")
        if not self._token:
            raise AuthRequired("La credencial de MiniMax no contiene el token de sesión.")

    @classmethod
    def extract_credential(cls, cookies: list[dict], url: str = "") -> dict:
        # La URL no hace falta aquí: la cookie `_token` ya solo aparece
        # después de un login real, así que es señal suficiente por sí sola.
        for cookie in cookies:
            if cookie.get("name") == "_token" and cookie.get("domain") == "platform.minimax.io":
                return {
                    "token": cookie["value"],
                    # Playwright usa -1 para cookies de sesión (sin caducidad).
                    "expires_at": cookie.get("expires") or 0,
                }
        raise AuthRequired(
            "El login terminó pero no apareció la cookie `_token`. ¿Se completó la sesión?"
        )

    def fetch(self) -> UsageSnapshot:
        try:
            response = httpx.get(
                USAGE_URL,
                cookies={"_token": self._token},
                headers={"accept": "application/json"},
                timeout=config.REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise FetchFailed(f"No se pudo contactar con MiniMax: {exc}") from exc

        # Un redirect al login también significa sesión muerta.
        if response.status_code in (301, 302, 303, 307, 308):
            raise AuthRequired("MiniMax redirigió al login: la sesión ya no vale.")
        if response.status_code in (401, 403):
            raise AuthRequired("MiniMax rechazó la sesión guardada.")
        if response.status_code >= 400:
            raise FetchFailed(f"MiniMax devolvió HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise FetchFailed("MiniMax devolvió una respuesta que no es JSON.") from exc

        status_code = payload.get("base_resp", {}).get("status_code", 0)
        if status_code in _AUTH_ERROR_CODES:
            message = payload.get("base_resp", {}).get("status_msg", "sesión inválida")
            raise AuthRequired(f"MiniMax rechazó la sesión: {message}.")
        if status_code:
            message = payload.get("base_resp", {}).get("status_msg", "error desconocido")
            raise FetchFailed(f"MiniMax devolvió el error {status_code}: {message}.")

        return UsageSnapshot(provider=self.key, quotas=self._build_quotas(payload))

    def _build_quotas(self, payload: dict) -> tuple[Quota, ...]:
        models = payload.get("model_remains") or []
        if not models:
            raise FetchFailed("MiniMax no devolvió ningún dato de consumo.")

        quotas: list[Quota] = []
        for model in models:
            if not isinstance(model, dict):
                continue

            name = model.get("model_name", "?")
            is_general = name == "general"

            # Del plan general queremos las dos ventanas siempre. Del resto,
            # solo si el modelo está activo: si no, son ceros constantes.
            if not is_general and model.get("current_interval_status") == _STATUS_INACTIVE:
                continue

            prefix = "" if is_general else f"{name} · "
            quotas.append(
                Quota(
                    label=f"{prefix}5 horas",
                    used_percent=_parse_percent(model.get("current_interval_used_percent")),
                    resets_at=_parse_epoch_ms(model.get("end_time")),
                )
            )
            quotas.append(
                Quota(
                    label=f"{prefix}Semanal",
                    used_percent=_parse_percent(model.get("current_weekly_used_percent")),
                    resets_at=_parse_epoch_ms(model.get("weekly_end_time")),
                )
            )

        if not quotas:
            raise FetchFailed("MiniMax no devolvió ninguna ventana de consumo activa.")
        return tuple(quotas)
