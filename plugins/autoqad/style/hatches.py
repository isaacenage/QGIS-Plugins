# -*- coding: utf-8 -*-
"""AutoCAD hatch patterns — a real ``acad.pat`` parser plus the standard set.

Pure module: no Qt, no QGIS.

An AutoCAD hatch pattern is a stack of infinite **line families**. Each family
is one line of the definition::

    *ANSI31, ANSI Iron / Brick / Stone masonry
    45, 0,0, 0,.125

which reads: *angle*, *origin-x*, *origin-y*, *delta-x*, *delta-y*, then an
optional dash pattern. ``delta-y`` is the perpendicular spacing between
repeats of the line; ``delta-x`` is the offset applied along the line direction
for each successive repeat (what produces staggered patterns like BRICK).

This maps cleanly onto QGIS: **one line family becomes one
``QgsLinePatternFillSymbolLayer``**, and a multi-family pattern becomes that
many stacked symbol layers. ANSI31 (one family), ANSI37 and NET (two families
at 90 degrees), BRICK (a staggered family plus a plain one) all reproduce
faithfully.

The one honest limitation: QGIS line-pattern fills have no per-repeat
``delta-x`` stagger. Patterns that rely on it (BRICK, ANSI33) reproduce their
line *families* exactly but draw the offset rows in line rather than staggered.
:attr:`HatchPattern.needs_stagger` flags those so the UI can say so.
"""

import math
import re

_HEADER_RE = re.compile(r"^\*([^,]+)\s*(?:,(.*))?$")


class LineFamily(object):
    """One line family within a hatch pattern. Lengths are in drawing units."""

    __slots__ = ("angle", "origin_x", "origin_y", "delta_x", "delta_y", "dashes")

    def __init__(self, angle, origin_x, origin_y, delta_x, delta_y, dashes=None):
        self.angle = float(angle)
        self.origin_x = float(origin_x)
        self.origin_y = float(origin_y)
        self.delta_x = float(delta_x)
        self.delta_y = float(delta_y)
        self.dashes = list(dashes or [])

    @property
    def spacing(self):
        """Perpendicular distance between repeats, always positive."""
        return abs(self.delta_y) or 0.125

    @property
    def is_dashed(self):
        return bool(self.dashes)

    def dash_vector(self, scale=1.0):
        """Return ``[dash, gap, ...]`` for this family, scaled by *scale*."""
        if not self.dashes:
            return []
        vector = []
        expecting_dash = True
        for element in self.dashes:
            length = (abs(element) or 1e-3) * scale
            is_dash = element >= 0
            if is_dash != expecting_dash:
                vector.append(1e-3 * scale)
                expecting_dash = not expecting_dash
            vector.append(length)
            expecting_dash = not expecting_dash
        if len(vector) % 2:
            vector.append(1e-3 * scale)
        return vector

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<LineFamily {0}deg d={1}>".format(self.angle, self.delta_y)


class HatchPattern(object):
    """A named hatch pattern: a description plus one or more line families."""

    __slots__ = ("name", "description", "families", "is_solid")

    def __init__(self, name, description="", families=None, is_solid=False):
        self.name = name
        self.description = description
        self.families = list(families or [])
        self.is_solid = is_solid

    @property
    def needs_stagger(self):
        """True when a family uses ``delta-x`` (see the module docstring)."""
        return any(abs(f.delta_x) > 1e-9 for f in self.families)

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<HatchPattern {0} x{1}>".format(self.name, len(self.families))


def parse_pat(text):
    """Parse ``.pat`` file *text* into an ordered ``{name: HatchPattern}`` dict.

    Malformed families are skipped rather than raising, so one bad line in a
    user-supplied pattern file cannot stop the rest from loading.
    """
    patterns = {}
    current = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue

        header = _HEADER_RE.match(line)
        if header:
            name = header.group(1).strip().upper()
            description = (header.group(2) or "").strip()
            current = HatchPattern(name, description,
                                   is_solid=(name == "SOLID"))
            patterns[name] = current
            continue

        if current is None:
            continue

        parts = []
        for chunk in line.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                parts.append(float(chunk))
            except ValueError:
                parts = []
                break

        if len(parts) >= 5:
            current.families.append(
                LineFamily(parts[0], parts[1], parts[2],
                           parts[3], parts[4], parts[5:]))
    return patterns


# --- the standard acad.pat patterns -----------------------------------------
#
# The subset a building drawing actually uses, transcribed from the published
# AutoCAD pattern definitions. Load a full acad.pat over the top with
# :func:`parse_pat` to get the rest.

