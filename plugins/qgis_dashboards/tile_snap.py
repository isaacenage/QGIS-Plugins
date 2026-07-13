# -*- coding: utf-8 -*-
"""Pure, Qt-free geometry helpers for magnetic tile drop placement.

The dashboard canvas (``dashboard_canvas.py``) uses these while a tile is
dragged so it lands flush against its neighbours and the page edges instead of
reverting to its drag-start position. Everything here works on plain
``(x, y, w, h)`` logical-pixel tuples so it can be unit-tested without QGIS
(see ``test/test_tile_snap.py``), exactly like ``zoom_fit.py``.

Two operations:

* :func:`snap_rect` — *magnetic edge snapping*. Keeps the tile's size and pulls
  each edge to the nearest neighbour/page snap line within a threshold, spacing
  neighbours by the global Element Gap.
* :func:`nearest_free` — *no-revert fallback*. When a drop overlaps something,
  finds the closest same-size placement that fits.
"""


def rects_overlap(a, b):
    """True if two ``(x, y, w, h)`` rects overlap (touching edges do not)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _nearest_line(value, lines, threshold):
    """Return the line nearest to *value* within *threshold*, else ``None``."""
    best = None
    best_d = threshold
    for ln in lines:
        d = abs(ln - value)
        if d <= best_d:
            best_d = d
            best = ln
    return best


def snap_rect(rect, others, region, gap, threshold):
    """Magnetically snap *rect*'s edges to neighbours/page edges, keeping size.

    ``rect`` is the dragged tile's proposed logical ``(x, y, w, h)``; ``others``
    the other tiles' logical rects; ``region`` the ``(w, h)`` page size; ``gap``
    the Element Gap kept between snapped neighbours; ``threshold`` the maximum
    logical-pixel distance an edge is pulled from.

    Size is fixed, so per axis only one edge can win — whichever of the two
    opposite edges sits closer to its nearest snap line. Returns the (possibly)
    moved rect; unchanged when no edge is in range.
    """
    x, y, w, h = rect
    region_w, region_h = region

    # ---- horizontal axis: left edge vs right edge ----
    left_lines = [0]
    right_lines = [region_w]
    for ox, oy, ow, oh in others:
        left_lines.append(ox + ow + gap)   # sit to the right of a neighbour
        left_lines.append(ox)              # align lefts
        right_lines.append(ox - gap)       # sit to the left of a neighbour
        right_lines.append(ox + ow)        # align rights

    left_target = _nearest_line(x, left_lines, threshold)
    right_target = _nearest_line(x + w, right_lines, threshold)
    left_d = abs(left_target - x) if left_target is not None else None
    right_d = abs(right_target - (x + w)) if right_target is not None else None
    if left_d is not None and (right_d is None or left_d <= right_d):
        x = left_target
    elif right_d is not None:
        x = right_target - w

    # ---- vertical axis: top edge vs bottom edge ----
    top_lines = [0]
    bottom_lines = [region_h]
    for ox, oy, ow, oh in others:
        top_lines.append(oy + oh + gap)
        top_lines.append(oy)
        bottom_lines.append(oy - gap)
        bottom_lines.append(oy + oh)

    top_target = _nearest_line(y, top_lines, threshold)
    bottom_target = _nearest_line(y + h, bottom_lines, threshold)
    top_d = abs(top_target - y) if top_target is not None else None
    bottom_d = abs(bottom_target - (y + h)
                   ) if bottom_target is not None else None
    if top_d is not None and (bottom_d is None or top_d <= bottom_d):
        y = top_target
    elif bottom_d is not None:
        y = bottom_target - h

    return (x, y, w, h)


def _fits(rect, others, region):
    """True if *rect* is in-bounds (within region) and overlaps no *others*."""
    x, y, w, h = rect
    region_w, region_h = region
    if x < 0 or y < 0 or x + w > region_w or y + h > region_h:
        return False
    return not any(rects_overlap(rect, o) for o in others)


def nearest_free(rect, others, region, step=8):
    """Closest same-size placement of *rect* that fits, else *rect* unchanged.

    Returns *rect* immediately when it already fits. Otherwise spiral-searches
    the *step* grid outward from the drop origin (clamped into the region) for
    the nearest non-overlapping in-bounds slot. If the region is too packed to
    hold the tile, returns *rect* unchanged — the caller still places it (this
    layer never reverts a move).
    """
    if _fits(rect, others, region):
        return rect

    x, y, w, h = rect
    region_w, region_h = region
    max_x = max(region_w - w, 0)
    max_y = max(region_h - h, 0)

    best = None
    best_d = None
    radius = step
    # rings of increasing radius around the original origin; stop once a ring
    # has been fully exhausted with a hit (closer hits are found on inner
    # rings)
    max_radius = max(region_w, region_h)
    while radius <= max_radius:
        found_on_ring = False
        for dx in range(-radius, radius + 1, step):
            for dy in range(-radius, radius + 1, step):
                # only the perimeter of the current ring
                if abs(dx) != radius and abs(dy) != radius:
                    continue
                cx = min(max(x + dx, 0), max_x)
                cy = min(max(y + dy, 0), max_y)
                cand = (cx, cy, w, h)
                if _fits(cand, others, region):
                    d = (cx - x) ** 2 + (cy - y) ** 2
                    if best_d is None or d < best_d:
                        best_d = d
                        best = cand
                        found_on_ring = True
        if found_on_ring:
            return best
        radius += step
    return best if best is not None else rect
