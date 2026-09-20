"""Sondeo periódico del consumo de todas las cuentas, fuera del hilo de la UI.

La petición de red nunca debe correr en el hilo de la interfaz: bloquearía el
repintado y las animaciones darían tirones.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from ..auth import accounts as accounts_registry
from ..auth import store
from ..core.models import AuthRequired, FetchFailed, UsageSnapshot
from ..providers import get as get_provider


class _FetchWorker(QObject):
    """Lee todas las cuentas, una tras otra. Vive en un QThread aparte."""

    succeeded = Signal(str, UsageSnapshot)
    auth_required = Signal(str, str)
    failed = Signal(str, str)
    finished = Signal()

    def fetch_all(self) -> None:
        try:
            for account in accounts_registry.list_accounts():
                self._fetch_one(account.id, account.provider)
        finally:
            # Pase lo que pase, el ciclo se cierra: si no, el guardia de
            # concurrencia se quedaría atascado y no habría más lecturas.
            self.finished.emit()

    def _fetch_one(self, account_id: str, provider_key: str) -> None:
        try:
            credential = store.load(account_id)
            snapshot = get_provider(provider_key)(credential).fetch()
        except AuthRequired as exc:
            self.auth_required.emit(account_id, str(exc))
        except FetchFailed as exc:
            self.failed.emit(account_id, str(exc))
        except Exception as exc:  # el hilo no puede morir por un fallo inesperado
            self.failed.emit(account_id, f"Error inesperado: {exc}")
        else:
            self.succeeded.emit(account_id, snapshot)


class UsagePoller(QObject):
    """Relee el consumo de todas las cuentas cada `interval` segundos."""

    updated = Signal(str, UsageSnapshot)
    auth_required = Signal(str, str)
    failed = Signal(str, str)
    cycle_finished = Signal()

    def __init__(self, interval_seconds: int, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._thread = QThread()
        self._worker = _FetchWorker()
        self._worker.moveToThread(self._thread)

        self._worker.succeeded.connect(self.updated)
        self._worker.auth_required.connect(self.auth_required)
        self._worker.failed.connect(self.failed)
        self._worker.finished.connect(self._on_cycle_finished)

        # Mientras haya un ciclo en vuelo no lanzamos otro: si la red va lenta,
        # encadenar timers acabaría acumulando peticiones.
        self._busy = False

        self._timer = QTimer(self)
        self._timer.setInterval(max(1, interval_seconds) * 1000)
        self._timer.timeout.connect(self.refresh)

        self._thread.start()

    def _on_cycle_finished(self) -> None:
        self._busy = False
        self.cycle_finished.emit()

    def set_interval(self, seconds: int) -> None:
        self._timer.setInterval(max(1, seconds) * 1000)

    def start(self) -> None:
        self._timer.start()
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()

    def refresh(self) -> None:
        """Fuerza una lectura ya, sin esperar al siguiente tick."""
        if self._busy:
            return
        self._busy = True
        # El trabajo se encola en el hilo del worker, no en el de la interfaz.
        QTimer.singleShot(0, self._worker, self._worker.fetch_all)

    def shutdown(self) -> None:
        self._timer.stop()
        self._thread.quit()
        self._thread.wait(3000)
