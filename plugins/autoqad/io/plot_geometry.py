# -*- coding: utf-8 -*-
"""Plot geometry — sheets, plot scale and the extent that fills them.

Pure module: no Qt, no QGIS. Everything here is arithmetic on numbers, which is
exactly why it lives apart from :mod:`.plot`: the awkward part of plotting is
the scale maths, and the awkward part is the part worth unit-testing.

The one relationship the whole module turns on::

    1 mm on paper at 1:S  ==  S mm on the ground
                          ==  (S / 1000) metres
                          ==  (S / 1000) * units_per_metre map units

*units_per_metre* is how many of the map CRS's units make a metre — 1 for a
metre-based projection, 3.28084 for a foot-based one, 1000 for a drawing whose
units are millimetres. It is the only place CRS knowledge enters, and the caller
supplies it, so this module never imports QGIS.

Sheet sizes are stored **portrait** (width <= height) and turned by
:func:`page_size`, which is how every plot dialog presents them.
"""

from collections import namedtuple

#: One paper size, in millimetres, portrait.
Sheet = namedtuple("Sheet", "name width height")

#: The sheets AutoQAD offers, ISO first because the rest of the plugin is metric.
SHEETS = (
    Sheet("ISO A4", 210.0, 297.0),
    Sheet("ISO A3", 297.0, 420.0),
    Sheet("ISO A2", 420.0, 594.0),
    Sheet("ISO A1", 594.0, 841.0),
    Sheet("ISO A0", 841.0, 1189.0),
    Sheet("ANSI A (Letter)", 215.9, 279.4),
    Sheet("ANSI B (Tabloid)", 279.4, 431.8),
    Sheet("ANSI C", 431.8, 558.8),
    Sheet("ANSI D", 558.8, 863.6),
    Sheet("ANSI E", 863.6, 1117.6),
    Sheet("ARCH A", 228.6, 304.8),
    Sheet("ARCH B", 304.8, 457.2),
    Sheet("ARCH C", 457.2, 609.6),
    Sheet("ARCH D", 609.6, 914.4),
    Sheet("ARCH E1", 762.0, 1066.8),
)

#: The sheet a fresh plot starts on.
DEFAULT_SHEET = "ISO A3"

#: Default distance from the sheet edge to the drawing frame, in millimetres.
DEFAULT_MARGIN_MM = 10.0

#: A frame narrower than this is not a plot, it is a rounding error.
MIN_FRAME_MM = 5.0

#: How much of a pad "fit to paper" leaves around the drawing, as a fraction.
#: AutoCAD fits tight; a couple of percent stops linework sitting exactly on
#: the frame edge, where a printer's own margin can clip it.
FIT_PADDING = 0.02

#: Extent used when a drawing has no entities (or one, at a single point).
EMPTY_EXTENT_SIZE = 100.0


def _mantissa_scales():
    """Generate the standard CAD scale denominators, smallest first.

    Decade-stepped through the mantissas draughtsmen actually use, so the
    nearest standard scale to any fit is never more than ~25% away.
    """
    values = []
    decade = 1.0
    while decade <= 100000.0:
        for mantissa in (1.0, 2.0, 2.5, 4.0, 5.0):
            value = decade * mantissa
            if value <= 200000.0:
                values.append(value)
        decade *= 10.0
    return tuple(sorted(set(values)))


#: Standard plot scale denominators — the 1:*N* list the dialog offers.
STANDARD_SCALES = _mantissa_scales()


# --- sheets ------------------------------------------------------------------


def sheet_names():
    """Every sheet name, in offer order."""
    return [s.name for s in SHEETS]


def sheet(name):
    """Return the named :class:`Sheet`, falling back to :data:`DEFAULT_SHEET`.

    Matching is case- and space-insensitive so ``"a3"`` finds ``"ISO A3"``.
    """
    key = str(name or "").strip().lower()
    for candidate in SHEETS:
        if candidate.name.lower() == key:
            return candidate
    for candidate in SHEETS:
        if key and key in candidate.name.lower():
            return candidate
    for candidate in SHEETS:
        if candidate.name == DEFAULT_SHEET:
            return candidate
    return SHEETS[0]


def page_size(name, landscape=True):
    """Return ``(width_mm, height_mm)`` for the named sheet in this orientation."""
    found = sheet(name)
    if landscape:
        return (max(found.width, found.height), min(found.width, found.height))
    return (min(found.width, found.height), max(found.width, found.height))


