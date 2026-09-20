#!/usr/bin/env python3
"""Comprobaciones de la lógica que puede romperse en silencio.

Ejecutar: .venv/bin/python test_monitor.py

Sin framework: solo asserts. Lo que se prueba es el parseo de la respuesta de
MiniMax (capturada de la red real), el guardado de credenciales y el formateo.
La interfaz se prueba mirándola.
"""

import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from monitor_consumos import config
from monitor_consumos.core.models import AuthRequired, FetchFailed, Quota, Severity, UsageSnapshot
from monitor_consumos.providers.claude import ClaudeProvider, _parse_resets_at
from monitor_consumos.providers.minimax import MiniMaxProvider, _parse_epoch_ms, _parse_percent
from monitor_consumos.providers.opencode import OpenCodeProvider

# Respuesta literal de platform.minimax.io capturada de la red el 2026-07-29.
REAL_RESPONSE = {
    "model_remains": [
        {
            "model_name": "general",
            "start_time": 1785319200000,
            "end_time": 1785337200000,
            "current_interval_used_percent": "1%",
            "current_interval_status": 1,
            "weekly_start_time": 1785110400000,
            "weekly_end_time": 1785715200000,
            "current_weekly_used_percent": "38%",
            "current_weekly_status": 1,
        },
        {
            "model_name": "video",
            "start_time": 1785283200000,
            "end_time": 1785369600000,
            "current_interval_used_percent": "0%",
            "current_interval_status": 3,
            "weekly_start_time": 1785110400000,
            "weekly_end_time": 1785715200000,
            "current_weekly_used_percent": "0%",
            "current_weekly_status": 3,
        },
    ],
    "base_resp": {"status_code": 0, "status_msg": "success"},
}


def test_percent_parsing():
    assert _parse_percent("38%") == 38.0
    assert _parse_percent("1%") == 1.0
    assert _parse_percent("100%") == 100.0
    assert _parse_percent(42) == 42.0
    # Nunca debe reventar: un porcentaje ilegible cuenta como 0, no como fallo.
    assert _parse_percent(None) == 0.0
    assert _parse_percent("basura") == 0.0
    print("ok  parseo de porcentajes")


def test_epoch_parsing():
    assert _parse_epoch_ms(1785337200000) == 1785337200.0
    assert _parse_epoch_ms(0) is None
    assert _parse_epoch_ms(None) is None
    print("ok  parseo de marcas de tiempo")


def test_real_response():
    provider = MiniMaxProvider({"token": "falso"})
    quotas = provider._build_quotas(REAL_RESPONSE)

    # El modelo 'video' tiene status 3 (sin plan): debe quedar fuera.
    assert len(quotas) == 2, f"esperaba 2 ventanas, salieron {len(quotas)}: {[q.label for q in quotas]}"

    five_hour, weekly = quotas
    assert five_hour.label == "5 horas"
    assert five_hour.used_percent == 1.0
    assert five_hour.resets_at == 1785337200.0
    assert weekly.label == "Semanal"
    assert weekly.used_percent == 38.0
    print("ok  respuesta real de MiniMax")


def test_auth_errors():
    provider = MiniMaxProvider({"token": "falso"})

    # Sin token no se puede ni construir.
    try:
        MiniMaxProvider({})
    except AuthRequired:
        pass
    else:
        raise AssertionError("una credencial sin token debería lanzar AuthRequired")

    # El login que no deja la cookie `_token` es un fallo de auth, no un éxito.
    try:
        MiniMaxProvider.extract_credential([{"name": "_ga", "domain": ".minimax.io", "value": "x"}])
    except AuthRequired:
        pass
    else:
        raise AssertionError("sin cookie _token debería lanzar AuthRequired")

    cookie = {"name": "_token", "domain": "platform.minimax.io", "value": "jwt", "expires": 123.0}
    assert MiniMaxProvider.extract_credential([cookie]) == {"token": "jwt", "expires_at": 123.0}
    print("ok  errores de autenticación")


# Respuesta literal (con valores de ejemplo) de api.anthropic.com/api/oauth/usage
# capturada de la red el 2026-09-06.
CLAUDE_RESPONSE = {
    "five_hour": {"utilization": 33.0, "resets_at": "2026-09-06T10:20:00.314860+00:00"},
    "seven_day": {"utilization": 54.0, "resets_at": "2026-09-08T21:00:00.314885+00:00"},
    "seven_day_sonnet": None,
    "limits": [
        {"kind": "session", "group": "session", "percent": 33, "resets_at": "2026-09-06T10:20:00.314860+00:00"},
        {"kind": "weekly_all", "group": "weekly", "percent": 54, "resets_at": "2026-09-08T21:00:00.314885+00:00"},
    ],
    "spend": {"used": {"amount_minor": 253, "currency": "USD"}, "percent": 12},
}


