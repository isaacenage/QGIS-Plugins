# -*- coding: utf-8 -*-
"""Chart-type registry — declarative metadata + pure helpers.

Each entry in :data:`CHART_SPECS` describes one chart type so that a single
:class:`~.chart.ChartElement` can render it and the Add-element dialog can build
the right config rows. Adding a chart type is: register a painter (see
``charts/painters.py``) and add one row here.

This module is intentionally Qt-free so the helpers can be unit-tested without a
QGIS/Qt runtime.
"""

# type -> metadata. ``painter`` is a key into charts.painters.PAINTERS.
#
# ``shape`` declares the data contract the type consumes (see chart_data.py):
#   "category" -> [(category, value)]           (the original uniform contract)
#   "series"   -> {categories, series, matrix}  (grouped / stacked)
#   "xy"/"xyz" -> [(x, y[, size], label)]        (scatter / bubble)
#   "bins"     -> [(label, count, lo, hi)]        (histogram)
#   "ohlc"     -> [(label, o, h, l, c)]           (candlestick)
# Entries default to "category" when ``shape`` is omitted.
CHART_SPECS = {
    # ---- category shape (original contract) ----
    "bar": {
        "label": "Bar (vertical)", "group": "Comparison",
        "painter": "bar", "supports_statistic": True,
        "fold_other": False, "default_cap": 12, "inner": 0.0},
    "barh": {
        "label": "Bar (horizontal)", "group": "Comparison",
        "painter": "barh", "supports_statistic": True,
        "fold_other": False, "default_cap": 12, "inner": 0.0},
    "lollipop": {
        "label": "Lollipop (vertical)", "group": "Comparison",
        "painter": "lollipop", "supports_statistic": True,
        "fold_other": False, "default_cap": 12, "inner": 0.0},
    "lollipop_h": {
        "label": "Lollipop (horizontal)", "group": "Comparison",
        "painter": "lollipop_h", "supports_statistic": True,
        "fold_other": False, "default_cap": 12, "inner": 0.0},
    "dot": {
        "label": "Dot plot", "group": "Comparison",
        "painter": "dot", "supports_statistic": True,
        "fold_other": False, "default_cap": 14, "inner": 0.0},
    "radial_bar": {
        "label": "Radial bar", "group": "Comparison",
        "painter": "radial_bar", "supports_statistic": True,
        "fold_other": False, "default_cap": 8, "inner": 0.25},
    "radar": {
        "label": "Radar", "group": "Comparison",
        "painter": "radar", "supports_statistic": True,
        "fold_other": False, "default_cap": 12, "inner": 0.0},
    "line": {
        "label": "Line", "group": "Trend",
        "painter": "line", "supports_statistic": True,
        "fold_other": False, "default_cap": 20, "inner": 0.0},
    "step": {
        "label": "Stepped line", "group": "Trend",
        "painter": "step", "supports_statistic": True,
        "fold_other": False, "default_cap": 20, "inner": 0.0},
    "spline": {
        "label": "Spline (smooth)", "group": "Trend",
        "painter": "spline", "supports_statistic": True,
        "fold_other": False, "default_cap": 20, "inner": 0.0},
    "area": {
        "label": "Area", "group": "Trend",
        "painter": "area", "supports_statistic": True,
        "fold_other": False, "default_cap": 20, "inner": 0.0},
    "waterfall": {
        "label": "Waterfall", "group": "Trend",
        "painter": "waterfall", "supports_statistic": True,
        "fold_other": False, "default_cap": 14, "inner": 0.0},
    "pie": {
        "label": "Pie", "group": "Composition",
        "painter": "pie", "supports_statistic": False,
        "fold_other": True, "default_cap": 7, "inner": 0.0},
    "donut": {
        "label": "Donut", "group": "Composition",
        "painter": "pie", "supports_statistic": False,
        "fold_other": True, "default_cap": 7, "inner": 0.55},
    "rose": {
        "label": "Rose (polar area)", "group": "Composition",
        "painter": "rose", "supports_statistic": True,
        "fold_other": True, "default_cap": 10, "inner": 0.0},
    "funnel": {
        "label": "Funnel", "group": "Composition",
        "painter": "funnel", "supports_statistic": True,
        "fold_other": False, "default_cap": 10, "inner": 0.0},
    "treemap": {
        "label": "Treemap", "group": "Composition",
        "painter": "treemap", "supports_statistic": True,
        "fold_other": False, "default_cap": 20, "inner": 0.0},
    # ---- series shape (grouped / stacked) ----
    "grouped_bar": {
        "label": "Grouped bar", "group": "Comparison",
        "painter": "grouped_bar", "shape": "series",
        "supports_statistic": True, "fold_other": False,
        "default_cap": 10, "inner": 0.0},
    "stacked_bar": {
        "label": "Stacked bar", "group": "Comparison",
        "painter": "stacked_bar", "shape": "series",
        "supports_statistic": True, "fold_other": False,
        "default_cap": 12, "inner": 0.0},
    # ---- xy / xyz shape (scatter / bubble) ----
    "scatter": {
        "label": "Scatter", "group": "Distribution",
        "painter": "scatter", "shape": "xy",
        "supports_statistic": False, "fold_other": False,
        "default_cap": 0, "inner": 0.0},
    "bubble": {
        "label": "Bubble", "group": "Distribution",
        "painter": "bubble", "shape": "xyz",
        "supports_statistic": False, "fold_other": False,
        "default_cap": 0, "inner": 0.0},
    # ---- bins shape (histogram) ----
    "histogram": {
        "label": "Histogram", "group": "Distribution",
        "painter": "histogram", "shape": "bins",
        "supports_statistic": False, "fold_other": False,
        "default_cap": 0, "inner": 0.0},
    # ---- ohlc shape (candlestick) ----
    "candlestick": {
        "label": "Candlestick", "group": "Distribution",
        "painter": "candlestick", "shape": "ohlc",
        "supports_statistic": False, "fold_other": False,
        "default_cap": 60, "inner": 0.0},
}

# Display order for the Add-element dialog combo (grouped by theme).
CHART_TYPE_ORDER = [
    "bar", "barh", "lollipop", "lollipop_h", "dot", "radial_bar", "radar",
    "line", "step", "spline", "area", "waterfall",
    "pie", "donut", "rose", "funnel", "treemap",
    "grouped_bar", "stacked_bar",
    "scatter", "bubble", "histogram", "candlestick",
]

DEFAULT_CHART_TYPE = "bar"


def shape_of(chart_type):
    """Return the data shape of ``chart_type`` (defaults to ``"category"``)."""
    return spec_for(chart_type).get("shape", "category")


def spec_for(chart_type):
    """Return the spec for ``chart_type`` (falling back to the default)."""
    return CHART_SPECS.get(chart_type, CHART_SPECS[DEFAULT_CHART_TYPE])


def _is_number(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def filter_literal(field, value):
    """Build a ``"field" = value`` expression, quoting non-numeric values."""
    if _is_number(value):
        return '"{}" = {}'.format(field, value)
    return '"{}" = \'{}\''.format(field, value)


def fold_categories(items, cap, fold_other=False):
    """Cap an ordered ``[(category, value)]`` list.

    With ``fold_other`` the tail past ``cap`` is summed into an ``"Other"``
    bucket (pie/donut); otherwise the list is simply truncated (bars/lines).
    """
    if not cap or cap <= 0 or len(items) <= cap:
        return list(items)
    head = list(items[:cap])
    if fold_other:
        other = sum(float(v) for _, v in items[cap:])
        head.append(("Other", other))
    return head
