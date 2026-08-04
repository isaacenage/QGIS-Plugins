# -*- coding: utf-8 -*-
"""PLOT — build a print layout from the drawing and send it somewhere.

AutoQAD does not reimplement the QGIS layout designer, and should not: a
designer is a hundred features deep and none of them are the thing a draughtsman
wants at plot time. What a draughtsman wants is AutoCAD's PLOT dialog — sheet,
area, scale, plot style, go — and that is a *layout builder*, not a designer.

So this module builds a :class:`QgsPrintLayout` programmatically: one page at
the chosen sheet size, one full-frame map item inside the margins, the drawing's
layers, the paper style overrides from :mod:`..style.plot_render`, and an extent
that is either fitted to the frame or pinned to an exact scale. Then
:func:`export_layout` hands it to :class:`QgsLayoutExporter`.

Two things are deliberately delegated rather than computed here:

* **Scale.** The pure maths in :mod:`.plot_geometry` sizes the extent and
  suggests a fit scale, but the *authoritative* scale is QGIS's own
  ``QgsLayoutItemMap.setScale``, which knows how the map CRS's units relate to
  paper. On a geographic CRS the pure suggestion is an approximation; the map
  item's is not.
* **Colour.** Nothing here knows that model space is black. It asks
  :mod:`..style.plot_render` for style overrides and attaches them.

The layout is a throwaway by default — built, exported, discarded — so plotting
twice does not litter the project with layouts. :func:`open_in_designer` is the
exception: it hands the layout to the project's layout manager and opens QGIS's
own designer on it, which is the bridge between AutoQAD's plot dialog and the
full designer for anyone who wants a title block.
"""

import os

from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsLayoutExporter,
    QgsLayoutItemMap,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsPrintLayout,
    QgsRectangle,
    QgsUnitTypes,
)

from ..core.compat import DISTANCE_METERS, LAYOUT_MM, enum_member
from ..style import plot_render, plotstyle
from . import plot_geometry

#: Where a plot can go.
TARGET_PDF = "pdf"
TARGET_PNG = "png"
TARGET_SVG = "svg"
TARGET_PRINTER = "printer"
TARGET_LAYOUT = "layout"

#: ``(key, label, extension)`` per target, in the order the dialog offers them.
TARGETS = (
    (TARGET_PDF, "PDF file", ".pdf"),
    (TARGET_PNG, "PNG image", ".png"),
    (TARGET_SVG, "SVG file", ".svg"),
    (TARGET_PRINTER, "System printer", ""),
    (TARGET_LAYOUT, "Open in QGIS Layout designer", ""),
)

#: What to plot.
AREA_DISPLAY = "display"
AREA_EXTENTS = "extents"
AREA_WINDOW = "window"

AREAS = (
    (AREA_DISPLAY, "Display", "Whatever the map canvas is currently showing."),
    (AREA_EXTENTS, "Extents", "Everything in the drawing."),
    (AREA_WINDOW, "Window", "A rectangle picked on the canvas."),
)

AREA_KEYS = tuple(key for key, _label, _help in AREAS)
TARGET_KEYS = tuple(key for key, _label, _ext in TARGETS)

#: The name the throwaway layout carries, and the stem designer layouts get.
LAYOUT_NAME = "AutoQAD Plot"


def target_extension(target):
    """The file extension a target writes, or ``""`` for the ones that do not."""
    for key, _label, extension in TARGETS:
        if key == str(target):
            return extension
    return ""


def target_label(target):
    for key, label, _extension in TARGETS:
        if key == str(target):
            return label
    return TARGETS[0][1]


def writes_a_file(target):
    return bool(target_extension(target))


# --- settings ----------------------------------------------------------------


