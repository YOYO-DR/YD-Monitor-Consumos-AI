"""Panel de consumo. Se despliega desde la bandeja o vive clavado en el escritorio."""

from __future__ import annotations

import time

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.account import Account
from ..core.models import Quota, UsageSnapshot
from . import theme
from .ring import UsageRing

#: Anillos por fila antes de saltar a la siguiente.
COLUMNS = 2


def format_duration(seconds: float) -> str:
    """3735 -> '1h 2m'. Por debajo del minuto baja a segundos."""
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, _ = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def format_age(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds < 5:
        return "ahora mismo"
    if seconds < 60:
        return f"hace {seconds}s"
    return f"hace {format_duration(seconds)}"


class _QuotaCell(QWidget):
    """Un anillo con su etiqueta y su cuenta atrás."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ring = UsageRing()
        self.label = QLabel("", objectName="quotaLabel")
        self.reset = QLabel("", objectName="resetLabel")

        for widget in (self.label, self.reset):
            widget.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.ring, alignment=Qt.AlignCenter)
        layout.addWidget(self.label)
        layout.addWidget(self.reset)

    def apply(self, quota: Quota) -> None:
        self.ring.set_target(quota.used_percent, quota.severity)
        self.label.setText(quota.label.upper())
        self.refresh_countdown(quota)

    def refresh_countdown(self, quota: Quota) -> None:
        remaining = quota.seconds_to_reset
        self.reset.setText(
            f"reinicia en {format_duration(remaining)}" if remaining is not None else ""
        )


class AccountSection(QWidget):
    """Bloque de una cuenta: su nombre y sus ventanas de consumo."""

    login_requested = Signal(str)

    def __init__(self, account: Account, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.account = account
        self._snapshot: UsageSnapshot | None = None
        self._cells: list[_QuotaCell] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Separa esta cuenta de la anterior; sobra en la primera.
        self._divider = QFrame(objectName="divider")
        self._divider.setFrameShape(QFrame.HLine)
        self._divider.setFixedHeight(1)
        self._divider.hide()
        layout.addWidget(self._divider)

        header = QHBoxLayout()
        self._name = QLabel(account.label, objectName="accountName")
        header.addWidget(self._name)
        header.addStretch(1)
        self._badge = QLabel("", objectName="accountBadge")
        header.addWidget(self._badge)
        layout.addLayout(header)

        self._grid = QGridLayout()
        self._grid.setSpacing(theme.GAP)
        layout.addLayout(self._grid)

        self._message = QLabel("", objectName="error")
        self._message.setWordWrap(True)
        self._message.hide()
        layout.addWidget(self._message)

        self._login_button = QPushButton("Iniciar sesión")
        self._login_button.clicked.connect(lambda: self.login_requested.emit(self.account.id))
        self._login_button.hide()
        layout.addWidget(self._login_button, alignment=Qt.AlignLeft)

    # -- Estados ------------------------------------------------------------

    def set_account(self, account: Account) -> None:
        self.account = account
        self._name.setText(account.label)

    def set_first(self, is_first: bool) -> None:
        self._divider.setVisible(not is_first)

    def show_snapshot(self, snapshot: UsageSnapshot) -> None:
        self._snapshot = snapshot
        self._sync_cells(len(snapshot.quotas))
        for cell, quota in zip(self._cells, snapshot.quotas):
            cell.apply(quota)
        self._message.hide()
        self._login_button.hide()
        self._badge.setText("")

    def show_auth_required(self, reason: str) -> None:
        self._snapshot = None
        for cell in self._cells:
            cell.ring.set_unknown()
            cell.reset.setText("")
        self._message.setText(reason)
        self._message.show()
        self._login_button.show()
        self._badge.setText("sin sesión")

    def show_error(self, message: str) -> None:
        # Mantenemos los anillos con el último dato bueno: un fallo de red no
        # significa que el consumo haya cambiado.
        self._message.setText(message)
        self._message.show()
        self._login_button.hide()
        self._badge.setText("sin conexión")

    def refresh_countdowns(self) -> None:
        if self._snapshot is None:
            return
        for cell, quota in zip(self._cells, self._snapshot.quotas):
            cell.refresh_countdown(quota)

    @property
    def snapshot(self) -> UsageSnapshot | None:
        return self._snapshot

    def _sync_cells(self, count: int) -> None:
        if count == len(self._cells):
            return

        while len(self._cells) < count:
            cell = _QuotaCell()
            index = len(self._cells)
            self._grid.addWidget(cell, index // COLUMNS, index % COLUMNS)
            self._cells.append(cell)

        while len(self._cells) > count:
            cell = self._cells.pop()
            self._grid.removeWidget(cell)
            cell.deleteLater()

        # Sin esto el layout de arriba sigue creyendo el tamaño que teníamos
        # cuando la sección estaba vacía, y el panel sale recortado.
        self._grid.invalidate()
        self.layout().invalidate()
        self.updateGeometry()


class UsagePanel(QWidget):
    """Panel con el consumo de todas las cuentas.

    Dos modos: desplegable desde la bandeja (se cierra al hacer clic fuera) o
    anclado al escritorio (siempre visible y arrastrable).
    """

    login_requested = Signal(str)
    refresh_requested = Signal()
    manage_requested = Signal()
    pin_toggled = Signal(bool)
    moved = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(theme.PANEL_STYLESHEET)

        self._pinned = False
        self._drag_offset: QPoint | None = None
        self._sections: dict[str, AccountSection] = {}
        self._last_update: float | None = None

        self._build()
        self._apply_window_flags()

        # La cuenta atrás y el "hace Ns" solo corren con el panel a la vista.
        self._ticker = QTimer(self)
        self._ticker.setInterval(1000)
        self._ticker.timeout.connect(self._tick)

    # -- Construcción -------------------------------------------------------

    def _build(self) -> None:
        self._root = QWidget(self, objectName="panelRoot")

        shadow = QGraphicsDropShadowEffect(self._root)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(theme.with_alpha(theme.BG, 200))
        self._root.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        # Hueco para que la sombra no se recorte contra el borde de la ventana.
        outer.setContentsMargins(16, 16, 16, 16)
        outer.addWidget(self._root)

        body = QVBoxLayout(self._root)
        body.setContentsMargins(theme.PADDING, theme.PADDING, theme.PADDING, theme.PADDING)
        body.setSpacing(theme.GAP)

        body.addLayout(self._build_header())

        self._sections_layout = QVBoxLayout()
        self._sections_layout.setSpacing(theme.GAP)
        body.addLayout(self._sections_layout)

        self._empty = QLabel(
            "Todavía no hay ninguna cuenta.\nAbre «Cuentas» para añadir la primera.",
            objectName="status",
        )
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.hide()
        body.addWidget(self._empty)

        body.addLayout(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(8)

        header.addWidget(QLabel("Consumos", objectName="title"))
        header.addStretch(1)

        self._status = QLabel("conectando…", objectName="status")
        header.addWidget(self._status)

        # Cerrar aquí es esconder, no salir: el widget sigue en la bandeja.
        close = QPushButton("✕", objectName="iconButton")
        close.setToolTip("Ocultar el panel (sigue en la bandeja)")
        close.setFixedSize(22, 22)
        close.clicked.connect(self.hide)
        header.addWidget(close)

        return header

    def _build_footer(self) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(8)

        manage = QPushButton("Cuentas")
        manage.clicked.connect(self.manage_requested)
        footer.addWidget(manage)

        footer.addStretch(1)

        refresh = QPushButton("Actualizar")
        refresh.clicked.connect(self.refresh_requested)
        footer.addWidget(refresh)

        self._pin_button = QPushButton("Anclar")
        self._pin_button.setCheckable(True)
        self._pin_button.setToolTip("Dejar el panel fijo en el escritorio")
        self._pin_button.clicked.connect(lambda checked: self.pin_toggled.emit(checked))
        footer.addWidget(self._pin_button)

        return footer

    # -- Modo anclado -------------------------------------------------------

    def set_pinned(self, pinned: bool) -> None:
        if pinned == self._pinned:
            return
        self._pinned = pinned

        self._pin_button.setChecked(pinned)
        self._pin_button.setText("Desanclar" if pinned else "Anclar")

        was_visible = self.isVisible()
        self._apply_window_flags()
        if was_visible:
            # Cambiar los flags obliga a recrear la ventana: hay que volver a
            # mostrarla o desaparecería sin más.
            self.show()

    @property
    def pinned(self) -> bool:
        return self._pinned

    def _apply_window_flags(self) -> None:
        if self._pinned:
            # Tool la mantiene fuera de la barra de tareas y del alt-tab, que es
            # lo que se espera de un widget de escritorio.
            flags = Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        else:
            # Popup se cierra sola al hacer clic fuera, como un menú.
            flags = Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        self.setWindowFlags(flags)

    # -- Arrastre (solo anclado) --------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - firma de Qt
        if self._pinned and event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - firma de Qt
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - firma de Qt
        if self._drag_offset is not None:
            self._drag_offset = None
            # Solo persistimos al soltar: guardar en cada píxel del arrastre
            # sería escribir en disco decenas de veces por segundo.
            self.moved.emit(self.x(), self.y())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -- Cuentas ------------------------------------------------------------

    def sync_accounts(self, accounts: list[Account]) -> None:
        """Ajusta las secciones a la lista de cuentas actual."""
        wanted = {account.id for account in accounts}

        for account_id in list(self._sections):
            if account_id not in wanted:
                section = self._sections.pop(account_id)
                self._sections_layout.removeWidget(section)
                section.deleteLater()

        for index, account in enumerate(accounts):
            section = self._sections.get(account.id)
            if section is None:
                section = AccountSection(account)
                section.login_requested.connect(self.login_requested)
                self._sections[account.id] = section
                self._sections_layout.addWidget(section)
            else:
                section.set_account(account)
            section.set_first(index == 0)

        self._empty.setVisible(not accounts)
        self._relayout()

    def section(self, account_id: str) -> AccountSection | None:
        return self._sections.get(account_id)

    def _relayout(self) -> None:
        """Recalcula el tamaño de la ventana tras cambiar el contenido.

        Cada QWidgetItem cachea el sizeHint de su widget, así que añadir
        anillos a una sección ya insertada no basta: hay que invalidar la
        cadena de layouts anidados antes de pedir el nuevo tamaño.
        """
        self._sections_layout.invalidate()
        self._root.layout().invalidate()
        self.layout().invalidate()
        self.adjustSize()

    # -- Estados ------------------------------------------------------------

    def show_snapshot(self, account_id: str, snapshot: UsageSnapshot) -> None:
        section = self._sections.get(account_id)
        if section is None:
            return
        section.show_snapshot(snapshot)
        self._last_update = time.time()
        self._tick()
        self._relayout()

    def show_auth_required(self, account_id: str, reason: str) -> None:
        section = self._sections.get(account_id)
        if section is not None:
            section.show_auth_required(reason)
            self._relayout()

    def show_error(self, account_id: str, message: str) -> None:
        section = self._sections.get(account_id)
        if section is not None:
            section.show_error(message)
            self._relayout()

    def show_busy(self, text: str = "actualizando…") -> None:
        self._status.setText(text)

    # -- Interno ------------------------------------------------------------

    def _tick(self) -> None:
        for section in self._sections.values():
            section.refresh_countdowns()
        if self._last_update is not None:
            self._status.setText(format_age(time.time() - self._last_update))

    # -- Ciclo de vida ------------------------------------------------------

    def popup_at(self, anchor: QPoint) -> None:
        """Muestra el panel junto a `anchor`, sin salirse de la pantalla."""
        self.adjustSize()
        size = self.size()

        x = anchor.x() - size.width() // 2
        y = anchor.y() - size.height()

        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left(), min(x, available.right() - size.width()))
            # Si el icono está arriba (barra superior), desplegamos hacia abajo.
            if y < available.top():
                y = anchor.y()
            y = max(available.top(), min(y, available.bottom() - size.height()))

        self.move(QPoint(x, y))
        self.show()

    def show_pinned_at(self, position: tuple[int, int] | None) -> None:
        """Muestra el panel anclado, en su última posición si la hay."""
        self.adjustSize()
        if position is not None:
            self.move(QPoint(*position))
        self.show()

    def showEvent(self, event) -> None:  # noqa: N802 - firma de Qt
        super().showEvent(event)
        self._tick()
        self._ticker.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - firma de Qt
        self._ticker.stop()
        super().hideEvent(event)
