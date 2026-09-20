"""Login interactivo lanzado desde la interfaz sin congelarla.

Playwright abre un navegador y bloquea varios minutos esperando al usuario, así
que va en su propio hilo. Su API síncrona funciona en cualquier hilo mientras no
haya un bucle asyncio corriendo, y Qt no usa asyncio.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .. import config
from ..auth import accounts as accounts_registry
from ..auth import store
from ..auth.browser_login import run_login
from ..core.models import AuthRequired
from ..providers import get as get_provider


class _LoginWorker(QObject):
    succeeded = Signal(str)
    failed = Signal(str, str)

    def run(self, account_id: str) -> None:
        try:
            account = accounts_registry.get(account_id)
            if account is None:
                raise AuthRequired("La cuenta ya no existe.")

            # El login trabaja con la clase, no con una instancia: todavía no
            # hay credencial con la que construir el proveedor.
            provider_cls = get_provider(account.provider)
            if provider_cls.login_mode == "local":
                # Sin navegador: la credencial ya la dejó otra aplicación en disco.
                credential = provider_cls.read_local_credential()
            else:
                credential = run_login(provider_cls, config.browser_profile_for(account_id))
            store.save(account_id, credential)
        except AuthRequired as exc:
            self.failed.emit(account_id, str(exc))
        except Exception as exc:
            self.failed.emit(account_id, f"El login falló: {exc}")
        else:
            self.succeeded.emit(account_id)


class LoginController(QObject):
    """Lanza logins en segundo plano y avisa del resultado."""

    succeeded = Signal(str)
    failed = Signal(str, str)
    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = _LoginWorker()
        self._worker.moveToThread(self._thread)

        self._running = False
        self._worker.succeeded.connect(self._finish)
        self._worker.failed.connect(self._finish)
        self._worker.succeeded.connect(self.succeeded)
        self._worker.failed.connect(self.failed)

        self._thread.start()

    @property
    def busy(self) -> bool:
        return self._running

    def _finish(self, *_: object) -> None:
        self._running = False
        self.busy_changed.emit(False)

    def start(self, account_id: str) -> bool:
        """Arranca el login de una cuenta. Devuelve False si ya había uno en curso."""
        # Dos navegadores de login a la vez solo confundirían al usuario, y
        # además competirían por el mismo perfil si fuese la misma cuenta.
        if self._running:
            return False
        self._running = True
        self.busy_changed.emit(True)
        QTimer.singleShot(0, self._worker, lambda: self._worker.run(account_id))
        return True

    def shutdown(self) -> None:
        self._thread.quit()
        self._thread.wait(3000)
