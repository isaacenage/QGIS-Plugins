# -*- coding: utf-8 -*-
"""Pure expression builders for the Legend (and Filter) widgets.

A Legend tile reads its layer's categorized/graduated renderer and lets the user
toggle classes on/off; the *checked* classes become a cross-filter expression
pushed onto the bus. This module turns a set of checked values (or value ranges)
into a QgsExpression string that is also a valid provider ``subsetString`` (so
the map can render the filtered subset by cloning its layer).

It is deliberately Qt/QGIS-free (a plain string builder) so it can be
unit-tested on its own, following the :mod:`pivot_engine` / :mod:`chart_data`
precedent.

Conventions:
  * all classes checked  -> ``None`` (no filter)
  * a subset checked     -> ``"field" IN (...)`` (+ ``IS NULL`` when NULL chosen)
  * nothing checked      -> ``"field" IN (NULL)`` (matches no feature, in both
    QgsExpression and provider SQL — ``x IN (NULL)`` is never true)
"""


def _literal(value):
    """Quote a scalar for a QgsExpression / SQL ``IN`` list."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return "'{}'".format(str(value).replace("'", "''"))


def _match_nothing(field):
    return '"{}" IN (NULL)'.format(field)


def categories_to_expression(field, selected_values, total_count):
    """Filter *field* to *selected_values* (a list of checked category values).

    Returns ``None`` when every class is selected (``len >= total_count``), and a
    never-true expression when nothing is selected. ``None`` values map to
    ``"field" IS NULL``.
    """
    if not field:
        return None
    if total_count and len(selected_values) >= total_count:
        return None
    non_null = [v for v in selected_values if v is not None]
    has_null = any(v is None for v in selected_values)
    parts = []
    if non_null:
        parts.append('"{}" IN ({})'.format(
            field, ", ".join(_literal(v) for v in non_null)))
    if has_null:
        parts.append('"{}" IS NULL'.format(field))
    if not parts:
        return _match_nothing(field)
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def ranges_to_expression(field, selected_ranges, total_count):
    """Filter *field* to *selected_ranges* (a list of ``(lo, hi)`` pairs).

    Returns ``None`` when every range is selected, a never-true expression when
    none are. Each range is ``"field" >= lo AND "field" <= hi``; multiple ranges
    are OR-ed.
    """
    if not field:
        return None
    if total_count and len(selected_ranges) >= total_count:
        return None
    if not selected_ranges:
        return _match_nothing(field)
    clauses = ['("{0}" >= {1} AND "{0}" <= {2})'.format(
        field, _literal(lo), _literal(hi)) for lo, hi in selected_ranges]
    if len(clauses) == 1:
        return clauses[0]
    return "(" + " OR ".join(clauses) + ")"