def frame_size(name, landscape=True, margin_mm=DEFAULT_MARGIN_MM):
    """Return the printable ``(width_mm, height_mm)`` inside the margins.

    A margin that would swallow the sheet is clamped rather than rejected, so a
    dialog spinner cannot produce a zero-sized or inverted frame.
    """
    width, height = page_size(name, landscape)
    margin = max(0.0, float(margin_mm))
    inner_w = width - 2.0 * margin
    inner_h = height - 2.0 * margin
    if inner_w < MIN_FRAME_MM or inner_h < MIN_FRAME_MM:
        # Give back the largest centred frame the sheet can actually hold.
        margin = max(0.0, min((width - MIN_FRAME_MM) / 2.0,
                              (height - MIN_FRAME_MM) / 2.0))
        inner_w = width - 2.0 * margin
        inner_h = height - 2.0 * margin
    return (max(MIN_FRAME_MM, inner_w), max(MIN_FRAME_MM, inner_h))


def frame_origin(name, landscape=True, margin_mm=DEFAULT_MARGIN_MM):
    """Return the frame's top-left ``(x_mm, y_mm)`` on the sheet."""
    width, height = page_size(name, landscape)
    frame_w, frame_h = frame_size(name, landscape, margin_mm)
    return (max(0.0, (width - frame_w) / 2.0), max(0.0, (height - frame_h) / 2.0))


# --- scale -------------------------------------------------------------------


def paper_mm_to_map_units(millimetres, denominator, units_per_metre=1.0):
    """Convert a paper distance to ground distance at 1:*denominator*."""
    return (float(millimetres) * float(units_per_metre)
            * float(denominator) / 1000.0)


def map_units_to_paper_mm(units, denominator, units_per_metre=1.0):
    """The inverse of :func:`paper_mm_to_map_units`."""
    scale = float(denominator) * float(units_per_metre)
    if scale <= 0.0:
        return 0.0
    return float(units) * 1000.0 / scale


def fit_scale(extent_width, extent_height, frame_width_mm, frame_height_mm,
              units_per_metre=1.0, padding=FIT_PADDING):
    """Return the 1:*N* denominator at which the extent just fills the frame.

    The larger of the two axis requirements wins, so the whole drawing lands
    inside the frame rather than the wider half of it. *padding* leaves a
    fractional margin; pass 0 for AutoCAD's tight fit.

    Returns 1.0 for a degenerate extent or frame — a scale that is at least
    usable, rather than a division by zero.
    """
    frame_w = float(frame_width_mm)
    frame_h = float(frame_height_mm)
    upm = float(units_per_metre)
    if frame_w <= 0.0 or frame_h <= 0.0 or upm <= 0.0:
        return 1.0

    grow = 1.0 + max(0.0, float(padding))
    width = max(0.0, float(extent_width)) * grow
    height = max(0.0, float(extent_height)) * grow
    if width <= 0.0 and height <= 0.0:
        return 1.0

    by_width = width * 1000.0 / (frame_w * upm)
    by_height = height * 1000.0 / (frame_h * upm)
    return max(by_width, by_height, 1e-9)


def extent_size(frame_width_mm, frame_height_mm, denominator,
                units_per_metre=1.0):
    """Return the ``(width, height)`` in map units the frame covers at 1:*N*."""
    return (paper_mm_to_map_units(frame_width_mm, denominator, units_per_metre),
            paper_mm_to_map_units(frame_height_mm, denominator, units_per_metre))


def nearest_standard_scale(denominator, choices=None, round_up=True):
    """Snap *denominator* to a standard CAD scale.

    With *round_up* (the default) the result is never smaller than the input,
    so snapping a fit scale can only ever pull the drawing further inside the
    frame — never crop it.
    """
    value = float(denominator)
    options = tuple(choices or STANDARD_SCALES)
    if value <= 0.0 or not options:
        return value
    if round_up:
        for candidate in options:
            if candidate >= value - 1e-9:
                return candidate
        return options[-1]
    return min(options, key=lambda c: abs(c - value))


def format_scale(denominator):
    """Render a denominator the way a title block would: ``1:100``, ``2:1``."""
    value = float(denominator)
    if value <= 0.0:
        return "1:1"
    if value < 1.0:
        factor = 1.0 / value
        return "{0}:1".format(format_number(factor))
    return "1:{0}".format(format_number(value))


def format_number(value):
    """Format a float the way a scale reads: ``100``, not ``100.0``."""
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return "{0:.4g}".format(value)


