# -*- coding: utf-8 -*-
"""Build QGIS symbols and renderers that reproduce AutoCAD's appearance.

The design decision that makes this fast: **resolved style is denormalised onto
each feature.** Every entity stores both the CAD truth (``aq_color`` as an ACI
index, ``aq_ltype``, ``aq_lw``) — which is what DXF export needs — *and* the
already-resolved render values (``aq_rgb`` hex, ``aq_w`` millimetres,
``aq_dash`` pattern string), which is what the renderer reads.

That means rendering evaluates a field read rather than a ByLayer lookup
expression per feature, and the renderer needs only a couple of rules instead
of one per CAD layer. The cost is a single bounded UPDATE over a layer's
features when that layer's colour/linetype/lineweight changes, which
:func:`resolve_entity_style` and the document's ``restyle_layer`` handle. One
writer, explicit refresh, no stale reads.

Rules split lines into solid and dashed because a QGIS line symbol layer must
opt into custom dash patterns up front; splitting is deterministic, whereas
data-defining the pen style is not reliable across QGIS versions.

**Paper space.** Every builder here takes an optional *plot_style*
(:class:`..style.plotstyle.PlotStyle`). Passing one swaps the bare field read
for the plot style's expression, which is how a drawing authored against black
model space plots black-on-white without a single attribute being rewritten —
see :mod:`.plotstyle`. Passing ``None`` (the default) is the screen renderer,
unchanged.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsLinePatternFillSymbolLayer,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProperty,
    QgsRuleBasedRenderer,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSymbolLayer,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)

try:
    from qgis.core import Qgis
except ImportError:                       # pragma: no cover - very old builds
    Qgis = None

from ..core.compat import RENDER_MAP_UNITS, RENDER_MM, enum_member
from . import aci, hatches, linetypes, lineweights, plotstyle

#: Field names carrying resolved render values.
FIELD_RGB = "aq_rgb"
FIELD_WIDTH = "aq_w"
FIELD_DASH = "aq_dash"

#: Field names carrying the CAD truth (what DXF export writes).
FIELD_LAYER = "aq_layer"
FIELD_COLOR = "aq_color"
FIELD_LTYPE = "aq_ltype"
FIELD_LWEIGHT = "aq_lw"
FIELD_LTSCALE = "aq_ltscale"
FIELD_TYPE = "aq_type"
FIELD_PATTERN = "aq_pattern"
FIELD_PAT_SCALE = "aq_pat_scale"
FIELD_PAT_ANGLE = "aq_pat_angle"

#: Text-entity fields. They live here rather than with the rest of the table
#: schema because the *renderer* is what reads them — the labelling built
#: below turns them into drawn text — and ``core.document`` already imports
#: from this module, so the dependency only goes one way.
FIELD_TEXT = "aq_text"
FIELD_HEIGHT = "aq_height"
FIELD_ROTATION = "aq_rot"


def _symbol_property(*candidates):
    """Resolve a ``QgsSymbolLayer`` data-defined property across QGIS versions.

    The enum was reorganised more than once (``PropertyStrokeColor`` ->
    ``Property.PropertyStrokeColor`` -> ``Property.StrokeColor``), so try each
    spelling and return the first that exists.
    """
    scope = getattr(QgsSymbolLayer, "Property", None)
    for name in candidates:
        if scope is not None and hasattr(scope, name):
            return getattr(scope, name)
        if hasattr(QgsSymbolLayer, name):
            return getattr(QgsSymbolLayer, name)
    return None


PROP_STROKE_COLOR = _symbol_property("PropertyStrokeColor", "StrokeColor")
PROP_STROKE_WIDTH = _symbol_property("PropertyStrokeWidth", "StrokeWidth")
PROP_CUSTOM_DASH = _symbol_property("PropertyCustomDash", "CustomDash")
PROP_FILL_COLOR = _symbol_property("PropertyFillColor", "FillColor")
PROP_LINE_ANGLE = _symbol_property("PropertyLineAngle", "LineAngle")
PROP_LINE_DISTANCE = _symbol_property("PropertyLineDistance", "LineDistance")


def _set_property(symbol_layer, prop, expression):
    """Attach a data-defined *field* if the property exists on this build."""
    if prop is None:
        return False
    symbol_layer.setDataDefinedProperty(prop, QgsProperty.fromField(expression))
    return True


def _set_expression(symbol_layer, prop, expression):
    """Attach a data-defined *expression* if the property exists on this build.

    Returns False on builds where the property does not exist, which leaves the
    symbol layer's static value in place rather than failing.
    """
    if prop is None:
        return False
    symbol_layer.setDataDefinedProperty(
        prop, QgsProperty.fromExpression(expression))
    return True


def _apply_colour(symbol_layer, prop, plot_style):
    """Bind a colour property to the resolved field, or to a plot style.

    The one branch that turns a screen renderer into a paper one.
    """
    if plot_style is None:
        return _set_property(symbol_layer, prop, FIELD_RGB)
    return _set_expression(symbol_layer, prop,
                           plot_style.color_expression(FIELD_RGB))


def _apply_width(symbol_layer, prop, plot_style, fallback_mm=None):
    """Bind a width property to the resolved field, or to a plot style."""
    if plot_style is None:
        return _set_property(symbol_layer, prop, FIELD_WIDTH)
    return _set_expression(
        symbol_layer, prop,
        plot_style.width_expression(FIELD_WIDTH, fallback_mm=fallback_mm))


# --- resolved-style computation ---------------------------------------------

def dash_string(vector):
    """Encode a dash vector the way QGIS's custom-dash property expects."""
    return ";".join("{0:.6g}".format(v) for v in vector)


