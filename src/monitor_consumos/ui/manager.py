"""Ventana de administración: alta y baja de cuentas, y preferencias."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import autostart, config, settings as settings_module
from ..auth import accounts as accounts_registry
from ..auth import store
from ..core.account import Account
from ..core.models import AuthRequired
from ..providers import REGISTRY
from . import theme


def _account_status(account: Account) -> str:
    """Texto corto sobre el estado de la sesión de una cuenta."""
    if not store.exists(account.id):
        return "sin sesión · pulsa «Entrar»"
    try:
        credential = store.load(account.id)
    except AuthRequired as exc:
        return str(exc)

    expires_at = credential.get("expires_at") or 0
    if expires_at:
        days = (expires_at - time.time()) / 86400
        return f"sesión activa · caduca en {days:.0f} días"
    return "sesión activa"


def _divider() -> QFrame:
    line = QFrame(objectName="divider")
    line.setFrameShape(QFrame.HLine)
    return line


class _AccountRow(QWidget):
    """Una fila de la lista: nombre, estado y acciones."""

    login_requested = Signal(str)
    renamed = Signal(str, str)
    removed = Signal(str)

    def __init__(self, account: Account, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.account = account

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(QLabel(account.label, objectName="accountName"))
        provider_name = REGISTRY[account.provider].display_name if account.provider in REGISTRY else account.provider
        text.addWidget(QLabel(f"{provider_name} · {_account_status(account)}", objectName="accountBadge"))
        layout.addLayout(text)

        layout.addStretch(1)

        login = QPushButton("Entrar")
        login.setToolTip("Abrir el navegador para iniciar sesión con esta cuenta")
        login.clicked.connect(lambda: self.login_requested.emit(self.account.id))
        layout.addWidget(login)

        rename = QPushButton("Renombrar")
        rename.clicked.connect(self._ask_rename)
        layout.addWidget(rename)

        remove = QPushButton("Eliminar", objectName="danger")
        remove.clicked.connect(self._confirm_remove)
        layout.addWidget(remove)

    def _ask_rename(self) -> None:
        label, ok = QInputDialog.getText(
            self, "Renombrar cuenta", "Nombre:", QLineEdit.Normal, self.account.label
        )
        if ok and label.strip():
            self.renamed.emit(self.account.id, label.strip())

    def _confirm_remove(self) -> None:
        # Borrar arrastra credencial y perfil de navegador: conviene preguntar.
        answer = QMessageBox.question(
            self,
            "Eliminar cuenta",
            f"¿Eliminar «{self.account.label}»?\n\n"
            "Se borrarán su sesión guardada y su perfil de navegador.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.removed.emit(self.account.id)


class ManagerWindow(QWidget):
    """Ventana normal (con barra de título) para administrar el monitor."""

    login_requested = Signal(str)
    accounts_changed = Signal()
    settings_changed = Signal()

    def __init__(self, current: settings_module.Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = current

        self.setWindowTitle("Monitor de consumos · Cuentas")
        self.setMinimumWidth(560)
        self.setStyleSheet(theme.PANEL_STYLESHEET + f"QWidget {{ background: {theme.SURFACE.name()}; }}")

        self._build()
        self.reload()

    # -- Construcción -------------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        outer.addWidget(QLabel("Cuentas", objectName="title"))

        self._list = QVBoxLayout()
        self._list.setSpacing(0)

        holder = QWidget()
        holder.setLayout(self._list)

        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(160)
        outer.addWidget(scroll, stretch=1)

        outer.addWidget(_divider())
        outer.addLayout(self._build_add_form())
        outer.addWidget(_divider())
        outer.addLayout(self._build_preferences())

    def _build_add_form(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(8)
        box.addWidget(QLabel("Añadir cuenta", objectName="accountName"))

        row = QHBoxLayout()
        row.setSpacing(8)

        self._provider_combo = QComboBox()
        for key, provider_cls in REGISTRY.items():
            self._provider_combo.addItem(provider_cls.display_name, key)
        row.addWidget(self._provider_combo)

        self._label_input = QLineEdit()
        self._label_input.setPlaceholderText("Nombre, p. ej. «MiniMax trabajo»")
        self._label_input.returnPressed.connect(self._add_account)
        row.addWidget(self._label_input, stretch=1)

        add = QPushButton("Añadir")
        add.clicked.connect(self._add_account)
        row.addWidget(add)

        box.addLayout(row)
        box.addWidget(
            QLabel(
                "Cada cuenta usa su propio perfil de navegador, así que puedes "
                "tener varias del mismo proveedor sin que se pisen.",
                objectName="sectionHint",
                wordWrap=True,
            )
        )
        return box

    def _build_preferences(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(10)
        box.addWidget(QLabel("Preferencias", objectName="accountName"))

        self._pin_check = QCheckBox("Mantener el panel anclado al escritorio")
        self._pin_check.setChecked(self._settings.pinned)
        self._pin_check.toggled.connect(self._on_pin_toggled)
        box.addWidget(self._pin_check)

        self._autostart_check = QCheckBox("Iniciar automáticamente con el sistema")
        self._autostart_check.setChecked(autostart.is_enabled())
        self._autostart_check.toggled.connect(self._on_autostart_toggled)
        box.addWidget(self._autostart_check)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Actualizar cada", objectName="sectionHint"))

        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(
            config.MIN_POLL_INTERVAL_SECONDS, config.MAX_POLL_INTERVAL_SECONDS
        )
        self._interval_spin.setValue(self._settings.clamped_interval())
        self._interval_spin.setSuffix(" s")
        self._interval_spin.valueChanged.connect(self._on_interval_changed)
        row.addWidget(self._interval_spin)

        row.addWidget(QLabel("(la consola web usa 5 s)", objectName="sectionHint"))
        row.addStretch(1)
        box.addLayout(row)

        return box

    # -- Datos --------------------------------------------------------------

    def reload(self) -> None:
        """Vuelve a pintar la lista de cuentas desde disco."""
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        accounts = accounts_registry.list_accounts()
        if not accounts:
            hint = QLabel("Todavía no hay ninguna cuenta.", objectName="sectionHint")
            hint.setAlignment(Qt.AlignCenter)
            self._list.addWidget(hint)
        else:
            for index, account in enumerate(accounts):
                if index:
                    self._list.addWidget(_divider())
                row = _AccountRow(account)
                row.login_requested.connect(self.login_requested)
                row.renamed.connect(self._rename_account)
                row.removed.connect(self._remove_account)
                self._list.addWidget(row)

        self._list.addStretch(1)

    # -- Acciones -----------------------------------------------------------

    def _add_account(self) -> None:
        provider = self._provider_combo.currentData()
        label = self._label_input.text().strip()
        if not label:
            label = f"{REGISTRY[provider].display_name} {len(accounts_registry.list_accounts()) + 1}"

        account = accounts_registry.add(provider, label)
        self._label_input.clear()
        self.reload()
        self.accounts_changed.emit()

        # Una cuenta recién creada no sirve de nada sin sesión: encadenamos el
        # login en vez de obligar a un segundo clic.
        self.login_requested.emit(account.id)

    def _rename_account(self, account_id: str, label: str) -> None:
        accounts_registry.rename(account_id, label)
        self.reload()
        self.accounts_changed.emit()

    def _remove_account(self, account_id: str) -> None:
        accounts_registry.remove(account_id)
        self.reload()
        self.accounts_changed.emit()

    def _on_pin_toggled(self, checked: bool) -> None:
        self._settings.pinned = checked
        settings_module.save(self._settings)
        self.settings_changed.emit()

    def _on_autostart_toggled(self, checked: bool) -> None:
        if checked:
            autostart.enable()
        else:
            autostart.disable()

    def _on_interval_changed(self, value: int) -> None:
        self._settings.poll_interval = value
        settings_module.save(self._settings)
        self.settings_changed.emit()

    def sync_from_settings(self, current: settings_module.Settings) -> None:
        """Refleja cambios hechos desde el panel (p. ej. el botón de anclar)."""
        self._settings = current
        self._pin_check.blockSignals(True)
        self._pin_check.setChecked(current.pinned)
        self._pin_check.blockSignals(False)
