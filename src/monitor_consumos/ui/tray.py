"""Icono de bandeja y orquestación de la aplicación."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import settings as settings_module
from ..auth import accounts as accounts_registry
from ..core.models import Severity, UsageSnapshot
from ..services.login import LoginController
from ..services.poller import UsagePoller
from . import theme
from .manager import ManagerWindow
from .panel import UsagePanel

#: Lado del icono en px. 64 se reescala limpio a los tamaños que pida el sistema.
ICON_SIZE = 64
ICON_THICKNESS = 9


def render_icon(percent: float | None, severity: Severity) -> QIcon:
    """Dibuja el icono: un anillo con el consumo más alto de todas las cuentas."""
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    inset = ICON_THICKNESS / 2 + 3
    rect = QRectF(0, 0, ICON_SIZE, ICON_SIZE).adjusted(inset, inset, -inset, -inset)

    # Pista tenue: sin datos, el icono sigue siendo legible como "anillo vacío".
    track = QPen(QColor(255, 255, 255, 60), ICON_THICKNESS)
    track.setCapStyle(Qt.RoundCap)
    painter.setPen(track)
    painter.drawEllipse(rect)

    if percent is not None and percent > 0:
        arc = QPen(theme.color_for(severity), ICON_THICKNESS)
        arc.setCapStyle(Qt.RoundCap)
        painter.setPen(arc)
        painter.drawArc(rect, 90 * 16, int(-(min(percent, 100) / 100.0) * 360 * 16))

    painter.end()

    icon = QIcon(pixmap)
    # Sin esto, algunas bandejas lo repintan en monocromo y se pierde el color.
    icon.setIsMask(False)
    return icon


class TrayApp(QObject):
    """Une el sondeo, el login y la interfaz."""

    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._settings = settings_module.load()
        self._snapshots: dict[str, UsageSnapshot] = {}
        #: Cuentas ya avisadas de sesión caducada, para no repetir la notificación
        #: en cada ciclo de sondeo.
        self._notified: set[str] = set()

        self._panel = UsagePanel()
        self._manager: ManagerWindow | None = None
        self._tray = QSystemTrayIcon(render_icon(None, Severity.OK))
        self._tray.setToolTip("Monitor de consumos")

        self._poller = UsagePoller(self._settings.clamped_interval(), self)
        self._login = LoginController(self)

        self._wire()
        self._tray.setContextMenu(self._build_menu())
        self._tray.show()

    # -- Cableado -----------------------------------------------------------

    def _wire(self) -> None:
        self._tray.activated.connect(self._on_tray_activated)
        # Sin esto, el clic en la notificación cae al vacío y el escritorio
        # relanza el `.desktop` en lugar de abrir el login de la cuenta.
        self._tray.messageClicked.connect(self._on_notification_clicked)

        self._poller.updated.connect(self._on_updated)
        self._poller.auth_required.connect(self._on_auth_required)
        self._poller.failed.connect(self._on_failed)

        self._login.succeeded.connect(self._on_login_succeeded)
        self._login.failed.connect(self._on_login_failed)

        self._panel.login_requested.connect(self._start_login)
        self._panel.refresh_requested.connect(self._poller.refresh)
        self._panel.manage_requested.connect(self.open_manager)
        self._panel.pin_toggled.connect(self._set_pinned)
        self._panel.moved.connect(self._on_panel_moved)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        menu.setStyleSheet(theme.PANEL_STYLESHEET)

        # Imprescindible en GNOME: la extensión AppIndicator mapea el clic
        # izquierdo al menú, así que `activated` no llega a dispararse y sin
        # esta entrada no habría forma de abrir el panel.
        show = QAction("Ver consumo", menu)
        show.triggered.connect(self._toggle_panel)
        menu.addAction(show)

        manage = QAction("Cuentas…", menu)
        manage.triggered.connect(self.open_manager)
        menu.addAction(manage)

        menu.addSeparator()

        refresh = QAction("Actualizar ahora", menu)
        refresh.triggered.connect(self._poller.refresh)
        menu.addAction(refresh)

        self._pin_action = QAction("Anclar al escritorio", menu)
        self._pin_action.setCheckable(True)
        self._pin_action.setChecked(self._settings.pinned)
        self._pin_action.triggered.connect(self._set_pinned)
        menu.addAction(self._pin_action)

        menu.addSeparator()

        quit_action = QAction("Salir", menu)
        quit_action.triggered.connect(self.quit_requested)
        menu.addAction(quit_action)

        return menu

    # -- Arranque -----------------------------------------------------------

    def start(self) -> None:
        accounts = accounts_registry.list_accounts()
        self._panel.sync_accounts(accounts)

        if not accounts:
            # Sin cuentas no hay nada que sondear: al administrador directamente.
            self.open_manager()
            return

        self._panel.set_pinned(self._settings.pinned)
        if self._settings.pinned:
            self._panel.show_pinned_at(self._settings.position)

        self._poller.start()

    # -- Cuentas ------------------------------------------------------------

    def open_manager(self) -> None:
        if self._manager is None:
            self._manager = ManagerWindow(self._settings)
            self._manager.login_requested.connect(self._start_login)
            self._manager.accounts_changed.connect(self._on_accounts_changed)
            self._manager.settings_changed.connect(self._on_settings_changed)

        self._manager.sync_from_settings(self._settings)
        self._manager.reload()
        self._manager.show()
        self._manager.raise_()
        self._manager.activateWindow()

    def _on_accounts_changed(self) -> None:
        accounts = accounts_registry.list_accounts()
        known = {account.id for account in accounts}

        # Nos olvidamos de lo que sabíamos de cuentas ya borradas.
        self._snapshots = {k: v for k, v in self._snapshots.items() if k in known}
        self._notified &= known

        self._panel.sync_accounts(accounts)
        self._refresh_icon()

        if accounts:
            self._poller.start()
        else:
            self._poller.stop()

    def _on_settings_changed(self) -> None:
        previous_pinned = self._settings.pinned
        self._settings = settings_module.load()

        self._poller.set_interval(self._settings.clamped_interval())
        if self._settings.pinned != previous_pinned:
            self._apply_pinned(self._settings.pinned)

    # -- Anclado ------------------------------------------------------------

    def _set_pinned(self, pinned: bool) -> None:
        self._settings.pinned = pinned
        settings_module.save(self._settings)
        self._apply_pinned(pinned)
        if self._manager is not None:
            self._manager.sync_from_settings(self._settings)

    def _apply_pinned(self, pinned: bool) -> None:
        self._pin_action.setChecked(pinned)
        self._panel.set_pinned(pinned)
        if pinned:
            self._panel.show_pinned_at(self._settings.position)
        else:
            self._panel.hide()

    def _on_panel_moved(self, x: int, y: int) -> None:
        self._settings.position = (x, y)
        settings_module.save(self._settings)

    # -- Reacciones del sondeo ----------------------------------------------

    def _on_updated(self, account_id: str, snapshot: UsageSnapshot) -> None:
        self._snapshots[account_id] = snapshot
        self._notified.discard(account_id)
        self._panel.show_snapshot(account_id, snapshot)
        self._refresh_icon()

    def _on_auth_required(self, account_id: str, reason: str) -> None:
        self._snapshots.pop(account_id, None)
        self._panel.show_auth_required(account_id, reason)
        self._refresh_icon()

        # Una notificación por cuenta, no una por ciclo de sondeo.
        if account_id in self._notified:
            return
        self._notified.add(account_id)

        account = accounts_registry.get(account_id)
        name = account.label if account else account_id
        self._tray.showMessage(
            "Monitor de consumos",
            f"«{name}» necesita que inicies sesión de nuevo.",
            QSystemTrayIcon.Warning,
            5000,
        )

    def _on_failed(self, account_id: str, message: str) -> None:
        # El sondeo sigue: los fallos de red suelen ser pasajeros.
        self._panel.show_error(account_id, message)

    def _refresh_icon(self) -> None:
        """El icono refleja la cuenta y ventana más cargadas de todas."""
        if not self._snapshots:
            self._tray.setIcon(render_icon(None, Severity.OK))
            self._tray.setToolTip("Monitor de consumos · sin datos")
            return

        peak = max(snapshot.peak_percent for snapshot in self._snapshots.values())
        self._tray.setIcon(render_icon(peak, Severity.from_percent(peak)))

        lines = []
        for account_id, snapshot in self._snapshots.items():
            account = accounts_registry.get(account_id)
            name = account.label if account else account_id
            detail = " · ".join(f"{q.label}: {q.used_percent:g}%" for q in snapshot.quotas)
            lines.append(f"{name} — {detail}")
        self._tray.setToolTip("\n".join(lines))

    # -- Login --------------------------------------------------------------

    def _on_notification_clicked(self) -> None:
        """Una cuenta pidió re-login: arranca su login o, si no sabemos cuál, abre el manager."""
        # `next(iter(set))` es la cuenta pendiente más vieja: la que disparó la
        # notificación. Si hay varias, mejor abrir el manager a que abrir la
        # primera al azar.
        pending = next(iter(self._notified), None)
        if pending is not None:
            self._start_login(pending)
        else:
            self.open_manager()

    def _start_login(self, account_id: str) -> None:
        if not self._login.start(account_id):
            self._tray.showMessage(
                "Monitor de consumos",
                "Ya hay un login abierto. Termínalo antes de empezar otro.",
                QSystemTrayIcon.Information,
                4000,
            )
            return

        account = accounts_registry.get(account_id)
        name = account.label if account else account_id
        self._panel.show_busy(f"abriendo el navegador para «{name}»…")

    def _on_login_succeeded(self, account_id: str) -> None:
        account = accounts_registry.get(account_id)
        name = account.label if account else account_id
        self._tray.showMessage(
            "Monitor de consumos",
            f"Sesión iniciada en «{name}». Leyendo el consumo…",
            QSystemTrayIcon.Information,
            3000,
        )
        self._notified.discard(account_id)
        if self._manager is not None and self._manager.isVisible():
            self._manager.reload()
        self._poller.start()

    def _on_login_failed(self, account_id: str, message: str) -> None:
        self._panel.show_auth_required(account_id, message)
        if self._manager is not None and self._manager.isVisible():
            self._manager.reload()
        self._tray.showMessage("Monitor de consumos", message, QSystemTrayIcon.Warning, 6000)

    # -- Panel --------------------------------------------------------------

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason not in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            return
        self._toggle_panel()

    def _toggle_panel(self) -> None:
        if self._panel.isVisible():
            self._panel.hide()
            return
        self._show_panel()
        # Al abrirlo pedimos dato fresco: puede llevar minutos cerrado.
        self._poller.refresh()

    def _show_panel(self) -> None:
        if self._settings.pinned:
            self._panel.show_pinned_at(self._settings.position)
            return

        geometry = self._tray.geometry()
        if geometry.isEmpty():
            # Algunas bandejas (varios entornos de Wayland, y AppIndicator en
            # GNOME) no exponen la geometría del icono; centramos como recurso.
            screen = QApplication.primaryScreen().availableGeometry()
            anchor = QPoint(screen.center().x(), screen.bottom() - 40)
        else:
            anchor = QPoint(geometry.center().x(), geometry.top())
        self._panel.popup_at(anchor)

    # -- Cierre -------------------------------------------------------------

    def shutdown(self) -> None:
        self._poller.shutdown()
        self._login.shutdown()
        if self._manager is not None:
            self._manager.close()
        self._panel.close()
        self._tray.hide()
