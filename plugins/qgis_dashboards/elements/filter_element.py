# -*- coding: utf-8 -*-
"""Filter widget — a multi-field "definition query" source.

ArcGIS dashboards let a user constrain a layer by picking one value per category
column; the combination (AND-ed across columns) becomes a definition query that
filters every connected tile. This widget does the same: it shows one dropdown
per configured field and pushes ``"f1" = 'a' AND "f2" = 'b'`` onto the bus.

It is a *pure* source (``accepts_filter = False``) so its value lists never
narrow themselves down when other tiles drive the dashboard — the user can
always re-pick. Wire it (Connections editor) to the map and/or any data tile;
against the map the AND-of-equalities is ``subsetString``-compatible, so the map
can render the filtered subset.
"""

from qgis.PyQt.QtWidgets import QWidget, QGridLayout, QLabel, QComboBox
from .base import DashboardElement, _FONT_FALLBACK


class FilterElement(DashboardElement):
    type_name = "filter"
    is_filter_source = True
    accepts_filter = False

    ALL = "(All)"

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        self._host = QWidget()
        self._grid = QGridLayout(self._host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(6)
        self.body.addWidget(self._host)
        self.body.addStretch(1)
        self._labels = []          # ordered [(field, QLabel, QComboBox)]
        self._combos = {}          # field -> QComboBox
        self._suppress = False
        self.apply_theme()
        self.refresh()

    # ---- config ----

    def _fields(self):
        """The configured category columns, tolerant of a comma-sep string."""
        raw = self.config.get("fields", [])
        if isinstance(raw, str):
            raw = [p.strip() for p in raw.split(",")]
        return [f for f in raw if f]

    # ---- interaction mode ----

    def set_interactive(self, on):
        super().set_interactive(on)
        for combo in self._combos.values():
            combo.setEnabled(bool(on))

    # ---- appearance ----

    def _restyle(self):
        th = self.effective_theme()
        bg = self.style_get("combo_bg", th.surface_bg)
        color = self.style_get("combo_color", th.text)
        fam = self.style_get("combo_font", th.font_family)
        px = int(self.style_get("combo_px", th.font_size))
        border = self.style_get("combo_border", th.border)
        accent = self.style_get("combo_accent", th.accent)
        combo_qss = (
            'QComboBox {{ background:{bg}; color:{c}; border:1px solid {b};'
            ' border-radius:8px; padding:4px 8px; min-height:26px;'
            ' font-family:"{f}", {fb}; font-size:{px}px; }}'
            'QComboBox:focus {{ border:1px solid {a}; }}'
            'QComboBox QAbstractItemView {{ background:{bg}; color:{c};'
            ' border:1px solid {b}; selection-background-color:{a};'
            ' selection-color:#ffffff; }}'.format(
                bg=bg, c=color, b=border, a=accent, f=fam, fb=_FONT_FALLBACK,
                px=px))
        label_qss = ('color:{c}; font-family:"{f}", {fb}; font-size:{px}px;'
                     ' background:transparent;'.format(
                         c=color, f=fam, fb=_FONT_FALLBACK, px=px))
        for _field, label, combo in self._labels:
            combo.setStyleSheet(combo_qss)
            label.setStyleSheet(label_qss)

    # ---- data ----

    def _rebuild_rows(self, fields):
        """Recreate one label+combo row per field (order-sensitive)."""
        for _field, label, combo in self._labels:
            combo.currentTextChanged.disconnect(self._on_change)
            self._grid.removeWidget(label)
            self._grid.removeWidget(combo)
            label.deleteLater()
            combo.deleteLater()
        self._labels = []
        self._combos = {}
        for r, field in enumerate(fields):
            label = QLabel(field)
            combo = QComboBox()
            combo.setEnabled(self._interactive)
            combo.currentTextChanged.connect(self._on_change)
            self._grid.addWidget(label, r, 0)
            self._grid.addWidget(combo, r, 1)
            self._labels.append((field, label, combo))
            self._combos[field] = combo

    def refresh(self):
        fields = self._fields()
        if [f for f, _l, _c in self._labels] != fields:
            self._rebuild_rows(fields)
        lyr = self.layer()
        self._suppress = True
        for field, _label, combo in self._labels:
            current = combo.currentText()
            combo.clear()
            combo.addItem(self.ALL)
            if lyr is not None:
                idx = lyr.fields().indexOf(field)
                if idx >= 0:
                    combo.addItems(
                        sorted({str(v) for v in lyr.uniqueValues(idx)}))
            i = combo.findText(current)
            combo.setCurrentIndex(i if i >= 0 else 0)
        self._suppress = False
        self._restyle()

    # ---- source behavior ----

    def _build_expression(self):
        parts = []
        for field, _label, combo in self._labels:
            text = combo.currentText()
            if text and text != self.ALL:
                parts.append(
                    '"{}" = \'{}\''.format(
                        field, text.replace(
                            "'", "''")))
        if not parts:
            return None
        return " AND ".join(parts)

    def _on_change(self, _text):
        if self._suppress:
            return
        self.bus.set_filter(self.id, self._build_expression())

    def _on_filters_cleared(self):
        self._suppress = True
        for _field, _label, combo in self._labels:
            i = combo.findText(self.ALL)
            if i >= 0:
                combo.setCurrentIndex(i)
        self._suppress = False
