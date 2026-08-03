# -*- coding: utf-8 -*-
"""AutoCAD lineweights — the fixed millimetre ladder CAD plots with.

Pure module: no Qt, no QGIS.

AutoCAD lineweights are **plot widths in millimetres**, drawn from a fixed
24-step ladder plus three sentinels (ByLayer, ByBlock, Default). This maps onto
QGIS with no approximation at all: a QGIS symbol width expressed in
``RenderMillimeters`` *is* a plot width in millimetres. That makes lineweight
the one part of the AutoCAD look that transfers exactly.

Values are stored in hundredths of a millimetre (the same integer encoding DXF
uses) so they compare and serialise exactly, with no float drift.
"""

BYLAYER = -1
BYBLOCK = -2
DEFAULT = -3

#: The fixed AutoCAD lineweight ladder, in hundredths of a millimetre.
LADDER = (
    0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50,
    53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211,
)

#: What "Default" resolves to when a layer does not override it (LWDEFAULT).
DEFAULT_HUNDREDTHS = 25

#: Width used for every entity when lineweight display is switched off
#: (AutoCAD's LWDISPLAY = 0). A hairline, not zero, so lines stay visible.
HAIRLINE_MM = 0.05


def to_mm(hundredths):
    """Convert a lineweight in hundredths of a millimetre to millimetres.

    Sentinels (ByLayer/ByBlock/Default) resolve to the default width; callers
    that can resolve ByLayer properly should do so *before* calling this.
    """
    value = int(hundredths)
    if value < 0:
        value = DEFAULT_HUNDREDTHS
    if value == 0:
        # AutoCAD lineweight 0.00 means "thinnest the device can draw".
        return HAIRLINE_MM
    return value / 100.0


def snap_to_ladder(hundredths):
    """Return the ladder entry closest to *hundredths*.

    DXF files in the wild carry off-ladder values; AutoCAD itself snaps them.
    Sentinels pass through untouched.
    """
    value = int(hundredths)
    if value < 0:
        return value
    return min(LADDER, key=lambda step: abs(step - value))


def label(hundredths):
    """Return the display label AutoCAD shows for a lineweight."""
    value = int(hundredths)
    if value == BYLAYER:
        return "ByLayer"
    if value == BYBLOCK:
        return "ByBlock"
    if value == DEFAULT:
        return "Default"
    return "{0:.2f} mm".format(value / 100.0)


def choices(include_sentinels=True):
    """Return ``[(label, value), ...]`` for a lineweight combo box."""
    items = []
    if include_sentinels:
        items.extend([
            (label(BYLAYER), BYLAYER),
            (label(BYBLOCK), BYBLOCK),
            (label(DEFAULT), DEFAULT),
        ])
    items.extend([(label(step), step) for step in LADDER])
    return items


def resolve(entity_lw, layer_lw, display_enabled=True):
    """Resolve an entity's effective plot width in millimetres.

    *entity_lw* may be a real width or ByLayer/ByBlock/Default; *layer_lw* is
    the owning layer's width. When *display_enabled* is False (LWDISPLAY off)
    every entity draws as a hairline, which is what AutoCAD does.
    """
    if not display_enabled:
        return HAIRLINE_MM

    value = int(entity_lw)
    if value in (BYLAYER, BYBLOCK):
        value = int(layer_lw)
    if value == DEFAULT:
        value = DEFAULT_HUNDREDTHS
    if value < 0:
        # A layer set to ByLayer/ByBlock is meaningless — fall back to default.
        value = DEFAULT_HUNDREDTHS
    return to_mm(value)