def resolve_entity_style(cad_layer, color=None, linetype=None, lineweight=None,
                         ltscale=1.0, global_ltscale=1.0,
                         lineweight_display=True, background_is_dark=False,
                         linetype_table=None):
    """Resolve one entity's ByLayer-aware style into render-ready values.

    Returns ``{aq_rgb, aq_w, aq_dash}`` — exactly the denormalised fields the
    renderer reads. *cad_layer* supplies every ByLayer default.
    """
    red, green, blue = cad_layer.resolve_color(
        aci.BYLAYER if color is None else color, background_is_dark)

    width_mm = cad_layer.resolve_lineweight(lineweight, lineweight_display)

    name = cad_layer.resolve_linetype(linetype)
    vector = linetypes.to_dash_vector(
        name, ltscale=global_ltscale, celtscale=ltscale, table=linetype_table)

    return {
        FIELD_RGB: "#{0:02x}{1:02x}{2:02x}".format(red, green, blue),
        FIELD_WIDTH: float(width_mm),
        FIELD_DASH: dash_string(vector),
    }


# --- line symbols ------------------------------------------------------------

def build_line_symbol(dashed=False, dash_unit_map_units=True,
                      fallback_color="#000000", fallback_width=0.25,
                      plot_style=None):
    """Return a data-driven :class:`QgsLineSymbol` for CAD curves.

    Colour and width always come from the resolved fields. When *dashed*, the
    dash vector comes from ``aq_dash`` too.

    Linetype dashes render in **map units** by default because model-space
    linetypes scale with the drawing — that is exactly why AutoCAD has LTSCALE.
    Pass ``dash_unit_map_units=False`` for paper-space (millimetre) output.

    With a *plot_style* the colour and width become plot-style expressions
    instead of plain field reads. The dash vector is left alone: a linetype is
    drawing content, not a plot decision.
    """
    line = QgsSimpleLineSymbolLayer()
    line.setColor(QColor(fallback_color))
    line.setWidth(fallback_width)
    line.setWidthUnit(RENDER_MM)
    line.setPenCapStyle(Qt.PenCapStyle.FlatCap)
    line.setPenJoinStyle(Qt.PenJoinStyle.MiterJoin)

    _apply_colour(line, PROP_STROKE_COLOR, plot_style)
    _apply_width(line, PROP_STROKE_WIDTH, plot_style,
                 fallback_mm=fallback_width)

    if dashed:
        line.setUseCustomDashPattern(True)
        line.setCustomDashPatternUnit(
            RENDER_MAP_UNITS if dash_unit_map_units else RENDER_MM)
        # A sane default so the layer is valid before the first feature.
        line.setCustomDashVector([1.0, 0.5])
        _set_property(line, PROP_CUSTOM_DASH, FIELD_DASH)

    symbol = QgsLineSymbol()
    symbol.changeSymbolLayer(0, line)
    return symbol


