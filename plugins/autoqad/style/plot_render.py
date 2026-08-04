# -*- coding: utf-8 -*-
"""Paper-space rendering — the drawing as it plots, not as it is drawn.

Model space is black and ACI 7 resolves to white (see
:class:`..core.variables.VariableStore.background_is_dark`). Paper is white.
Something has to reconcile the two, and there are only three honest places to
do it:

1. Rewrite ``aq_rgb`` before plotting and put it back after. Rejected: it is a
   bounded UPDATE over the whole drawing, twice, and a crash mid-plot leaves the
   drawing recoloured.
2. Give the drawing a second set of colour fields. Rejected: two sources of
   truth.
3. Render the same data through a different renderer. This module.

QGIS already has the mechanism for (3): a **layer style override**, which is a
per-map-item style attached to a layout map frame. The canvas keeps its own
style, the layout frame renders with another, and neither knows about the other.
:func:`style_overrides` returns exactly the ``{layer_id: qml}`` dict
:meth:`QgsLayoutItemMap.setLayerStyleOverrides` wants.

The same paper style is also published two other ways, so the user is not
obliged to go through AutoQAD's own plot dialog to get a correct plot:

* :func:`install_plot_styles` adds a named ``AutoQAD Plot`` style to each
  drawing table's style manager, selectable from the layer properties dialog.
* :func:`register_plot_theme` records a map theme of the same name, so a map
  frame in the **stock QGIS layout designer** can simply "follow map theme" and
  come out black-on-white.

Neither is removed when the session ends. A map theme referencing named layer
styles is an artifact the user may have wired into a layout of their own, and
deleting it on deactivate would silently break their work — the asymmetry is
deliberate.
"""

from qgis.core import QgsMapLayerStyle

from ..core.document import LINES, POINTS, POLYGONS
from . import plotstyle, symbology

#: The named style added to each drawing table, and the map theme selecting it.
PLOT_STYLE_NAME = "AutoQAD Plot"
PLOT_THEME_NAME = "AutoQAD Plot"


# --- what plots --------------------------------------------------------------


def non_plotting_layers(document):
    """CAD layer names excluded from plotted output.

    AutoCAD's three ways of keeping something off the sheet, honoured together:
    a layer marked no-plot, a frozen layer, and a layer turned off.
    """
    return [layer.name for layer in document.layers.all()
            if not layer.plottable or not layer.is_visible]


def plot_filter(document):
    """The expression restricting a plot to plottable entities, or ``None``."""
    return symbology.excluded_layers_filter(non_plotting_layers(document))


# --- paper renderers ---------------------------------------------------------


def paper_renderers(document, plot_style=None):
    """Return ``{table_name: (renderer, labeling_or_None)}`` for paper output.

    The same builders the canvas uses, given a plot style and a plot filter.
    Linetype dashes stay in map units: a dashed line is drawing content and has
    to keep its LTSCALE-driven proportions at whatever scale it plots.
    """
    style = plot_style or plotstyle.PlotStyle()
    restrict = plot_filter(document)

    lines = symbology.restrict_renderer(
        symbology.build_line_renderer(plot_style=style), restrict)

    points = symbology.restrict_renderer(
        symbology.build_point_renderer(plot_style=style), restrict)
    labeling = symbology.build_text_labeling(
        document.variables.get("TEXTSIZE"), plot_style=style,
        extra_filter=restrict)

    polygons = symbology.restrict_renderer(
        symbology.build_fill_renderer(document.used_patterns(),
                                      document.pattern_table,
                                      plot_style=style),
        restrict)

    return {
        LINES: (lines, None),
        POINTS: (points, labeling),
        POLYGONS: (polygons, None),
    }


# --- style capture -----------------------------------------------------------
#
# There is no API to serialise a renderer that no layer is wearing, so a layer
# has to wear it to be read. The obvious implementation — dress the *live* layer,
# read it, undress it in a ``finally`` — is wrong twice over.
#
# It is wrong in principle: for the duration of the capture the canvas is showing
# plot colours, and any exception between the two halves leaves the drawing
# recoloured with no user action that would explain it.
#
# It is also wrong in practice. Dressing and undressing all three tables in one
# pass reliably crashes the QGIS process after a few repetitions (a use-after-
# free between the transferred renderer and the style restore) — while doing it
# to any single table repeats indefinitely without complaint. That is the kind
# of bug that would have surfaced as "QGIS closes when I plot twice".
#
# So the paper style is fitted to a **clone**. The clone is a Python-owned throw-
# away that shares no state with the drawing, the live layers are never touched,
# and both problems go away at once. A clone is cheap either way: for a
# GeoPackage drawing it re-opens the source lazily, and for a memory-backed one
# it carries no features at all — and a style needs no data to serialise.


