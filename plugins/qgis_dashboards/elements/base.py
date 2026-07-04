# -*- coding: utf-8 -*-
"""Base element.

ArcGIS Dashboards elements share an anatomy: a title area, a visualization
area, and a description area, plus a data source (a layer) and an optional
filter. This base class encodes that so indicator / chart / list elements only
implement their visualization.

Identity & wiring:
  - every element carries a stable ``id`` (persisted in ``config``) so the
    user-defined connection graph on the bus can route filters source->target.
  - a target's live filter is ``bus.combined_filter_for(self.id)`` AND-ed with
    the element-local ``base_filter``.

Appearance:
  - the effective theme is the global ``bus.theme`` merged with this element's
    optional per-tile override (``config["style"]``); ``apply_theme`` restyles
    the tile and lets subclasses repaint custom views.
"""

import uuid

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPainterPath, QRegion
from qgis.PyQt.QtWidgets import QFrame, QVBoxLayout, QLabel
from qgis.core import (
    QgsProject,
    QgsFeatureRequest,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
)

from .style_migrate import migrate_element_style
from .aggregate_filter import inject_filter

# Appended after a chosen family so a per-tile role font degrades gracefully
# (mirrors theme.Theme._FONT_FALLBACK).
_FONT_FALLBACK = '"Segoe UI", "Helvetica Neue", Arial, sans-serif'

_ALIGN = {
    "left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    "center": Qt.AlignmentFlag.AlignCenter,
    "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
}

# Sentinel for "we have never computed a combined filter yet", so the first
# filtersChanged after construction always refreshes (distinct from None, which
# is a real, unfiltered combined-filter value). See ``_on_filters_changed``.
_FILTER_UNSET = object()