class PlotSettings(object):
    """One plot's configuration — the state of AutoCAD's PLOT dialog.

    Every field has a usable default, so ``PlotSettings()`` plots the whole
    drawing fitted to a landscape A3 in the drawing's own colours.
    """

    __slots__ = ("sheet", "landscape", "margin_mm", "area", "window",
                 "scale", "centred", "style_mode", "lineweights",
                 "minimum_width_mm", "target", "path", "dpi")

    def __init__(self, sheet=plot_geometry.DEFAULT_SHEET, landscape=True,
                 margin_mm=plot_geometry.DEFAULT_MARGIN_MM,
                 area=AREA_EXTENTS, window=None, scale=0.0, centred=True,
                 style_mode=plotstyle.NORMAL, lineweights=True,
                 minimum_width_mm=0.0, target=TARGET_PDF, path="", dpi=300):
        self.sheet = plot_geometry.sheet(sheet).name
        self.landscape = bool(landscape)
        self.margin_mm = max(0.0, float(margin_mm))
        self.area = area if area in AREA_KEYS else AREA_EXTENTS
        #: ``(xmin, ymin, xmax, ymax)`` when *area* is ``window``.
        self.window = plot_geometry.normalise_extent(window)
        #: Denominator; 0 means "fit to paper".
        self.scale = max(0.0, float(scale))
        self.centred = bool(centred)
        self.style_mode = plotstyle.normalise(style_mode)
        self.lineweights = bool(lineweights)
        self.minimum_width_mm = max(0.0, float(minimum_width_mm))
        self.target = target if target in TARGET_KEYS else TARGET_PDF
        self.path = str(path or "")
        self.dpi = max(48, int(dpi))

    # ---- derived ----

    @property
    def fit_to_paper(self):
        return self.scale <= 0.0

    def page_size(self):
        return plot_geometry.page_size(self.sheet, self.landscape)

    def frame_size(self):
        return plot_geometry.frame_size(self.sheet, self.landscape,
                                        self.margin_mm)

    def frame_origin(self):
        return plot_geometry.frame_origin(self.sheet, self.landscape,
                                          self.margin_mm)

    def plot_style(self):
        return plotstyle.PlotStyle(self.style_mode, self.lineweights,
                                   self.minimum_width_mm)

    # ---- value semantics ----

    def replace(self, **changes):
        data = self.to_dict()
        data.update(changes)
        return PlotSettings.from_dict(data)

    def to_dict(self):
        return {name: getattr(self, name) for name in self.__slots__}

    @classmethod
    def from_dict(cls, data):
        return cls(**dict(data or {}))

    @classmethod
    def from_variables(cls, variables, target=TARGET_PDF, path=""):
        """Seed a plot from the PLOT* system variables."""
        return cls(sheet=variables.get("PLOTSHEET"),
                   landscape=variables.get("PLOTLAND"),
                   margin_mm=variables.get("PLOTMARGIN"),
                   area=variables.get("PLOTAREA"),
                   scale=variables.get("PLOTSCALE"),
                   style_mode=variables.get("PLOTSTYLE"),
                   lineweights=variables.get("PLOTLW"),
                   minimum_width_mm=variables.get("PLOTLWMIN"),
                   dpi=variables.get("PLOTDPI"),
                   target=target, path=path)

    def save_to_variables(self, variables):
        """Write the reusable parts back, so the next PLOT remembers them.

        The window rectangle and the output path are *not* saved: both are
        answers to "this plot", not settings.
        """
        for name, value in (("PLOTSHEET", self.sheet),
                            ("PLOTLAND", self.landscape),
                            ("PLOTMARGIN", self.margin_mm),
                            ("PLOTAREA", self.area),
                            ("PLOTSCALE", self.scale),
                            ("PLOTSTYLE", self.style_mode),
                            ("PLOTLW", self.lineweights),
                            ("PLOTLWMIN", self.minimum_width_mm),
                            ("PLOTDPI", self.dpi)):
            variables.set(name, value)

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<PlotSettings {0} {1} {2}>".format(
            self.sheet, "landscape" if self.landscape else "portrait",
            "fit" if self.fit_to_paper else plot_geometry.format_scale(
                self.scale))


# --- the drawing's extent ----------------------------------------------------


