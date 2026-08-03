# -*- coding: utf-8 -*-
"""AutoCAD linetypes — a real ``acad.lin`` parser plus the standard patterns.

Pure module: no Qt, no QGIS.

An AutoCAD linetype definition is two lines::

    *DASHED,Dashed __ __ __ __ __ __ __ __ __ __ __
    A,.5,-.25

The second line is an alignment flag (always ``A``) followed by pattern
elements measured in **drawing units**: positive is a dash, negative is a gap,
and zero is a dot. That maps directly onto a QGIS custom dash vector, which is
why simple linetypes reproduce exactly.

Two honest caveats, both surfaced rather than hidden:

* **Dots.** A zero-length element is a true point in AutoCAD. QGIS dash vectors
  reject zero, so a dot becomes :data:`DOT_LENGTH` drawing units drawn with a
  round cap — visually a dot, geometrically a very short dash.
* **Complex linetypes.** Elements like ``["GAS",STANDARD,S=.1,R=0,X=-.1,Y=-.05]``
  embed text or shapes. Those cannot be expressed as a dash vector at all; they
  need a marker line. :func:`parse_lin` records them on the pattern as
  :attr:`Linetype.embedded` and sets :attr:`Linetype.is_complex`, so the
  symbology builder can route them to a marker line and the UI can warn.

Scaling follows AutoCAD: the effective length of every element is
``element x LTSCALE x CELTSCALE``. Because model-space linetypes scale with the
drawing (that is exactly why LTSCALE exists), the default render unit is map
units; :func:`to_dash_vector_mm` is provided for paper-space output.
"""

import re

#: Length (in drawing units, before scaling) used to draw a zero-length dot.
DOT_LENGTH = 1e-3

_HEADER_RE = re.compile(r"^\*([^,]+)\s*(?:,(.*))?$")
_EMBEDDED_RE = re.compile(r"\[[^\]]*\]")


class Linetype(object):
    """One linetype definition.

    :param name: the pattern name as it appears in DXF (e.g. ``"HIDDEN"``).
    :param description: the human-readable description line.
    :param elements: pattern elements in drawing units — positive dash,
        negative gap, zero dot. Empty means a continuous line.
    :param embedded: raw text of any embedded text/shape elements.
    """

    __slots__ = ("name", "description", "elements", "embedded")

    def __init__(self, name, description="", elements=None, embedded=None):
        self.name = name
        self.description = description
        self.elements = list(elements or [])
        self.embedded = list(embedded or [])

    @property
    def is_continuous(self):
        """True when the pattern draws an unbroken line."""
        return not self.elements

    @property
    def is_complex(self):
        """True when the pattern embeds text or shapes (see module docstring)."""
        return bool(self.embedded)

    @property
    def pattern_length(self):
        """Total length of one repeat, in drawing units."""
        return sum(abs(e) or DOT_LENGTH for e in self.elements)

    def dash_vector(self, scale=1.0):
        """Return ``[dash, gap, dash, gap, ...]`` scaled by *scale*.

        QGIS custom dash vectors must alternate dash/gap and contain no zeros.
        Where a definition breaks that alternation — it starts with a gap, or
        places two same-sign elements in a row — a :data:`DOT_LENGTH` filler of
        the missing kind is inserted so the sequence stays well-formed.
        """
        if not self.elements:
            return []

        vector = []
        expecting_dash = True
        for element in self.elements:
            length = (abs(element) or DOT_LENGTH) * scale
            is_dash = element >= 0
            if is_dash != expecting_dash:
                # Insert a filler of the expected kind to preserve alternation.
                vector.append(DOT_LENGTH * scale)
                expecting_dash = not expecting_dash
            vector.append(length)
            expecting_dash = not expecting_dash

        if len(vector) % 2:
            # Must end on a gap so the pattern tiles cleanly.
            vector.append(DOT_LENGTH * scale)
        return vector

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<Linetype {0} {1}>".format(self.name, self.elements)


def parse_lin(text):
    """Parse ``.lin`` file *text* into an ordered ``{name: Linetype}`` dict.

    Unparseable stanzas are skipped rather than raising, so one malformed entry
    in a user-supplied file cannot stop the rest from loading.
    """
    patterns = {}
    lines = [ln.strip() for ln in text.splitlines()]
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line or line.startswith(";"):
            continue
        header = _HEADER_RE.match(line)
        if not header:
            continue

        name = header.group(1).strip().upper()
        description = (header.group(2) or "").strip()

        if index >= len(lines):
            break
        body = lines[index]
        index += 1

        embedded = _EMBEDDED_RE.findall(body)
        body_clean = _EMBEDDED_RE.sub("", body)

        parts = [p.strip() for p in body_clean.split(",")]
        if parts and parts[0].upper() == "A":
            parts = parts[1:]

        elements = []
        for part in parts:
            if not part:
                continue
            try:
                elements.append(float(part))
            except ValueError:
                continue

        patterns[name] = Linetype(name, description, elements, embedded)
    return patterns


# --- the standard acad.lin patterns -----------------------------------------
#
# Transcribed from the published AutoCAD linetype definitions. These are the
# patterns a floor plan actually uses; a user can load a full acad.lin over the
# top with :func:`parse_lin`.

