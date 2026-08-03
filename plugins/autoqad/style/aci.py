# -*- coding: utf-8 -*-
"""The AutoCAD Color Index (ACI) — the 256-colour palette CAD drawings use.

Pure module: no Qt, no QGIS. Colours are ``(r, g, b)`` int triples so the table
is unit-testable without a QGIS runtime.

The palette is *generated*, not transcribed, because it has an exact closed
form. Indices 10-249 are 24 hues at 15 degree steps, each in 5 brightness
levels, each level in a saturated and a half-saturated ("pastel") variant::

    index 10 -> hue   0, level 255, saturated      -> (255,   0,   0)
    index 11 -> hue   0, level 255, half-saturated -> (255, 127, 127)
    index 12 -> hue   0, level 165, saturated      -> (165,   0,   0)
    ...
    index 30 -> hue  30, level 255, saturated      -> (255, 127,   0)
    index 90 -> hue 120, level 255, saturated      -> (  0, 255,   0)

Indices 0-9 (ByBlock plus the seven "standard" colours plus two greys) and
250-255 (a grey ramp) are fixed and listed explicitly.

Index 7 is special: it means "white on a dark background, black on a light
one". :func:`rgb` returns white for it; :func:`display_rgb` resolves it against
a background colour, which is what the renderer actually wants.
"""

# ACI 0 is ByBlock and 256 is ByLayer — neither is a real colour.
BYBLOCK = 0
BYLAYER = 256

# Fixed low indices. 7 is the "contrast" colour (see module docstring).
_LOW = {
    1: (255, 0, 0),        # red
    2: (255, 255, 0),      # yellow
    3: (0, 255, 0),        # green
    4: (0, 255, 255),      # cyan
    5: (0, 0, 255),        # blue
    6: (255, 0, 255),      # magenta
    7: (255, 255, 255),    # white / black — resolved against the background
    8: (128, 128, 128),    # dark grey
    9: (192, 192, 192),    # light grey
}

# Fixed grey ramp at the top of the table.
_HIGH = {
    250: (51, 51, 51),
    251: (91, 91, 91),
    252: (132, 132, 132),
    253: (173, 173, 173),
    254: (214, 214, 214),
    255: (255, 255, 255),
}

# The five brightness levels each hue steps through.
_LEVELS = (255, 165, 127, 76, 38)


def _hsv_to_rgb(hue_deg, saturation, value):
    """Convert HSV to an integer RGB triple.

    *hue_deg* is in degrees, *saturation* in 0..1, *value* in 0..255. Values are
    truncated (not rounded) to match the reference palette exactly.
    """
    if saturation <= 0.0:
        v = int(value)
        return (v, v, v)

    sector = (hue_deg % 360.0) / 60.0
    i = int(sector)
    f = sector - i

    p = value * (1.0 - saturation)
    q = value * (1.0 - saturation * f)
    t = value * (1.0 - saturation * (1.0 - f))

    if i == 0:
        r, g, b = value, t, p
    elif i == 1:
        r, g, b = q, value, p
    elif i == 2:
        r, g, b = p, value, t
    elif i == 3:
        r, g, b = p, q, value
    elif i == 4:
        r, g, b = t, p, value
    else:
        r, g, b = value, p, q
    return (int(r), int(g), int(b))


def _build_table():
    table = {0: (0, 0, 0)}
    table.update(_LOW)
    for index in range(10, 250):
        offset = index - 10
        hue = (offset // 10) * 15.0
        level = _LEVELS[(offset % 10) // 2]
        saturation = 1.0 if offset % 2 == 0 else 0.5
        table[index] = _hsv_to_rgb(hue, saturation, level)
    table.update(_HIGH)
    return table


TABLE = _build_table()


def rgb(index):
    """Return the ``(r, g, b)`` triple for ACI *index* (0-255).

    Out-of-range indices fall back to ACI 7.
    """
    try:
        index = int(index)
    except (TypeError, ValueError):
        return TABLE[7]
    return TABLE.get(index, TABLE[7])


def display_rgb(index, background_is_dark=False):
    """Resolve ACI *index* for display against a light or dark background.

    ACI 7 renders white on dark backgrounds and black on light ones — the one
    index whose appearance depends on context. Every other index is absolute.
    """
    if int(index) == 7:
        return (255, 255, 255) if background_is_dark else (0, 0, 0)
    return rgb(index)


def hex_color(index, background_is_dark=False):
    """Return ACI *index* as a ``#rrggbb`` string."""
    r, g, b = display_rgb(index, background_is_dark)
    return "#{0:02x}{1:02x}{2:02x}".format(r, g, b)


def nearest_index(r, g, b):
    """Return the ACI index whose colour is closest to ``(r, g, b)``.

    Used when importing true-colour geometry into an ACI-indexed drawing.
    Searches 1-255 (0 and 256 are ByBlock/ByLayer, not colours).
    """
    best_index = 7
    best_distance = None
    for index in range(1, 256):
        tr, tg, tb = TABLE[index]
        distance = (tr - r) ** 2 + (tg - g) ** 2 + (tb - b) ** 2
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_index = index
            if distance == 0:
                break
    return best_index


#: Human-readable names for the indices that have them (the CAD standard seven).
NAMES = {
    1: "Red", 2: "Yellow", 3: "Green", 4: "Cyan",
    5: "Blue", 6: "Magenta", 7: "White/Black",
    8: "Dark Grey", 9: "Light Grey",
    BYLAYER: "ByLayer", BYBLOCK: "ByBlock",
}


def name(index):
    """Return a display label for ACI *index*."""
    return NAMES.get(int(index), "ACI {0}".format(index))
