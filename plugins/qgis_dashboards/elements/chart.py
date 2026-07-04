# -*- coding: utf-8 -*-
"""Generic chart element.

One element renders every category chart type (bar / barh / line / area /
pie / donut). ``config["chart_type"]`` selects the painter from the registry
(``charts/painters.py``); the binding and behavior are shared: group features
by a category field, aggregate a statistic per group, and act as a filter
SOURCE — clicking a bar/point/slice pushes ``"category = X"`` tagged with this
element's id; clicking the same one again clears it.

This replaces the former ``serial_chart`` and ``pie_chart`` element classes;
their saved configs are migrated to ``chart`` in ``elements/__init__.py``.
"""

from collections import defaultdict

from .base import DashboardElement
from .chart_specs import (
    spec_for, shape_of, fold_categories, filter_literal, DEFAULT_CHART_TYPE,
)
from . import chart_data
from .charts.painters import PAINTERS


class ChartElement(DashboardElement):
    type_name = "chart"
    is_filter_source = True

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        self.view = None
        self._build_view()
        self._selected = None
        self._produced = []
        self.apply_theme()
        self.refresh()

    # ---- spec / appearance ----

    def _chart_type(self):
        return self.config.get("chart_type", DEFAULT_CHART_TYPE)

    def _spec(self):
        return spec_for(self._chart_type())

    def _shape(self):
        return shape_of(self._chart_type())

    def _painter_cls(self):
        return PAINTERS.get(self._spec()["painter"], PAINTERS["bar"])

    def _build_view(self):
        """Create the painter widget matching the current ``chart_type``."""
        painter_cls = self._painter_cls()
        self.view = painter_cls()          # instantiate — _painter_cls returns the class
        self.view.categoryClicked.connect(self._on_category)
        self.body.addWidget(self.view)

    def reconfigure(self):
        """Swap the painter widget when the chart type changed, then refresh.

        The base ``reconfigure`` only re-applies theme + data; the painter is
        chosen once in ``__init__``, so without this a chart_type change would
        keep the original painter (every chart would stay a bar chart). An exact
        type check is required because ``area`` subclasses ``line`` — an
        ``isinstance`` check would not detect a line<->area switch.
        """
        if type(self.view) is not self._painter_cls():
            old = self.view
            try:
                old.categoryClicked.disconnect(self._on_category)
            except (TypeError, RuntimeError):
                pass
            self.body.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
            self._build_view()
        super().reconfigure()

    def _restyle(self):
        self.view.set_theme(self.effective_theme())
        # per-tile Plot-role overrides (axis/label color + font, value labels)
        self.view.set_style({
            "axis_color": self.style_get("axis_color"),
            "axis_font": self.style_get("axis_font"),
            "axis_px": self.style_get("axis_px"),
            "show_value_labels": self.style_get("show_value_labels", True),
        })

    # ---- data ----

    def _stat(self):
        """The effective statistic (forced to count when unsupported)."""
        if not self._spec().get("supports_statistic"):
            return "count"
        return self.config.get("statistic", "count")

    def _rows(self, fields):
        """Yield ``{field: value}`` dicts for the requested fields.

        Bridges QGIS features to the Qt-free producers in ``chart_data``: it
        materializes only the fields a shape needs, so the pure helpers never
        touch a QgsFeature.
        """
        fields = [f for f in fields if f]
        for feat in self.iter_features():
            yield {f: feat[f] for f in fields}

    def _aggregate(self):
        """Return ordered (category, value) pairs under the current filter."""
        cat_field = self.config.get("category_field")
        if not cat_field:
            return []
        spec = self._spec()
        stat = self._stat()
        value_field = self.config.get("value_field")

        buckets = defaultdict(list)
        for f in self.iter_features():
            key = f[cat_field]
            if stat == "count":
                buckets[str(key)].append(1)
            else:
                # QGIS NULL is a null QVariant (not None) and breaks sum();
                # coerce and drop non-numerics.
                try:
                    buckets[str(key)].append(float(f[value_field]))
                except (TypeError, ValueError):
                    continue

        out = []
        for k, vals in buckets.items():
            if stat == "count":
                out.append((k, len(vals)))
            elif stat == "sum":
                out.append((k, sum(vals)))
            elif stat == "mean":
                out.append((k, sum(vals) / len(vals) if vals else 0))
        out.sort(key=lambda x: x[1], reverse=True)

        cap = self.style_get("max_categories", spec.get("default_cap", 12))
        return fold_categories(out, int(cap), spec.get("fold_other", False))

    def _produce(self):
        """Produce the data payload for the active chart shape."""
        shape = self._shape()
        cfg = self.config
        if shape == "series":
            cap = int(self.style_get("max_categories",
                                     self._spec().get("default_cap", 10)))
            return chart_data.aggregate_series(
                self._rows([cfg.get("category_field"), cfg.get("series_field"),
                            cfg.get("value_field")]),
                cfg.get("category_field"), cfg.get("series_field"),
                cfg.get("value_field"), self._stat(), cat_cap=cap)
        if shape in ("xy", "xyz"):
            size = cfg.get("size_field") if shape == "xyz" else None
            return chart_data.collect_points(
                self._rows([cfg.get("x_field"), cfg.get("y_field"), size]),
                cfg.get("x_field"), cfg.get("y_field"), size)
        if shape == "bins":
            vf = cfg.get("value_field")
            vals = [r.get(vf) for r in self._rows([vf])]
            return chart_data.histogram_bins(vals, cfg.get("bin_count", 10))
        if shape == "ohlc":
            return chart_data.aggregate_ohlc(
                self._rows([cfg.get("category_field"), cfg.get("open_field"),
                            cfg.get("high_field"), cfg.get("low_field"),
                            cfg.get("close_field")]),
                cfg.get("category_field"), cfg.get("open_field"),
                cfg.get("high_field"), cfg.get("low_field"),
                cfg.get("close_field"))
        return self._aggregate()

    def refresh(self):
        self._produced = self._produce()
        self._render_selection()

    def _render_selection(self):
        """Redraw the current data with the current selection — no re-query.

        Used both by ``refresh`` and directly on a click so the highlighted bar
        updates instantly, independent of the (possibly heavy) cross-filter
        fan-out. A source-only chart is not a filter target, so its own
        ``filtersChanged`` is a no-op for it; without this its selection would
        otherwise only repaint as a side effect of an unrelated refresh.
        """
        self.view.set_data(self._produced, self._selected,
                           self._spec().get("inner", 0.0))

    # ---- bus reaction ----

    def _on_filters_cleared(self):
        self._selected = None

    def _filter_for(self, cat):
        """Build the filter expression a clicked element should push."""
        if self._shape() == "bins":
            vf = self.config.get("value_field")
            if not vf:
                return None
            for label, _count, lo, hi in (self._produced or []):
                if label == cat:
                    return '"{0}" >= {1} AND "{0}" < {2}'.format(vf, lo, hi)
            return None
        cat_field = self.config.get("category_field")
        if not cat_field:
            return None
        return filter_literal(cat_field, cat)

    def _on_category(self, cat):
        if not self._interactive:   # Build mode: clicks don't cross-filter
            return
        if cat == "Other":
            return
        if self._shape() in ("xy", "xyz"):   # point clouds don't cross-filter
            return
        if self._selected == cat:                # toggle off
            self._selected = None
            self._render_selection()             # instant feedback, then fan out
            self.bus.set_filter(self.id, None)
        else:
            expr = self._filter_for(cat)
            if expr is None:
                return
            self._selected = cat
            self._render_selection()             # instant feedback, then fan out
            self.bus.set_filter(self.id, expr)
