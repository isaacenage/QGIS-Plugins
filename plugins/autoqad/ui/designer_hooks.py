# -*- coding: utf-8 -*-
"""AutoQAD inside QGIS's own Layout designer.

The designer is QGIS's window, not AutoQAD's, and the honest limits are worth
stating because they decide the shape of this module:

* You **can** reach it. ``iface.layoutDesignerOpened`` hands over a
  :class:`QgsLayoutDesignerInterface`, whose ``window()`` is a real
  ``QMainWindow`` — so a toolbar, actions and dock widgets can be added.
* You **cannot** meaningfully restyle it. Its widgets are QGIS's, and a
  stylesheet broad enough to reach them would leak into the rest of QGIS. So
  AutoQAD adds *actions*, never a skin.

What actually matters is not the chrome anyway. A map frame in the designer
inherits the drawing's model-space colours — ACI 7 resolved white against a
black canvas — so on white paper it plots as a blank sheet. That is a rendering
problem, and it is solved by the same style overrides
:mod:`..style.plot_render` builds for AutoQAD's own plot path.

So this module does two things:

1. **Applies the plot style automatically** to every map frame in a designer
   opened while AutoQAD is active (the ``PLOTAUTO`` variable, on by default).
   That is the answer to "while AutoQAD is on, the layout should be black on
   white regardless of what the canvas looks like".
2. **Adds an AutoQAD toolbar** to the designer with the manual equivalents:
   re-apply the plot style, drop it again, and zoom the frame to the drawing.

Everything is reversible. :meth:`DesignerHooks.detach` removes every toolbar it
added and disconnects the signal, so unloading the plugin leaves the designer as
QGIS shipped it.
"""

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QToolBar

from ..core.compat import QAction
from ..io import plot as plot_io
from ..style import plot_render, plotstyle
from . import icons, theme

#: The object name AutoQAD's toolbar carries, so it can be found and removed.
TOOLBAR_NAME = "aqDesignerToolbar"


def map_items(layout):
    """Every :class:`QgsLayoutItemMap` in *layout*, in layout order."""
    from qgis.core import QgsLayoutItemMap

    if layout is None:
        return []
    try:
        return [item for item in layout.items()
                if isinstance(item, QgsLayoutItemMap)]
    except (RuntimeError, AttributeError):        # pragma: no cover
        return []


def apply_plot_style(layout, document, plot_style=None, white_paper=True):
    """Give every map frame in *layout* the drawing's paper style.

    Returns the number of frames changed. Frames showing none of the drawing's
    layers are left alone — a layout may legitimately hold a locator map of
    something else entirely, and recolouring that would be vandalism.
    """
    overrides = plot_render.style_overrides(document, plot_style)
    if not overrides:
        return 0

    from qgis.PyQt.QtGui import QColor

    drawing_ids = set(overrides)
    changed = 0
    for item in map_items(layout):
        try:
            shown = {layer.id() for layer in item.layers()}
        except (RuntimeError, AttributeError):    # pragma: no cover
            continue
        # An empty layer set means "follow the project", which does include the
        # drawing — so those count too.
        if shown and not (shown & drawing_ids):
            continue

        item.setLayerStyleOverrides(overrides)
        item.setKeepLayerStyles(True)
        if white_paper:
            item.setBackgroundEnabled(True)
            item.setBackgroundColor(QColor(255, 255, 255))
        item.invalidateCache()
        item.refresh()
        changed += 1
    return changed


def clear_plot_style(layout):
    """Drop AutoQAD's style overrides from every map frame. Returns the count."""
    changed = 0
    for item in map_items(layout):
        try:
            if not item.keepLayerStyles():
                continue
        except (RuntimeError, AttributeError):    # pragma: no cover
            continue
        item.setLayerStyleOverrides({})
        item.setKeepLayerStyles(False)
        item.invalidateCache()
        item.refresh()
        changed += 1
    return changed


def zoom_to_drawing(layout, document):
    """Point every map frame at the drawing's extents. Returns the count."""
    from qgis.core import QgsRectangle

    bounds = plot_io.drawing_extent(document,
                                    plot_render.plot_filter(document))
    if bounds is None:
        return 0

    rectangle = QgsRectangle(bounds[0], bounds[1], bounds[2], bounds[3])
    changed = 0
    for item in map_items(layout):
        item.zoomToExtent(rectangle)
        item.invalidateCache()
        item.refresh()
        changed += 1
    return changed


