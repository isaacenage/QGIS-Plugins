# -*- coding: utf-8 -*-
"""Statistic + field <-> aggregate-expression helpers (pure, no Qt/QGIS).

The indicator element renders from a QGIS aggregate expression string
(``config["value_expression"]``, e.g. ``sum("pop")``) so the dashboard filter
splices in via ``base.evaluate``'s ``filter:=`` injection. This module lets the
config form offer a friendly Statistic + Field builder while still writing that
same expression string — so ``indicator.py`` is unchanged and older dashboards
(which stored a raw expression) keep working.

Kept top-level (not under ``elements/``) so it imports without the QGIS-laden
``elements`` package ``__init__``, matching the repo's other pure helpers
(``zoom_fit``, ``layout_util``, ``tile_snap``) — so it is unit-testable with a
plain Python interpreter.
"""

import re

# Ordered for the config-form combo; "count" first (the default, field-less).
STATISTICS = ("count", "sum", "mean", "min", "max")

_FIELD_STATS = ("sum", "mean", "min", "max")
_ALIASES = {"average": "mean", "avg": "mean"}

_COUNT_RE = re.compile(r"^\s*count\s*\(\s*1\s*\)\s*$", re.IGNORECASE)
_AGG_RE = re.compile(r'^\s*(sum|mean|min|max)\s*\(\s*"([^"]+)"\s*\)\s*$',
                     re.IGNORECASE)


def build_aggregate(statistic, field):
    """(statistic, field) -> aggregate expression string, or None if invalid."""
    stat = (statistic or "").strip().lower()
    stat = _ALIASES.get(stat, stat)
    if stat in ("", "count"):
        return "count(1)"
    if stat not in _FIELD_STATS:
        return None
    name = (field or "").strip()
    if not name:
        return None
    return '{}("{}")'.format(stat, name)


def parse_aggregate(expr):
    """Best-effort reverse map; anything not a clean aggregate -> None."""
    if not expr:
        return None
    if _COUNT_RE.match(expr):
        return ("count", None)
    m = _AGG_RE.match(expr)
    if m:
        return (m.group(1).lower(), m.group(2))
    return None
