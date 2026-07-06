# -*- coding: utf-8 -*-
"""Add / configure element form.

Minimal config UI per element type. Uses QgsMapLayerComboBox /
QgsFieldComboBox where it helps. This is the MVP stand-in for ArcGIS's rich
configuration panels — enough to bind data and see the dashboard work.

The controls live in :class:`ElementConfigForm` (a plain ``QWidget``) so the
same form can be **embedded** in the right-edge inspector panel (it emits
:attr:`~ElementConfigForm.changed` on every edit so the host can preview live).
:class:`AddElementDialog` is a thin modal wrapper kept for standalone use and
tests; it re-exposes the form's public attributes (``type_combo``,
``layer_combo``, ``_dyn``, ``result_config``, ``managed_keys``).
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QComboBox, QLineEdit, QDialogButtonBox, QCheckBox,
    QPlainTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QSpinBox, QFontComboBox, QScrollArea,
)
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox
from qgis.core import QgsMapLayerProxyModel, QgsFieldProxyModel
from .elements import ELEMENT_LABELS
from .elements.chart_specs import (
    CHART_SPECS, CHART_TYPE_ORDER, DEFAULT_CHART_TYPE, shape_of,
)
from .form_util import compact_form, no_horizontal_scroll, shrink_combo
from .field_select import FieldListSelector
from .indicator_expr import build_aggregate, parse_aggregate, STATISTICS

# element types that bind to no vector layer (the Layer row is hidden for them).
# The legend mirrors every layer on the map, so it binds to none of its own.
_LAYERLESS_TYPES = ("text", "image", "header", "legend")

_IMAGE_FILTER = ("Images (*.png *.jpg *.jpeg *.svg *.gif *.bmp *.webp);;"
                 "All files (*)")

# free-text config keys whose leading/trailing spaces are meaningful and must
# be preserved verbatim (e.g. a value suffix of " sqm" -> "2912 sqm"). Every
# other QLineEdit value is stripped as before.
_RAW_TEXT_KEYS = frozenset({"prefix", "suffix"})


class _PathPicker(QWidget):
    """A read/write path field with a 'Browse…' button (image file chooser).

    In *multiline* mode the field is a :class:`QPlainTextEdit` so a long,
    multi-line SVG snippet can be pasted intact — a single-line ``QLineEdit``
    collapses the newlines — and the Browse button sits below it.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None, multiline=False):
        super().__init__(parent)
        self._multiline = multiline
        browse = QPushButton("Browse…")
        browse.setProperty("variant", "secondary")
        browse.clicked.connect(self._browse)
        if multiline:
            self._edit = QPlainTextEdit()
            self._edit.setTabChangesFocus(True)
            fm = self._edit.fontMetrics()
            self._edit.setFixedHeight(fm.lineSpacing() * 3 + 14)
            self._edit.textChanged.connect(self.changed)
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(4)
            root.addWidget(self._edit)
            btn_row = QHBoxLayout()
            btn_row.setContentsMargins(0, 0, 0, 0)
            btn_row.addStretch(1)
            btn_row.addWidget(browse)
            root.addLayout(btn_row)
        else:
            self._edit = QLineEdit()
            self._edit.textChanged.connect(self.changed)
            row = QHBoxLayout(self)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(self._edit, 1)
            row.addWidget(browse)

    def _get_text(self):
        return self._edit.toPlainText() if self._multiline else self._edit.text()

    def _set_text(self, value):
        if self._multiline:
            self._edit.setPlainText(value or "")
        else:
            self._edit.setText(value or "")

    def _browse(self):
        start = self.path()
        if "<svg" in start.lower():          # don't seed the dialog with markup
            start = ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", start, _IMAGE_FILTER)
        if path:
            self._set_text(path)

    def path(self):
        return self._get_text().strip()

    def set_path(self, value):
        self._set_text(value)

    def set_placeholder(self, text):
        self._edit.setPlaceholderText(text or "")