STANDARD_LIN = """
*CONTINUOUS,Solid line
A
*BORDER,Border __ __ . __ __ . __ __ . __ __ . __ __ .
A,.5,-.25,.5,-.25,0,-.25
*BORDER2,Border (.5x) __.__.__.__.__.__.__.__.__.__.__.
A,.25,-.125,.25,-.125,0,-.125
*BORDERX2,Border (2x) ____  ____  .  ____  ____  .  ___
A,1.0,-.5,1.0,-.5,0,-.5
*CENTER,Center ____ _ ____ _ ____ _ ____ _ ____ _ ____
A,1.25,-.25,.25,-.25
*CENTER2,Center (.5x) ___ _ ___ _ ___ _ ___ _ ___ _ ___
A,.75,-.125,.125,-.125
*CENTERX2,Center (2x) ________  __  ________  __  _____
A,2.5,-.5,.5,-.5
*DASHDOT,Dash dot __ . __ . __ . __ . __ . __ . __ . __
A,.5,-.25,0,-.25
*DASHDOT2,Dash dot (.5x) _._._._._._._._._._._._._._._.
A,.25,-.125,0,-.125
*DASHDOTX2,Dash dot (2x) ____  .  ____  .  ____  .  ___
A,1.0,-.5,0,-.5
*DASHED,Dashed __ __ __ __ __ __ __ __ __ __ __ __ __ _
A,.5,-.25
*DASHED2,Dashed (.5x) _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
A,.25,-.125
*DASHEDX2,Dashed (2x) ____  ____  ____  ____  ____  ___
A,1.0,-.5
*DIVIDE,Divide ____ . . ____ . . ____ . . ____ . . ____
A,.5,-.25,0,-.25,0,-.25
*DIVIDE2,Divide (.5x) __..__..__..__..__..__..__..__.._
A,.25,-.125,0,-.125,0,-.125
*DIVIDEX2,Divide (2x) ________  .  .  ________  .  .  _
A,1.0,-.5,0,-.5,0,-.5
*DOT,Dot . . . . . . . . . . . . . . . . . . . . . . . .
A,0,-.25
*DOT2,Dot (.5x) .....................................
A,0,-.125
*DOTX2,Dot (2x) .  .  .  .  .  .  .  .  .  .  .  .  .  .
A,0,-.5
*HIDDEN,Hidden __ __ __ __ __ __ __ __ __ __ __ __ __ __
A,.25,-.125
*HIDDEN2,Hidden (.5x) _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
A,.125,-.0625
*HIDDENX2,Hidden (2x) ____ ____ ____ ____ ____ ____ ___
A,.5,-.25
*PHANTOM,Phantom ______  __  __  ______  __  __  ______
A,1.25,-.25,.25,-.25,.25,-.25
*PHANTOM2,Phantom (.5x) ___ _ _ ___ _ _ ___ _ _ ___ _ _
A,.625,-.125,.125,-.125,.125,-.125
*PHANTOMX2,Phantom (2x) ____________    ____    ____
A,2.5,-.5,.5,-.5,.5,-.5
"""

#: The built-in linetype table, keyed by upper-case name.
STANDARD = parse_lin(STANDARD_LIN)

#: Sentinel names, mirroring the colour/lineweight sentinels.
BYLAYER = "BYLAYER"
BYBLOCK = "BYBLOCK"
CONTINUOUS = "CONTINUOUS"


def get(name, table=None):
    """Return the :class:`Linetype` for *name*, falling back to CONTINUOUS."""
    patterns = table if table is not None else STANDARD
    key = str(name or CONTINUOUS).upper()
    return patterns.get(key) or patterns[CONTINUOUS]


def names(table=None):
    """Return the available linetype names, CONTINUOUS first."""
    patterns = table if table is not None else STANDARD
    ordered = sorted(patterns.keys())
    if CONTINUOUS in ordered:
        ordered.remove(CONTINUOUS)
        ordered.insert(0, CONTINUOUS)
    return ordered


def resolve(entity_ltype, layer_ltype):
    """Resolve an entity's effective linetype name against its layer."""
    value = str(entity_ltype or BYLAYER).upper()
    if value in (BYLAYER, BYBLOCK):
        value = str(layer_ltype or CONTINUOUS).upper()
    if value in (BYLAYER, BYBLOCK):
        value = CONTINUOUS
    return value


def to_dash_vector(name, ltscale=1.0, celtscale=1.0, table=None):
    """Return the QGIS dash vector for *name* in **drawing units**.

    Mirrors AutoCAD: effective length is ``element x LTSCALE x CELTSCALE``.
    An empty list means a continuous line.
    """
    return get(name, table).dash_vector(float(ltscale) * float(celtscale))


def to_dash_vector_mm(name, ltscale=1.0, celtscale=1.0,
                      scale_denominator=100.0, units_per_metre=1.0, table=None):
    """Return the dash vector in **paper millimetres** for plot-space output.

    A pattern element of *e* drawing units, at plot scale 1:*scale_denominator*,
    covers ``e / units_per_metre x 1000 / scale_denominator`` mm on paper.
    """
    factor = (1000.0 / float(units_per_metre)) / float(scale_denominator)
    vector = get(name, table).dash_vector(float(ltscale) * float(celtscale))
    return [v * factor for v in vector]
