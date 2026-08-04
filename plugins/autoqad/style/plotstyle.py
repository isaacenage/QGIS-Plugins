# -*- coding: utf-8 -*-
"""Plot style tables — AutoCAD's CTB, expressed as QGIS expressions.

Pure module: no Qt, no QGIS.

Model space is black, so ACI 7 — the default colour of layer ``"0"`` and
therefore of most entities — resolves to **white**, and that white is written
into every feature's ``aq_rgb`` field (see :mod:`.symbology`). Paper is white.
Plotting a drawing with its model-space colours would therefore render the bulk
of it in the one colour that disappears against the sheet.

AutoCAD solves this with a **plot style table**: a mapping applied at plot time
that leaves the drawing itself untouched. This module is that mapping, emitted
as QGIS *expression strings* rather than as new attribute values — which is the
whole point. A plot style becomes a data-defined property on a paper-space
renderer, so:

* no attribute rewrite (``restyle_all`` over a large drawing is not free);
* no second copy of the data;
* model space keeps looking exactly as it did.

Three tables, matching the ones AutoCAD ships:

``normal``
    Colours plot as drawn, except pure white, which plots black. The direct
    equivalent of what AutoCAD does with ACI 7 on a white sheet.
``monochrome``
    Everything plots black — ``monochrome.ctb``.
``grayscale``
    Colours plot as their perceptual grey — ``grayscale.ctb``.

Grayscale folds *through* normal: white becomes black first, then everything is
desaturated. Without that ordering the default colour would come out white, and
a grayscale plot of a CAD drawing would be a blank sheet.

One deliberate imprecision: the white-to-black rule keys on the *resolved*
colour rather than on the ACI index, so ACI 255 (also pure white) flips as well.
That is the right answer anyway — a pure white entity is unplottable on white
paper whatever index produced it.
"""

from . import lineweights

#: Field names this module writes expressions against. They mirror
#: :mod:`.symbology`'s constants, restated here as plain strings so the
#: dependency only goes one way (symbology imports plotstyle, never the
#: reverse). Callers pass the real constants in.
DEFAULT_COLOR_FIELD = "aq_rgb"
DEFAULT_WIDTH_FIELD = "aq_w"

#: Colour used when a feature has no resolved colour at all.
FALLBACK_COLOR = "#000000"

NORMAL = "normal"
MONOCHROME = "monochrome"
GRAYSCALE = "grayscale"

#: ``(key, label, description)`` per table, in the order the UI lists them.
MODES = (
    (NORMAL, "Normal",
     "Plot the drawing's colours. White plots black."),
    (MONOCHROME, "Monochrome",
     "Plot every entity black, whatever its colour."),
    (GRAYSCALE, "Grayscale",
     "Plot colours as their perceptual grey. White plots black."),
)

MODE_KEYS = tuple(key for key, _label, _help in MODES)


def normalise(mode):
    """Return a known mode key for *mode*, defaulting to :data:`NORMAL`."""
    key = str(mode or "").strip().lower()
    return key if key in MODE_KEYS else NORMAL


def label_for(mode):
    """Return the human label for *mode*."""
    key = normalise(mode)
    for candidate, label, _help in MODES:
        if candidate == key:
            return label
    return MODES[0][1]


def describe(mode):
    """Return the one-line description for *mode*."""
    key = normalise(mode)
    for candidate, _label, help_text in MODES:
        if candidate == key:
            return help_text
    return MODES[0][2]


# --- expression fragments ----------------------------------------------------


def _quote(value):
    """Return *value* as a single-quoted QGIS expression string literal."""
    return "'{0}'".format(str(value).replace("'", "''"))


def _source(field, fallback=FALLBACK_COLOR):
    """The feature's resolved colour, never NULL."""
    return 'coalesce("{0}", {1})'.format(field, _quote(fallback))


def _contrast(field, fallback=FALLBACK_COLOR):
    """The colour with pure white folded to black — the ACI 7 plot rule."""
    source = _source(field, fallback)
    return ("CASE WHEN lower({0}) IN ('#ffffff', '#fff', 'white') "
            "THEN '#000000' ELSE {0} END").format(source)


