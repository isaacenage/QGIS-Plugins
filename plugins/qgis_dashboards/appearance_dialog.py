# -*- coding: utf-8 -*-
"""Appearance editor — edit the dashboard theme.

The editing controls live in :class:`AppearanceForm` (a plain ``QWidget``) so
the same form can be **embedded** in two places:

  - the Settings hub's *Appearance* page (whole-dashboard theme, applied live),
  - the right-edge inspector panel (a single tile's override).

:class:`AppearanceDialog` is a thin modal wrapper around the form, kept for
backwards compatibility / standalone use.

Two modes:
  - "global": edit the whole-dashboard theme (background, foreground, borders,
    chart colors, fonts, ...).
  - "element": edit one tile's override; only the keys a tile may override are
    shown, and the result is written to ``config["style"]``.

Fonts are chosen with ``QFontComboBox``, which lists every font available to
the QGIS/Qt application (including fonts QGIS itself has registered).
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QWidget, QPushButton,
    QSpinBox, QFontComboBox, QColorDialog, QDialogButtonBox,
    QScrollArea, QToolButton, QCheckBox, QComboBox,
)
from qgis.PyQt.QtGui import QColor, QFont, QPixmap, QPainter, QIcon
from qgis.PyQt.QtCore import Qt, pyqtSignal, QSize, QRectF

from .theme import Theme, OVERRIDE_KEYS, DEFAULT_SERIES
from . import presets
from .form_util import compact_form, no_horizontal_scroll, shrink_combo

# (key, label) for the simple color rows.
# Note: ``chrome_bg`` (the window/tab/rail chrome) is intentionally NOT editable —
# it stays at the neutral default so dialogs and chrome read consistently. Only the
# canvas drawing-area background ("Canvas background" → ``window_bg``) is exposed.
# Note: the "Tile border" color lives on the *Layout* page (next to border
# thickness + transparency), not here, so border color + thickness stay together
# and aren't duplicated across the Themes and Layout pages.
GLOBAL_COLORS = [
    ("window_bg", "Canvas background"),
    ("surface_bg", "Tile background"),
    ("chart_bg", "Chart background"),
    ("text", "Text (foreground)"),
    ("text_muted", "Secondary text"),
    ("accent", "Accent / highlight"),
    ("grid_line", "Grid dots"),
]
# Per-tile overrides DO carry the border color (alongside its thickness +
# transparency spinners below), so a single tile can restyle its own outline.
ELEMENT_COLORS = [
    ("surface_bg", "Tile background"),
    ("chart_bg", "Chart background"),
    ("text", "Text (foreground)"),
    ("text_muted", "Secondary text"),
    ("accent", "Accent / highlight"),
    ("border", "Tile border"),
]


def _swatch_icon(values, size=16, n=5):
    """A small multi-color pill summarizing a preset's palette for a combo row.

    Draws the accent plus the first few series colors as rounded chips on a
    surface-colored ground, so the dropdown reads as a visual gallery.
    """
    w, h = size * n + 6, size + 6
    px = QPixmap(w, h)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    colors = [values.get("accent", "#2b7de9")]
    colors += list(values.get("series", []))[:n - 1]
    x = 3.0
    for c in colors[:n]:
        p.setBrush(QColor(c))
        p.setPen(QColor(0, 0, 0, 28))
        p.drawRoundedRect(QRectF(x, 3.0, size - 3, size), 3, 3)
        x += size
    p.end()
    return QIcon(px)


class _ColorButton(QPushButton):
    """A swatch button that opens a color picker."""

    changed = pyqtSignal()

    def __init__(self, hex_color, parent=None):
        super().__init__(parent)
        self._color = hex_color or "#000000"
        self.setFixedSize(120, 24)
        self.clicked.connect(self._pick)
        self._refresh()

    def _refresh(self):
        c = QColor(self._color)
        text_color = "#ffffff" if c.lightness() < 140 else "#1b2733"
        self.setStyleSheet(
            "background:{}; color:{}; border:1px solid #b6bfc8; border-radius:4px;"
            .format(self._color, text_color))
        self.setText(self._color)

    def _pick(self):
        # Parent the picker to the top-level window, not this swatch button:
        # the button carries a ``background:<color>`` stylesheet that would
        # otherwise cascade into the dialog and tint its whole chrome. The
        # window's stylesheet gives the picker the normal light look.
        c = QColorDialog.getColor(
            QColor(
                self._color),
            self.window(),
            "Pick color")
        if c.isValid():
            self._color = c.name()
            self._refresh()
            self.changed.emit()

    def color(self):
        return self._color

    def set_color(self, hex_color):
        """Set the swatch silently (no ``changed`` emission)."""
        self._color = hex_color or "#000000"
        self._refresh()


class _PaletteEditor(QWidget):
    """Editable row of series colors with add/remove."""

    changed = pyqtSignal()

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self._colors = list(colors) if colors else list(DEFAULT_SERIES)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._rebuild()

    def _rebuild(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, hexc in enumerate(self._colors):
            btn = _ColorButton(hexc)
            btn.setFixedSize(28, 24)
            btn.changed.connect(lambda i=i, b=btn: self._set(i, b.color()))
            self._lay.addWidget(btn)
        add = QToolButton()
        add.setText("+")
        add.clicked.connect(self._add)
        rem = QToolButton()
        rem.setText("−")
        rem.clicked.connect(self._remove)
        self._lay.addWidget(add)
        self._lay.addWidget(rem)
        self._lay.addStretch(1)

    def _set(self, i, hexc):
        if 0 <= i < len(self._colors):
            self._colors[i] = hexc
            self.changed.emit()

    def _add(self):
        nxt = DEFAULT_SERIES[len(self._colors) % len(DEFAULT_SERIES)]
        self._colors.append(nxt)
        self._rebuild()
        self.changed.emit()

    def _remove(self):
        if len(self._colors) > 1:
            self._colors.pop()
            self._rebuild()
            self.changed.emit()

    def colors(self):
        return list(self._colors)

    def set_colors(self, colors):
        """Replace the palette silently (no ``changed`` emission)."""
        self._colors = list(colors) if colors else list(DEFAULT_SERIES)
        self._rebuild()


class AppearanceForm(QWidget):
    """Embeddable theme editor (global theme or one tile's override).

    Emits :attr:`changed` on every control edit / preset choice so a host can
    preview live. In global mode it can also call *on_apply* directly with the
    freshly-built :class:`Theme` (used by the Settings hub for live preview).
    """

    changed = pyqtSignal()

    def __init__(self, theme, mode="global", on_apply=None, parent=None,
                 scrollable=True):
        super().__init__(parent)
        self.mode = mode
        self._on_apply = on_apply
        self._cleared = False
        self._base_theme = theme
        # Guards re-entrancy while a preset populates the controls below.
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # ---- preset gallery (global mode only) --------------------------
        # Presets set window/chrome colors that an element override can't carry,
        # so the one-click gallery is shown for the whole-dashboard theme only.
        self._preset = None
        if mode == "global":
            self._preset = QComboBox()
            shrink_combo(self._preset)
            self._preset.setIconSize(QSize(90, 22))
            self._preset.addItem(presets.CUSTOM)
            for name in presets.names():
                self._preset.addItem(
                    _swatch_icon(
                        presets.values_for(name)), name)
            match = presets.match(theme)
            self._preset.setCurrentText(match or presets.CUSTOM)
            self._preset.currentIndexChanged.connect(self._on_preset_chosen)
            preset_row = QFormLayout()
            compact_form(preset_row)
            preset_row.addRow("Preset theme", self._preset)
            root.addLayout(preset_row)

        # When embedded in the Settings panel (scrollable=False) the rows are
        # added directly so the panel's own outer scroll handles overflow — no
        # nested scroll areas. Standalone (the per-tile inspector) keeps its
        # own.
        inner = QWidget()
        form = QFormLayout(inner)
        compact_form(form)
        if scrollable:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            no_horizontal_scroll(scroll)
            scroll.setWidget(inner)
            root.addWidget(scroll, 1)
        else:
            root.addWidget(inner, 1)
        self._rows_form = form   # kept so reload_fonts() can swap the pickers

        rows = ELEMENT_COLORS if mode == "element" else GLOBAL_COLORS
        self._color_btns = {}
        for key, label in rows:
            btn = _ColorButton(getattr(theme, key))
            btn.changed.connect(self._on_edit)
            self._color_btns[key] = btn
            form.addRow(label, btn)

        # series palette
        self._palette = _PaletteEditor(theme.series)
        self._palette.changed.connect(self._on_edit)
        form.addRow("Chart series colors", self._palette)

        # fonts — body family + an optional separate heading family (a pairing)
        self._font = QFontComboBox()
        shrink_combo(self._font)
        if theme.font_family:
            self._font.setCurrentFont(QFont(theme.font_family))
        self._font.currentFontChanged.connect(self._on_edit)
        form.addRow("Body font", self._font)
        self._use_font = QCheckBox("Use this font")
        self._use_font.setToolTip("Otherwise the QGIS default font is used")
        self._use_font.setChecked(bool(theme.font_family))
        self._use_font.stateChanged.connect(self._on_edit)
        form.addRow("", self._use_font)

        self._heading_font = QFontComboBox()
        shrink_combo(self._heading_font)
        if theme.heading_font:
            self._heading_font.setCurrentFont(QFont(theme.heading_font))
        elif theme.font_family:
            self._heading_font.setCurrentFont(QFont(theme.font_family))
        self._heading_font.currentFontChanged.connect(self._on_edit)
        form.addRow("Heading font", self._heading_font)
        self._use_heading = QCheckBox("Separate heading font")
        self._use_heading.setToolTip("Pair a different font for headings")
        self._use_heading.setChecked(bool(theme.heading_font))
        self._use_heading.stateChanged.connect(self._on_edit)
        form.addRow("", self._use_heading)

        # Text SIZES and corner radius are LAYOUT settings, not theme settings.
        # In global mode they live in the Settings hub's *Layout* page (so the
        # whole-dashboard theme editor here is purely colors + fonts and is not
        # redundant with Layout). A per-tile override (element mode) may still
        # tune its own text sizes; tiles never override the global radius.
        self._radius = None
        if mode == "element":
            self._font_size = self._spin(theme.font_size, 6, 48)
            form.addRow("Base font size", self._font_size)
            self._title_size = self._spin(theme.title_size, 8, 48)
            form.addRow("Element title size", self._title_size)
            self._value_size = self._spin(theme.value_size, 10, 96)
            form.addRow("Indicator value size", self._value_size)
            # transparency + border thickness (global defaults live on Layout;
            # these let one tile override them — border color is the row
            # above).
            self._opacity = self._spin(theme.tile_opacity, 0, 100)
            form.addRow("Tile opacity (%)", self._opacity)
            self._border_width = self._spin(theme.border_width, 0, 8)
            form.addRow("Border thickness (px)", self._border_width)
        else:
            self._font_size = self._title_size = self._value_size = None
            self._opacity = self._border_width = None

        # element mode: a quiet "clear" affordance that drops the tile's
        # override entirely (the tile falls back to the global theme).
        if mode == "element":
            clear = QPushButton("Clear overrides — use the dashboard theme")
            clear.setProperty("variant", "secondary")
            clear.clicked.connect(self._clear_overrides)
            root.addWidget(clear, 0, Qt.AlignmentFlag.AlignLeft)

    def reload_fonts(self):
        """Rebuild the body + heading font pickers from the live Qt font DB.

        ``QFontComboBox`` snapshots the font database when constructed and does
        not refresh when a font is added/removed, so after the user installs a
        custom font we swap each picker for a fresh one — preserving the current
        selection and signal wiring — instead of reopening Settings."""
        self._font = self._swap_font_combo(self._font)
        self._heading_font = self._swap_font_combo(self._heading_font)

    def _swap_font_combo(self, old):
        """Replace one QFontComboBox in the form with a fresh, current-DB copy."""
        family = old.currentFont().family()
        new = QFontComboBox()
        shrink_combo(new)
        # set before connecting: no _on_edit
        new.setCurrentFont(QFont(family))
        new.currentFontChanged.connect(self._on_edit)
        self._rows_form.replaceWidget(old, new)
        old.deleteLater()
        return new

    def _spin(self, value, lo, hi):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(int(value))
        s.valueChanged.connect(self._on_edit)
        return s

    def _font_family(self):
        return self._font.currentFont().family() if self._use_font.isChecked() else ""

    def _heading_family(self):
        if self._use_heading.isChecked():
            return self._heading_font.currentFont().family()
        return ""

    # ---- editing / preview ---------------------------------------------

    def _on_edit(self, *_):
        """A manual control edit: no longer cleared, flip preset to Custom,
        notify the host, and (global) live-apply."""
        if self._loading:
            return
        self._cleared = False
        self._mark_custom()
        self.changed.emit()
        if self.mode == "global" and self._on_apply:
            self._on_apply(self.result_theme())

    def _clear_overrides(self):
        """Drop the tile override; the tile renders with the global theme."""
        self._cleared = True
        self.changed.emit()

    def is_cleared(self):
        return self._cleared

    # ---- presets --------------------------------------------------------

    def _mark_custom(self, *_):
        """A manual edit means the live theme no longer equals any preset."""
        if self._loading or self._preset is None:
            return
        if self._preset.currentText() != presets.CUSTOM:
            self._preset.blockSignals(True)
            self._preset.setCurrentText(presets.CUSTOM)
            self._preset.blockSignals(False)

    def _on_preset_chosen(self, *_):
        name = self._preset.currentText()
        if name == presets.CUSTOM:
            return
        # Layer the preset over the current theme so radius/sizes are kept.
        self._populate_from_theme(presets.theme_for(name, self._base_theme))
        self._cleared = False
        self.changed.emit()
        if self.mode == "global" and self._on_apply:
            self._on_apply(self.result_theme())

    def _populate_from_theme(self, theme):
        """Load every control from *theme* without re-triggering preset logic."""
        self._loading = True
        try:
            for key, btn in self._color_btns.items():
                btn.set_color(getattr(theme, key))
            self._palette.set_colors(theme.series)
            self._use_font.setChecked(bool(theme.font_family))
            if theme.font_family:
                self._font.setCurrentFont(QFont(theme.font_family))
            self._use_heading.setChecked(bool(theme.heading_font))
            head = theme.heading_font or theme.font_family
            if head:
                self._heading_font.setCurrentFont(QFont(head))
            if self._font_size is not None:
                self._font_size.setValue(int(theme.font_size))
            if self._title_size is not None:
                self._title_size.setValue(int(theme.title_size))
            if self._value_size is not None:
                self._value_size.setValue(int(theme.value_size))
            if self._opacity is not None:
                self._opacity.setValue(int(theme.tile_opacity))
            if self._border_width is not None:
                self._border_width.setValue(int(theme.border_width))
            if self._radius is not None:
                self._radius.setValue(int(theme.radius))
        finally:
            self._loading = False

    def result_theme(self):
        """Full Theme (global mode)."""
        data = self._base_theme.to_dict()
        for key, btn in self._color_btns.items():
            data[key] = btn.color()
        data["series"] = self._palette.colors()
        data["font_family"] = self._font_family()
        data["heading_font"] = self._heading_family()
        # Sizes/radius are Layout-owned; only set them if this form exposes them
        # (element mode), otherwise keep the base theme's values.
        if self._font_size is not None:
            data["font_size"] = self._font_size.value()
        if self._title_size is not None:
            data["title_size"] = self._title_size.value()
        if self._value_size is not None:
            data["value_size"] = self._value_size.value()
        if self._radius is not None:
            data["radius"] = self._radius.value()
        return Theme.from_dict(data)

    def result_override(self):
        """Partial override dict (element mode). None if cleared."""
        if self._cleared:
            return None
        ov = {}
        for key, btn in self._color_btns.items():
            ov[key] = btn.color()
        ov["series"] = self._palette.colors()
        ov["font_family"] = self._font_family()
        ov["heading_font"] = self._heading_family()
        if self._font_size is not None:
            ov["font_size"] = self._font_size.value()
        if self._title_size is not None:
            ov["title_size"] = self._title_size.value()
        if self._value_size is not None:
            ov["value_size"] = self._value_size.value()
        if self._opacity is not None:
            ov["tile_opacity"] = self._opacity.value()
        if self._border_width is not None:
            ov["border_width"] = self._border_width.value()
        return {k: v for k, v in ov.items() if k in OVERRIDE_KEYS}


class AppearanceDialog(QDialog):
    """Modal wrapper around :class:`AppearanceForm` (standalone / legacy use)."""

    def __init__(self, theme, mode="global", on_apply=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle("Tile appearance" if mode == "element"
                            else "Dashboard appearance")
        self.resize(420, 520)

        root = QVBoxLayout(self)
        self._form = AppearanceForm(theme, mode=mode, on_apply=on_apply,
                                    parent=self)
        root.addWidget(self._form, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        if mode == "global":
            apply_btn = btns.addButton(QDialogButtonBox.StandardButton.Apply)
            apply_btn.clicked.connect(self._form._on_edit)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def result_theme(self):
        return self._form.result_theme()

    def result_override(self):
        return self._form.result_override()