def build_line_renderer(dash_unit_map_units=True, plot_style=None):
    """Return a rule-based renderer for the curve table.

    Two rules: entities whose resolved dash pattern is empty draw solid, the
    rest draw with their custom dash. Splitting on a field value is exact and
    version-proof, where data-defining the pen style is not.
    """
    root = QgsRuleBasedRenderer.Rule(None)

    solid = QgsRuleBasedRenderer.Rule(
        build_line_symbol(dashed=False, plot_style=plot_style),
        filterExp='"{0}" IS NULL OR "{0}" = \'\''.format(FIELD_DASH),
        label="Continuous")
    root.appendChild(solid)

    dashed = QgsRuleBasedRenderer.Rule(
        build_line_symbol(dashed=True, dash_unit_map_units=dash_unit_map_units,
                          plot_style=plot_style),
        filterExp='"{0}" IS NOT NULL AND "{0}" != \'\''.format(FIELD_DASH),
        label="Linetype")
    root.appendChild(dashed)

    return QgsRuleBasedRenderer(root)


# --- point symbols -----------------------------------------------------------

#: Entities in the point table whose geometry is an *anchor* rather than a
#: mark: the visible thing is the label drawn at it, not a glyph.
ANCHOR_TYPES = ("TEXT", "MTEXT")

_ANCHOR_FILTER = " OR ".join(
    '"{0}" = \'{1}\''.format(FIELD_TYPE, name) for name in ANCHOR_TYPES)


def build_point_renderer(plot_style=None):
    """Return a renderer for the point table (nodes, block and text anchors).

    Two rules. Real points get AutoCAD's node cross. Text insertion points get
    nothing — their content is drawn by :func:`build_text_labeling`, and a
    cross sitting under every string is noise a CAD user does not expect.
    """
    symbol = QgsMarkerSymbol.createSimple({
        "name": "cross2",
        "size": "2",
        "color": "#000000",
    })
    layer = symbol.symbolLayer(0)
    _apply_colour(layer, PROP_STROKE_COLOR, plot_style)
    _apply_colour(layer, PROP_FILL_COLOR, plot_style)

    root = QgsRuleBasedRenderer.Rule(None)
    root.appendChild(QgsRuleBasedRenderer.Rule(
        symbol, filterExp="NOT ({0})".format(_ANCHOR_FILTER), label="Nodes"))

    # An explicit, fully transparent rule rather than no rule at all: a feature
    # that matches nothing is not guaranteed to reach the labelling provider.
    blank = QgsMarkerSymbol.createSimple({"name": "circle", "size": "0"})
    blank.setOpacity(0.0)
    root.appendChild(QgsRuleBasedRenderer.Rule(
        blank, filterExp=_ANCHOR_FILTER, label="Text anchors"))

    return QgsRuleBasedRenderer(root)


# --- text ---------------------------------------------------------------------
#
# CAD text is an entity with a height in *drawing units*, not a cartographic
# label with a point size: a 2.5-unit note has to stay 2.5 units tall through
# every zoom, exactly as it would in AutoCAD. That maps onto QGIS labelling
# with the text size in map units and every varying value data-defined off the
# feature — height, rotation and the same resolved colour the curves use.

def _label_placement():
    """``OverPoint``, wherever this build keeps it."""
    if Qgis is not None and hasattr(Qgis, "LabelPlacement"):
        return Qgis.LabelPlacement.OverPoint
    return QgsPalLayerSettings.OverPoint


def _label_quadrant():
    """``AboveRight`` — text runs up and right from its insertion point."""
    if Qgis is not None and hasattr(Qgis, "LabelQuadrantPosition"):
        return Qgis.LabelQuadrantPosition.AboveRight
    return QgsPalLayerSettings.QuadrantAboveRight


def _label_property(name):
    return enum_member(QgsPalLayerSettings, "Property", name)


