"""Alta, baja y listado de cuentas.

El índice de cuentas (`accounts.json`) no contiene secretos: solo id, proveedor
y nombre visible. Las credenciales viven aparte, en `store`, una por cuenta.
"""

from __future__ import annotations

import json
import os
import shutil

from .. import config
from ..core.account import Account
from . import store


def _write_index(accounts: list[Account]) -> None:
    config.ensure_dirs()
    payload = [account.to_dict() for account in accounts]

    tmp = config.ACCOUNTS_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, config.ACCOUNTS_FILE)


def _read_index() -> list[Account]:
    try:
        raw = json.loads(config.ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        # Un índice corrupto no debe dejar la app inservible: se parte de cero.
        return []

    accounts = []
    for entry in raw if isinstance(raw, list) else []:
        try:
            accounts.append(Account.from_dict(entry))
        except (KeyError, TypeError):
            continue  # entrada suelta ilegible: la saltamos
    return accounts


def _migrate_legacy() -> list[Account]:
    """Convierte el formato viejo (una credencial por proveedor) en una cuenta.

    Antes la credencial se guardaba como `credentials/minimax.json`, sin
    concepto de cuenta. Conservamos ese id para no tener que mover el fichero:
    la sesión que ya tuvieras sigue valiendo.
    """
    from ..providers import REGISTRY

    migrated = [
        Account(id=key, provider=key, label=cls.display_name)
        for key, cls in REGISTRY.items()
        if store.exists(key)
    ]
    if not migrated:
        return []

    _write_index(migrated)

    # El perfil del navegador era único; ahora hay uno por cuenta. Lo movemos a
    # la cuenta migrada para no perder la sesión con Google o GitHub que ya
    # estuviera guardada ahí.
    legacy_profile = config.CONFIG_DIR / "browser-profile"
    if legacy_profile.is_dir():
        destination = config.browser_profile_for(migrated[0].id)
        if not destination.exists():
            config.ensure_dirs()
            try:
                legacy_profile.rename(destination)
            except OSError:
                pass  # perfil en uso o sin permisos: se rehará en el próximo login

    return migrated


def list_accounts() -> list[Account]:
    accounts = _read_index()
    if not accounts and not config.ACCOUNTS_FILE.exists():
        accounts = _migrate_legacy()
    return accounts


def get(account_id: str) -> Account | None:
    return next((a for a in list_accounts() if a.id == account_id), None)


def add(provider: str, label: str) -> Account:
    """Da de alta una cuenta. Todavía sin credencial: eso lo hace el login."""
    accounts = list_accounts()
    account = Account(id=Account.new_id(), provider=provider, label=label.strip() or provider)
    accounts.append(account)
    _write_index(accounts)
    return account


def rename(account_id: str, label: str) -> None:
    accounts = list_accounts()
    for index, account in enumerate(accounts):
        if account.id == account_id:
            accounts[index] = Account(account.id, account.provider, label.strip() or account.id)
            _write_index(accounts)
            return


def remove(account_id: str) -> None:
    """Borra la cuenta y todo su rastro: credencial y perfil de navegador."""
    _write_index([a for a in list_accounts() if a.id != account_id])
    store.clear(account_id)
    shutil.rmtree(config.browser_profile_for(account_id), ignore_errors=True)
