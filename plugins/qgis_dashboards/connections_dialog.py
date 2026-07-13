# -*- coding: utf-8 -*-
"""Per-element connections editor — wire one tile's cross-filter links.

ArcGIS source -> action -> target, made explicit and user-editable, but scoped
to a *single* element (opened from that tile's right-click menu). It shows the
element's connections from its own perspective:

* if the element **is a filter source** (chart / pivot / selector), an outgoing
  section — "This filters →" — lists every candidate *target* (anything that
  accepts a filter); ticking one means "when this tile filters, that tile
  re-queries".
* if the element **accepts a filter** (indicator / chart / pivot / list), an
  incoming section — "← Filtered by" — lists every candidate *source*; ticking
  one wires that source onto this tile.

Dual-role tiles (chart, pivot) show both sections. A tile that neither sources
nor accepts filters (e.g. the map) shows an explanatory note.

The editing controls live in :class:`ConnectionsForm` (a plain ``QWidget``) so
it can be embedded in the right-edge inspector panel. With ``live=True`` each
checkbox writes its edge to the bus immediately (so cross-filtering previews as
you tick); otherwise writes are deferred to :meth:`ConnectionsForm.apply`.

All writes go through the bus edge-by-edge (:meth:`DashboardBus.set_connected`),
so editing one tile never disturbs links that don't involve it.
:class:`ElementConnectionsDialog` is a thin modal wrapper kept for standalone
use and tests.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QCheckBox,
    QLabel,
    QScrollArea,
    QWidget,
    QDialogButtonBox,
)


class ConnectionsForm(QWidget):
    """Embeddable editor for one *element*'s cross-filter links."""

    changed = pyqtSignal()   # an edge was toggled (host may react)

    def __init__(self, bus, element, elements, live=False, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.element = element
        self._live = live

        # (peer_id, direction) -> QCheckBox, where direction is "out" (this
        # element filters the peer) or "in" (the peer filters this element).
        self._checks = {}
        # action rows (edges whose target is a map): (src_id, tgt_id,
        # {action:cb})
        self._action_rows = []

        others = [e for e in elements if e.id != element.id]
        out_targets = ([e for e in others if e.accepts_filter]
                       if element.is_filter_source else [])
        in_sources = ([e for e in others if e.is_filter_source]
                      if element.accepts_filter else [])

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        intro = QLabel(
            "Choose how <b>{}</b> connects to the other tiles on this page. "
            "Selecting a value in a source tile cross-filters every tile it is "
            "wired to.".format(
                element.display_name()))
        intro.setWordWrap(True)
        intro.setProperty("connHint", True)
        root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        if not out_targets and not in_sources:
            empty = QLabel(
                "This tile doesn't take part in cross-filtering.\n"
                "Add a chart, pivot or selector to drive other tiles.")
            empty.setWordWrap(True)
            empty.setProperty("connHint", True)
            col.addWidget(empty)

        if element.is_filter_source:
            col.addWidget(self._section(
                "This drives →", out_targets, "out",
                lambda peer: bus.is_connected(element.id, peer.id),
                "No eligible targets on this page."))

        if element.accepts_filter:
            col.addWidget(self._section(
                "← Filtered by", in_sources, "in",
                lambda peer: bus.is_connected(peer.id, element.id),
                "No eligible sources on this page."))

        col.addStretch(1)

    # action columns shown when an edge's target is a map
    # (source→action→target)
    ACTION_LABELS = (("filter", "Filter"), ("zoom", "Zoom"), ("pan", "Pan"),
                     ("flash", "Flash"), ("show_popup", "Show pop-up"))

    def _section(self, title, peers, direction, is_on, empty_text):
        box = QGroupBox(title)
        lay = QVBoxLayout(box)
        lay.setSpacing(8)
        if not peers:
            hint = QLabel(empty_text)
            hint.setWordWrap(True)
            hint.setProperty("connHint", True)
            lay.addWidget(hint)
        for peer in peers:
            if self._target_is_map(peer, direction):
                lay.addWidget(self._action_row(peer, direction))
            else:
                cb = QCheckBox(peer.display_name())
                cb.setCursor(Qt.CursorShape.PointingHandCursor)
                cb.setChecked(is_on(peer))
                self._checks[(peer.id, direction)] = cb
                cb.toggled.connect(
                    lambda on, pid=peer.id, d=direction:
                    self._on_toggle(pid, d, on))
                lay.addWidget(cb)
        return box

    def _edge_ids(self, peer, direction):
        """The (source_id, target_id) of the edge this row represents."""
        if direction == "out":          # this element → peer
            return self.element.id, peer.id
        return peer.id, self.element.id  # peer → this element

    def _target_is_map(self, peer, direction):
        target = peer if direction == "out" else self.element
        return getattr(target, "type_name", None) == "map"

    def _action_row(self, peer, direction):
        """A peer name + per-action checkboxes (Filter/Zoom/Pan/Flash/Pop-up).

        Used when the edge's target is a map, so the user picks which ArcGIS
        actions the source drives on it. The edge exists iff any action is
        ticked; unticking all removes it.
        """
        src, tgt = self._edge_ids(peer, direction)
        current = (self.bus.edge_actions(src, tgt)
                   if self.bus.is_connected(src, tgt) else set())
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        name = QLabel(peer.display_name())
        col.addWidget(name)
        checks = {}
        row = QHBoxLayout()
        row.setSpacing(10)
        for key, label in self.ACTION_LABELS:
            cb = QCheckBox(label)
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setChecked(key in current)
            checks[key] = cb
            cb.toggled.connect(
                lambda _on, s=src, t=tgt, c=checks:
                self._on_action_toggle(s, t, c))
            row.addWidget(cb)
        row.addStretch(1)
        col.addLayout(row)
        self._action_rows.append((src, tgt, checks))
        return box

    def _on_toggle(self, peer_id, direction, on):
        if self._live:
            self._write_edge(peer_id, direction, on)
        self.changed.emit()

    def _on_action_toggle(self, src, tgt, checks):
        if self._live:
            self.bus.set_edge_actions(src, tgt, self._action_set(checks))
        self.changed.emit()

    @staticmethod
    def _action_set(checks):
        return {k for k, cb in checks.items() if cb.isChecked()}

    def _write_edge(self, peer_id, direction, on):
        eid = self.element.id
        if direction == "out":      # this element → peer
            self.bus.set_connected(eid, peer_id, on)
        else:                       # peer → this element
            self.bus.set_connected(peer_id, eid, on)

    def apply(self):
        """Write the ticked wiring back onto the bus, edge by edge."""
        for (peer_id, direction), cb in self._checks.items():
            self._write_edge(peer_id, direction, cb.isChecked())
        for src, tgt, checks in self._action_rows:
            self.bus.set_edge_actions(src, tgt, self._action_set(checks))


class ElementConnectionsDialog(QDialog):
    """Modal wrapper around :class:`ConnectionsForm` (standalone / tests)."""

    def __init__(self, bus, element, elements, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.element = element
        self.setWindowTitle('Connections — {}'.format(element.display_name()))
        self.resize(400, 480)

        # The dialog is a top-level window, so the parent window's themed
        # stylesheet does not always reach it — apply the dashboard theme
        # directly so its surfaces/text never fall through to the (possibly
        # dark) QGIS application palette.
        if bus is not None and getattr(bus, "theme", None) is not None:
            self.setStyleSheet(bus.theme.window_qss())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(12)
        self._form = ConnectionsForm(bus, element, elements, live=False,
                                     parent=self)
        # expose the checkbox map so existing call sites/tests still reach it
        self._checks = self._form._checks
        root.addWidget(self._form, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def apply(self):
        self._form.apply()