def units_per_metre(crs):
    """How many map units make a metre in *crs*.

    Returns 1.0 for anything unresolvable, which is right for the metre-based
    projections CAD work almost always uses and harmless elsewhere — this feeds
    the *suggested* scale only; the layout item computes the real one.
    """
    try:
        factor = QgsUnitTypes.fromUnitToUnitFactor(DISTANCE_METERS,
                                                   crs.mapUnits())
    except (AttributeError, TypeError, ValueError):    # pragma: no cover
        return 1.0
    return factor if factor and factor > 0.0 else 1.0


def _feature_extent(layer, restrict):
    """Bounding box of the features passing *restrict*, or ``None``."""
    from qgis.core import QgsFeatureRequest

    request = QgsFeatureRequest().setFilterExpression(restrict)
    request.setSubsetOfAttributes([])
    bounds = None
    try:
        for feature in layer.getFeatures(request):
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            box = geometry.boundingBox()
            bounds = QgsRectangle(box) if bounds is None else bounds
            bounds.combineExtentWith(box)
    except RuntimeError:                               # pragma: no cover
        return None
    return bounds


def drawing_extent(document, restrict=None):
    """Return the drawing's bounding box as a tuple, or ``None`` when empty.

    Honours the plot filter so a frozen or no-plot layer cannot drag the plot
    extent out to somewhere the sheet will show as empty paper.
    """
    combined = None
    for layer in document.all_tables():
        try:
            layer.updateExtents()
        except (RuntimeError, AttributeError):         # pragma: no cover
            pass
        try:
            if layer.featureCount() == 0:
                continue
        except (RuntimeError, TypeError):              # pragma: no cover
            pass

        box = _feature_extent(layer, restrict) if restrict else layer.extent()
        if box is None or box.isEmpty():
            continue
        combined = QgsRectangle(box) if combined is None else combined
        combined.combineExtentWith(box)

    if combined is None or combined.isNull():
        return None
    return (combined.xMinimum(), combined.yMinimum(),
            combined.xMaximum(), combined.yMaximum())


def subject_extent(document, settings, canvas=None):
    """The extent the user asked to plot, before it is fitted to the frame."""
    if settings.area == AREA_WINDOW and settings.window:
        return settings.window

    if settings.area == AREA_DISPLAY and canvas is not None:
        try:
            box = canvas.extent()
            return (box.xMinimum(), box.yMinimum(),
                    box.xMaximum(), box.yMaximum())
        except (RuntimeError, AttributeError):         # pragma: no cover
            pass

    bounds = drawing_extent(document, plot_render.plot_filter(document))
    if bounds is not None:
        return bounds

    # Nothing plottable. Fall back to the canvas so the sheet at least shows
    # where the user is looking, rather than an arbitrary origin.
    if canvas is not None:
        try:
            box = canvas.extent()
            return (box.xMinimum(), box.yMinimum(),
                    box.xMaximum(), box.yMaximum())
        except (RuntimeError, AttributeError):         # pragma: no cover
            pass
    return None


def suggested_scale(document, settings, canvas=None):
    """The 1:*N* a fit would land on, for the dialog to show. Never zero."""
    bounds = subject_extent(document, settings, canvas)
    frame_w, frame_h = settings.frame_size()
    width, height = plot_geometry.extent_dimensions(
        plot_geometry.ensure_area(bounds))
    return plot_geometry.fit_scale(width, height, frame_w, frame_h,
                                   units_per_metre(document.crs()))


# --- the layout --------------------------------------------------------------