class ElementConfigForm(QWidget):
    """Embeddable per-type config form.

    When *element* is given it is in **configure** mode: the element type is
    locked and every row is prefilled from the existing ``config`` so the same
    per-type form re-edits a live tile.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None, element=None):
        super().__init__(parent)
        self._element = element
        # the rows live in a scroll area so a tall config (e.g. indicator)
        # scrolls instead of clipping inside the fixed-height inspector panel
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        no_horizontal_scroll(scroll)
        inner = QWidget()
        self.form = QFormLayout(inner)
        compact_form(self.form)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        self.type_combo = QComboBox()
        shrink_combo(self.type_combo)
        for key, label in ELEMENT_LABELS.items():
            self.type_combo.addItem(label, key)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.form.addRow("Element type", self.type_combo)

        self.title_edit = QLineEdit()
        self.title_edit.textChanged.connect(self.changed)
        self.form.addRow("Title", self.title_edit)

        self.layer_combo = QgsMapLayerComboBox()
        shrink_combo(self.layer_combo)
        self.layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)
        self.layer_combo.layerChanged.connect(self._on_layer)
        self.form.addRow("Layer", self.layer_combo)

        # dynamic rows live in this dict so we can clear them on type change
        self._dyn = {}
        # non-config rows (kept for forms that need a control which is not a
        # managed config key) — tracked separately so they are NOT reported by
        # result_config()/managed_keys().
        self._extra_rows = []
        # the chart section's field rows depend on the selected chart_type; this
        # holds the type across a rebuild so switching it keeps the selection.
        self._pending_chart_type = None

        if element is not None:
            idx = self.type_combo.findData(element.type_name)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
            self.type_combo.setEnabled(False)   # type is fixed when editing
            self.title_edit.setText(element.config.get("title", ""))
            if element.type_name == "chart":
                self._pending_chart_type = element.config.get("chart_type")
            lyr = element.layer()
            if lyr is not None:
                self.layer_combo.setLayer(lyr)

        self._rebuild()
        if element is not None:
            self._load_values(element.config)
        if element is not None and element.type_name == "indicator":
            self._prefill_agg("statistic", "value_field", "value_expression",
                              element.config)
            self._prefill_agg("reference_statistic", "reference_field",
                              "reference_expression", element.config)

    def _spin(self, lo, hi, value):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(value)
        return s

    def _clear_dynamic(self):
        for w in list(self._dyn.values()) + self._extra_rows:
            lbl = self.form.labelForField(w)
            if lbl:
                lbl.deleteLater()
            w.deleteLater()
        self._dyn = {}
        self._extra_rows = []

    def _add_dyn(self, key, label, widget):
        # combos (incl. field/font pickers) would otherwise size to their
        # widest entry and overrun the narrow inspector panel — let them elide.
        if isinstance(widget, QComboBox):
            shrink_combo(widget)
        self._dyn[key] = widget
        self.form.addRow(label, widget)
        self._wire(widget)

    def _wire(self, widget):
        """Connect a dynamic control's change signal to :attr:`changed`."""
        if isinstance(widget, FieldListSelector):
            widget.changed.connect(self.changed)
            return
        if isinstance(widget, _PathPicker):
            widget.changed.connect(self.changed)
        elif isinstance(widget, QgsFieldComboBox):
            widget.fieldChanged.connect(lambda *_: self.changed.emit())
        elif isinstance(widget, QFontComboBox):
            widget.currentFontChanged.connect(lambda *_: self.changed.emit())
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(lambda *_: self.changed.emit())
        elif isinstance(widget, QCheckBox):
            widget.toggled.connect(lambda *_: self.changed.emit())
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(lambda *_: self.changed.emit())
        elif isinstance(widget, QPlainTextEdit):
            widget.textChanged.connect(self.changed)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda *_: self.changed.emit())

    def _field_combo(self, allow_empty=False, numeric=False):
        c = QgsFieldComboBox()
        if allow_empty:
            c.setAllowEmptyFieldName(True)
        if numeric:
            c.setFilters(QgsFieldProxyModel.Numeric)
        c.setLayer(self.layer_combo.currentLayer())
        return c

    def _field_list(self):
        w = FieldListSelector()
        w.set_layer(self.layer_combo.currentLayer())
        return w

    def _set_layer_row_visible(self, visible):
        lbl = self.form.labelForField(self.layer_combo)
        self.layer_combo.setVisible(visible)
        if lbl:
            lbl.setVisible(visible)

    def _on_type_changed(self):
        self._rebuild()
        self.changed.emit()

    def _rebuild(self):
        self._clear_dynamic()
        t = self.type_combo.currentData()
        self._set_layer_row_visible(t not in _LAYERLESS_TYPES)
        if t == "text":
            # text *content* is data; its typography/alignment live in the
            # Tile Appearance panel now.
            self._add_dyn("text", "Text", QPlainTextEdit())
        elif t == "image":
            # the image *file* is data; scaling/alignment live in Tile Appearance.
            self._add_dyn("path", "Image file", _PathPicker())
        elif t == "header":
            # the top-level "Title" row is the banner text (data); the banner's
            # fonts/colors/alignment and logo size/position live in Tile
            # Appearance, and the banner height is the generic tile size there.
            logo_picker = _PathPicker(multiline=True)
            logo_picker.set_placeholder("File path, or paste <svg …> code")
            self._add_dyn("logo_path", "Logo image (opt)", logo_picker)
            # gap between the logo and the title text (px); shown once a logo is
            # set, mirroring the indicator's icon spacing.
            self._add_dyn("logo_gap", "Logo spacing (px)", self._spin(0, 200, 12))
            logo_picker.changed.connect(
                lambda: self._set_row_visible(self._dyn.get("logo_gap"),
                                              bool(logo_picker.path())))
            self._set_row_visible(self._dyn.get("logo_gap"),
                                  bool(logo_picker.path()))
        elif t == "indicator":
            self._add_agg_rows("statistic", "value_field",
                               "value_expression", "Value")
            self._add_agg_rows("reference_statistic", "reference_field",
                               "reference_expression", "Reference")
            self._add_dyn("top_text", "Top label (opt)", QLineEdit(""))
            self._add_dyn("prefix", "Value prefix", QLineEdit(""))
            self._add_dyn("suffix", "Value suffix", QLineEdit(""))
            self._add_dyn("decimals", "Decimal places", self._spin(0, 6, 0))
            self._add_dyn("no_value_text", "No-data text", QLineEdit("No data"))
            icon_picker = _PathPicker(multiline=True)
            icon_picker.set_placeholder("File path, or paste <svg …> code")
            self._add_dyn("icon_path", "Icon image (opt)", icon_picker)
            # gap between the icon and the value (px); only relevant once an
            # icon is set, so the row appears when a path/SVG is present.
            self._add_dyn("icon_gap", "Icon spacing (px)", self._spin(0, 200, 10))
            icon_picker.changed.connect(
                lambda: self._set_row_visible(self._dyn.get("icon_gap"),
                                              bool(icon_picker.path())))
            self._set_row_visible(self._dyn.get("icon_gap"),
                                  bool(icon_picker.path()))
            self._sync_agg_rows("statistic", "value_field", "value_expression")
            self._sync_agg_rows("reference_statistic", "reference_field",
                                "reference_expression")
            # value text size, icon size/position and the value animation are
            # styling — configured from the Tile Appearance panel.
        elif t == "map":
            mode = QComboBox()
            for label, key in (("Off (don't filter)", "off"),
                               ("Visible extent (map frame)", "extent"),
                               ("Selected features", "selection"),
                               ("Relay active filter", "relay")):
                mode.addItem(label, key)
            i = mode.findData("extent")
            mode.setCurrentIndex(i if i >= 0 else 0)
            self._add_dyn("source_filter_mode", "Filter connected tiles by", mode)
        elif t == "chart":
            combo = QComboBox()
            for key in CHART_TYPE_ORDER:
                combo.addItem(CHART_SPECS[key]["label"], key)
            self._add_dyn("chart_type", "Chart type", combo)
            ct = self._pending_chart_type or DEFAULT_CHART_TYPE
            i = combo.findData(ct)
            if i >= 0:
                combo.setCurrentIndex(i)
            combo.currentIndexChanged.connect(self._on_chart_type_changed)
            self._add_chart_rows(combo.currentData())
        elif t == "pivot":
            self._add_dyn("row_field", "Row field", self._field_combo())
            self._add_dyn("col_field", "Column field (optional)",
                          self._field_combo(allow_empty=True))
            stat = QComboBox()
            stat.addItems(["count", "sum", "mean", "min", "max"])
            self._add_dyn("statistic", "Statistic", stat)
            self._add_dyn("value_field", "Value field (sum/mean/min/max)",
                          self._field_combo(numeric=True))
            chk = QCheckBox()
            chk.setChecked(True)
            self._add_dyn("show_totals", "Show totals", chk)
        elif t == "category_selector":
            self._add_dyn("category_field", "Category field", self._field_combo())
        elif t == "filter":
            # multi-field definition query: one dropdown per chosen column
            self._add_dyn("fields", "Filter fields", self._field_list())
        # legend takes no rows — it mirrors every layer on the map automatically
        elif t == "list":
            self._add_dyn("display_fields", "Columns to show", self._field_list())
            self._add_dyn("sort_field", "Sort by (optional)",
                          self._field_combo(allow_empty=True))
            direction = QComboBox()
            direction.addItem("Ascending", "asc")
            direction.addItem("Descending", "desc")
            self._add_dyn("sort_dir", "Sort direction", direction)

    def _on_chart_type_changed(self):
        """Rebuild the chart field rows for the newly-selected chart type.

        Field selections that survive the shape change (e.g. ``category_field``)
        are preserved by snapshotting the dynamic values and restoring them after
        the rebuild.
        """
        combo = self._dyn.get("chart_type")
        if combo is None:
            return
        new_type = combo.currentData()
        if new_type == self._pending_chart_type:
            return                       # no real change (e.g. reload echo)
        self._pending_chart_type = new_type
        snapshot = self._dynamic_values()
        self._rebuild()
        self._load_values(snapshot)
        self.changed.emit()

    def _add_chart_stat_value(self):
        stat = QComboBox()
        stat.addItems(["count", "sum", "mean"])
        self._add_dyn("statistic", "Statistic", stat)
        self._add_dyn("value_field", "Value field (sum/mean)",
                      self._field_combo(numeric=True))

    _STAT_LABELS = {"count": "Count", "sum": "Sum", "mean": "Average",
                    "min": "Minimum", "max": "Maximum"}

    def _add_agg_rows(self, stat_key, field_key, expr_key, label):
        """Statistic combo + field + Custom-expression row group.

        Writes the derived aggregate into *expr_key* (what the element reads);
        keeps *stat_key*/*field_key* for round-trip editing. ``custom`` reveals
        the raw expression line.
        """
        stat = QComboBox()
        for key in STATISTICS:
            stat.addItem(self._STAT_LABELS[key], key)
        stat.addItem("Custom expression…", "custom")
        self._add_dyn(stat_key, label + " statistic", stat)
        self._add_dyn(field_key, label + " field", self._field_combo(numeric=True))
        self._add_dyn(expr_key, label + " expression (custom)", QLineEdit(""))
        stat.currentIndexChanged.connect(
            lambda *_: self._sync_agg_rows(stat_key, field_key, expr_key))

    def _sync_agg_rows(self, stat_key, field_key, expr_key):
        """Show only the rows the current statistic needs."""
        stat = self._dyn.get(stat_key)
        field = self._dyn.get(field_key)
        expr = self._dyn.get(expr_key)
        if stat is None:
            return
        key = stat.currentData()
        self._set_row_visible(field, key in ("sum", "mean", "min", "max"))
        self._set_row_visible(expr, key == "custom")

    def _set_row_visible(self, widget, visible):
        if widget is None:
            return
        lbl = self.form.labelForField(widget)
        widget.setVisible(visible)
        if lbl:
            lbl.setVisible(visible)

    def _add_chart_rows(self, chart_type):
        """Add the field rows a chart type's data shape needs."""
        shape = shape_of(chart_type)
        if shape == "category":
            self._add_dyn("category_field", "Category field", self._field_combo())
            self._add_chart_stat_value()
        elif shape == "series":
            self._add_dyn("category_field", "Category field", self._field_combo())
            self._add_dyn("series_field", "Series field", self._field_combo())
            self._add_chart_stat_value()
        elif shape == "xy":
            self._add_dyn("x_field", "X field (numeric)",
                          self._field_combo(numeric=True))
            self._add_dyn("y_field", "Y field (numeric)",
                          self._field_combo(numeric=True))
        elif shape == "xyz":
            self._add_dyn("x_field", "X field (numeric)",
                          self._field_combo(numeric=True))
            self._add_dyn("y_field", "Y field (numeric)",
                          self._field_combo(numeric=True))
            self._add_dyn("size_field", "Size field (numeric)",
                          self._field_combo(numeric=True))
        elif shape == "bins":
            self._add_dyn("value_field", "Value field (numeric)",
                          self._field_combo(numeric=True))
            self._add_dyn("bin_count", "Number of bins", self._spin(2, 50, 10))
        elif shape == "ohlc":
            self._add_dyn("category_field", "Category (x) field", self._field_combo())
            self._add_dyn("open_field", "Open field", self._field_combo())
            self._add_dyn("high_field", "High field", self._field_combo())
            self._add_dyn("low_field", "Low field", self._field_combo())
            self._add_dyn("close_field", "Close field", self._field_combo())

    def _on_layer(self, _lyr):
        lyr = self.layer_combo.currentLayer()
        for w in self._dyn.values():
            if isinstance(w, QgsFieldComboBox):
                w.setLayer(lyr)
            elif isinstance(w, FieldListSelector):
                w.set_layer(lyr)
        self.changed.emit()

    def _load_values(self, config):
        """Prefill the dynamic rows from an existing element's config."""
        for key, w in self._dyn.items():
            if key not in config:
                continue
            val = config[key]
            if isinstance(w, QgsFieldComboBox):
                w.setField(val or "")
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(val))
            elif isinstance(w, QSpinBox):
                try:
                    w.setValue(int(val))
                except (TypeError, ValueError):
                    pass
            elif isinstance(w, QFontComboBox):
                # QFontComboBox subclasses QComboBox — must precede it here
                if val:
                    w.setCurrentFont(QFont(val))
            elif isinstance(w, QComboBox):
                i = w.findData(val)
                if i >= 0:
                    w.setCurrentIndex(i)
            elif isinstance(w, _PathPicker):
                w.set_path(val or "")
            elif isinstance(w, FieldListSelector):
                names = val if isinstance(val, list) else (
                    [s.strip() for s in val.split(",")] if isinstance(val, str)
                    else [])
                w.set_selected([n for n in names if n])
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(val if isinstance(val, str) else "")
            elif isinstance(w, QLineEdit):
                if key in ("display_fields", "fields") and isinstance(val, list):
                    w.setText(", ".join(val))
                else:
                    w.setText("" if val is None else str(val))

    def _prefill_agg(self, stat_key, field_key, expr_key, config):
        """Reverse-map a stored expression onto the Statistic+Field rows.

        Prefers an explicit ``statistic`` key; else parses the expression; else
        (for the reference) leaves it as an empty Custom so there is no ref.
        """
        stat_combo = self._dyn.get(stat_key)
        field_combo = self._dyn.get(field_key)
        if stat_combo is None:
            return
        explicit = config.get(stat_key)
        parsed = parse_aggregate(config.get(expr_key))
        if explicit:
            stat, field = explicit, config.get(field_key)
        elif parsed:
            stat, field = parsed[0], parsed[1]
        elif config.get(expr_key):
            stat, field = "custom", None          # unrecognized -> Custom
        elif expr_key == "value_expression":
            stat, field = "count", None           # value defaults to Count
        else:
            stat, field = "custom", None          # reference defaults to none
        i = stat_combo.findData(stat)
        if i >= 0:
            stat_combo.setCurrentIndex(i)
        if field and isinstance(field_combo, QgsFieldComboBox):
            field_combo.setField(field)
        self._sync_agg_rows(stat_key, field_key, expr_key)

    def managed_keys(self):
        """Config keys this form owns — so a configure-edit can drop the ones
        the user cleared (an absent key removes, rather than keeps, the old)."""
        keys = set(self._dyn.keys())
        keys.update({"title", "layer_id"})
        return keys

    def _dynamic_values(self, drop_empty=True):
        """Snapshot the current dynamic-row values keyed by config key.

        With *drop_empty* an empty QLineEdit drops its key (matching the
        configure-edit "cleared field removes the key" contract); the chart
        rebuild snapshot passes ``drop_empty=False`` so a partly-filled form is
        restored verbatim across a chart-type switch.
        """
        out = {}
        for key, w in self._dyn.items():
            if isinstance(w, QgsFieldComboBox):
                out[key] = w.currentField()
            elif isinstance(w, QCheckBox):
                out[key] = w.isChecked()
            elif isinstance(w, QSpinBox):
                out[key] = w.value()
            elif isinstance(w, QFontComboBox):
                # QFontComboBox subclasses QComboBox — must precede it here
                out[key] = w.currentFont().family()
            elif isinstance(w, QComboBox):
                data = w.currentData()
                out[key] = data if data is not None else w.currentText()
            elif isinstance(w, _PathPicker):
                out[key] = w.path()
            elif isinstance(w, FieldListSelector):
                names = w.selected()
                if names:
                    out[key] = names
                elif not drop_empty:
                    out[key] = []
            elif isinstance(w, QPlainTextEdit):
                out[key] = w.toPlainText()
            elif isinstance(w, QLineEdit):
                if key in _RAW_TEXT_KEYS:
                    # keep the spaces the user typed (e.g. a " sqm" suffix), so
                    # only an entirely empty field drops the key.
                    raw = w.text()
                    if raw:
                        out[key] = raw
                    elif not drop_empty:
                        out[key] = ""
                    continue
                val = w.text().strip()
                if val:
                    out[key] = ([s.strip() for s in val.split(",")]
                                if key in ("display_fields", "fields") else val)
                elif not drop_empty:
                    out[key] = ""
        return out

    def result_config(self):
        t = self.type_combo.currentData()
        cfg = {"title": self.title_edit.text() or ELEMENT_LABELS[t]}
        lyr = self.layer_combo.currentLayer()
        if lyr:
            cfg["layer_id"] = lyr.id()
        cfg.update(self._dynamic_values())
        if t == "indicator":
            self._resolve_agg(cfg, "statistic", "value_field",
                              "value_expression")
            self._resolve_agg(cfg, "reference_statistic", "reference_field",
                              "reference_expression")
        return t, cfg

    def _resolve_agg(self, cfg, stat_key, field_key, expr_key):
        """Turn Statistic+Field into the aggregate expr, unless Custom."""
        stat = cfg.get(stat_key)
        if stat == "custom":
            return                       # keep the user's raw expression as-is
        if stat is None:
            return
        expr = build_aggregate(stat, cfg.get(field_key))
        if expr:
            cfg[expr_key] = expr
        else:
            cfg.pop(expr_key, None)      # incomplete (e.g. Sum with no field)


class AddElementDialog(QDialog):
    """Modal wrapper around :class:`ElementConfigForm` (standalone / tests)."""

    def __init__(self, parent=None, element=None):
        super().__init__(parent)
        self.setWindowTitle("Configure element" if element else
                            "Add dashboard element")
        root = QVBoxLayout(self)
        self._form = ElementConfigForm(parent=self, element=element)
        root.addWidget(self._form, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                        | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        # re-expose the form's public surface so existing call sites / tests
        # (which reach in for these attributes) keep working unchanged.
        self.type_combo = self._form.type_combo
        self.title_edit = self._form.title_edit
        self.layer_combo = self._form.layer_combo

    @property
    def _dyn(self):
        # the form rebinds its dict on every type change, so always defer to it
        return self._form._dyn

    def managed_keys(self):
        return self._form.managed_keys()

    def result_config(self):
        return self._form.result_config()
