"""Tokens de diseño: un único sitio donde tocar colores, tipografía y ritmo."""

from __future__ import annotations

from PySide6.QtGui import QColor

from ..core.models import Severity

# --- Superficies -----------------------------------------------------------
BG = QColor("#0E1116")
SURFACE = QColor("#161A21")
SURFACE_RAISED = QColor("#1D222B")
BORDER = QColor(255, 255, 255, 20)

# --- Texto -----------------------------------------------------------------
TEXT = QColor("#E8EDF5")
TEXT_MUTED = QColor("#8B95A5")
TEXT_FAINT = QColor("#5A6472")

# --- Estado ----------------------------------------------------------------
TRACK = QColor("#242B36")

_SEVERITY_COLORS: dict[Severity, QColor] = {
    Severity.OK: QColor("#2DD4A7"),
    Severity.WARN: QColor("#F0B429"),
    Severity.CRITICAL: QColor("#FF5A5F"),
}

ERROR = QColor("#FF5A5F")

# --- Ritmo -----------------------------------------------------------------
RADIUS = 14
PADDING = 18
GAP = 14

#: Duración de la interpolación al llegar un dato nuevo.
ANIMATION_MS = 900

FONT_FAMILY = "Inter, Segoe UI, Cantarell, Ubuntu, DejaVu Sans, sans-serif"


def color_for(severity: Severity) -> QColor:
    return _SEVERITY_COLORS[severity]


def lighten(color: QColor, amount: int = 40) -> QColor:
    """Versión más clara, para el extremo brillante de los degradados."""
    return QColor.fromHsv(
        color.hue(),
        max(0, color.saturation() - amount // 2),
        min(255, color.value() + amount),
    )


def with_alpha(color: QColor, alpha: int) -> QColor:
    out = QColor(color)
    out.setAlpha(alpha)
    return out


PANEL_STYLESHEET = f"""
QWidget#panelRoot {{
    background: {SURFACE.name()};
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: {RADIUS}px;
}}
QLabel {{
    color: {TEXT.name()};
    font-family: {FONT_FAMILY};
    background: transparent;
}}
QLabel#title {{
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
QLabel#quotaLabel {{
    color: {TEXT_MUTED.name()};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.6px;
}}
QLabel#resetLabel {{
    color: {TEXT_FAINT.name()};
    font-size: 10px;
}}
QLabel#status {{
    color: {TEXT_FAINT.name()};
    font-size: 10px;
}}
QLabel#error {{
    color: {ERROR.name()};
    font-size: 11px;
}}
QLabel#accountName {{
    font-size: 12px;
    font-weight: 600;
    color: {TEXT.name()};
}}
QLabel#accountBadge {{
    color: {TEXT_FAINT.name()};
    font-size: 10px;
}}
QLabel#sectionHint {{
    color: {TEXT_MUTED.name()};
    font-size: 11px;
}}
QFrame#divider {{
    background: rgba(255, 255, 255, 18);
    max-height: 1px;
    border: none;
}}
QPushButton#iconButton {{
    background: transparent;
    border: none;
    color: {TEXT_FAINT.name()};
    font-size: 13px;
    padding: 0;
    border-radius: 11px;
}}
QPushButton#iconButton:hover {{
    background: rgba(255, 255, 255, 22);
    color: {TEXT.name()};
}}
QPushButton#danger {{
    color: {ERROR.name()};
}}
QPushButton#danger:hover {{
    background: rgba(255, 90, 95, 30);
    border-color: rgba(255, 90, 95, 90);
}}
QLineEdit, QComboBox, QSpinBox {{
    background: {BG.name()};
    color: {TEXT.name()};
    border: 1px solid rgba(255, 255, 255, 24);
    border-radius: 8px;
    padding: 7px 10px;
    font-family: {FONT_FAMILY};
    font-size: 12px;
    selection-background-color: {_SEVERITY_COLORS[Severity.OK].name()};
    selection-color: {BG.name()};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: rgba(45, 212, 167, 140);
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 18px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: rgba(255, 255, 255, 22);
    border-radius: 4px;
}}
QSpinBox::up-arrow, QSpinBox::down-arrow {{
    width: 8px;
    height: 8px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_RAISED.name()};
    color: {TEXT.name()};
    border: 1px solid rgba(255, 255, 255, 24);
    selection-background-color: rgba(45, 212, 167, 60);
    outline: none;
}}
QCheckBox {{
    color: {TEXT.name()};
    font-family: {FONT_FAMILY};
    font-size: 12px;
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid rgba(255, 255, 255, 40);
    background: {BG.name()};
}}
QCheckBox::indicator:checked {{
    background: {_SEVERITY_COLORS[Severity.OK].name()};
    border-color: {_SEVERITY_COLORS[Severity.OK].name()};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QPushButton {{
    background: {SURFACE_RAISED.name()};
    color: {TEXT.name()};
    border: 1px solid rgba(255, 255, 255, 20);
    border-radius: 8px;
    padding: 7px 14px;
    font-family: {FONT_FAMILY};
    font-size: 11px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: #262D38;
    border-color: rgba(255, 255, 255, 40);
}}
QPushButton:pressed {{
    background: #202631;
}}
"""