def build_layout(document, settings, canvas=None, project=None):
    """Build the print layout for this plot. Returns ``(layout, denominator)``.

    The layout is *not* added to the project — see :func:`open_in_designer` for
    the path that does.
    """
    project = project or document.project

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(LAYOUT_NAME)
    layout.setUnits(LAYOUT_MM)

    page_w, page_h = settings.page_size()
    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(page_w, page_h, LAYOUT_MM))

    frame_w, frame_h = settings.frame_size()
    origin_x, origin_y = settings.frame_origin()

    map_item = QgsLayoutItemMap(layout)
    map_item.setId("AutoQAD drawing")

    # Order matters, and getting it wrong is not a cosmetic bug. An item has to
    # be *in* the layout before it is moved or resized: positioned beforehand it
    # keeps a default frame size, and the scale QGIS then reports is computed
    # against that phantom size rather than the sheet — off by orders of
    # magnitude, silently. ``addLayoutItem`` also transfers ownership to the
    # layout, which is what stops the item outliving it.
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(origin_x, origin_y, LAYOUT_MM))
    map_item.attemptResize(QgsLayoutSize(frame_w, frame_h, LAYOUT_MM))

    # Plot in the drawing's own CRS, not the project's. A map frame with no CRS
    # of its own inherits the project's, and if that is geographic while the
    # drawing is projected, QGIS reads the drawing's metres as degrees — the
    # plot still renders, but at a scale four orders of magnitude out. There is
    # no cheap way for a user to notice that on screen, so it is pinned here.
    crs = document.crs()
    if crs is not None and crs.isValid():
        map_item.setCrs(crs)

    # White paper, always. The canvas colour is a model-space setting and has no
    # business reaching a sheet — this is the guarantee that makes a black
    # model space safe to plot from.
    map_item.setBackgroundEnabled(True)
    map_item.setBackgroundColor(QColor(255, 255, 255))
    map_item.setFrameEnabled(False)

    layers = [layer for layer in document.all_tables()]
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)

    overrides = plot_render.style_overrides(document, settings.plot_style())
    if overrides:
        map_item.setLayerStyleOverrides(overrides)
        map_item.setKeepLayerStyles(True)

    denominator = _apply_extent(map_item, document, settings, canvas,
                                frame_w, frame_h)
    return (layout, denominator)


def _apply_extent(map_item, document, settings, canvas, frame_w, frame_h):
    """Point the map item at the right ground, at the right scale.

    Fitting sets the extent and lets QGIS report the scale. A fixed scale sets a
    correctly-centred extent first and then ``setScale``, which recomputes the
    extent about that centre — so the number in the title block is the number
    QGIS actually plotted at, on any CRS.
    """
    bounds = subject_extent(document, settings, canvas)
    extent, suggestion = plot_geometry.plot_extent(
        bounds, frame_w, frame_h,
        denominator=None if settings.fit_to_paper else settings.scale,
        units_per_metre=units_per_metre(document.crs()))

    map_item.setExtent(QgsRectangle(extent[0], extent[1],
                                    extent[2], extent[3]))
    if not settings.fit_to_paper:
        try:
            map_item.setScale(float(settings.scale))
        except (RuntimeError, TypeError, ValueError):   # pragma: no cover
            pass

    try:
        return float(map_item.scale())
    except (RuntimeError, TypeError, ValueError):       # pragma: no cover
        return suggestion


# --- output ------------------------------------------------------------------


def _export_result(name):
    return enum_member(QgsLayoutExporter, "ExportResult", name)


def _describe_failure(exporter, code):
    """Turn an export result code into something a command line can print."""
    message = ""
    try:
        message = exporter.errorMessage() or ""
    except (RuntimeError, AttributeError):              # pragma: no cover
        pass
    if message:
        return message
    try:
        if code == _export_result("Canceled"):
            return "Plot cancelled."
        if code == _export_result("FileError"):
            return ("Could not write the file. Check the path is valid and "
                    "not open in another program.")
        if code == _export_result("MemoryError"):
            return "Not enough memory to render the plot at this size and DPI."
        if code == _export_result("PrintError"):
            return "The printer rejected the job."
    except AttributeError:                              # pragma: no cover
        pass
    return "The plot failed (code {0}).".format(code)


def _ensure_directory(path):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        try:
            os.makedirs(directory)
        except OSError as error:
            return str(error)
    return ""


