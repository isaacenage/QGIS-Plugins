# -*- coding: utf-8 -*-
"""Per-element Tile Appearance form.

A schema-driven editor that builds itself from
:data:`elements.style_schema.STYLE_SCHEMAS` for the edited element's type, so
every element shows **only** the controls it can use (the indicator value's
typography, a table's header/row styling, the text body, …) plus a generic
**Tile** section (size / background / border) shared by all.

Design notes:

* It replaces ``AppearanceForm(mode="element")`` in the inspector. The legacy
  :class:`~appearance_dialog.AppearanceForm` stays for the global (Settings)
  theme editor and is untouched.
* Overrides are **sparse**: a control is seeded from the global theme's value
  (so it shows the live appearance), and only fields the user changes away from
  that baseline are written to ``config["style"]``. Everything else keeps
  tracking the theme.
* The **Tile size** field edits the tile's pixel geometry (via
  ``GridTile.set_size_px``), not ``config["style"]`` — exposed through
  :meth:`tile_size`.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QScrollArea, QToolButton,
    QComboBox, QSpinBox, QCheckBox, QFontComboBox, QLabel, QPushButton,
)

from .appearance_dialog import _ColorButton, _PaletteEditor
from .elements import style_schema as ss
from .form_util import compact_form, no_horizontal_scroll, shrink_combo


class _CollapsibleSection(QWidget):
    """A titled section with a click-to-collapse header and a form body."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self._btn = QToolButton()
        self._btn.setText(title)
        self._btn.setObjectName("styleSectionHeader")
        self._btn.setCheckable(True)
        self._btn.setChecked(True)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._btn.setArrowType(Qt.ArrowType.DownArrow)
        self._btn.toggled.connect(self._toggle)
        v.addWidget(self._btn)
        self._body = QWidget()
        self.form = QFormLayout(self._body)
        compact_form(self.form)
        self.form.setContentsMargins(6, 4, 0, 10)
        v.addWidget(self._body)

    def _toggle(self, on):
        self._body.setVisible(on)
        self._btn.setArrowType(Qt.ArrowType.DownArrow if on
                               else Qt.ArrowType.RightArrow)