def _grey(field, fallback=FALLBACK_COLOR):
    """Rec. 601 luminance of the contrast-corrected colour, as 0-255."""
    base = _contrast(field, fallback)
    return ("to_int(0.299 * color_part({0}, 'red')"
            " + 0.587 * color_part({0}, 'green')"
            " + 0.114 * color_part({0}, 'blue'))").format(base)


def color_expression(mode, field=DEFAULT_COLOR_FIELD, fallback=FALLBACK_COLOR):
    """Return the QGIS expression that maps a drawn colour to a plotted one.

    Suitable for a symbol layer's stroke/fill colour data-defined property, or
    for the labelling's text colour.
    """
    key = normalise(mode)
    if key == MONOCHROME:
        return _quote("#000000")
    if key == GRAYSCALE:
        grey = _grey(field, fallback)
        return "color_rgb({0}, {0}, {0})".format(grey)
    return _contrast(field, fallback)


def width_expression(field=DEFAULT_WIDTH_FIELD, enabled=True,
                     minimum_mm=0.0, fallback_mm=None):
    """Return the QGIS expression for an entity's plotted width, in millimetres.

    With *enabled* false every entity plots at the hairline width, which is what
    AutoCAD's "Plot object lineweights" checkbox does when cleared — the drawing
    still plots, just without weight.

    *minimum_mm* floors the plotted width. A lineweight that renders acceptably
    on screen can disappear on paper at high DPI; a floor of one hairline is the
    usual remedy and costs nothing when every entity is already above it.
    """
    hairline = float(getattr(lineweights, "HAIRLINE_MM", 0.05))
    if fallback_mm is None:
        fallback_mm = hairline

    if not enabled:
        return "{0:.6g}".format(max(hairline, float(minimum_mm)))

    width = 'coalesce("{0}", {1:.6g})'.format(field, float(fallback_mm))
    floor = max(0.0, float(minimum_mm))
    if floor <= 0.0:
        return width
    return "max({0}, {1:.6g})".format(width, floor)


class PlotStyle(object):
    """One plot configuration's colour and lineweight rules.

    Immutable by convention: :meth:`replace` returns a new instance rather than
    mutating, so a settings object can be threaded through the renderer builders
    without any of them being able to change it.
    """

    __slots__ = ("mode", "lineweights_enabled", "minimum_width_mm")

    def __init__(self, mode=NORMAL, lineweights_enabled=True,
                 minimum_width_mm=0.0):
        self.mode = normalise(mode)
        self.lineweights_enabled = bool(lineweights_enabled)
        self.minimum_width_mm = max(0.0, float(minimum_width_mm))

    # ---- expressions ----

    def color_expression(self, field=DEFAULT_COLOR_FIELD,
                         fallback=FALLBACK_COLOR):
        return color_expression(self.mode, field, fallback)

    def width_expression(self, field=DEFAULT_WIDTH_FIELD, fallback_mm=None):
        return width_expression(field,
                                enabled=self.lineweights_enabled,
                                minimum_mm=self.minimum_width_mm,
                                fallback_mm=fallback_mm)

    # ---- value semantics ----

    def replace(self, **changes):
        """Return a copy with *changes* applied."""
        data = self.to_dict()
        data.update(changes)
        return PlotStyle.from_dict(data)

    def to_dict(self):
        return {
            "mode": self.mode,
            "lineweights_enabled": self.lineweights_enabled,
            "minimum_width_mm": self.minimum_width_mm,
        }

    @classmethod
    def from_dict(cls, data):
        data = dict(data or {})
        return cls(mode=data.get("mode", NORMAL),
                   lineweights_enabled=data.get("lineweights_enabled", True),
                   minimum_width_mm=data.get("minimum_width_mm", 0.0))

    @classmethod
    def from_variables(cls, variables):
        """Build a style from the PLOTSTYLE / PLOTLW / PLOTLWMIN variables."""
        return cls(mode=variables.get("PLOTSTYLE"),
                   lineweights_enabled=variables.get("PLOTLW"),
                   minimum_width_mm=variables.get("PLOTLWMIN"))

    def __eq__(self, other):
        if not isinstance(other, PlotStyle):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<PlotStyle {0}{1}>".format(
            self.mode, "" if self.lineweights_enabled else " (no lineweights)")