def build_text_labeling(default_height=2.5, plot_style=None,
                        extra_filter=None):
    """Return labelling that draws ``aq_text`` as CAD text, or ``None``.

    Returns ``None`` only if the running build has no labelling API to speak
    of, so the caller can skip installing it rather than fail.

    *extra_filter* is ANDed into the Show property, which is how a plot leaves
    out the text on a non-plotting CAD layer — labelling has no rule tree to
    hang a filter off, so the condition goes on the one property that decides
    whether a string is drawn at all.
    """
    try:
        settings = QgsPalLayerSettings()
        text_format = QgsTextFormat()
    except (NameError, TypeError):        # pragma: no cover - no labelling API
        return None

    text_format.setSize(default_height)
    text_format.setSizeUnit(RENDER_MAP_UNITS)
    text_format.setColor(QColor("#000000"))

    settings.setFormat(text_format)
    settings.fieldName = FIELD_TEXT
    settings.isExpression = False
    settings.placement = _label_placement()
    settings.quadOffset = _label_quadrant()

    # CAD text is drawn, not negotiated for: never drop a string because two
    # of them overlap, and never let one push a neighbouring label around.
    settings.displayAll = True
    settings.obstacle = False
    settings.priority = 10

    properties = settings.dataDefinedProperties()
    for name, field in (("Size", FIELD_HEIGHT),
                        ("LabelRotation", FIELD_ROTATION)):
        member = _label_property(name)
        if member is not None:
            properties.setProperty(member, QgsProperty.fromField(field))

    colour = _label_property("Color")
    if colour is not None:
        if plot_style is None:
            properties.setProperty(colour, QgsProperty.fromField(FIELD_RGB))
        else:
            properties.setProperty(colour, QgsProperty.fromExpression(
                plot_style.color_expression(FIELD_RGB)))

    show = _label_property("Show")
    if show is not None:
        condition = '"{0}" IS NOT NULL AND "{0}" != \'\''.format(FIELD_TEXT)
        if extra_filter:
            condition = "({0}) AND ({1})".format(condition, extra_filter)
        properties.setProperty(show, QgsProperty.fromExpression(condition))
    settings.setDataDefinedProperties(properties)

    return QgsVectorLayerSimpleLabeling(settings)


# --- hatch / fill symbols ----------------------------------------------------

def _angle_expression(base_angle):
    """Family angle rotated by the feature's own hatch angle, normalised."""
    return '((({0:.6g} + coalesce("{1}", 0)) % 360) + 360) % 360'.format(
        float(base_angle), FIELD_PAT_ANGLE)


def _spacing_expression(base_spacing):
    """Family spacing multiplied by the feature's own hatch scale.

    Floored well above zero: a zero or missing scale would otherwise ask the
    renderer for infinitely many hatch lines.
    """
    return 'max({0:.6g} * coalesce(nullif("{1}", 0), 1), 0.000001)'.format(
        float(base_spacing), FIELD_PAT_SCALE)


def build_hatch_symbol(pattern_name, pattern_scale=1.0, pattern_angle=0.0,
                       fallback_color="#000000", line_width_mm=0.13,
                       pattern_table=None, data_defined=True,
                       plot_style=None):
    """Return a :class:`QgsFillSymbol` reproducing an AutoCAD hatch pattern.

    Each of the pattern's line families becomes one
    :class:`QgsLinePatternFillSymbolLayer`, stacked in definition order — which
    is why ANSI37 and NET come out as true cross-hatches rather than an
    approximation. SOLID is a plain fill.

    *pattern_scale* and *pattern_angle* set the symbol's static geometry. With
    *data_defined* the same two values are also driven per feature from
    ``aq_pat_scale`` / ``aq_pat_angle``, so HATCH's scale and angle prompts
    actually change what is drawn — the renderer keys its rules on the pattern
    *name* alone, and without this every hatch of a given pattern would render
    at scale 1 and angle 0 whatever the user answered. Turn it off for legend
    swatches and other featureless previews.
    """
    pattern = hatches.get(pattern_name, pattern_table)
    symbol = QgsFillSymbol()

    if pattern.is_solid or not pattern.families:
        fill = QgsSimpleFillSymbolLayer()
        fill.setColor(QColor(fallback_color))
        fill.setStrokeStyle(Qt.PenStyle.NoPen)
        _apply_colour(fill, PROP_FILL_COLOR, plot_style)
        symbol.changeSymbolLayer(0, fill)
        return symbol

    first = True
    for family in pattern.families:
        angle, spacing, offset = hatches.family_geometry(
            family, pattern_scale, pattern_angle)

        fill_layer = QgsLinePatternFillSymbolLayer()
        fill_layer.setLineAngle(angle)
        fill_layer.setDistance(max(spacing, 1e-6))
        fill_layer.setDistanceUnit(RENDER_MAP_UNITS)
        try:
            fill_layer.setOffset(offset)
            fill_layer.setOffsetUnit(RENDER_MAP_UNITS)
        except AttributeError:            # pragma: no cover - older builds
            pass

        if data_defined:
            _set_expression(fill_layer, PROP_LINE_ANGLE, _angle_expression(
                family.angle))
            _set_expression(fill_layer, PROP_LINE_DISTANCE,
                            _spacing_expression(family.spacing))

        stroke = QgsSimpleLineSymbolLayer()
        stroke.setColor(QColor(fallback_color))
        stroke.setWidth(line_width_mm)
        stroke.setWidthUnit(RENDER_MM)
        _apply_colour(stroke, PROP_STROKE_COLOR, plot_style)

        dashes = family.dash_vector(pattern_scale)
        if dashes:
            stroke.setUseCustomDashPattern(True)
            stroke.setCustomDashPatternUnit(RENDER_MAP_UNITS)
            stroke.setCustomDashVector(dashes)

        sub_symbol = QgsLineSymbol()
        sub_symbol.changeSymbolLayer(0, stroke)
        fill_layer.setSubSymbol(sub_symbol)

        if first:
            symbol.changeSymbolLayer(0, fill_layer)
            first = False
        else:
            symbol.appendSymbolLayer(fill_layer)

    return symbol