def export_layout(layout, settings, parent=None):
    """Send *layout* wherever the settings say. Returns ``(ok, message)``."""
    exporter = QgsLayoutExporter(layout)

    if settings.target == TARGET_PRINTER:
        return _print(exporter, parent)

    path = settings.path
    if not path:
        return (False, "No output file was given.")
    problem = _ensure_directory(path)
    if problem:
        return (False, "Could not create the output folder: " + problem)

    if settings.target == TARGET_PDF:
        options = QgsLayoutExporter.PdfExportSettings()
        options.dpi = float(settings.dpi)
        # A CAD plot is linework. Rasterising it would throw away the one
        # property that makes a PDF drawing useful — that it stays sharp when
        # someone zooms into a detail.
        options.rasterizeWholeImage = False
        options.forceVectorOutput = True
        code = exporter.exportToPdf(path, options)

    elif settings.target == TARGET_SVG:
        options = QgsLayoutExporter.SvgExportSettings()
        options.dpi = float(settings.dpi)
        options.forceVectorOutput = True
        code = exporter.exportToSvg(path, options)

    else:
        options = QgsLayoutExporter.ImageExportSettings()
        options.dpi = float(settings.dpi)
        code = exporter.exportToImage(path, options)

    if code == _export_result("Success"):
        return (True, "Plotted to {0}".format(path))
    return (False, _describe_failure(exporter, code))


def _print(exporter, parent=None):
    """Send the layout to a system printer, via the standard print dialog."""
    try:
        from qgis.PyQt.QtPrintSupport import QPrintDialog, QPrinter
    except ImportError:                                 # pragma: no cover
        return (False, "Printing needs Qt's print support, which this QGIS "
                       "build does not provide. Plot to PDF instead.")

    printer = QPrinter()
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle("Plot")
    accepted = getattr(dialog, "exec", None) or getattr(dialog, "exec_")
    if not accepted():
        return (False, "Plot cancelled.")

    code = exporter.print(printer, QgsLayoutExporter.PrintExportSettings())
    if code == _export_result("Success"):
        return (True, "Plot sent to {0}.".format(printer.printerName()))
    return (False, _describe_failure(exporter, code))


def open_in_designer(layout, iface, project=None):
    """Hand the layout to the project and open QGIS's designer on it.

    The escape hatch from AutoQAD's plot dialog into the full designer, for a
    title block or anything else AutoQAD does not model. The layout is given a
    unique name so repeated previews accumulate as separate layouts rather than
    silently replacing one another — the same thing AutoCAD's named page setups
    do.
    """
    from qgis.core import QgsProject

    project = project or QgsProject.instance()
    manager = project.layoutManager()

    name = LAYOUT_NAME
    index = 2
    existing = {existing_layout.name() for existing_layout in manager.layouts()}
    while name in existing:
        name = "{0} {1}".format(LAYOUT_NAME, index)
        index += 1
    layout.setName(name)

    if not manager.addLayout(layout):
        return (False, "QGIS refused to add the layout to the project.")
    try:
        iface.openLayoutDesigner(layout)
    except (RuntimeError, AttributeError):              # pragma: no cover
        return (True, "Layout '{0}' added to the project.".format(name))
    return (True, "Opened '{0}' in the Layout designer.".format(name))


def plot(document, settings, canvas=None, iface=None, project=None,
         parent=None):
    """Build and output one plot. Returns ``(ok, message)``.

    The whole of PLOT, in one call an agent or a script can make.
    """
    project = project or document.project
    try:
        layout, denominator = build_layout(document, settings, canvas, project)
    except (RuntimeError, ValueError) as error:
        return (False, "Could not build the plot layout: {0}".format(error))

    scale_text = plot_geometry.format_scale(denominator)

    if settings.target == TARGET_LAYOUT:
        if iface is None:
            return (False, "Opening a layout needs the QGIS interface.")
        ok, message = open_in_designer(layout, iface, project)
        return (ok, "{0} Plotted at {1}.".format(message, scale_text)
                if ok else message)

    ok, message = export_layout(layout, settings, parent)
    if ok:
        return (True, "{0} at {1} on {2}.".format(
            message, scale_text, settings.sheet))
    return (ok, message)
