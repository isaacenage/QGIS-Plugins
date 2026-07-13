# -*- coding: utf-8 -*-
"""Map element — a live mirror of the QGIS map canvas.

The dashboard is its own window, but a user may still want a map tile. This
element embeds a real ``QgsMapCanvas`` that tracks ``iface.mapCanvas()``: it
shows the same displayed layers and, in **Build mode**, follows the main canvas
as the user pans/zooms or toggles layers.

The tile behaves differently in the two dashboard modes (driven by the layout
lock via :meth:`set_interactive`):

* **Build mode** (unlocked): the hosting :class:`~dashboard_canvas.GridTile` owns
  the mouse through its full-tile drag overlay (like every other tile), so a
  left-drag anywhere on the map moves the tile and a right-click opens the tile
  menu. The map itself is inert — it mirrors the QGIS extent and pushes no filter.
* **Use mode** (locked): a left-**drag** pans the map (a ``QgsMapToolPan``) and a
  left-**click** (no drag) **identifies** the bound layer's feature under the
  cursor in a small popup. Panning/zooming pushes a debounced spatial extent
  filter so connected
  tiles re-query to the visible frame (it is a filter **source**), and the map
  **flies** to the features matching its connected sources' filter (it is a
  fly-to **target**) — single feature → that feature's bounds, many → their union.
  Clearing the filter returns the map to mirroring the QGIS canvas.

Wiring (both as a source and as a fly-to target) is edited from the tile's
``Connections…`` menu like any other element. A ``source_filter_mode`` config
(``off`` / ``extent`` / ``selection`` / ``relay``, default ``extent``; it
supersedes the legacy ``extent_filter_enabled`` bool) chooses what the map pushes:
the visible extent, the bound layer's selected features, or a relay of whatever
filter it receives. As a *visual target* it also renders a filtered clone of its
bound layer when a connected source (Filter/Legend) filters it.
"""

from html import escape

from qgis.PyQt.QtCore import QTimer, Qt, QPoint
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QFrame, QVBoxLayout, QLabel
from qgis.gui import QgsMapCanvas, QgsMapToolPan, QgsRubberBand
from qgis.core import (
    QgsFeatureRequest, QgsRectangle, QgsGeometry, NULL,
    QgsExpressionContext, QgsExpressionContextUtils,
)
from .base import DashboardElement, _FILTER_UNSET
from .map_filter import extent_filter_expression
from .map_identify import search_rect, feature_summary

# a left press/release that moves under this many pixels counts as a click
# (identify) rather than a drag (pan).
CLICK_THRESHOLD = 4
# identify search box half-size, in screen pixels around the click.
IDENTIFY_TOL_PX = 6


class _PanIdentifyTool(QgsMapToolPan):
    """Use-mode map tool: a left-drag pans, a left-click (no drag) identifies.

    Panning is handled by :class:`QgsMapToolPan` (the canonical left-drag pan, so
    the user no longer needs the middle mouse button); we only add the
    click-to-identify on top. A press that moves less than ``CLICK_THRESHOLD`` px
    before release counts as a click rather than a pan.

    Build-mode moving is **not** handled here — the hosting ``GridTile``'s
    full-tile drag overlay owns the mouse in Build mode, and this tool is only
    installed while the tile is in Use mode (see ``MapElement.set_interactive``).
    """

    def __init__(self, canvas, on_identify):
        super().__init__(canvas)
        self._on_identify = on_identify   # callable(local_QPoint) -> identify
        # press pos (canvas px) for click/drag detection
        self._press = None
        self._moved = 0         # cumulative movement (px) since press

    def canvasPressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.pos()
            self._moved = 0
        super().canvasPressEvent(e)

    def canvasMoveEvent(self, e):
        if self._press is not None:
            self._moved = max(self._moved,
                              (e.pos() - self._press).manhattanLength())
        super().canvasMoveEvent(e)

    def canvasReleaseEvent(self, e):
        super().canvasReleaseEvent(e)   # let QgsMapToolPan finish the pan
        click = (e.button() == Qt.MouseButton.LeftButton
                 and self._press is not None and self._moved <= CLICK_THRESHOLD)
        self._press = None
        if click:
            self._on_identify(e.pos())


