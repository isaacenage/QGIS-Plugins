# -*- coding: utf-8 -*-
"""Signal bus / shared dashboard context.

ArcGIS Dashboards models cross-filtering as *source -> action -> target*.
Originally this was a single global filter every element honored. The bus now
carries an explicit, user-editable wiring: each source pushes a filter tagged
with its own element id, and a target only sees filters from sources it is
connected to (see :class:`DashboardWindow`'s Connections editor).

Besides cross-filtering, the bus is the one object every element shares, so it
also carries the live ``iface`` (for the map mirror), the active ``Theme``, and
fans out project/layer/theme change notifications.

A "filter" is always a QgsExpression-compatible string (or ``None`` to clear).
"""

from qgis.PyQt.QtCore import QObject, pyqtSignal

from .theme import Theme


class DashboardBus(QObject):
    # Any source filter changed. No payload: targets recompute via
    # ``combined_filter_for(self.id)``.
    filtersChanged = pyqtSignal()

    # The user pressed "Clear filter": sources should reset their own
    # selection state (highlighted bar, combo box, ...).
    filtersCleared = pyqtSignal()

    # The wiring between elements changed (a target may gain/lose a source).
    connectionsChanged = pyqtSignal()

    # The set of project layers changed; config combos + map refresh.
    layersChanged = pyqtSignal()

    # The global/active theme changed; every tile re-applies appearance.
    themeChanged = pyqtSignal()

    # Feature ids to flash/zoom on the map element.
    featureAction = pyqtSignal(object)

    def __init__(self, iface=None, theme=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._theme = theme or Theme.default()
        self._active_page = "default"
        self._page_filters = {"default": {}}      # page_id -> {source_id: expr}
        self._page_connections = {"default": {}}  # page_id -> {source_id: set}

    # ---- page-local state (active page) ----

    @property
    def _source_filters(self):
        return self._page_filters.setdefault(self._active_page, {})

    @property
    def _connections(self):
        return self._page_connections.setdefault(self._active_page, {})

    def set_active_page(self, page_id):
        self._active_page = page_id or "default"
        self._page_filters.setdefault(self._active_page, {})
        self._page_connections.setdefault(self._active_page, {})
        self.connectionsChanged.emit()
        self.filtersChanged.emit()

    def forget_page(self, page_id):
        self._page_filters.pop(page_id, None)
        self._page_connections.pop(page_id, None)

    # ---- theme ----

    @property
    def theme(self):
        return self._theme

    def set_theme(self, theme):
        self._theme = theme or Theme.default()
        self.themeChanged.emit()

    # ---- cross-filtering ----

    def set_filter(self, source_id, expression):
        """Record (or clear) the filter contributed by one source element."""
        expression = expression or None
        if expression is None:
            self._source_filters.pop(source_id, None)
        else:
            self._source_filters[source_id] = expression
        self.filtersChanged.emit()

    def combined_filter_for(self, target_id):
        """AND of every connected source's filter, or None if unfiltered."""
        parts = []
        for source_id, expr in self._source_filters.items():
            if expr and target_id in self._connections.get(source_id, set()):
                parts.append("({})".format(expr))
        return " AND ".join(parts) if parts else None

    def active_filter_count(self):
        return len(self._source_filters)

    def clear_all_filters(self):
        had = bool(self._source_filters)
        self._source_filters.clear()
        self.filtersCleared.emit()
        if had:
            self.filtersChanged.emit()

    def forget_element(self, element_id):
        """Drop a removed element from filters and the wiring graph."""
        self._source_filters.pop(element_id, None)
        self._connections.pop(element_id, None)
        for targets in self._connections.values():
            targets.discard(element_id)
        self.filtersChanged.emit()

    # ---- connection graph ----

    def targets_of(self, source_id):
        return set(self._connections.get(source_id, set()))

    def sources_of(self, target_id):
        """Reverse lookup: every source whose filter reaches *target_id*."""
        return {src for src, tgts in self._connections.items()
                if target_id in tgts}

    def is_connected(self, source_id, target_id):
        return target_id in self._connections.get(source_id, set())

    def set_connected(self, source_id, target_id, connected):
        """Add or remove a single source → target edge, leaving others intact.

        A no-op (the edge already matches *connected*) emits no signals.
        """
        if source_id == target_id or self.is_connected(source_id, target_id) == bool(connected):
            return
        targets = self.targets_of(source_id)
        if connected:
            targets.add(target_id)
        else:
            targets.discard(target_id)
        self.set_targets(source_id, targets)

    def set_targets(self, source_id, target_ids):
        targets = {t for t in target_ids if t and t != source_id}
        if targets:
            self._connections[source_id] = targets
        else:
            self._connections.pop(source_id, None)
        self.connectionsChanged.emit()
        # Rewiring a source that contributes no active filter cannot change any
        # target's combined_filter_for(...), so skip the (expensive) filter
        # fan-out — every accepting tile re-queries its layer on filtersChanged.
        # This is what made ticking Connections checkboxes heavy on a dashboard
        # with many tiles: each tick triggered N full layer scans for no change.
        if self._source_filters.get(source_id):
            self.filtersChanged.emit()

    def connections_to_dict(self, page_id=None):
        conns = (self._page_connections.get(page_id, {})
                 if page_id is not None else self._connections)
        return {src: sorted(tgts) for src, tgts in conns.items() if tgts}

    def load_connections(self, data, page_id=None):
        target = page_id if page_id is not None else self._active_page
        conns = {}
        if isinstance(data, dict):
            for src, tgts in data.items():
                if tgts:
                    conns[src] = set(tgts)
        self._page_connections[target] = conns
        self.connectionsChanged.emit()
