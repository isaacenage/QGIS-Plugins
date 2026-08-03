# -*- coding: utf-8 -*-
"""The AutoQAD map tool — the canvas end of the input pipeline.

One tool serves every command. It does not know what LINE or FILLET are; it
knows only what the active prompt wants, which it reads from the runner. Move
events go to the throttled :class:`~.pointer.PointerTracker`, clicks resolve to
either a point or an entity pick, and everything is handed to the runner, which
decides what it means.

Mouse buttons follow AutoCAD: left picks, right ends the current input the way
Enter does, and Escape cancels. ``pos()``/``globalPos()`` are used rather than
Qt6's ``position()`` because the former are bound on both PyQt5 and PyQt6 —
deprecated, but the only spelling that works across the supported QGIS range.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.core import QgsPointXY, QgsRectangle
from qgis.gui import QgsMapTool


class AutoQadMapTool(QgsMapTool):
    """Routes canvas input into the command runner."""

    #: Emitted with the resolved cursor point after every processed move.
    pointMoved = pyqtSignal(object)
    #: Emitted when the tool is deactivated, so the UI can untick its button.
    deactivated = pyqtSignal()

    def __init__(self, canvas, runner, pointer, preview, variables, document,
                 crosshair=None, dyninput=None):
        super().__init__(canvas)
        self.canvas = canvas
        self.runner = runner
        self.pointer = pointer
        self.preview = preview
        self.variables = variables
        self.document = document
        self.crosshair = crosshair
        self.dyninput = dyninput
        self._selection = []
        self._window_anchor = None

        self.pointer.pointChanged.connect(self._on_point)
        self.pointer.snapChanged.connect(self._on_snap)
        self.pointer.trackingChanged.connect(self._on_tracking)

    # ---- activation ----

    def activate(self):
        super().activate()
        # The crosshair replaces the OS pointer entirely; only fall back to a
        # system cross when it is switched off.
        if self.crosshair is not None and self.variables.get("CROSSHAIR"):
            # Set it on the tool as well as the canvas: QgsMapTool re-applies
            # its own cursor on activation, and would otherwise overwrite the
            # blank one the crosshair installs.
            self.setCursor(Qt.CursorShape.BlankCursor)
            self.crosshair.set_visible(True)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        if self.dyninput is not None:
            self.dyninput.set_visible(True)
        self.pointer.set_enabled(True)

    def deactivate(self):
        self.pointer.set_enabled(False)
        self.preview.clear()
        if self.crosshair is not None:
            self.crosshair.set_visible(False)
        if self.dyninput is not None:
            self.dyninput.set_visible(False)
        super().deactivate()
        self.deactivated.emit()

    def isEditTool(self):
        return True

    # ---- pointer feedback ----

    def _on_point(self, point):
        self._refresh_overlays()
        self.pointMoved.emit(point)

    def _on_snap(self, _snap):
        self._refresh_overlays()

    def _on_tracking(self, _angle):
        self.preview.set_tracking_base(self.pointer.base_point)
        self._refresh_overlays()

    def _refresh_overlays(self):
        """Redraw every cursor-following overlay. One call per processed frame.

        Crosshair, rubber band, snap marker and dynamic input all move
        together, driven by the single resolved point — so they can never
        disagree about where the cursor is.
        """
        point = self.pointer.current_point
        if point is None:
            return

        self.preview.update(point, self.pointer.tracking_angle,
                            self.pointer.current_snap)

        if self.crosshair is not None:
            self.crosshair.move_to(point)

        if self.dyninput is not None:
            prompt = self.runner.prompt
            base = self.runner.base_point
            self.dyninput.update(
                self.pointer.current_screen, point,
                base_point=base,
                locked_angle=self.pointer.tracking_angle,
                prompt_text=self._dyn_prompt_text(prompt),
                kind=self._dyn_kind(prompt, base))

    @staticmethod
    def _dyn_kind(prompt, base_point):
        """Which readout the current prompt wants."""
        if prompt is None:
            return "first"
        if prompt.kind in ("distance", "angle"):
            return prompt.kind
        return "point" if base_point is not None else "first"

    @staticmethod
    def _dyn_prompt_text(prompt):
        """The prompt line, with its keyword options, shown under the cursor."""
        if prompt is None:
            return ""
        text = prompt.message
        if prompt.options:
            text += " [{0}]".format("/".join(prompt.options))
        return text

    # ---- events ----

    def canvasMoveEvent(self, event):
        """Record the move and return. All real work is deferred to the timer."""
        position = event.pos()
        map_point = self.toMapCoordinates(position)
        self.pointer.on_move(position, (map_point.x(), map_point.y()))

    def canvasPressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Right-click ends the current input, as Enter does in AutoCAD.
            self.runner.supply_text("")
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        position = event.pos()
        map_point = self.toMapCoordinates(position)
        raw = (map_point.x(), map_point.y())

        if self.runner.wants_selection:
            self._pick_entity(position, raw)
            return

        if self.runner.wants_point:
            # Resolve synchronously so the committed point comes from this
            # click rather than whatever the last timer tick produced.
            resolved = self.pointer.resolve(position, raw) or raw
            self.runner.supply_point(resolved)
            self._sync_base_point()
            return

        # No command running: a click starts a selection for the next command.
        self._pick_entity(position, raw, accumulate=True)

    def canvasReleaseEvent(self, event):
        pass

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.runner.escape()
            self.preview.clear()
            self.pointer.reset()
            self.clear_selection()
            event.accept()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.runner.supply_text("")
            event.accept()
        elif key == Qt.Key.Key_F8:
            self.variables.toggle("ORTHOMODE")
            event.accept()
        elif key == Qt.Key.Key_F10:
            self.variables.toggle("POLARMODE")
            event.accept()
        elif key == Qt.Key.Key_F3:
            self.variables.toggle("OSNAPON")
            event.accept()
        elif key == Qt.Key.Key_F9:
            self.variables.toggle("SNAPMODE")
            event.accept()
        else:
            super().keyPressEvent(event)

    # ---- prompt synchronisation ----

    def _sync_base_point(self):
        """Keep the pointer's constraint anchor aligned with the prompt."""
        self.pointer.set_base_point(self.runner.base_point)
        self.preview.set_tracking_base(self.runner.base_point)

    def sync_to_prompt(self):
        """Called by the controller whenever the active prompt changes."""
        self._sync_base_point()
        prompt = self.runner.prompt
        self.preview.set_descriptor(prompt.rubber if prompt else None)

    # ---- entity picking ----

    def _pick_rect(self, map_point):
        pixels = max(1, int(self.variables.get("PICKBOX")))
        tolerance = self.canvas.mapUnitsPerPixel() * pixels
        return QgsRectangle(map_point[0] - tolerance, map_point[1] - tolerance,
                            map_point[0] + tolerance, map_point[1] + tolerance)

    def _pick_entity(self, _position, map_point, accumulate=False):
        """Pick the topmost entity under the cursor and feed it to the runner.

        Uses the canvas's snapping locator — the same warm C++ index the snap
        engine uses — rather than iterating features.
        """
        hit = self.pick_at(map_point)
        if hit is None:
            if not accumulate:
                # An empty pick at a selection prompt means "done selecting".
                self.runner.supply_selection(list(self._selection))
                self.clear_selection()
            return

        if hit in self._selection:
            self._selection.remove(hit)
        else:
            self._selection.append(hit)
        self._refresh_highlight()

        prompt = self.runner.prompt
        if prompt is not None and getattr(prompt, "single", False):
            self.runner.supply_selection([hit])
            self.clear_selection()

    def pick_at(self, map_point):
        """Return ``(table_name, feature_id)`` under *map_point*, or ``None``."""
        if self.document is None or not self.document.is_open:
            return None

        point = QgsPointXY(map_point[0], map_point[1])
        pixels = max(1, int(self.variables.get("PICKBOX")))
        tolerance = self.canvas.mapUnitsPerPixel() * pixels
        utils = self.canvas.snappingUtils()
        if utils is None:
            return None

        best = None
        for layer in self.document.all_tables():
            try:
                locator = utils.locatorForLayer(layer)
            except (AttributeError, RuntimeError):
                continue
            if locator is None:
                continue

            match = locator.nearestEdge(point, tolerance)
            if not match.isValid():
                match = locator.nearestVertex(point, tolerance)
            if not match.isValid():
                continue
            if not self._is_editable(layer, match.featureId()):
                continue
            if best is None or match.distance() < best[0]:
                name = layer.customProperty("autoqad/table") or layer.name()
                best = (match.distance(), (name, match.featureId()))

        return best[1] if best else None

    def _is_editable(self, layer, feature_id):
        try:
            feature = layer.getFeature(feature_id)
        except (RuntimeError, KeyError):
            return True
        if feature is None or not feature.isValid():
            return True
        cad = self.document.layers.get(feature.attribute("aq_layer"))
        return cad is None or cad.is_editable

    # ---- selection ----

    @property
    def selection(self):
        return list(self._selection)

    def set_selection(self, selection):
        self._selection = list(selection)
        self._refresh_highlight()

    def clear_selection(self):
        self._selection = []
        self.preview.clear_highlight()

    def _refresh_highlight(self):
        geometries = []
        for table_name, feature_id in self._selection:
            layer = self.document.table(table_name)
            if layer is None:
                continue
            try:
                feature = layer.getFeature(feature_id)
            except (RuntimeError, KeyError):
                continue
            if feature is not None and feature.isValid():
                geometry = feature.geometry()
                if geometry is not None and not geometry.isEmpty():
                    geometries.append(geometry)
        self.preview.highlight(geometries)
