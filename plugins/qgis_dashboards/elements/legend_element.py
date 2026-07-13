# -*- coding: utf-8 -*-
"""Legend widget — a live, interactive legend that mirrors the map.

This tile shows **exactly what the map shows**: every vector layer on the QGIS
map canvas, in draw order, each with its current symbology (one row per legend
class, with the real symbol swatch). It is an *interactive* legend — ticking a
class off **hides that classification on the map** (and back on to show it),
exactly like the checkboxes in the QGIS Layers panel.

Implementation notes:
  * Layers + symbology come from ``iface.mapCanvas().layers()`` and each
    renderer's ``legendSymbolItems()`` — the same generic API QGIS's own legend
    uses, so it works for categorized / graduated / rule-based / single-symbol
    renderers (single-symbol layers show one non-toggle row).
  * Toggling calls ``renderer.checkLegendSymbolItem(ruleKey, on)`` then
    ``layer.triggerRepaint()``; the dashboard map (which mirrors these layers)
    and the QGIS canvas both update. The shared layer's *data* is never touched
    — only the symbology class visibility, which is what a legend toggles.
  * It is not a cross-filter bus participant (``is_filter_source`` /
    ``accepts_filter`` are both False): it controls map rendering directly, so it
    needs no Connections wiring.
"""

import contextlib

from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
from qgis.core import QgsProject, QgsVectorLayer, QgsSymbolLayerUtils

from .base import DashboardElement

_SWATCH = QSize(18, 18)
_ROLE = Qt.ItemDataRole.UserRole   # stores (layer_id, ruleKey) on toggle rows


class LegendElement(DashboardElement):
    type_name = "legend"
    is_filter_source = False
    accepts_filter = False

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setIconSize(_SWATCH)
        self.list.itemChanged.connect(self._on_item_changed)
        self.body.addWidget(self.list)
        self._suppress = False
        # mirror the live map: rebuild when its layer set changes
        self._canvas = self._map_canvas()
        if self._canvas is not None:
            self._canvas.layersChanged.connect(self.refresh)
        self.apply_theme()
        self.refresh()

    def _map_canvas(self):
        iface = getattr(self.bus, "iface", None)
        return iface.mapCanvas() if iface is not None else None

    def teardown(self):
        if self._canvas is not None:
            try:
                self._canvas.layersChanged.disconnect(self.refresh)
            except (TypeError, RuntimeError):
                pass
            self._canvas = None

    # ---- interaction mode (Use vs Build) ----

    def set_interactive(self, on):
        super().set_interactive(on)
        # Build mode: inert so arranging tiles can't toggle map visibility.
        self.list.setEnabled(bool(on))

    # ---- appearance ----

    def _restyle(self):
        th = self.effective_theme()
        self.list.setStyleSheet(
            'QListWidget {{ background:transparent; border:none;'
            ' color:{c}; font-family:{f}; font-size:{px}px; }}'
            'QListWidget::item {{ padding:2px 0; }}'.format(
                c=th.text, f=th.font_stack(), px=th.font_size))

    # ---- mirror the map's layers + symbology ----

    def _layers(self):
        """Vector layers shown on the map canvas, in draw order."""
        canvas = self._canvas or self._map_canvas()
        if canvas is not None:
            return [lyr for lyr in canvas.layers()
                    if isinstance(lyr, QgsVectorLayer)]
        # fallback when no iface canvas (e.g. tests): every project vector
        # layer
        return [lyr for lyr in QgsProject.instance().mapLayers().values()
                if isinstance(lyr, QgsVectorLayer)]

    def refresh(self):
        self._suppress = True
        self.list.clear()
        layers = self._layers()
        if not layers:
            placeholder = QListWidgetItem("No layers on the map")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(placeholder)
            self._suppress = False
            self._restyle()
            return
        for layer in layers:
            renderer = layer.renderer()
            if renderer is None:
                continue
            self._add_layer_header(layer.name())
            checkable = False
            try:
                checkable = renderer.legendSymbolItemsCheckable()
            except Exception:
                checkable = False
            try:
                items = renderer.legendSymbolItems()
            except Exception:
                items = []
            for leg in items:
                self._add_symbol_row(layer, renderer, leg, checkable)
        self._suppress = False
        self._restyle()

    def _add_layer_header(self, name):
        item = QListWidgetItem(name)
        # a non-interactive group label
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.list.addItem(item)

    def _add_symbol_row(self, layer, renderer, leg, checkable):
        item = QListWidgetItem("    " + (leg.label() or ""))
        symbol = leg.symbol()
        if symbol is not None:                    # legend symbols can be null
            with contextlib.suppress(Exception):  # preview render may fail
                pix = QgsSymbolLayerUtils.symbolPreviewPixmap(symbol, _SWATCH)
                item.setIcon(QIcon(pix))
        key = leg.ruleKey()
        if checkable and key:
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable
                          | Qt.ItemFlag.ItemIsEnabled)
            visible = True
            try:
                visible = renderer.legendSymbolItemChecked(key)
            except Exception:
                visible = True
            item.setCheckState(Qt.CheckState.Checked if visible
                               else Qt.CheckState.Unchecked)
            item.setData(_ROLE, (layer.id(), key))
        else:
            # single-symbol / non-checkable class: show it, but it can't toggle
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setData(_ROLE, None)
        self.list.addItem(item)

    # ---- interactivity: toggle a class on the map ----

    def _on_item_changed(self, item):
        if self._suppress or not self._interactive:
            return
        data = item.data(_ROLE)
        if not data:
            return
        layer_id, key = data
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            return
        renderer = layer.renderer()
        if renderer is None:
            return
        try:
            if not renderer.legendSymbolItemsCheckable():
                return
            checked = item.checkState() == Qt.CheckState.Checked
            renderer.checkLegendSymbolItem(key, checked)
        except Exception:
            return
        # repaint every canvas showing this layer — the dashboard map mirror and
        # the main QGIS canvas both reflect the class being hidden/shown.
        layer.triggerRepaint()
