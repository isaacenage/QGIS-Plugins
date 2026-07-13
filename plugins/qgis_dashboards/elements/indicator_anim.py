# -*- coding: utf-8 -*-
"""Animated value display for the Indicator element.

ArcGIS-style dashboards animate their big number when it changes. This widget
encapsulates that so :mod:`indicator` stays small. It shows the indicator's
formatted value and animates transitions in one of four modes:

* ``odometer``   — the number eases from the previous value to the new value.
* ``rolling``    — slot-machine: each digit column rolls vertically (custom
                   painted by :class:`_RollingNumber`).
* ``typewriter`` — the text reveals one character at a time.
* ``fade``       — the new value fades/flashes in.

Anything else (``""`` / ``"none"``) updates instantly. Easing uses Qt's
``OutCubic`` curve; the HTML export mirrors the same curve in ``runtime.js``.
"""

from qgis.PyQt.QtCore import Qt, QVariantAnimation, QEasingCurve
from qgis.PyQt.QtGui import QFont, QFontMetrics, QPainter, QColor
from qgis.PyQt.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect,
)

DEFAULT_DURATION = 900   # ms


class _RollingNumber(QWidget):
    """A label-like widget that rolls each changed character vertically.

    On :meth:`set_text` every character position whose glyph changed slides its
    old glyph up and out while the new glyph slides up into place; unchanged
    positions are drawn statically. One shared progress value drives the roll.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._old = ""
        self._new = ""
        self._t = 1.0
        self._color = QColor("#2b7de9")
        self._font = QFont()
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_tick)

    def configure(self, color, pixel_size, family, weight=700, italic=False):
        self._color = QColor(color)
        f = QFont(family)
        f.setPixelSize(int(pixel_size))
        # setBold is used (not setWeight) for Qt5/Qt6 weight-scale portability.
        f.setBold(int(weight) >= 600)
        f.setItalic(bool(italic))
        self._font = f
        self.setMinimumHeight(int(pixel_size) + 8)
        self.update()

    def set_text(self, text, animate=True, duration=DEFAULT_DURATION):
        text = "" if text is None else str(text)
        self._anim.stop()
        if not animate or not self._new:
            self._old = self._new = text
            self._t = 1.0
            self.update()
            return
        self._old = self._new
        self._new = text
        self._t = 0.0
        self._anim.setDuration(int(duration))
        self._anim.start()

    def _on_tick(self, value):
        self._t = float(value)
        self.update()

    def paintEvent(self, _e):
        painter = QPainter(self)
        painter.setFont(self._font)
        painter.setPen(self._color)
        fm = QFontMetrics(self._font)
        new = self._new
        old = self._old
        width = max(fm.horizontalAdvance(new), fm.horizontalAdvance(old))
        x = (self.width() - width) / 2.0
        baseline = (self.height() + fm.ascent() - fm.descent()) / 2.0
        rise = fm.height()
        for i in range(len(new)):
            ch = new[i]
            oc = old[i] if i < len(old) else ""
            adv = fm.horizontalAdvance(ch)
            if self._t >= 1.0 or ch == oc or not oc:
                painter.drawText(int(x), int(baseline), ch)
            else:
                # new char rises into place; old char rises out the top
                offset = (1.0 - self._t) * rise
                painter.drawText(int(x), int(baseline + offset), ch)
                painter.drawText(int(x), int(baseline + offset - rise), oc)
            x += adv
        painter.end()


class IndicatorValue(QWidget):
    """The indicator's big number, with an optional change animation.

    For every mode except ``rolling`` the value lives in an inner ``QLabel``
    named ``indValue`` (so the theme's ``#indValue`` QSS still applies);
    ``rolling`` swaps in the custom :class:`_RollingNumber` painter.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel("—", self)
        self._label.setObjectName("indValue")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._roll = _RollingNumber(self)
        self._roll.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._label)
        lay.addWidget(self._roll)

        self._mode = ""
        self._duration = DEFAULT_DURATION
        self._formatter = str
        self._family = "Inter"
        self._pixel_size = 30
        self._color = "#2b7de9"
        self._last_number = None
        self._current_text = "—"
        self._num_anim = None
        self._type_anim = None
        self._fade = None

    # ---- styling -------------------------------------------------------
    def apply_style(self, color, pixel_size, family, weight=700, italic=False):
        self._color = color
        self._pixel_size = int(pixel_size)
        self._family = family or "Inter"
        weight = int(weight)
        f = QFont(self._family)
        f.setPixelSize(self._pixel_size)
        f.setBold(weight >= 600)
        f.setItalic(bool(italic))
        self._label.setFont(f)
        # Inline stylesheet on the label itself so the per-tile value
        # size/color/weight wins over the inherited #indValue rule from the tile
        # stylesheet.
        self._label.setStyleSheet(
            "#indValue {{ color:{c}; font-size:{s}px; font-weight:{w};"
            " font-style:{st}; }}".format(
                c=color, s=self._pixel_size, w=weight,
                st="italic" if italic else "normal"))
        self._roll.configure(
            color,
            self._pixel_size,
            self._family,
            weight,
            italic)

    def set_options(self, mode, duration, formatter):
        self._mode = (mode or "").lower()
        if self._mode == "none":
            self._mode = ""
        self._duration = int(duration or DEFAULT_DURATION)
        self._formatter = formatter or str

    # ---- value update --------------------------------------------------
    def set_value(self, number, text):
        """Show *text* (already formatted); *number* is its numeric value or
        ``None``. Animates from the previously shown value per the set mode."""
        text = "" if text is None else str(text)
        if self._mode == "rolling":
            self._show_roll()
            self._roll.set_text(text, animate=True, duration=self._duration)
            self._remember(number, text)
            return

        self._show_label()
        self._stop()
        had_prev = isinstance(self._last_number, (int, float))
        if (self._mode == "odometer" and isinstance(number, (int, float))
                and had_prev and number != self._last_number):
            self._run_odometer(float(self._last_number), float(number), text)
        elif self._mode == "typewriter" and text != self._current_text:
            self._run_typewriter(text)
        elif self._mode == "fade" and text != self._current_text:
            self._label.setText(text)
            self._run_fade()
        else:
            self._label.setText(text)
        self._remember(number, text)

    def _remember(self, number, text):
        self._current_text = text
        if isinstance(number, (int, float)):
            self._last_number = number

    # ---- mode helpers --------------------------------------------------
    def _show_label(self):
        self._roll.hide()
        self._label.show()

    def _show_roll(self):
        self._label.hide()
        self._roll.show()

    def _stop(self):
        for anim in (self._num_anim, self._type_anim, self._fade):
            if anim is not None:
                anim.stop()
        self._num_anim = self._type_anim = self._fade = None

    def _run_odometer(self, start, end, final_text):
        anim = QVariantAnimation(self)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(self._duration)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(
            lambda v: self._label.setText(self._formatter(float(v))))
        anim.finished.connect(lambda: self._label.setText(final_text))
        self._num_anim = anim
        anim.start()

    def _run_typewriter(self, final_text):
        anim = QVariantAnimation(self)
        anim.setStartValue(0)
        anim.setEndValue(len(final_text))
        anim.setDuration(self._duration)
        anim.valueChanged.connect(
            lambda n: self._label.setText(final_text[:int(n)]))
        anim.finished.connect(lambda: self._label.setText(final_text))
        self._type_anim = anim
        anim.start()

    def _run_fade(self):
        effect = QGraphicsOpacityEffect(self._label)
        self._label.setGraphicsEffect(effect)
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(self._duration)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: effect.setOpacity(float(v)))
        anim.finished.connect(lambda: effect.setOpacity(1.0))
        self._fade = anim
        anim.start()