def test_claude_resets_at_parsing():
    assert _parse_resets_at("2026-09-06T10:20:00.314860+00:00") == datetime.fromisoformat(
        "2026-09-06T10:20:00.314860+00:00"
    ).timestamp()
    assert _parse_resets_at(None) is None
    assert _parse_resets_at("no es una fecha") is None
    print("ok  parseo de resets_at de Claude")


def test_claude_real_response():
    provider = ClaudeProvider({"token": "falso"})
    quotas = provider._build_quotas(CLAUDE_RESPONSE)

    assert len(quotas) == 2, f"esperaba 2 ventanas, salieron {len(quotas)}: {[q.label for q in quotas]}"
    sesion, semanal = quotas
    assert sesion.label == "5 horas"
    assert sesion.used_percent == 33.0
    assert semanal.label == "Semanal"
    assert semanal.used_percent == 54.0
    print("ok  respuesta real de Claude")


def test_claude_auth_errors():
    try:
        ClaudeProvider({})
    except AuthRequired:
        pass
    else:
        raise AssertionError("una credencial sin token debería lanzar AuthRequired")

    # Claude no hace login por navegador: extract_credential siempre falla.
    try:
        ClaudeProvider.extract_credential([])
    except AuthRequired:
        pass
    else:
        raise AssertionError("extract_credential de Claude debería lanzar AuthRequired siempre")
    print("ok  errores de autenticación de Claude")


def test_claude_read_local_credential():
    from monitor_consumos.providers import claude as claude_module

    original_path = claude_module.CREDENTIALS_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fake_path = Path(tmp) / "credentials.json"
            claude_module.CREDENTIALS_PATH = fake_path

            # Sin fichero: hay que decirle al usuario que use `claude` primero.
            try:
                ClaudeProvider.read_local_credential()
            except AuthRequired:
                pass
            else:
                raise AssertionError("sin fichero de credenciales debería lanzar AuthRequired")

            fake_path.write_text(
                json.dumps({"claudeAiOauth": {"accessToken": "abc", "expiresAt": 1788681602838}}),
                encoding="utf-8",
            )
            credential = ClaudeProvider.read_local_credential()
            assert credential == {"token": "abc", "expires_at": 1788681602838 / 1000}
            print("ok  lectura de credencial local de Claude")
    finally:
        claude_module.CREDENTIALS_PATH = original_path


# Fragmento real (con nombres de variable `$R[n]` propios del framework de la
# web) capturado del HTML de opencode.ai/workspace/<id>/go el 2026-09-06.
OPENCODE_HTML_FIXTURE = """
<script>
$R[28]($R[18], $R[33] = {
    mine: true,
    useBalance: false,
    allowTraining: true,
    region: $R[34] = ["us","eu","sg","cn"],
    rollingUsage: $R[35] = {
        status: "ok",
        resetInSec: 18000,
        usagePercent: 0,
        usage: 0,
        limit: 1200000000
    },
    weeklyUsage: $R[36] = {
        status: "ok",
        resetInSec: 62160,
        usagePercent: 96.4,
        usage: 2893032524,
        limit: 3000000000
    },
    monthlyUsage: $R[37] = {
        status: "rate-limited",
        resetInSec: 1501288,
        usagePercent: 100,
        usage: 6000199664,
        limit: 6000000000
    }
});
</script>
"""


def test_opencode_real_response():
    provider = OpenCodeProvider({"cookies": {"session": "falso"}, "workspace_id": "wrk_123"})
    quotas = provider._build_quotas(OPENCODE_HTML_FIXTURE)

    assert len(quotas) == 3, f"esperaba 3 ventanas, salieron {len(quotas)}: {[q.label for q in quotas]}"
    rolling, weekly, monthly = quotas
    assert rolling.label == "5 horas"
    assert rolling.used_percent == 0.0
    assert weekly.label == "Semanal"
    assert weekly.used_percent == 96.4
    assert monthly.label == "Mensual"
    assert monthly.used_percent == 100.0
    # resetInSec es relativo: comprobamos que se traduce a un instante futuro.
    assert weekly.resets_at > time.time()
    print("ok  respuesta real de OpenCode Zen")


def test_opencode_missing_usage_raises():
    provider = OpenCodeProvider({"cookies": {"session": "falso"}, "workspace_id": "wrk_123"})
    try:
        provider._build_quotas("<html>sin datos de consumo</html>")
    except FetchFailed:
        pass
    else:
        raise AssertionError("HTML sin bloques de uso debería lanzar FetchFailed")
    print("ok  OpenCode sin datos de consumo reconocibles")


