# -*- coding: utf-8 -*-
"""Pure, Qt-free one-click auto-arrange layout.

Computes gap-free tile rectangles that fill the dashboard page (the canvas
export/print region's *content* area) while honoring per-element shape biases.
The sidebar's "Auto-arrange" button calls this through a thin wrapper in
``window.py``; this module has no Qt/QGIS dependency so it is unit-testable
without QGIS (see ``test/test_auto_layout.py``), mirroring ``zoom_fit.py`` and
``layout_util.py``.

Contract: ``compute_auto_layout(items, width, height)`` returns one logical
``(x, y, w, h)`` rect per input item (index-aligned to ``items``) tiling the
``width x height`` rectangle **exactly** — no overlap, no gap. Shape rules are
biases; exact fill always wins.
"""

import math

# Charts whose natural shape is roughly square (circular / area fills).
_CIRCULAR_CHARTS = frozenset({
    "pie", "donut", "rose", "radar", "radial_bar", "treemap"})

# Per-role ordering for the main band (lower = earlier / more prominent).
_ROLE_ORDER = {
    "map": 0, "chart": 1, "pivot": 2, "list": 2,
    "category_selector": 3, "text": 4, "image": 4}

# At most this many indicators on one row before wrapping to a second row.
_MAX_INDICATORS_PER_ROW = 6


def shape_for(type_name, chart_type=None):
    """Return ``(aspect, weight)`` for an element.

    ``aspect`` is the target width/height ratio (>1 landscape, 1 square,
    <1 portrait); ``weight`` is the relative area priority (bigger -> larger
    tile). These drive the justified-row sizing in :func:`compute_auto_layout`.
    """
    if type_name == "map":
        return (1.0, 3.0)            # biggest tile, ~square
    if type_name in ("list", "pivot"):
        return (0.7, 1.3)            # portrait (taller than wide)
    if type_name == "chart":
        if chart_type in _CIRCULAR_CHARTS:
            return (1.0, 1.2)        # circular charts -> square
        return (1.6, 1.2)            # bars/lines/etc -> wide landscape
    if type_name == "category_selector":
        return (2.5, 0.6)            # a dropdown: wide and short
    if type_name in ("text", "image"):
        return (1.4, 0.8)
    if type_name == "indicator":
        return (1.4, 0.6)
    return (1.4, 1.0)                # unknown -> flexible


def compute_auto_layout(items, width, height):
    """Gap-free rects filling ``width x height``, one per item (input order).

    ``items``: list of ``(type_name, chart_type_or_None)``.
    Returns ``[(x, y, w, h), ...]`` aligned to ``items``.
    """
    n = len(items)
    if n == 0:
        return []
    W = max(1, int(width))
    H = max(1, int(height))
    if n == 1:
        return [(0, 0, W, H)]

    headers = [i for i, (t, _) in enumerate(items) if t == "header"]
    indicators = [i for i, (t, _) in enumerate(items) if t == "indicator"]
    main = [i for i, (t, _) in enumerate(items)
            if t not in ("header", "indicator")]

    # Bands stacked top -> bottom; the bottom-most present band fills the
    # remaining height so the page is covered exactly.
    groups = []
    if headers:
        groups.append(("header", headers))
    if indicators:
        groups.append(("indicator", indicators))
    if main:
        groups.append(("main", main))

    rects = [None] * n
    y = 0
    for gi, (kind, idxs) in enumerate(groups):
        last = (gi == len(groups) - 1)
        avail = H - y
        if last:
            gh = avail
        elif kind == "header":
            gh = _clamp(int(round(H * 0.12)), 40, avail - 1)
            gh = min(gh, max(1, avail - 1))  # never consume all remaining px
        else:  # indicator strip with a main band below it
            gh = _clamp(int(round(H * 0.18)), 60, avail - 1)
            gh = min(gh, max(1, avail - 1))  # never consume all remaining px
        if kind == "header":
            _lay_equal_row(rects, idxs, y, W, gh)
        elif kind == "indicator":
            _lay_indicators(rects, idxs, y, W, gh)
        else:
            _lay_main(rects, items, idxs, y, W, gh)
        y += gh
    return rects


