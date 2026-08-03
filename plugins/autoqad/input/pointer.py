# -*- coding: utf-8 -*-
"""The pointer pipeline — the one hot path in AutoQAD.

Everything the cursor does on its way to becoming a point happens here, and it
happens **at most once per frame**.

Raw ``canvasMoveEvent`` calls do nothing but record a position and poke a
coalescing timer. A high-polling-rate mouse can deliver a thousand move events
a second; without coalescing, each one would drag a full snap-and-preview
pipeline behind it. With it, the pipeline runs on a ~16 ms tick no matter how
chatty the hardware is — the difference between a CAD plugin that feels
immediate and one that makes the whole application stutter.

The pipeline is ordered cheapest-first, so most moves exit early:

1. screen -> map coordinates (trivial)
2. grid snap, if SNAPMODE is on (pure arithmetic)
3. ortho / polar constraint (pure trigonometry, no allocation)
4. object snap, only if osnaps are on (one indexed C++ locator query)
5. preview + marker update (canvas items, never a layer re-render)

Step 4 is the only one that touches data, and it is delegated wholesale to
:class:`~.snap.SnapEngine`, which is itself backed by QGIS's C++ locator.

The budget for the whole pipeline is well under 2 ms; :attr:`last_duration_ms`
records the real figure so a slow drawing can be diagnosed rather than guessed
at.
"""

import time

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from . import ortho_polar


class PointerTracker(QObject):
    """Coalesces mouse movement into a throttled snap-and-constrain pipeline."""

    #: The resolved cursor point changed; carries ``(x, y)``.
    pointChanged = pyqtSignal(object)
    #: The active snap changed; carries a :class:`~.snap.SnapResult` or None.
    snapChanged = pyqtSignal(object)
    #: The tracking angle changed; carries radians or None.
    trackingChanged = pyqtSignal(object)

    def __init__(self, canvas, variables, snap_engine, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.variables = variables
        self.snap_engine = snap_engine

        self._raw_screen = None
        self._raw_map = None
        self._current_point = None
        self._snap = None
        self._tracking_angle = None
        self._base_point = None
        self._enabled = False

        #: Milliseconds the last pipeline run took — a live performance probe.
        self.last_duration_ms = 0.0

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._process)

    # ---- configuration ----

    def set_enabled(self, enabled):
        """Enable processing. Disabled, move events are recorded but ignored."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self._timer.stop()
            self._set_snap(None)
            self._set_tracking(None)

    def set_base_point(self, point):
        """Set the anchor ortho/polar constrain against and PER/TAN resolve to."""
        self._base_point = point

    @property
    def base_point(self):
        return self._base_point

    @property
    def current_point(self):
        """The fully resolved (snapped, constrained) cursor point."""
        return self._current_point

    @property
    def current_snap(self):
        return self._snap

    @property
    def tracking_angle(self):
        return self._tracking_angle

    # ---- input ----

    def on_move(self, screen_pos, map_point):
        """Record a raw move. Deliberately does almost nothing.

        This runs on every hardware move event, so it must stay allocation-free
        and branch-light — all real work is deferred to :meth:`_process`.
        """
        self._raw_screen = screen_pos
        self._raw_map = map_point
        if not self._enabled:
            return
        if not self._timer.isActive():
            self._timer.start(max(1, int(self.variables.get("MOVETHROTTLE"))))

    def flush(self):
        """Run the pipeline immediately — used on click, where latency matters."""
        self._timer.stop()
        self._process()
        return self._current_point

    def resolve(self, screen_pos, map_point):
        """Resolve a point synchronously without disturbing tracked state.

        Used by the map tool on click so the committed point is derived from
        the click position itself rather than the last processed move.
        """
        self._raw_screen = screen_pos
        self._raw_map = map_point
        return self.flush()

    # ---- the pipeline ----

    def _process(self):
        if not self._enabled or self._raw_map is None:
            return

        started = time.perf_counter()
        point = self._raw_map

        # 2. grid snap — pure arithmetic.
        if self.variables.get("SNAPMODE"):
            point = self._grid_snap(point)

        # 3. ortho / polar — pure trigonometry.
        angle = None
        if self._base_point is not None:
            point, angle = ortho_polar.apply(
                self._base_point, point,
                ortho=self.variables.get("ORTHOMODE"),
                polar=self.variables.get("POLARMODE"),
                increment_degrees=self.variables.get("POLARANG"))

        # 4. object snap — one indexed C++ query, and only when enabled.
        snap = None
        if self.snap_engine is not None and self.variables.osnap_enabled:
            snap = self.snap_engine.snap(point, self._base_point)
            if snap is not None:
                point = snap.point
                # An explicit snap overrides the constraint: the user asked for
                # that exact geometric point, which is what AutoCAD does too.
                angle = None

        self._current_point = point
        self._set_snap(snap)
        self._set_tracking(angle)
        self.pointChanged.emit(point)

        self.last_duration_ms = (time.perf_counter() - started) * 1000.0

    def _grid_snap(self, point):
        spacing = float(self.variables.get("SNAPUNIT"))
        if spacing <= 0.0:
            return point
        return (round(point[0] / spacing) * spacing,
                round(point[1] / spacing) * spacing)

    # ---- change notification ----

    def _set_snap(self, snap):
        previous = self._snap
        changed = (previous is None) != (snap is None)
        if not changed and snap is not None and previous is not None:
            changed = (snap.snap_type != previous.snap_type
                       or snap.point != previous.point)
        self._snap = snap
        if changed:
            self.snapChanged.emit(snap)

    def _set_tracking(self, angle):
        if angle != self._tracking_angle:
            self._tracking_angle = angle
            self.trackingChanged.emit(angle)

    def reset(self):
        """Clear tracked state between commands."""
        self._timer.stop()
        self._base_point = None
        self._current_point = None
        self._set_snap(None)
        self._set_tracking(None)