class DesignerHooks(QObject):
    """Installs AutoQAD's additions into every QGIS layout designer.

    One instance lives on the controller for the life of the session. It holds
    only weak intent — a list of the toolbars it created — so a designer the
    user closes takes its toolbar with it and nothing here has to notice.
    """

    def __init__(self, iface, document, variables, message=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.document = document
        self.variables = variables
        self._message = message
        self._toolbars = []
        self._attached = False

    # ---- lifecycle ----

    def attach(self):
        """Start hooking designers, and fix up any already open."""
        if self._attached:
            return
        signal = getattr(self.iface, "layoutDesignerOpened", None)
        if signal is not None:
            try:
                signal.connect(self._on_designer_opened)
                self._attached = True
            except (TypeError, RuntimeError):     # pragma: no cover
                self._attached = False

        for designer in self._open_designers():
            self._on_designer_opened(designer)

    def detach(self):
        """Undo everything :meth:`attach` did."""
        signal = getattr(self.iface, "layoutDesignerOpened", None)
        if signal is not None:
            try:
                signal.disconnect(self._on_designer_opened)
            except (TypeError, RuntimeError):     # pragma: no cover
                pass
        self._attached = False

        for toolbar in self._toolbars:
            try:
                window = toolbar.parentWidget()
                if window is not None:
                    window.removeToolBar(toolbar)
                toolbar.deleteLater()
            except RuntimeError:                  # designer already closed
                continue
        self._toolbars = []

    def _open_designers(self):
        """Designers already open when the session starts."""
        getter = getattr(self.iface, "openLayoutDesigners", None)
        if getter is None:
            return []
        try:
            return list(getter() or [])
        except (RuntimeError, TypeError):         # pragma: no cover
            return []

    # ---- per-designer setup ----

    def _on_designer_opened(self, designer):
        window = self._window_of(designer)
        if window is None:
            return
        self._add_toolbar(designer, window)

        if not self.variables.get("PLOTAUTO"):
            return
        if not self.document.is_open:
            return

        changed = apply_plot_style(designer.layout(), self.document,
                                   self._plot_style())
        if changed:
            self._notify(
                designer,
                "AutoQAD plot style applied to {0} map frame{1} — the drawing "
                "plots black on white. Turn this off with SETVAR PLOTAUTO 0."
                .format(changed, "" if changed == 1 else "s"))

    @staticmethod
    def _window_of(designer):
        try:
            return designer.window()
        except (RuntimeError, AttributeError):    # pragma: no cover
            return None

    def _add_toolbar(self, designer, window):
        """Add the AutoQAD toolbar, unless this designer already has one."""
        existing = window.findChild(QToolBar, TOOLBAR_NAME)
        if existing is not None:
            return existing

        toolbar = QToolBar("AutoQAD", window)
        toolbar.setObjectName(TOOLBAR_NAME)

        for key, text, tip, slot in (
                ("plot", "AutoQAD plot style",
                 "Render the drawing for paper: model-space white becomes "
                 "black and the map frame gets a white background.",
                 lambda: self._apply(designer)),
                ("undo", "Drawing colours",
                 "Drop the plot style and show the drawing exactly as the "
                 "canvas does.",
                 lambda: self._clear(designer)),
                ("measure", "Zoom to drawing",
                 "Fit every map frame to the drawing's extents.",
                 lambda: self._zoom(designer))):
            # The designer is QGIS's window and follows QGIS's theme, so the
            # glyphs are tinted with the chrome text colour rather than
            # AutoQAD's accent — an accent-coloured toolbar would read as an
            # alien graft in someone else's window.
            action = QAction(
                icons.monochrome_icon(key, theme.PALETTE["text"]), text, window)
            action.setToolTip(tip)
            action.triggered.connect(slot)
            toolbar.addAction(action)

        window.addToolBar(toolbar)
        self._toolbars.append(toolbar)
        return toolbar

    # ---- actions ----

    def _plot_style(self):
        return plotstyle.PlotStyle.from_variables(self.variables)

    def _apply(self, designer):
        changed = apply_plot_style(designer.layout(), self.document,
                                   self._plot_style())
        self._notify(designer, self._count_message(
            changed, "AutoQAD plot style applied to"))

    def _clear(self, designer):
        changed = clear_plot_style(designer.layout())
        self._notify(designer, self._count_message(
            changed, "Drawing colours restored on"))

    def _zoom(self, designer):
        changed = zoom_to_drawing(designer.layout(), self.document)
        if not changed:
            self._notify(designer, "The drawing is empty — nothing to zoom to.")
            return
        self._notify(designer, self._count_message(changed, "Zoomed"))

    @staticmethod
    def _count_message(changed, verb):
        if not changed:
            return "No map frame in this layout shows the drawing."
        return "{0} {1} map frame{2}.".format(
            verb, changed, "" if changed == 1 else "s")

    # ---- feedback ----

    def _notify(self, designer, text):
        """Say it in the designer's own message bar, and in the command line."""
        bar = None
        try:
            bar = designer.messageBar()
        except (RuntimeError, AttributeError):    # pragma: no cover
            bar = None
        if bar is not None:
            try:
                bar.pushInfo("AutoQAD", text)
            except (RuntimeError, TypeError):     # pragma: no cover
                pass
        if self._message is not None:
            try:
                self._message(text)
            except RuntimeError:                  # pragma: no cover
                pass
