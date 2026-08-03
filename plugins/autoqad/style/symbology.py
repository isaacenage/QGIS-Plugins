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
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsLinePatternFillSymbolLayer,
    QgsFillSymbol,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsProperty,
    QgsRuleBasedRenderer,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSymbolLayer,
)

from ..core.compat import RENDER_MAP_UNITS, RENDER_MM
from . import aci, hatches, linetypes, lineweights

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


def _set_property(symbol_layer, prop, expression):
    """Attach a data-defined *expression* if the property exists on this build."""
    if prop is None:
        return False
    symbol_layer.setDataDefinedProperty(prop, QgsProperty.fromField(expression))
    return True


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
                      fallback_color="#000000", fallback_width=0.25):
    """Return a data-driven :class:`QgsLineSymbol` for CAD curves.

    Colour and width always come from the resolved fields. When *dashed*, the
    dash vector comes from ``aq_dash`` too.

    Linetype dashes render in **map units** by default because model-space
    linetypes scale with the drawing — that is exactly why AutoCAD has LTSCALE.
    Pass ``dash_unit_map_units=False`` for paper-space (millimetre) output.
    """
    line = QgsSimpleLineSymbolLayer()
    line.setColor(QColor(fallback_color))
    line.setWidth(fallback_width)
    line.setWidthUnit(RENDER_MM)
    line.setPenCapStyle(Qt.PenCapStyle.FlatCap)
    line.setPenJoinStyle(Qt.PenJoinStyle.MiterJoin)

    _set_property(line, PROP_STROKE_COLOR, FIELD_RGB)
    _set_property(line, PROP_STROKE_WIDTH, FIELD_WIDTH)

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


def build_line_renderer(dash_unit_map_units=True):
    """Return a rule-based renderer for the curve table.

    Two rules: entities whose resolved dash pattern is empty draw solid, the
    rest draw with their custom dash. Splitting on a field value is exact and
    version-proof, where data-defining the pen style is not.
    """
    root = QgsRuleBasedRenderer.Rule(None)

    solid = QgsRuleBasedRenderer.Rule(
        build_line_symbol(dashed=False),
        filterExp='"{0}" IS NULL OR "{0}" = \'\''.format(FIELD_DASH),
        label="Continuous")
    root.appendChild(solid)

    dashed = QgsRuleBasedRenderer.Rule(
        build_line_symbol(dashed=True, dash_unit_map_units=dash_unit_map_units),
        filterExp='"{0}" IS NOT NULL AND "{0}" != \'\''.format(FIELD_DASH),
        label="Linetype")
    root.appendChild(dashed)

    return QgsRuleBasedRenderer(root)


# --- point symbols -----------------------------------------------------------

def build_point_renderer():
    """Return a renderer for the point table (nodes, block and text anchors)."""
    symbol = QgsMarkerSymbol.createSimple({
        "name": "cross2",
        "size": "2",
        "color": "#000000",
    })
    layer = symbol.symbolLayer(0)
    _set_property(layer, PROP_STROKE_COLOR, FIELD_RGB)
    _set_property(layer, PROP_FILL_COLOR, FIELD_RGB)

    root = QgsRuleBasedRenderer.Rule(None)
    root.appendChild(QgsRuleBasedRenderer.Rule(symbol, label="Nodes"))
    return QgsRuleBasedRenderer(root)


# --- hatch / fill symbols ----------------------------------------------------

def build_hatch_symbol(pattern_name, pattern_scale=1.0, pattern_angle=0.0,
                       fallback_color="#000000", line_width_mm=0.13,
                       pattern_table=None):
    """Return a :class:`QgsFillSymbol` reproducing an AutoCAD hatch pattern.

    Each of the pattern's line families becomes one
    :class:`QgsLinePatternFillSymbolLayer`, stacked in definition order — which
    is why ANSI37 and NET come out as true cross-hatches rather than an
    approximation. SOLID is a plain fill.
    """
    pattern = hatches.get(pattern_name, pattern_table)
    symbol = QgsFillSymbol()

    if pattern.is_solid or not pattern.families:
        fill = QgsSimpleFillSymbolLayer()
        fill.setColor(QColor(fallback_color))
        fill.setStrokeStyle(Qt.PenStyle.NoPen)
        _set_property(fill, PROP_FILL_COLOR, FIELD_RGB)
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

        stroke = QgsSimpleLineSymbolLayer()
        stroke.setColor(QColor(fallback_color))
        stroke.setWidth(line_width_mm)
        stroke.setWidthUnit(RENDER_MM)
        _set_property(stroke, PROP_STROKE_COLOR, FIELD_RGB)

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


def build_fill_renderer(pattern_names=None, pattern_table=None):
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
            build_hatch_symbol(name, pattern_table=pattern_table),
            filterExp='"{0}" = \'{1}\''.format(FIELD_PATTERN,
                                               str(name).replace("'", "''")),
            label=str(name))
        root.appendChild(rule)

    # Anything with no pattern set still needs to draw.
    fallback = QgsRuleBasedRenderer.Rule(
        build_hatch_symbol(hatches.SOLID, pattern_table=pattern_table),
        filterExp='"{0}" IS NULL'.format(FIELD_PATTERN),
        label="Unpatterned")
    root.appendChild(fallback)

    return QgsRuleBasedRenderer(root)


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