# --- extents -----------------------------------------------------------------
#
# Extents are plain ``(xmin, ymin, xmax, ymax)`` tuples so the maths stays
# testable; ``plot.py`` converts to and from ``QgsRectangle`` at the boundary.


def normalise_extent(extent):
    """Return *extent* with its corners ordered, or ``None``."""
    if extent is None:
        return None
    try:
        xmin, ymin, xmax, ymax = (float(v) for v in extent)
    except (TypeError, ValueError):
        return None
    return (min(xmin, xmax), min(ymin, ymax), max(xmin, xmax), max(ymin, ymax))


def extent_centre(extent):
    xmin, ymin, xmax, ymax = normalise_extent(extent)
    return ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)


def extent_dimensions(extent):
    xmin, ymin, xmax, ymax = normalise_extent(extent)
    return (xmax - xmin, ymax - ymin)


def centred_extent(centre_x, centre_y, width, height):
    """Build an extent of *width* x *height* around a centre point."""
    half_w = max(0.0, float(width)) / 2.0
    half_h = max(0.0, float(height)) / 2.0
    return (float(centre_x) - half_w, float(centre_y) - half_h,
            float(centre_x) + half_w, float(centre_y) + half_h)


def ensure_area(extent, minimum=EMPTY_EXTENT_SIZE):
    """Give a zero-width or zero-height extent a usable size.

    A drawing holding one point has a zero-area bounding box; plotting it would
    ask for an infinite scale. Growing it around its centre is the only answer
    that keeps the point where the user put it.
    """
    bounds = normalise_extent(extent)
    if bounds is None:
        return centred_extent(0.0, 0.0, minimum, minimum)
    centre_x, centre_y = extent_centre(bounds)
    width, height = extent_dimensions(bounds)
    if width > 0.0 and height > 0.0:
        return bounds
    return centred_extent(centre_x, centre_y,
                          width if width > 0.0 else float(minimum),
                          height if height > 0.0 else float(minimum))


def inflate(extent, factor=FIT_PADDING):
    """Grow an extent by a fraction of its size, around its centre."""
    bounds = ensure_area(extent)
    if factor <= 0.0:
        return bounds
    centre_x, centre_y = extent_centre(bounds)
    width, height = extent_dimensions(bounds)
    grow = 1.0 + float(factor)
    return centred_extent(centre_x, centre_y, width * grow, height * grow)


def fit_to_aspect(extent, frame_width_mm, frame_height_mm):
    """Grow *extent* around its centre until it matches the frame's aspect.

    Only ever grows, so nothing that was inside the extent falls outside it —
    which is what makes this safe to use as "the extent that plots".
    """
    bounds = ensure_area(extent)
    frame_w = float(frame_width_mm)
    frame_h = float(frame_height_mm)
    if frame_w <= 0.0 or frame_h <= 0.0:
        return bounds

    centre_x, centre_y = extent_centre(bounds)
    width, height = extent_dimensions(bounds)
    frame_aspect = frame_w / frame_h
    extent_aspect = width / height if height > 0.0 else frame_aspect

    if extent_aspect > frame_aspect:
        height = width / frame_aspect          # too wide: grow vertically
    else:
        width = height * frame_aspect          # too tall: grow horizontally
    return centred_extent(centre_x, centre_y, width, height)


def plot_extent(extent, frame_width_mm, frame_height_mm, denominator=None,
                units_per_metre=1.0, padding=FIT_PADDING):
    """Return the extent to hand a layout map, and the scale it plots at.

    With *denominator* the extent is sized to that exact scale around the
    subject's centre — AutoCAD's "plot at 1:100 whatever fits". Without it the
    subject is fitted to the frame and the resulting scale is reported back.

    Returns ``(extent, denominator)``.
    """
    bounds = ensure_area(extent)
    if denominator is not None and float(denominator) > 0.0:
        centre_x, centre_y = extent_centre(bounds)
        width, height = extent_size(frame_width_mm, frame_height_mm,
                                    denominator, units_per_metre)
        return (centred_extent(centre_x, centre_y, width, height),
                float(denominator))

    width, height = extent_dimensions(bounds)
    scale = fit_scale(width, height, frame_width_mm, frame_height_mm,
                      units_per_metre, padding)
    fitted = fit_to_aspect(inflate(bounds, padding),
                           frame_width_mm, frame_height_mm)
    return (fitted, scale)