class DashboardElement(QFrame):
    """A single dashboard tile. Subclass and implement refresh()."""

    type_name = "element"
    is_filter_source = False   # pushes filters onto the bus
    accepts_filter = True      # re-queries when a connected source filters
    full_bleed = False         # when True the visualization fills the tile
                               # edge-to-edge: no title/description chrome and
                               # no internal padding (e.g. the live map mirror)
    handles_own_body_drag = False   # when True the element drives its own
                               # body drag in Build mode (e.g. the map), so the
                               # tile keeps a thin top drag strip instead of the
                               # full-tile drag overlay every other tile gets

    def __init__(self, bus, config=None, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.config = config or {}
        self.id = self.config.get("id") or uuid.uuid4().hex[:8]
        self.config["id"] = self.id
        # relocate any legacy top-level visual keys into config["style"] so the
        # per-tile appearance system reads them uniformly via style_get().
        migrate_element_style(self.config, self.type_name,
                              getattr(self.bus, "theme", None))
        # elements with the shared title chrome (not full-bleed, not a tile that
        # renders its own heading like text/header) get per-tile title styling.
        self._has_base_title = not self.full_bleed
        # content-interaction mode (Use vs Build): True == Use mode, contents
        # react to the user (cross-filter clicks, map pan/identify); False ==
        # Build mode, contents inert so tiles can be moved/resized/configured.
        # The hosting GridTile drives this from the layout lock via
        # ``set_interactive``; the initial value is overwritten when the tile is
        # placed (DashboardCanvas.add_tile -> GridTile.set_locked).
        self._interactive = True
        # the combined filter we last refreshed on; a filtersChanged that leaves
        # it unchanged is a no-op for this tile, so we skip the layer re-query.
        self._last_combined_filter = _FILTER_UNSET
        self.setObjectName("dashboardElement")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # full-bleed tiles fill edge-to-edge; their rectangular child is clipped
        # to the theme's rounded corners in _update_fullbleed_mask so the map /
        # image follow the global corner radius like every other tile
        self.setProperty("fullBleed", bool(self.full_bleed))

        self._outer = QVBoxLayout(self)
        if self.full_bleed:
            self._outer.setContentsMargins(0, 0, 0, 0)
            self._outer.setSpacing(0)
        else:
            self._outer.setContentsMargins(12, 8, 12, 10)
            self._outer.setSpacing(6)

        # --- title area (omitted entirely for full-bleed tiles) ---
        self.title_label = QLabel(self.config.get("title", self.type_name.title()))
        self.title_label.setObjectName("elementTitle")
        if self.full_bleed:
            self.title_label.hide()
        else:
            self._outer.addWidget(self.title_label)

        # --- visualization area (subclasses fill this) ---
        self.body = QVBoxLayout()
        self.body.setSpacing(0 if self.full_bleed else 4)
        self._outer.addLayout(self.body, stretch=1)

        # --- description area (optional; omitted for full-bleed tiles) ---
        desc = self.config.get("description")
        self.desc_label = QLabel(desc or "")
        self.desc_label.setObjectName("elementDescription")
        self.desc_label.setWordWrap(True)
        if self.full_bleed:
            self.desc_label.hide()
        else:
            self.desc_label.setVisible(bool(desc))
            self._outer.addWidget(self.desc_label)

        # subscribe to the cross-filter bus + appearance
        self.bus.filtersChanged.connect(self._on_filters_changed)
        self.bus.layersChanged.connect(self.refresh)
        self.bus.themeChanged.connect(self.apply_theme)
        self.bus.filtersCleared.connect(self._on_filters_cleared)

    # ---- identity / metadata ----

    def display_name(self):
        from ..elements import ELEMENT_LABELS
        title = self.config.get("title")
        return title or ELEMENT_LABELS.get(self.type_name, self.type_name)

    # ---- appearance ----

    def effective_theme(self):
        return self.bus.theme.merged_with(self.config.get("style"))

    def style_get(self, key, default=None):
        """Read a per-tile style override value (``config["style"]``).

        An absent key — or one cleared to ``None``/``""`` — yields *default*, so
        an untouched role tracks the theme-derived fallback the caller passes.
        """
        style = self.config.get("style")
        if isinstance(style, dict):
            val = style.get(key)
            if val not in (None, ""):
                return val
        return default

    def apply_text_role(self, label, prefix, *, color, font, size,
                        weight=400, italic=False, align=None, force_color=None):
        """Apply a styled text *role* to *label* from ``config["style"]``.

        Reads ``{prefix}_color/_font/_px/_weight/_italic`` (and ``_align`` when
        *align* is given), each falling back to the theme-derived value passed
        in, and sets one inline stylesheet so the role wins over the inherited
        tile QSS. Keeps every element's role styling DRY. ``force_color`` wins
        over the role/theme color (used by the indicator's trend coloring).
        """
        c = force_color or self.style_get(prefix + "_color", color)
        fam = self.style_get(prefix + "_font", font)
        px = int(self.style_get(prefix + "_px", size) or size)
        w = int(self.style_get(prefix + "_weight", weight) or weight)
        it = bool(self.style_get(prefix + "_italic", italic))
        label.setStyleSheet(
            'color:{c}; font-family:"{f}", {fb}; font-size:{px}px;'
            ' font-weight:{w}; font-style:{st}; background:transparent;'.format(
                c=c, f=fam, fb=_FONT_FALLBACK, px=px, w=w,
                st="italic" if it else "normal"))
        if align is not None:
            a = self.style_get(prefix + "_align", align)
            label.setAlignment(_ALIGN.get(a, _ALIGN["left"]))
        return label

    def apply_theme(self):
        self.setStyleSheet(self.effective_theme().tile_qss())
        self._update_fullbleed_mask()
        self._style_base_title()
        self._restyle()

    def _style_base_title(self):
        """Style the shared ``#elementTitle`` from the per-tile ``title_*`` role.

        Defaults reproduce the tile-QSS heading look (theme text color / heading
        family / title size / weight 600) so untouched tiles are unchanged.
        Elements that render their own heading (text/header) or are full-bleed
        opt out via ``_has_base_title``.
        """
        if not getattr(self, "_has_base_title", False):
            return
        th = self.effective_theme()
        self.apply_text_role(self.title_label, "title", color=th.text,
                             font=th.heading_family(), size=th.title_size,
                             weight=600, italic=False, align="left")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_fullbleed_mask()

    def _update_fullbleed_mask(self):
        """Clip a full-bleed tile to the theme's rounded corners.

        A normal tile gets its rounded corners from the QSS ``border-radius`` on
        ``#dashboardElement``. A full-bleed tile holds a rectangular child that
        paints over those corners — most notably the map's ``QgsMapCanvas`` (a
        ``QGraphicsView`` whose viewport ignores stylesheet rounding). To make
        the map and image follow the global corner radius we mask the whole tile
        to a rounded region (re-applied on resize / theme change). Non-full-bleed
        tiles need no mask — their QSS rounding already shows.
        """
        if not self.full_bleed:
            return
        w, h = self.width(), self.height()
        r = self.effective_theme().radius
        if w <= 0 or h <= 0:
            return
        if r <= 0:
            self.clearMask()
            return
        r = min(float(r), w / 2.0, h / 2.0)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(w), float(h), r, r)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def _restyle(self):
        """Hook for subclasses with custom-painted views; default repaint."""
        self.update()

    def reconfigure(self):
        """Re-read ``config`` after an in-place edit (the Configure dialog).

        Updates the shared title/description chrome and re-applies appearance +
        data so a configuration change is reflected without recreating the tile.
        Subclasses that cache config in ``__init__`` override to extend this.
        """
        self.title_label.setText(self.config.get("title", self.type_name.title()))
        desc = self.config.get("description")
        self.desc_label.setText(desc or "")
        if not self.full_bleed:
            self.desc_label.setVisible(bool(desc))
        # config edits (e.g. base_filter / layer binding) can change the combined
        # filter with no bus signal; invalidate so the next filtersChanged is
        # never wrongly skipped by the change-detection in _on_filters_changed.
        self._last_combined_filter = _FILTER_UNSET
        self.apply_theme()
        self.refresh()

    # ---- data helpers shared by every data-driven element ----

    def layer(self):
        lid = self.config.get("layer_id")
        if not lid:
            return None
        return QgsProject.instance().mapLayer(lid)

    def _combined_filter(self):
        """AND the element's own filter with its connected sources' filter."""
        parts = [p for p in (self.config.get("base_filter"),
                             self.bus.combined_filter_for(self.id)) if p]
        if not parts:
            return None
        return " AND ".join("({})".format(p) for p in parts)

    def iter_features(self):
        """Yield features honoring the combined filter. Safe if no layer."""
        lyr = self.layer()
        if lyr is None:
            return
        req = QgsFeatureRequest()
        expr_str = self._combined_filter()
        if expr_str:
            # A spatial source (the map) pushes a filter referencing ``@layer``
            # and ``layer_property(@layer, 'crs')``. Those resolve only when the
            # request carries an expression context with the layer scope —
            # without it ``layer_property`` is NULL, ``intersects`` is NULL, and
            # ``coalesce(..., true)`` lets every feature through, so the chart /
            # list / pivot never filter by extent (the indicator did, because its
            # ``evaluate`` builds this same scoped context). Provide it here.
            ctx = QgsExpressionContext()
            ctx.appendScopes(
                QgsExpressionContextUtils.globalProjectLayerScopes(lyr))
            req.setExpressionContext(ctx)
            req.setFilterExpression(expr_str)
        for f in lyr.getFeatures(req):
            yield f

    def evaluate(self, expression_str):
        """Evaluate an aggregate-style QgsExpression against the layer.

        QGIS aggregate functions ignore the feature-request filter, so the live
        cross-filter is spliced directly into every aggregate call as its
        ``filter:=`` argument (e.g. ``sum("pop")`` -> ``sum("pop",
        filter:=(<filter>))``) so an indicator reacts to its connected sources
        like the iterate-based elements do. The filter is also exposed as the
        ``@dashboard_filter`` variable for expressions that reference it.
        """
        lyr = self.layer()
        if lyr is None or not expression_str:
            return None
        flt = self._combined_filter()
        expr = QgsExpression(inject_filter(expression_str, flt))
        ctx = QgsExpressionContext()
        ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(lyr))
        if flt is not None and ctx.lastScope() is not None:
            ctx.lastScope().setVariable("dashboard_filter", flt)
        val = expr.evaluate(ctx)
        if expr.hasEvalError():
            return None
        return val

    # ---- interaction mode (Use vs Build) ----

    def set_interactive(self, on):
        """Enable/disable content interaction (Use mode vs Build mode).

        In **Use mode** (``on=True``) the element's contents react to the user
        (clicking a chart to cross-filter, selecting a list row, panning the
        map). In **Build mode** (``on=False``) contents are inert so the user
        can move / resize / configure tiles without firing filters. Presentational
        elements need nothing; interactive elements (chart, pivot, list, selector,
        text, map) override and act on the flag.
        """
        self._interactive = bool(on)

    def on_tile_double_click(self):
        """Double-click on the tile body (Build mode only).

        The Build-mode drag overlay covers the whole tile, so a double-click on
        the body is routed here instead of reaching the element directly. Most
        elements do nothing; the text tile overrides this to edit its text.
        """
        pass

    # ---- bus reaction ----

    def _on_filters_changed(self):
        # filtersChanged is a payload-less global broadcast: it fires for *any*
        # source's change. This tile only needs to re-query when *its own*
        # combined filter actually changes (i.e. a source it is wired to
        # changed). Short-circuiting the unchanged case keeps a single filter
        # edit O(connected tiles) instead of O(all tiles) — the difference
        # between snappy and frozen on a dashboard with many tiles.
        if not self.accepts_filter:
            return
        flt = self._combined_filter()
        if flt == self._last_combined_filter:
            return
        self._last_combined_filter = flt
        self.refresh()

    def _on_filters_cleared(self):
        """Sources override to reset their own selection state."""
        pass

    def refresh(self):
        """Subclasses override to redraw from current data + filter."""
        raise NotImplementedError

    def teardown(self):
        """Release external signal connections before the tile is destroyed.

        Bus connections are auto-dropped when this QObject dies; subclasses
        that wire *long-lived external* signals (e.g. the QGIS map canvas)
        override this to disconnect them explicitly.
        """
        pass

    # ---- persistence ----

    def to_dict(self):
        d = dict(self.config)
        d["__type__"] = self.type_name
        d["id"] = self.id
        return d