STANDARD_PAT = """
*SOLID, Solid fill
45, 0,0, 0,.125
*ANSI31, ANSI Iron / Brick / Stone masonry
45, 0,0, 0,.125
*ANSI32, ANSI Steel
45, 0,0, 0,.375
45, .176776695,0, 0,.375
*ANSI33, ANSI Bronze / Brass / Copper
45, 0,0, 0,.25
45, .176776695,0, 0,.25, .125,-.0625
*ANSI34, ANSI Plastic / Rubber
45, 0,0, 0,.75
45, .176776695,0, 0,.75
45, .353553391,0, 0,.75
45, .530330086,0, 0,.75
*ANSI35, ANSI Fire brick / Refractory material
45, 0,0, 0,.25
45, .176776695,0, 0,.25, .3125,-.0625,0,-.0625
*ANSI36, ANSI Marble / Slate / Glass
45, 0,0, .21875,.125, .3125,-.0625,0,-.0625
*ANSI37, ANSI Lead / Zinc / Magnesium / Sound insulation
45, 0,0, 0,.125
135, 0,0, 0,.125
*ANSI38, ANSI Aluminum
45, 0,0, 0,.125
135, 0,0, 0,.125, .3125,-.1875
*NET, Horizontal / vertical grid
0, 0,0, 0,.125
90, 0,0, 0,.125
*NET3, Network pattern 0-60-120
0, 0,0, 0,.125
60, 0,0, 0,.125
120, 0,0, 0,.125
*LINE, Parallel horizontal lines
0, 0,0, 0,.125
*ANGLE, Angle steel
0, 0,0, 0,.275, .2,-.075
90, 0,0, 0,.275, .2,-.075
*BRICK, Standard brick pattern
0, 0,0, 0,.25
90, 0,0, .25,.25, .25,-.25
*BRSTONE, Brick and stone
0, 0,0, 0,.25
90, 0,0, .5,.25, .25,-.25
*CROSS, A series of crosses
0, 0,0, .25,.25, .125,-.375
90, .0625,-.0625, .25,.25, .125,-.375
*DASH, Dashed lines
0, 0,0, .125,.125, .125,-.125
*DOTS, A series of dots
0, 0,0, .03125,.0625, 0,-.0625
*EARTH, Earth or ground
0, 0,0, .25,.25, .25,-.125
90, 0,0, .25,.25, .25,-.125
*GRASS, Grass area
90, 0,0, .5,.866025403, .1875,-.6875
45, 0,0, .5,.866025403, .1875,-.6875
135, 0,0, .5,.866025403, .1875,-.6875
*GRAVEL, Gravel pattern
0, 0,0, .25,.125, .0625,-.1875
0, .125,.0625, .25,.125, .0625,-.1875
*HEX, Hexagons
0, 0,0, .1875,.108253175, .125,-.25
120, 0,0, .1875,.108253175, .125,-.25
60, .108253175,.0625, .1875,.108253175, .125,-.25
*HONEY, Honeycomb pattern
0, 0,0, .1875,.108253175, .125,-.25
120, 0,0, .1875,.108253175, .125,-.25
60, .108253175,.0625, .1875,.108253175, .125,-.25
*HOUND, Houndstooth check
0, 0,0, .25,.0625, .5,-.25
90, 0,0, .25,.0625, .5,-.25
*MUDST, Mud and sand
0, 0,0, .25,.125, .0625,-.1875
*PLAST, Plastic material
0, 0,0, 0,.25
*SACNCR, Concrete
45, 0,0, 0,.09375
*SQUARE, Small aligned squares
0, 0,0, .125,.125, .125,-.125
90, 0,0, .125,.125, .125,-.125
*STARS, Star of David
0, 0,0, 0,.216506351, .125,-.125
60, 0,0, 0,.216506351, .125,-.125
120, .0625,.108253175, 0,.216506351, .125,-.125
*STEEL, Steel material
45, 0,0, 0,.125
*SWAMP, Swampy area
0, 0,0, .5,.866025403, .125,-.875
90, .0625,0, .866025403,.5, .0625,-1.669550983
90, .09375,0, .866025403,.5, .03125,-1.70080098
90, .03125,0, .866025403,.5, .03125,-1.70080098
*TRANS, Heat transfer material
0, 0,0, 0,.25
0, 0,.125, 0,.25, .125,-.125
*TRIANG, Equilateral triangles
60, 0,0, .1875,.324759526, .1875,-.1875
120, 0,0, .1875,.324759526, .1875,-.1875
0, -.09375,.162379763, .1875,.324759526, .1875,-.1875
*ZIGZAG, Staircase effect
0, 0,0, .125,.125, .125,-.125
90, .125,0, .125,.125, .125,-.125
"""

#: The built-in hatch pattern table, keyed by upper-case name.
STANDARD = parse_pat(STANDARD_PAT)

SOLID = "SOLID"


def get(name, table=None):
    """Return the :class:`HatchPattern` for *name*, falling back to SOLID."""
    patterns = table if table is not None else STANDARD
    key = str(name or SOLID).upper()
    return patterns.get(key) or patterns[SOLID]


def names(table=None):
    """Return the available pattern names, SOLID first."""
    patterns = table if table is not None else STANDARD
    ordered = sorted(patterns.keys())
    if SOLID in ordered:
        ordered.remove(SOLID)
        ordered.insert(0, SOLID)
    return ordered


def family_geometry(family, pattern_scale=1.0, pattern_angle=0.0):
    """Return ``(angle_degrees, spacing, offset)`` for a QGIS line-pattern fill.

    *pattern_angle* rotates the whole pattern (AutoCAD's hatch angle), which is
    added to each family's own angle. *pattern_scale* multiplies every length.
    """
    angle = (family.angle + float(pattern_angle)) % 360.0
    spacing = family.spacing * float(pattern_scale)
    # The family origin projected perpendicular to the line direction gives the
    # phase offset of the first line.
    radians = math.radians(angle)
    offset = (-family.origin_x * math.sin(radians)
              + family.origin_y * math.cos(radians)) * float(pattern_scale)
    return (angle, spacing, offset)