class TileStyleForm(QWidget):
    """Schema-built per-tile appearance editor (inspector ``element`` mode)."""

    changed = pyqtSignal()

    def __init__(self, element, theme, parent=None):
        super().__init__(parent)
        self._element = element
        self._theme = theme           # the GLOBAL theme — the override baseline
        self._cleared = False
        self._loading = True
        self._fields = {}             # key -> (StyleField, getter callable)
        self._tile = getattr(element, "_grid_tile", None)
        self._w_spin = self._h_spin = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        no_horizontal_scroll(scroll)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        for section in ss.sections_for(element.type_name):
            box = _CollapsibleSection(section.title)
            for field in section.fields:
                self._add_field(box.form, field)
            col.addWidget(box)
        col.addStretch(1)

        clear = QPushButton("Clear overrides — use the dashboard theme")
        clear.setProperty("variant", "secondary")
        clear.clicked.connect(self._clear_overrides)
        root.addWidget(clear, 0, Qt.AlignmentFlag.AlignLeft)

        self.setStyleSheet(
            "QToolButton#styleSectionHeader { border:none; background:transparent;"
            " font-weight:700; padding:4px 2px; }")
        self._loading = False

    # ---- field construction -------------------------------------------------

    def _seed(self, field):
        """The value a control starts at: the tile's override, else the theme
        baseline (so an untouched control shows the live appearance)."""
        base = ss.default_for(field, self._theme)
        return self._element.style_get(field.key, base)

    def _add_field(self, form, field):
        if field.kind == ss.TILE_SIZE:
            form.addRow("Tile size", self._build_size_row())
            return
        widget, getter = self._build_widget(field)
        self._fields[field.key] = (field, getter)
        form.addRow(field.label, widget)

    def _build_size_row(self):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        rect = self._tile.grid_rect() if self._tile is not None else (0, 0, 320, 200)
        self._w_spin = self._size_spin(rect[2])
        self._h_spin = self._size_spin(rect[3])
        h.addWidget(self._w_spin)
        h.addWidget(QLabel("×"))
        h.addWidget(self._h_spin)
        h.addWidget(QLabel("px"))
        h.addStretch(1)
        return row

    def _size_spin(self, value):
        s = QSpinBox()
        s.setRange(40, 10000)
        s.setSingleStep(10)
        s.setValue(int(value))
        s.valueChanged.connect(self._on_edit)
        return s

    def _build_widget(self, field):
        seed = self._seed(field)
        kind = field.kind
        if kind == ss.COLOR:
            w = _ColorButton(seed)
            w.changed.connect(self._on_edit)
            return w, w.color
        if kind == ss.FONT:
            w = QFontComboBox()
            shrink_combo(w)
            if seed:
                w.setCurrentFont(QFont(str(seed)))
            w.currentFontChanged.connect(lambda *_: self._on_edit())
            return w, (lambda: w.currentFont().family())
        if kind == ss.SIZE:
            w = QSpinBox()
            w.setRange(int(field.opts.get("lo", 0)),
                       int(field.opts.get("hi", 9999)))
            w.setSingleStep(int(field.opts.get("step", 1)))
            try:
                w.setValue(int(seed))
            except (TypeError, ValueError):
                pass
            w.valueChanged.connect(lambda *_: self._on_edit())
            return w, w.value
        if kind == ss.WEIGHT:
            w = QComboBox()
            shrink_combo(w)
            for label, val in ss.WEIGHTS:
                w.addItem(label, val)
            self._select_data(w, seed)
            w.currentIndexChanged.connect(lambda *_: self._on_edit())
            return w, w.currentData
        if kind in (ss.ITALIC, ss.BOOL):
            w = QCheckBox()
            w.setChecked(bool(seed))
            w.toggled.connect(lambda *_: self._on_edit())
            return w, w.isChecked
        if kind == ss.ALIGN:
            w = QComboBox()
            shrink_combo(w)
            for label, val in ss.ALIGNS:
                w.addItem(label, val)
            self._select_data(w, seed)
            w.currentIndexChanged.connect(lambda *_: self._on_edit())
            return w, w.currentData
        if kind == ss.CHOICE:
            w = QComboBox()
            shrink_combo(w)
            for label, val in field.opts.get("choices", []):
                w.addItem(label, val)
            self._select_data(w, seed)
            w.currentIndexChanged.connect(lambda *_: self._on_edit())
            return w, w.currentData
        if kind == ss.PALETTE:
            w = _PaletteEditor(seed if isinstance(seed, list) else None)
            w.changed.connect(self._on_edit)
            return w, w.colors
        # unknown kind — render an inert label so the form still builds
        return QLabel(str(seed)), (lambda: None)

    @staticmethod
    def _select_data(combo, value):
        i = combo.findData(value)
        if i >= 0:
            combo.setCurrentIndex(i)

    # ---- editing ------------------------------------------------------------

    def _on_edit(self, *_):
        if self._loading:
            return
        self._cleared = False
        self.changed.emit()

    def _clear_overrides(self):
        self._cleared = True
        self.changed.emit()

    def is_cleared(self):
        return self._cleared

    # ---- results ------------------------------------------------------------

    @staticmethod
    def _equal(a, b):
        if isinstance(a, list) or isinstance(b, list):
            return list(a or []) == list(b or [])
        if isinstance(a, str) and isinstance(b, str):
            return a.strip().lower() == b.strip().lower()
        return a == b

    def result_override(self):
        """The sparse override dict — only fields changed from the theme
        baseline. ``None`` when the user cleared the override entirely."""
        if self._cleared:
            return None
        ov = {}
        for key, (field, getter) in self._fields.items():
            val = getter()
            if val in (None, ""):
                continue
            base = ss.default_for(field, self._theme)
            if not self._equal(val, base):
                ov[key] = val
        return ov

    def tile_size(self):
        """The chosen tile size ``(w, h)`` in px, or ``None`` if no tile."""
        if self._w_spin is None or self._h_spin is None:
            return None
        return (self._w_spin.value(), self._h_spin.value())
