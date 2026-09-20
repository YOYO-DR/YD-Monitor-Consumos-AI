"""Contrato que debe cumplir cada cuenta de IA monitorizada."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import UsageSnapshot


class Provider(ABC):
    """Un servicio de IA cuyo consumo sabemos leer.

    Cada proveedor decide cómo se autentica y cómo traduce su respuesta
    a `UsageSnapshot`. La UI no sabe nada de MiniMax ni de cookies.
    """

    #: Identificador estable, usado como clave en disco y en el registro.
    key: str
    #: Nombre visible en la interfaz.
    display_name: str
    #: URL donde el usuario inicia sesión.
    login_url: str
    #: "browser" (por defecto): login interactivo con Playwright, ver
    #: `extract_credential`. "local": no hay navegador, la credencial ya
    #: existe en disco porque otra aplicación (p. ej. Claude Code) la dejó
    #: ahí; ver `read_local_credential`.
    login_mode: str = "browser"

    @abstractmethod
    def fetch(self) -> UsageSnapshot:
        """Devuelve el consumo actual.

        Lanza `AuthRequired` si la credencial no sirve, `FetchFailed` si el
        fallo es transitorio.
        """

    @classmethod
    @abstractmethod
    def extract_credential(cls, cookies: list[dict], url: str = "") -> dict:
        """Reduce las cookies del navegador tras el login a lo mínimo que hay que guardar.

        Se llama en bucle mientras el usuario todavía está tecleando en el
        navegador, así que debe lanzar `AuthRequired` mientras el login no
        haya terminado de verdad, no solo cuando falten cookies: algunos
        proveedores (OpenCode) ya sueltan cookies de sesión anónima nada más
        cargar la página de login, antes de autenticarse. `url` es la página
        en la que está el navegador en ese instante; sirve para exigir, por
        ejemplo, que ya no estemos en la pantalla de login.

        Es de clase a propósito: el login ocurre antes de que exista ninguna
        credencial, así que no puede haber instancia todavía. Solo se llama
        para proveedores con `login_mode == "browser"`.

        Lanza `AuthRequired` si el login no ha terminado o no dejó lo que hacía falta.
        """

    @classmethod
    def read_local_credential(cls) -> dict:
        """Lee una credencial que ya existe en disco, sin abrir navegador.

        Solo la implementan proveedores con `login_mode == "local"`.
        """
        raise NotImplementedError(f"{cls.__name__} no soporta login local.")
