# -*- coding: utf-8 -*-
"""Pure aggregation helpers for the non-category chart shapes.

The original chart contract is a uniform ``[(category, value)]`` list produced
by :meth:`ChartElement._aggregate`. The Tier-2 chart types (grouped/stacked
bars, scatter/bubble, histogram, candlestick) need richer data shapes, so each
shape gets a producer here. These functions are intentionally **Qt-free / QGIS-
free** — they operate on plain Python rows (``list`` of ``dict``) and numbers —
so they can be unit-tested without a QGIS runtime, exactly like
``pivot_engine.compute_pivot``.

Data shapes (what each producer returns; consumed by the matching painter):

* ``series`` → ``{"categories": [str], "series": [str], "matrix": [[float]]}``
* ``xy``     → ``[(x, y, label)]``
* ``xyz``    → ``[(x, y, size, label)]``
* ``bins``   → ``[(label, count, lo, hi)]``
* ``ohlc``   → ``[(label, open, high, low, close)]``
* ``squarify`` is a geometry helper used by the treemap painter.
"""

from collections import OrderedDict, defaultdict


def _num(value):
    """Coerce to ``float`` or return ``None`` (QGIS NULL is a null QVariant)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reduce(values, stat):
    """Reduce a list of numbers by ``count`` / ``sum`` / ``mean``."""
    if stat == "count":
        return float(len(values))
    nums = [v for v in (_num(x) for x in values) if v is not None]
    if not nums:
        return 0.0
    if stat == "sum":
        return float(sum(nums))
    if stat == "mean":
        return float(sum(nums) / len(nums))
    return float(len(values))


def aggregate_series(rows, cat_field, series_field, value_field, stat,
                     cat_cap=12, series_cap=8):
    """Group ``rows`` by category x series into a dense matrix.

    Returns ``{"categories", "series", "matrix"}`` where ``matrix[i][j]`` is the
    aggregate for category ``i`` and series ``j`` (0 where a pair is absent).
    Categories and series are ordered by descending grand total and capped.
    """
    if not cat_field or not series_field:
        return {"categories": [], "series": [], "matrix": []}

    buckets = defaultdict(list)            # (cat, series) -> [values]
    cat_totals = defaultdict(float)
    series_totals = defaultdict(float)
    for r in rows:
        cat = str(r.get(cat_field))
        ser = str(r.get(series_field))
        raw = 1 if stat == "count" else r.get(value_field)
        buckets[(cat, ser)].append(raw)

    # cell aggregates first (so ordering uses real reduced values)
    cells = {key: _reduce(vals, stat) for key, vals in buckets.items()}
    for (cat, ser), v in cells.items():
        cat_totals[cat] += v
        series_totals[ser] += v

    cats = [c for c, _ in sorted(cat_totals.items(),
                                 key=lambda kv: kv[1], reverse=True)][:cat_cap]
    sers = [s for s,
            _ in sorted(series_totals.items(),
                        key=lambda kv: kv[1],
                        reverse=True)][:series_cap]
    matrix = [[cells.get((c, s), 0.0) for s in sers] for c in cats]
    return {"categories": cats, "series": sers, "matrix": matrix}


def collect_points(rows, x_field, y_field, size_field=None, cap=2000):
    """Read raw ``(x, y[, size], label)`` tuples; drop non-numeric, cap count."""
    if not x_field or not y_field:
        return []
    out = []
    for r in rows:
        x = _num(r.get(x_field))
        y = _num(r.get(y_field))
        if x is None or y is None:
            continue
        if size_field:
            s = _num(r.get(size_field))
            if s is None:
                continue
            out.append((x, y, s, ""))
        else:
            out.append((x, y, ""))
        if len(out) >= cap:
            break
    return out


def histogram_bins(values, bin_count):
    """Bin numeric ``values`` into ``bin_count`` equal-width buckets.

    Returns ``[(label, count, lo, hi)]``. The final bin is inclusive of the max.
    Returns ``[]`` when there is no numeric data.
    """
    nums = [v for v in (_num(x) for x in values) if v is not None]
    if not nums:
        return []
    try:
        bins = max(1, int(bin_count))
    except (TypeError, ValueError):
        bins = 10
    lo, hi = min(nums), max(nums)
    if hi == lo:                      # degenerate: one bin holding everything
        return [(_range_label(lo, hi), float(len(nums)), lo, hi)]
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in nums:
        idx = int((v - lo) / width)
        if idx >= bins:              # the max value lands in the last bin
            idx = bins - 1
        counts[idx] += 1
    out = []
    for i, c in enumerate(counts):
        b_lo = lo + i * width
        b_hi = lo + (i + 1) * width
        out.append((_range_label(b_lo, b_hi), float(c), b_lo, b_hi))
    return out


def _range_label(lo, hi):
    def f(v):
        v = float(v)
        return "{:g}".format(round(v, 2))
    return "{}–{}".format(f(lo), f(hi))


def aggregate_ohlc(rows, cat_field, open_field, high_field, low_field,
                   close_field, cap=60):
    """Build ``[(label, open, high, low, close)]`` grouped by category.

    Within a category (in first-seen order) ``open`` is the first row's open,
    ``high`` the max high, ``low`` the min low, ``close`` the last row's close.
    Rows missing any of the four numeric values are skipped.
    """
    if not (cat_field and open_field and high_field and low_field
            and close_field):
        return []
    groups = OrderedDict()
    for r in rows:
        o = _num(r.get(open_field))
        h = _num(r.get(high_field))
        lo = _num(r.get(low_field))
        c = _num(r.get(close_field))
        if None in (o, h, lo, c):
            continue
        cat = str(r.get(cat_field))
        if cat not in groups:
            groups[cat] = [o, h, lo, c]      # open, high, low, close
        else:
            g = groups[cat]
            g[1] = max(g[1], h)
            g[2] = min(g[2], lo)
            g[3] = c                          # last close wins
    out = [(cat, g[0], g[1], g[2], g[3]) for cat, g in groups.items()]
    return out[:cap]


def squarify(values, x, y, width, height):
    """Squarified treemap layout.

    Given a list of positive ``values`` and a bounding rect, return a list of
    ``(value_index, rx, ry, rw, rh)`` rectangles whose areas are proportional to
    the values and whose aspect ratios are kept close to 1. Pure geometry — no
    Qt — so it is unit-testable. Implements Bruls/Huizing/van Wijk squarify.
    """
    items = [(i, float(v)) for i, v in enumerate(values) if float(v) > 0]
    if not items or width <= 0 or height <= 0:
        return []
    total = sum(v for _, v in items)
    scale = (width * height) / total
    scaled = [(i, v * scale) for i, v in items]      # areas in px^2

    rects = []
    rx, ry, rw, rh = float(x), float(y), float(width), float(height)
    row = []
    i = 0
    while i < len(scaled):
        shortest = min(rw, rh)
        if not row:
            row = [scaled[i]]
            i += 1
            continue
        if _worst(row, shortest) >= _worst(row + [scaled[i]], shortest):
            row.append(scaled[i])
            i += 1
        else:
            rx, ry, rw, rh = _layout_row(row, rx, ry, rw, rh, rects)
            row = []
    if row:
        _layout_row(row, rx, ry, rw, rh, rects)
    return rects


def _worst(row, shortest):
    areas = [a for _, a in row]
    s = sum(areas)
    if s <= 0:
        return float("inf")
    side = s / shortest
    hi = max(areas)
    lo = min(areas)
    return max((side * side * hi) / (s * s), (s * s) / (side * side * lo))


def _layout_row(row, rx, ry, rw, rh, rects):
    s = sum(a for _, a in row)
    if rw >= rh:                      # lay the row down a left-hand column
        col_w = s / rh if rh else 0
        oy = ry
        for idx, a in row:
            h = a / col_w if col_w else 0
            rects.append((idx, rx, oy, col_w, h))
            oy += h
        return rx + col_w, ry, rw - col_w, rh
    else:                             # lay the row across a top strip
        row_h = s / rw if rw else 0
        ox = rx
        for idx, a in row:
            w = a / row_h if row_h else 0
            rects.append((idx, ox, ry, w, row_h))
            ox += w
        return rx, ry + row_h, rw, rh - row_h