def _lay_equal_row(rects, idxs, y, W, h):
    """Lay *idxs* as equal-width adjacent cells across the full width."""
    widths = _equal_ints(W, len(idxs))
    x = 0
    for i, wi in zip(idxs, widths):
        rects[i] = (x, y, wi, h)
        x += wi


def _lay_indicators(rects, idxs, y, W, h):
    """Equal, adjacent KPI cells; wrap to a second row past the per-row cap."""
    k = len(idxs)
    rows = 1 if k <= _MAX_INDICATORS_PER_ROW else 2
    # items per row, as even as possible
    counts = _equal_ints(k, rows)
    heights = _equal_ints(h, rows)
    ry = y
    start = 0
    for r in range(rows):
        c = counts[r]
        _lay_equal_row(rects, idxs[start:start + c], ry, W, heights[r])
        ry += heights[r]
        start += c


def _lay_main(rects, items, idxs, y, W, H):
    """Justified-row packing of the main tiles into ``W x H`` (origin x=0, y)."""
    # reading order: map, charts, lists/pivots, selectors, text/image
    order = sorted(idxs, key=lambda i: (_ROLE_ORDER.get(items[i][0], 5), i))
    entries = []                              # (orig_index, aspect, weight)
    for i in order:
        t, ct = items[i]
        a, wt = shape_for(t, ct)
        entries.append((i, a, wt))

    rows = _row_count(entries, W, H)
    counts = _equal_ints(len(entries), rows)  # even item count per row

    groups = []
    s = 0
    for c in counts:
        groups.append(entries[s:s + c])
        s += c

    # Natural row height from width-justification, then boosted by the row's
    # heaviest tile so the map's row is taller (-> map is the biggest tile).
    nat = []
    for g in groups:
        denom = sum(a * math.sqrt(wt) for (_, a, wt) in g) or 1.0
        boost = math.sqrt(max(wt for (_, _, wt) in g))
        nat.append((W / denom) * boost)
    heights = _proportional_ints(nat, H)      # sum to H exactly

    ry = y
    for g, gh in zip(groups, heights):
        # linear weight (not sqrt) so the heaviest tile — the map — claims the
        # most width; this is what makes the map the biggest tile. Differs
        # deliberately from the sqrt(wt) used in the row-height denominator
        # above.
        wkeys = [a * wt for (_, a, wt) in g]
        widths = _proportional_ints(wkeys, W)  # sum to W exactly
        cx = 0
        for (i, _, _), wi in zip(g, widths):
            rects[i] = (cx, ry, wi, gh)
            cx += wi
        ry += gh


def _row_count(entries, W, H):
    """Pick a row count so cells roughly keep their mean target aspect."""
    n = len(entries)
    if n <= 1:
        return 1
    mean_a = sum(a for (_, a, _) in entries) / n
    r = round(math.sqrt(max(1.0, n * mean_a * H / float(W))))
    return max(1, min(n, int(r)))


def _clamp(v, lo, hi):
    if hi < lo:
        return lo
    return max(lo, min(hi, v))


def _equal_ints(total, k):
    """*k* near-equal integers summing exactly to *total*."""
    return _proportional_ints([1.0] * k, total)


def _proportional_ints(weights, total):
    """Integers proportional to *weights* summing exactly to *total*.

    Cumulative rounding: the running rounded cumulative always lands on
    ``total`` at the end, so the pieces sum to exactly ``total``.

    Precondition: ``total`` is large relative to the number of weights and
    weights are not vanishingly small, so every returned piece is >= 1.
    Both conditions hold for all callers in this module — page dimensions
    are hundreds of pixels and shape weights are >= 0.6 — so no ``max(1,
    ...)`` clamp is applied.  Adding such a clamp would break the exact-sum
    (exact-tiling) guarantee.
    """
    s = sum(weights) or 1.0
    out = []
    prev = 0
    acc = 0.0
    for w in weights:
        acc += w
        cum = int(round(acc / s * total))
        out.append(cum - prev)
        prev = cum
    return out