def test_opencode_auth_errors():
    try:
        OpenCodeProvider({})
    except AuthRequired:
        pass
    else:
        raise AssertionError("una credencial sin cookies debería lanzar AuthRequired")

    cookies = [
        {"name": "session", "domain": "opencode.ai", "value": "abc"},
        {"name": "csrf", "domain": ".opencode.ai", "value": "def"},
        {"name": "_ga", "domain": ".google-analytics.com", "value": "ignorada"},
    ]

    # opencode.ai ya deja cookies de sesión (anónima) nada más cargar /auth,
    # antes de que el usuario haya entrado: no basta con tener cookies si
    # seguimos en la pantalla de login. Este es justo el bug que causaba que
    # el login se diera por completado al instante.
    try:
        OpenCodeProvider.extract_credential(cookies, "https://opencode.ai/auth")
    except AuthRequired:
        pass
    else:
        raise AssertionError("con cookies pero todavía en /auth debería lanzar AuthRequired")

    try:
        OpenCodeProvider.extract_credential([], "https://opencode.ai/workspace/wrk_123")
    except AuthRequired:
        pass
    else:
        raise AssertionError("sin cookies de opencode.ai debería lanzar AuthRequired")

    assert OpenCodeProvider.extract_credential(cookies, "https://opencode.ai/workspace/wrk_123") == {
        "cookies": {"session": "abc", "csrf": "def"},
        "workspace_id": "wrk_123",
    }
    print("ok  errores de autenticación de OpenCode")


def test_severity():
    assert Severity.from_percent(0) is Severity.OK
    assert Severity.from_percent(69.9) is Severity.OK
    assert Severity.from_percent(70) is Severity.WARN
    assert Severity.from_percent(89.9) is Severity.WARN
    assert Severity.from_percent(90) is Severity.CRITICAL
    assert Severity.from_percent(100) is Severity.CRITICAL

    # El icono debe reflejar la ventana más cargada, no la primera.
    snapshot = UsageSnapshot(
        provider="minimax",
        quotas=(Quota("5 horas", 4.0), Quota("Semanal", 93.0)),
    )
    assert snapshot.peak_percent == 93.0
    assert snapshot.severity is Severity.CRITICAL
    print("ok  franjas de severidad")


def test_credential_store(monkeypatched_dir):
    from monitor_consumos.auth import store

    store.save("prueba", {"token": "secreto", "expires_at": time.time() + 86400})
    assert store.exists("prueba")
    assert store.load("prueba")["token"] == "secreto"

    # La credencial es un secreto: nadie más que el usuario puede leerla.
    mode = (monkeypatched_dir / "credentials" / "prueba.json").stat().st_mode & 0o777
    assert mode == 0o600, f"permisos {oct(mode)}, esperaba 0o600"

    # Una credencial ya caducada debe pedir login, no devolverse como válida.
    store.save("caducada", {"token": "x", "expires_at": time.time() - 10})
    try:
        store.load("caducada")
    except AuthRequired:
        pass
    else:
        raise AssertionError("una credencial caducada debería lanzar AuthRequired")

    try:
        store.load("inexistente")
    except AuthRequired:
        pass
    else:
        raise AssertionError("una credencial ausente debería lanzar AuthRequired")

    store.clear("prueba")
    assert not store.exists("prueba")
    print("ok  almacén de credenciales")


def test_duration_format():
    from monitor_consumos.ui.panel import format_duration

    assert format_duration(45) == "45s"
    assert format_duration(90) == "1m"
    assert format_duration(3600) == "1h 0m"
    assert format_duration(3735) == "1h 2m"
    assert format_duration(90000) == "1d 1h"
    assert format_duration(-5) == "0s"
    print("ok  formato de duraciones")


def test_accounts():
    from monitor_consumos.auth import accounts

    assert accounts.list_accounts() == []

    uno = accounts.add("minimax", "MiniMax personal")
    dos = accounts.add("minimax", "MiniMax trabajo")

    # Dos cuentas del mismo proveedor deben ser independientes.
    assert uno.id != dos.id
    assert uno.provider == dos.provider == "minimax"
    assert len(accounts.list_accounts()) == 2

    # Y perfiles de navegador distintos: si compartieran uno, el segundo login
    # reutilizaría la sesión del primero.
    assert config.browser_profile_for(uno.id) != config.browser_profile_for(dos.id)

    accounts.rename(uno.id, "Renombrada")
    assert accounts.get(uno.id).label == "Renombrada"

    # Un nombre en blanco no debe dejar la cuenta sin etiqueta.
    accounts.rename(uno.id, "   ")
    assert accounts.get(uno.id).label == uno.id

    accounts.remove(uno.id)
    assert accounts.get(uno.id) is None
    assert [a.id for a in accounts.list_accounts()] == [dos.id]
    print("ok  alta y baja de cuentas")