def _style_xml(layer):
    """Serialise a layer's current style to QML XML."""
    style = QgsMapLayerStyle()
    style.readFromLayer(layer)
    return style.xmlData()


def _capture_paper_style(layer, renderer, labeling):
    """Return the QML for *layer* wearing this style, or ``None``.

    The live layer is read but never modified.
    """
    try:
        clone = layer.clone()
    except (RuntimeError, AttributeError):    # pragma: no cover
        return None
    if clone is None:
        return None

    try:
        clone.setRenderer(renderer)
        if labeling is not None:
            clone.setLabeling(labeling)
            clone.setLabelsEnabled(True)
        return _style_xml(clone)
    except RuntimeError:                      # pragma: no cover
        return None


def paper_styles(document, plot_style=None):
    """Return ``{QgsVectorLayer: qml_xml}`` for the drawing's paper styles."""
    styles = {}
    for name, (renderer, labeling) in paper_renderers(
            document, plot_style).items():
        layer = document.table(name)
        if layer is None:
            continue
        xml = _capture_paper_style(layer, renderer, labeling)
        if xml:
            styles[layer] = xml
    return styles


def style_overrides(document, plot_style=None):
    """Return ``{layer_id: qml_xml}`` for :meth:`setLayerStyleOverrides`.

    The direct route: no named styles, no map theme, nothing written into the
    project. A layout map frame given this dict renders the drawing for paper
    and the canvas never notices.
    """
    return {layer.id(): xml
            for layer, xml in paper_styles(document, plot_style).items()}


# --- named styles and the map theme ------------------------------------------


def install_plot_styles(document, plot_style=None,
                        style_name=PLOT_STYLE_NAME):
    """Add (or refresh) the named paper style on every drawing table.

    Uses ``addStyle`` with the captured XML rather than ``addStyleFromLayer``,
    so the layer's *current* style is never made current-something-else along
    the way. Returns the layers touched.
    """
    touched = []
    for layer, xml in paper_styles(document, plot_style).items():
        manager = layer.styleManager()
        if manager is None:
            continue
        try:
            if style_name in manager.styles():
                manager.removeStyle(style_name)
            manager.addStyle(style_name, QgsMapLayerStyle(xml))
        except (RuntimeError, AttributeError):    # pragma: no cover
            continue
        touched.append(layer)
    return touched


def register_plot_theme(document, plot_style=None, project=None,
                        theme_name=PLOT_THEME_NAME,
                        style_name=PLOT_STYLE_NAME):
    """Publish the paper style as a QGIS map theme. Returns True on success.

    This is what lets the **built-in** layout designer produce a correct plot:
    tick "Follow map theme" on the map frame and pick ``AutoQAD Plot``. No
    AutoQAD dialog involved, and it keeps working for atlas and report output
    that AutoQAD's own plot path does not cover.
    """
    from qgis.core import QgsMapThemeCollection

    project = project or document.project
    layers = install_plot_styles(document, plot_style, style_name)
    if not layers:
        return False

    record = QgsMapThemeCollection.MapThemeRecord()
    for layer in layers:
        layer_record = QgsMapThemeCollection.MapThemeLayerRecord(layer)
        layer_record.usingCurrentStyle = True
        layer_record.currentStyle = style_name
        # Added in a later 3.x; absent on the older builds AutoQAD still
        # supports, where every recorded layer is visible by definition.
        try:
            layer_record.isVisible = True
        except AttributeError:                    # pragma: no cover
            pass
        record.addLayerRecord(layer_record)

    collection = project.mapThemeCollection()
    try:
        if collection.hasMapTheme(theme_name):
            collection.update(theme_name, record)
        else:
            collection.insert(theme_name, record)
    except (RuntimeError, AttributeError):        # pragma: no cover
        return False
    return True


def theme_exists(project, theme_name=PLOT_THEME_NAME):
    """True when the plot map theme is registered in *project*."""
    try:
        return project.mapThemeCollection().hasMapTheme(theme_name)
    except (RuntimeError, AttributeError):        # pragma: no cover
        return False