class IdentifyPopup(QFrame):
    """A small themed popup of ``field: value`` rows shown near an identify click."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("identifyPopup")
        self.setVisible(False)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(10, 8, 10, 8)
        self._lay.setSpacing(2)

    def show_rows(self, point, rows, theme):
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not rows:
            self.setVisible(False)
            return
        # soft hairline border + theme surface; never a heavy/dark outline
        self.setStyleSheet(
            "#identifyPopup{{background:{bg};border:1px solid {border};"
            "border-radius:6px;}}"
            "QLabel{{color:{text};background:transparent;"
            "font-family:{font};font-size:{size}px;}}".format(
                bg=theme.surface_bg, border=theme.border, text=theme.text,
                font=theme.font_stack(), size=theme.font_size))
        for name, val in rows:
            lab = QLabel("<b>{}</b>&nbsp;&nbsp;{}".format(
                escape(str(name)), escape(str(val))))
            lab.setTextFormat(Qt.TextFormat.RichText)
            self._lay.addWidget(lab)
        self.adjustSize()
        par = self.parentWidget()
        x, y = point.x() + 12, point.y() + 12
        if par is not None:
            x = min(x, max(par.width() - self.width(), 0))
            y = min(y, max(par.height() - self.height(), 0))
        self.move(max(x, 0), max(y, 0))
        self.setVisible(True)
        self.raise_()


class MapElement(DashboardElement):
    type_name = "map"
    # The map honors an incoming filter for *rendering* only: when a connected
    # source (Filter/Legend) pushes a subset-compatible expression, the map shows
    # a filtered **clone** of its bound layer (the shared project layer is never
    # touched). Its identify / fly-to helpers stay filter-agnostic.
    accepts_filter = True
    is_filter_source = True   # the visible extent / selection drives connected tiles
    full_bleed = True   # the canvas fills the tile: no title/description, no padding
    # handles_own_body_drag stays False (inherited): in Build mode the tile's
    # full-tile drag overlay moves the map and routes its right-click menu, just
    # like every other tile. Use-mode pan/identify run through
    # _PanIdentifyTool.

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        # migrate the legacy bool flag to the source-mode key once, so the
        # Configure dialog reflects the real mode and future saves use the new
        # key.
        self.config["source_filter_mode"] = self._source_mode()
        self.config.pop("extent_filter_enabled", None)
        # map tiles start inert; the hosting tile applies the real mode via
        # set_interactive once it is placed (honouring the layout lock).
        self._interactive = False
        self.canvas = QgsMapCanvas()
        # Bring the embedded canvas to parity with the main QGIS canvas, which
        # enables these from settings on startup. A bare QgsMapCanvas leaves all
        # three OFF, so every pan/zoom re-renders every feature from scratch,
        # synchronously on the UI thread — the cause of the stutter (badly
        # amplified by SVG markers, which get re-rasterized each frame without a
        # cache). With caching the canvas reuses rendered features, parallel
        # rendering moves the work off the UI thread, and preview jobs keep the
        # view responsive during interaction.
        self.canvas.setCachingEnabled(True)
        self.canvas.setParallelRenderingEnabled(True)
        self.canvas.setPreviewJobsEnabled(True)
        self.body.addWidget(self.canvas)
        # Use-mode interaction tool: left-drag pans, left-click identifies. It is
        # installed only while the tile is in Use mode (set_interactive); in Build
        # mode the GridTile's drag overlay owns the mouse, so the map has no
        # tool.
        self._tool = _PanIdentifyTool(self.canvas, self._identify_at)
        self._rubber = None
        self._identify_popup = None
        # the last combined-source filter we flew to, so the map's own extent
        # pushes (which don't change it) never trigger a re-fly / feedback
        # loop.
        self._last_fly_expr = None
        # the last expression we pushed as a source — guards against re-emitting
        # the same filter (esp. in relay mode, where pushing would otherwise
        # re-fire filtersChanged -> recompute -> push in a loop).
        self._last_pushed = None
        # set when the map programmatically flies to an incoming filter, so the
        # extentsChanged it provokes does NOT push the flown-to extent back out as
        # a source filter. Without this, clicking a chart wired to the map causes
        # fly -> extent push -> every connected tile re-queries with the heavy
        # per-feature intersects(transform(...)) spatial expression — the multi-
        # second freeze. A fly-to should zoom the map, not re-filter the dashboard
        # by the zoom rectangle (a genuine user pan still pushes normally).
        self._suppress_extent_push = False
        # rendering-only filtered clone of the bound layer (visual target).
        self._filtered_clone = None
        # the bound layer whose selectionChanged we are subscribed to (selection
        # source mode), so we can detach cleanly on a mode / layer change.
        self._sel_layer = None

        # debounce: a pan/zoom drag emits many extentsChanged; coalesce them
        # into one filter push so connected tiles re-query once on settle.
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self._push_source_filter)

        self._source = self._qgis_canvas()
        if self._source is not None:
            self._source.extentsChanged.connect(self._sync_extent)
            self._source.layersChanged.connect(self.refresh)
            self._source.destinationCrsChanged.connect(self._sync_crs)
        # the tile's own extent (driven by Use-mode pan/zoom/fly) is what we
        # push
        self.canvas.extentsChanged.connect(self._schedule_filter)
        # any pan/zoom/fly moves the view out from under a popped identify
        # result
        self.canvas.extentsChanged.connect(self._dismiss_identify)
        # re-evaluate when the wiring graph changes (a target was
        # (un)connected)
        self.bus.connectionsChanged.connect(self._schedule_filter)
        self.bus.featureAction.connect(self._zoom_to)
        # fly-to target: react to any connected source's filter changing
        self.bus.filtersChanged.connect(self._fly_to_filtered)
        # relay source mode re-pushes the incoming filter when it changes
        self.bus.filtersChanged.connect(self._schedule_filter)
        self._update_selection_hook()
        self.apply_theme()
        self.refresh()

    def _qgis_canvas(self):
        iface = getattr(self.bus, "iface", None)
        return iface.mapCanvas() if iface is not None else None

    def teardown(self):
        self._filter_timer.stop()
        self._detach_selection_hook()
        self._drop_clone()
        for sig, slot in ((self.bus.connectionsChanged, self._schedule_filter),
                          (self.bus.filtersChanged, self._fly_to_filtered),
                          (self.bus.filtersChanged, self._schedule_filter),
                          (self.canvas.extentsChanged, self._schedule_filter),
                          (self.canvas.extentsChanged, self._dismiss_identify)):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        src = self._source
        if src is None:
            return
        for sig, slot in ((src.extentsChanged, self._sync_extent),
                          (src.layersChanged, self.refresh),
                          (src.destinationCrsChanged, self._sync_crs)):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        self._source = None

    def reconfigure(self):
        # full-bleed: no title chrome to update. Re-evaluate the source mode (the
        # selection hook + a fresh push) and re-render so a mode / layer change
        # takes effect immediately.
        self.apply_theme()
        self._update_selection_hook()
        self._last_pushed = None       # force the new mode to re-push
        self._last_combined_filter = _FILTER_UNSET   # don't skip the next filter
        self.refresh()
        self._push_source_filter()

    def _restyle(self):
        # the map background is a per-tile style role; the identify popup reads
        # the effective theme directly (so its surface/text/border overrides,
        # exposed as the "Identify popup" role, apply automatically).
        th = self.effective_theme()
        self.canvas.setCanvasColor(
            QColor(
                self.style_get(
                    "map_bg",
                    th.surface_bg)))
        self.canvas.refresh()

    # ---- interaction mode (Use vs Build) ----

    def set_interactive(self, on):
        super().set_interactive(on)
        self._dismiss_identify()
        if on:
            # entering Use mode: install the pan/identify tool (left-drag pans,
            # left-click identifies) and become a source (push extent if wired)
            self.canvas.setMapTool(self._tool)
            self._schedule_filter()
            self._last_fly_expr = None
            self._fly_to_filtered()
        else:
            # leaving Use mode: drop the tool (the tile overlay takes the mouse),
            # stop being a source and re-mirror the QGIS canvas
            self.canvas.unsetMapTool(self._tool)
            self._set_pushed(None)
            self._last_fly_expr = None
            self._sync_extent(force=True)

    # ---- cross-filter source (extent / selection / relay) ----

    def _source_mode(self):
        """The map's source strategy, migrating the legacy bool flag.

        ``off`` / ``extent`` / ``selection`` / ``relay``. Older blobs carry
        ``extent_filter_enabled`` (bool) instead of ``source_filter_mode``:
        ``False`` -> ``off``, ``True`` / absent -> ``extent``.
        """
        mode = self.config.get("source_filter_mode")
        if mode in ("off", "extent", "selection", "relay"):
            return mode
        return "extent" if self.config.get(
            "extent_filter_enabled", True) else "off"

    def showEvent(self, event):
        # Becoming the active page's map: re-apply the current source filter so it
        # belongs to this page (pushes are gated on visibility, below).
        super().showEvent(event)
        self._schedule_filter()

    def _schedule_filter(self):
        self._filter_timer.start()

    def _set_pushed(self, expr):
        """Push *expr* as this map's source filter, skipping no-op repeats."""
        if expr == self._last_pushed:
            return
        self._last_pushed = expr
        self.bus.set_filter(self.id, expr)

    def _push_source_filter(self):
        # A fly-to (reacting to an incoming filter) provokes an extentsChanged
        # that schedules this push; consume the suppression flag so we don't push
        # the flown-to extent back out (which would re-query every connected tile
        # with the heavy spatial expression). Read+clear before the early returns
        # so the flag never gets stuck.
        suppress = self._suppress_extent_push
        self._suppress_extent_push = False
        # Only the visible (active-page) map in Use mode pushes, so its filter
        # never lands in another page's page-local filter state and a Build-mode
        # map never filters anything.
        if not self._interactive or not self.isVisible():
            return
        mode = self._source_mode()
        if mode == "extent":
            if suppress:
                return
            ext = self.canvas.extent()
            authid = self.canvas.mapSettings().destinationCrs().authid()
            expr = extent_filter_expression(
                ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum(),
                authid or None)
        elif mode == "selection":
            lyr = self.layer()
            ids = list(lyr.selectedFeatureIds()) if lyr is not None else []
            expr = "$id IN ({})".format(", ".join(str(i)
                                                  for i in ids)) if ids else None
        elif mode == "relay":
            # forward whatever our connected sources filter us by, so a
            # Filter/Legend wired only to the map propagates to the map's
            # targets.
            expr = self.bus.combined_filter_for(self.id)
        else:   # "off"
            expr = None
        self._set_pushed(expr)

    # ---- selection-source subscription ----

    def _update_selection_hook(self):
        """Subscribe to the bound layer's selection iff in 'selection' mode."""
        self._detach_selection_hook()
        if self._source_mode() != "selection":
            return
        lyr = self.layer()
        if lyr is not None:
            lyr.selectionChanged.connect(self._schedule_filter)
            self._sel_layer = lyr

    def _detach_selection_hook(self):
        if self._sel_layer is not None:
            try:
                self._sel_layer.selectionChanged.disconnect(
                    self._schedule_filter)
            except (TypeError, RuntimeError):
                pass
            self._sel_layer = None

    # ---- rendering-only visual subset (target) ----

    def _drop_clone(self):
        if self._filtered_clone is not None:
            self._filtered_clone.deleteLater()
            self._filtered_clone = None

    # ---- mirror the main QGIS canvas ----

    def refresh(self):
        src = self._source
        if src is None:
            return
        base_layers = list(src.layers())
        layers = base_layers
        new_clone = None
        # visual target: if a connected source filters us with a subset-compatible
        # expression, render a filtered clone of the bound layer in its place. The
        # shared project layer is never modified. A spatial expr (from another map)
        # that the provider can't compile is detected via setSubsetString -> render
        # unfiltered.
        bound = self.layer()
        incoming = self.bus.combined_filter_for(self.id)
        if incoming and bound is not None and bound in base_layers:
            clone = bound.clone()
            if clone.setSubsetString(incoming):
                new_clone = clone
                layers = [
                    new_clone if lyr is bound else lyr for lyr in base_layers]
        self.canvas.setLayers(layers)
        old = self._filtered_clone
        self._filtered_clone = new_clone
        self._sync_crs()
        self._sync_extent()
        if old is not None and old is not new_clone:
            old.deleteLater()

    def _sync_crs(self):
        if self._source is not None:
            self.canvas.setDestinationCrs(
                self._source.mapSettings().destinationCrs())
            self.canvas.refresh()

    def _sync_extent(self, force=False):
        # Mirror the QGIS extent only in Build mode; in Use mode the tile is
        # independently navigable, so a live pan must not be overwritten by an
        # iface extentsChanged. `force` re-mirrors on the way back to Build
        # mode.
        if self._source is None:
            return
        if self._interactive and not force:
            return
        self.canvas.setExtent(self._source.extent())
        self.canvas.refresh()

    # ---- Use-mode identify ----

    def _identify_at(self, local_point):
        lyr = self.layer()
        if lyr is None:
            self._dismiss_identify()
            return
        transform = self.canvas.getCoordinateTransform()
        if transform is None:
            return
        map_pt = transform.toMapCoordinates(local_point.x(), local_point.y())
        tol = transform.mapUnitsPerPixel() * IDENTIFY_TOL_PX
        xmin, ymin, xmax, ymax = search_rect(map_pt.x(), map_pt.y(), tol)
        req = QgsFeatureRequest().setFilterRect(QgsRectangle(xmin, ymin, xmax, ymax))
        feat = next(iter(lyr.getFeatures(req)), None)
        if feat is None:
            self._dismiss_identify()
            return
        names = [f.name() for f in lyr.fields()]
        # convert QGIS NULLs to None so the pure summary renders them as blanks
        values = [None if v == NULL else v for v in feat.attributes()]
        rows = feature_summary(names, values, limit=12)
        if self._identify_popup is None:
            self._identify_popup = IdentifyPopup(self.canvas)
        self._identify_popup.show_rows(
            local_point, rows, self.effective_theme())

    def _dismiss_identify(self):
        if self._identify_popup is not None:
            self._identify_popup.setVisible(False)

    # ---- fly-to target (zoom to connected sources' filtered features) ----

    def _fly_to_filtered(self):
        if not self._interactive:
            return
        # Location actions (zoom/pan/flash/show_popup) are driven only by edges
        # that declare one — a filter-only edge narrows the layer clone (via
        # refresh/combined_filter_for) but must NOT move the map.
        expr = self.bus.location_filter_for(self.id)
        # the map's own extent pushes don't change this expression, so guarding
        # on it prevents a pan -> push -> fly feedback loop.
        if expr == self._last_fly_expr:
            return
        self._last_fly_expr = expr
        if expr is None:
            # No location edge is driving the map. Re-mirror the QGIS extent only
            # on a genuine clear (nothing filtering it either); if a filter-only
            # edge is active, leave the map where the user left it.
            if self.bus.combined_filter_for(self.id) is None:
                self._sync_extent(force=True)
            return
        lyr = self.layer()
        if lyr is None:
            return
        acts = self.bus.location_actions_for(self.id)
        # One geometry-only pass: we need each matching feature's geometry (for
        # the bbox and the flash) but none of its attributes, so setNoAttributes
        # skips attribute I/O, and we reuse the collected geometries for the flash
        # instead of a second getFeatures scan.
        req = QgsFeatureRequest().setFilterExpression(expr).setNoAttributes()
        # scope so a spatial source's @layer / layer_property(...) resolves
        ctx = QgsExpressionContext()
        ctx.appendScopes(
            QgsExpressionContextUtils.globalProjectLayerScopes(lyr))
        req.setExpressionContext(ctx)
        rect = QgsRectangle()
        rect.setMinimal()
        geoms = []
        for f in lyr.getFeatures(req):
            geom = f.geometry()
            if not geom.isEmpty():
                rect.combineExtentWith(geom.boundingBox())
                geoms.append(QgsGeometry(geom))
        if not rect.isEmpty():
            moved = False
            if "zoom" in acts:
                rect.scale(1.5)
                # a reaction to a selection, not a user pan: don't push it back
                # out
                self._suppress_extent_push = True
                self.canvas.setExtent(rect)
                moved = True
            elif "pan" in acts:
                self._suppress_extent_push = True
                self.canvas.setCenter(rect.center())
                moved = True
            if moved:
                self.canvas.refresh()
            if "flash" in acts:
                self._flash(lyr, geoms)
        if "show_popup" in acts:
            self._popup_for_expr(expr, lyr)

    def _popup_for_expr(self, expr, lyr):
        """Show the identify popup for the first feature matching *expr*.

        Reuses the Use-mode identify machinery, anchored at the feature's
        centroid (converted to canvas pixels) instead of the cursor.
        """
        ctx = QgsExpressionContext()
        ctx.appendScopes(
            QgsExpressionContextUtils.globalProjectLayerScopes(lyr))
        req = QgsFeatureRequest().setFilterExpression(expr)
        req.setExpressionContext(ctx)
        feat = next(iter(lyr.getFeatures(req)), None)
        if feat is None:
            return
        geom = feat.geometry()
        if geom.isEmpty():
            return
        transform = self.canvas.getCoordinateTransform()
        if transform is None:
            return
        centroid = geom.centroid().asPoint()
        dev = transform.transform(centroid)
        point = QPoint(int(dev.x()), int(dev.y()))
        names = [f.name() for f in lyr.fields()]
        values = [None if v == NULL else v for v in feat.attributes()]
        rows = feature_summary(names, values, limit=12)
        if self._identify_popup is None:
            self._identify_popup = IdentifyPopup(self.canvas)
        self._identify_popup.show_rows(point, rows, self.effective_theme())

    # ---- feature action (zoom/flash on a list-row pick) ----

    def _zoom_to(self, fids):
        lyr = self.layer()
        if lyr is None or not fids:
            return
        # geometry-only single pass, reused for both the bbox and the flash
        req = QgsFeatureRequest().setFilterFids(fids).setNoAttributes()
        rect = QgsRectangle()
        rect.setMinimal()
        geoms = []
        for f in lyr.getFeatures(req):
            geom = f.geometry()
            if not geom.isEmpty():
                rect.combineExtentWith(geom.boundingBox())
                geoms.append(QgsGeometry(geom))
        if not rect.isEmpty():
            rect.scale(1.5)
            self._suppress_extent_push = True   # programmatic zoom, not a user pan
            self.canvas.setExtent(rect)
            self.canvas.refresh()
            self._flash(lyr, geoms)

    def _flash(self, lyr, geoms):
        if self._rubber:
            self.canvas.scene().removeItem(self._rubber)
        self._rubber = QgsRubberBand(self.canvas, lyr.geometryType())
        self._rubber.setWidth(3)
        for geom in geoms:
            self._rubber.addGeometry(geom, lyr)
        QTimer.singleShot(1200, self._clear_flash)

    def _clear_flash(self):
        if self._rubber:
            self.canvas.scene().removeItem(self._rubber)
            self._rubber = None