def build_fill_renderer(pattern_names=None, pattern_table=None,
                        plot_style=None):
    """Return a rule-based renderer for the polygon table.

    One rule per hatch pattern *in use*. Passing the drawing's distinct
    ``aq_pattern`` values keeps the rule count to what the drawing actually
    needs rather than the whole pattern catalogue.
    """
    names = list(pattern_names or [hatches.SOLID])
    if hatches.SOLID not in names:
        names.append(hatches.SOLID)

    root = QgsRuleBasedRenderer.Rule(None)
    for name in names:
        rule = QgsRuleBasedRenderer.Rule(
            build_hatch_symbol(name, pattern_table=pattern_table,
                               plot_style=plot_style),
            filterExp='"{0}" = \'{1}\''.format(FIELD_PATTERN,
                                               str(name).replace("'", "''")),
            label=str(name))
        root.appendChild(rule)

    # Anything with no pattern set still needs to draw.
    fallback = QgsRuleBasedRenderer.Rule(
        build_hatch_symbol(hatches.SOLID, pattern_table=pattern_table,
                           plot_style=plot_style),
        filterExp='"{0}" IS NULL'.format(FIELD_PATTERN),
        label="Unpatterned")
    root.appendChild(fallback)

    return QgsRuleBasedRenderer(root)


# --- paper-space rule filtering ----------------------------------------------


def restrict_renderer(renderer, extra_filter):
    """AND *extra_filter* into every rule of a rule-based renderer.

    How a plot leaves out the entities on a frozen or non-plotting CAD layer.
    Filtering at the rule level rather than by swapping the layer's subset
    string matters: a subset string is layer state shared with the rest of
    QGIS, and a plot must never disturb what the canvas is showing.

    Returns *renderer*, so it can be used inline.
    """
    if not extra_filter:
        return renderer
    root = getattr(renderer, "rootRule", None)
    if root is None:
        return renderer
    for rule in root().children():
        existing = rule.filterExpression()
        rule.setFilterExpression(
            "({0}) AND ({1})".format(existing, extra_filter) if existing
            else extra_filter)
    return renderer


def excluded_layers_filter(layer_names, field=FIELD_LAYER):
    """Return an expression matching entities *not* on any of *layer_names*.

    ``NULL`` layer names are kept: an entity with no CAD layer recorded is
    malformed, and silently dropping it from a plot would hide the problem at
    exactly the moment the user needs to see it.
    """
    names = [str(n) for n in (layer_names or [])]
    if not names:
        return None
    quoted = ", ".join("'{0}'".format(n.replace("'", "''")) for n in names)
    return '("{0}" NOT IN ({1}) OR "{0}" IS NULL)'.format(field, quoted)


# --- preview helpers (used by the layer manager and pattern pickers) ---------

def preview_line_symbol(cad_layer, background_is_dark=False,
                        linetype_table=None):
    """Return a concrete (non data-driven) symbol showing a layer's own style.

    Used for the swatches in the Layer Manager, where there is no feature to
    read resolved fields from.
    """
    red, green, blue = cad_layer.rgb(background_is_dark)
    line = QgsSimpleLineSymbolLayer()
    line.setColor(QColor(red, green, blue))
    line.setWidth(max(cad_layer.width_mm(), lineweights.HAIRLINE_MM))
    line.setWidthUnit(RENDER_MM)

    vector = linetypes.to_dash_vector(cad_layer.linetype, table=linetype_table)
    if vector:
        # Preview swatches are drawn in millimetres, so scale the drawing-unit
        # pattern into something visible at swatch size.
        line.setUseCustomDashPattern(True)
        line.setCustomDashPatternUnit(RENDER_MM)
        longest = max(vector) or 1.0
        line.setCustomDashVector([v * (4.0 / longest) for v in vector])

    symbol = QgsLineSymbol()
    symbol.changeSymbolLayer(0, line)
    return symbol