def test_account_removal_clears_credential():
    from monitor_consumos.auth import accounts, store

    cuenta = accounts.add("minimax", "Temporal")
    store.save(cuenta.id, {"token": "secreto", "expires_at": time.time() + 86400})
    assert store.exists(cuenta.id)

    accounts.remove(cuenta.id)
    # Borrar la cuenta no puede dejar su credencial olvidada en disco.
    assert not store.exists(cuenta.id)
    print("ok  borrar cuenta arrastra su credencial")


def test_legacy_migration():
    from monitor_consumos.auth import accounts, store

    # Formato viejo: credencial por proveedor, sin índice de cuentas.
    config.ACCOUNTS_FILE.unlink(missing_ok=True)
    store.save("minimax", {"token": "antiguo", "expires_at": time.time() + 86400})

    migradas = accounts.list_accounts()
    assert len(migradas) == 1, f"esperaba 1 cuenta migrada, salieron {len(migradas)}"
    assert migradas[0].id == "minimax", "el id debe conservarse o la sesión se perdería"
    assert migradas[0].provider == "minimax"
    # La credencial que ya existía tiene que seguir siendo válida tras migrar.
    assert store.load(migradas[0].id)["token"] == "antiguo"
    print("ok  migración del formato antiguo")


def test_settings():
    from monitor_consumos import settings as settings_module

    assert settings_module.load().poll_interval == config.DEFAULT_POLL_INTERVAL_SECONDS

    guardado = settings_module.Settings(pinned=True, position=(120, 340), poll_interval=15)
    settings_module.save(guardado)

    leido = settings_module.load()
    assert leido.pinned is True
    assert leido.position == (120, 340)
    assert leido.poll_interval == 15

    # El fichero es editable a mano: un intervalo absurdo no puede convertir
    # el widget en un bucle de peticiones.
    assert settings_module.Settings(poll_interval=0).clamped_interval() == config.MIN_POLL_INTERVAL_SECONDS
    assert settings_module.Settings(poll_interval=999999).clamped_interval() == config.MAX_POLL_INTERVAL_SECONDS

    config.SETTINGS_FILE.write_text("{no es json", encoding="utf-8")
    # Un fichero corrupto debe caer a los valores por defecto, no reventar.
    assert settings_module.load().poll_interval == config.DEFAULT_POLL_INTERVAL_SECONDS
    print("ok  preferencias")


def test_autostart():
    from monitor_consumos import autostart

    assert autostart.is_enabled() is False

    autostart.enable()
    assert autostart.is_enabled() is True
    assert config.AUTOSTART_FILE.read_text(encoding="utf-8").startswith("[Desktop Entry]")

    # Repetir enable() no debe fallar ni duplicar nada: se sobrescribe.
    autostart.enable()
    assert autostart.is_enabled() is True

    autostart.disable()
    assert autostart.is_enabled() is False

    # Desactivar sin haber activado antes no debe reventar.
    autostart.disable()
    print("ok  autoarranque")


def _point_config_at(root: Path) -> None:
    config.CONFIG_DIR = root
    config.CREDENTIALS_DIR = root / "credentials"
    config.BROWSER_PROFILES_DIR = root / "browser-profiles"
    config.ACCOUNTS_FILE = root / "accounts.json"
    config.SETTINGS_FILE = root / "settings.json"
    config.AUTOSTART_DIR = root / "autostart"
    config.AUTOSTART_FILE = config.AUTOSTART_DIR / "monitor-consumos.desktop"


def main():
    test_percent_parsing()
    test_epoch_parsing()
    test_real_response()
    test_auth_errors()
    test_claude_resets_at_parsing()
    test_claude_real_response()
    test_claude_auth_errors()
    test_claude_read_local_credential()
    test_opencode_real_response()
    test_opencode_missing_usage_raises()
    test_opencode_auth_errors()
    test_severity()
    test_duration_format()

    # Cada bloque que toca disco estrena directorio: así el orden de los tests
    # no puede cambiar el resultado.
    for prueba in (
        test_credential_store,
        test_accounts,
        test_account_removal_clears_credential,
        test_legacy_migration,
        test_settings,
        test_autostart,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _point_config_at(root)
            if prueba is test_credential_store:
                prueba(root)
            else:
                prueba()

    print("\ntodo correcto")


if __name__ == "__main__":
    main()
