"""Anillo de progreso dibujado a mano y animado.

Qt no trae un anillo con degradado y extremos redondeados, así que lo pintamos
con QPainter. El valor se interpola con QPropertyAnimation: al llegar un dato
nuevo el arco viaja hasta él en vez de saltar.
"""

from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QColor, QConicalGradient, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..core.models import Severity
from . import theme

#: Grosor del arco en píxeles.
THICKNESS = 9
#: Margen interior para que el extremo redondeado no se recorte.
INSET = THICKNESS / 2 + 2


class UsageRing(QWidget):
    """Anillo que muestra un porcentaje de 0 a 100."""

    def __init__(self, diameter: int = 96, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._value = 0.0
        self._severity = Severity.OK
        self._has_data = False

        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._animation = QPropertyAnimation(self, b"value", self)
        self._animation.setDuration(theme.ANIMATION_MS)
        # OutCubic: arranca rápido y frena al final. Da sensación de precisión,
        # no de rebote — es un dato, no un juguete.
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    # -- Propiedad animable -------------------------------------------------

    def _get_value(self) -> float:
        return self._value

    def _set_value(self, value: float) -> None:
        self._value = max(0.0, min(100.0, float(value)))
        self.update()

    value = Property(float, _get_value, _set_value)

    # -- API ----------------------------------------------------------------

    def set_target(self, percent: float, severity: Severity) -> None:
        """Anima el anillo hasta `percent`."""
        self._severity = severity
        self._has_data = True

        self._animation.stop()
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(max(0.0, min(100.0, float(percent))))
        self._animation.start()

    def set_unknown(self) -> None:
        """Sin datos todavía: solo la pista, sin arco ni número."""
        self._animation.stop()
        self._has_data = False
        self._value = 0.0
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._diameter, self._diameter)

    # -- Pintado ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 - firma de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect()).adjusted(INSET, INSET, -INSET, -INSET)

        self._paint_track(painter, rect)
        if self._has_data and self._value > 0:
            self._paint_arc(painter, rect)
        self._paint_label(painter)

    def _paint_track(self, painter: QPainter, rect: QRectF) -> None:
        pen = QPen(theme.TRACK, THICKNESS)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(rect)

    def _paint_arc(self, painter: QPainter, rect: QRectF) -> None:
        accent = theme.color_for(self._severity)

        # Los ángulos de Qt van en 1/16 de grado, 0 a las 3 en punto y sentido
        # antihorario. Arrancamos arriba y avanzamos en horario (span negativo).
        start_angle = 90 * 16
        span_angle = int(-(self._value / 100.0) * 360 * 16)

        gradient = QConicalGradient(rect.center(), 90.0)
        # El degradado recorre el sentido antihorario, o sea el inverso al del
        # arco: por eso el color de arranque va en la posición 1.0.
        gradient.setColorAt(1.0, theme.lighten(accent, 55))
        gradient.setColorAt(0.55, accent)
        gradient.setColorAt(0.0, theme.lighten(accent, 55))

        pen = QPen(gradient, THICKNESS)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, start_angle, span_angle)

    def _paint_label(self, painter: QPainter) -> None:
        if not self._has_data:
            painter.setPen(theme.TEXT_FAINT)
            font = QFont()
            font.setPointSize(13)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, "—")
            return

        painter.setPen(theme.TEXT)
        font = QFont()
        font.setPointSize(20)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)

        # El número se redondea al pintar, pero el arco usa el valor continuo:
        # así el texto no parpadea mientras la animación corre.
        # Desplazamos ambas líneas desde el centro en vez de anclarlas a los
        # bordes: así el bloque queda óptimamente centrado sea cual sea el
        # diámetro, y el símbolo nunca se monta sobre la cifra.
        rect = QRectF(self.rect())
        painter.drawText(rect.translated(0, -8), Qt.AlignCenter, f"{round(self._value)}")

        painter.setPen(theme.TEXT_MUTED)
        small = QFont()
        small.setPointSize(9)
        small.setWeight(QFont.Medium)
        painter.setFont(small)
        painter.drawText(rect.translated(0, 20), Qt.AlignCenter, "%")
