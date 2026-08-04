# -*- coding: utf-8 -*-
"""The AutoQAD controller — assembles the whole system and wires it together.

Everything that has to know about everything else lives here, and nowhere else:
the document, the variables, the command registry and runner, the pointer
pipeline, the snap engine, the previews, the map tool and the docks.

The wiring is deliberately one-directional. The runner emits what changed; the
UI listens. The UI emits what the user did; the runner consumes it. Neither
reaches into the other, which is what keeps a command runnable with no UI
present at all — the property the scripting facade depends on.
"""

import os

from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from qgis.core import QgsProject

from .commands import build_registry
from .core.document import DrawingDocument
from .core.variables import VariableStore
from .engine.command import CommandContext
from .engine.runner import CommandRunner
from .input.cmdinput import DynamicCommandInput
from .input.crosshair import CrosshairCursor
from .input.dyninput import DynamicInput
from .input.maptool import AutoQadMapTool
from .input.pointer import PointerTracker
from .input.rubber import PreviewManager
from .input.snap import SnapEngine
from .ui.command_bar import CommandBarDock
from .ui.tool_palette import ToolPaletteDock


class AutoQadController(QObject):
    """Owns one AutoQAD session inside a QGIS instance."""

    #: Emitted when the session is switched on or off.
    activeChanged = pyqtSignal(bool)

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.canvas = iface.mapCanvas()

        self.variables = VariableStore(self)
        self.document = DrawingDocument(self.variables)
        self.registry = build_registry()

        self.context = CommandContext(
            document=self.document,
            variables=self.variables,
            canvas=self.canvas,
            iface=iface,
            message=self._write)
        self.context.registry = self.registry
        self.context.open_dialog = self.open_dialog

        self.runner = CommandRunner(self.context, self.registry, self)

        self.snap_engine = SnapEngine(self.canvas, self.variables,
                                      self.document)
        self.pointer = PointerTracker(self.canvas, self.variables,
                                      self.snap_engine, self)
        self.context.pointer = self.pointer
        self.preview = PreviewManager(self.canvas, self.variables)
        self.crosshair = CrosshairCursor(self.canvas, self.variables)
        self.dyninput = DynamicInput(self.canvas, self.variables)
        self.cmd_input = DynamicCommandInput(self.canvas, self.variables,
                                             self.registry, self)

        self.map_tool = AutoQadMapTool(
            self.canvas, self.runner, self.pointer, self.preview,
            self.variables, self.document,
            crosshair=self.crosshair, dyninput=self.dyninput)

        self.command_bar = CommandBarDock(self.variables, self.registry,
                                          iface.mainWindow())
        self.palette = ToolPaletteDock(iface.mainWindow())

        self._dialogs = {}
        self._active = False
        #: True while QGIS is emptying the whole project, so the layer-removal
        #: handler knows the removal is not a decision the user made.
        self._project_clearing = False
        #: The user's own canvas colour, restored when CAD mode exits.
        self._saved_canvas_color = None
        #: Hooks into QGIS's own Layout designer; created on first activation.
        self._designer_hooks = None
        #: The map tool displaced while a plot window is being picked.
        self._pick_previous_tool = None
        self._pick_tool = None
        self._wire()

    # ---- CAD mode ----
    #
    # Enabling AutoQAD puts QGIS into model space: the canvas goes black and
    # ACI 7 — the default colour of layer "0" and therefore of most entities —
    # resolves to white instead of black. That is not decoration; a CAD drawing
    # is authored against a dark background and its default colour is defined
    # relative to it, so a white canvas would render the whole drawing in the
    # one colour that disappears against it.
    #
    # The user's own canvas colour is saved and restored on exit, so turning
    # the plugin off leaves their project exactly as they set it up.

    def _enter_cad_mode(self):
        from qgis.PyQt.QtGui import QColor

        if self._saved_canvas_color is None:
            self._saved_canvas_color = self.canvas.canvasColor()

        self.canvas.setCanvasColor(QColor(self.variables.get("CANVASCOLOR")))
        self.canvas.refresh()
        # Re-resolve every entity's colour against the new background.
        if self.document.is_open:
            self.document.restyle_all()
            self.document.refresh()

    def _exit_cad_mode(self):
        if self._saved_canvas_color is None:
            return
        self.canvas.setCanvasColor(self._saved_canvas_color)
        self._saved_canvas_color = None
        self.canvas.refresh()

    # ---- wiring ----

    def _wire(self):
        self.command_bar.submitted.connect(self._on_submitted)
        self.command_bar.cancelled.connect(self._on_cancelled)
        self.palette.commandRequested.connect(self.run_command)

        self.runner.promptChanged.connect(self._on_prompt_changed)
        self.runner.messaged.connect(self._write)
        self.runner.rubberChanged.connect(self.preview.set_descriptor)
        self.runner.commandStarted.connect(self._on_command_started)
        self.runner.commandEnded.connect(self._on_command_ended)
        self.runner.selectionConsumed.connect(self.map_tool.clear_selection)

        # Typing on the canvas belongs to the command line, as it does in
        # AutoCAD — without this every prompt that wants text looks frozen.
        # It goes to the box at the cursor when that is on, and straight to
        # the dock when it is not.
        self.map_tool.keyTyped.connect(self._on_key_typed)
        self.map_tool.canvasClicked.connect(self.cmd_input.close)

        self.cmd_input.submitted.connect(self._on_cmd_input_submitted)
        self.cmd_input.cancelled.connect(self._on_cancelled)
        self.cmd_input.visibilityChanged.connect(self._on_cmd_input_shown)

        # "Select objects … <Enter>" has to reach the picks the map tool has
        # been collecting; the runner has no other way to see them.
        self.runner.selection_provider = lambda: self.map_tool.selection

        self.pointer.pointChanged.connect(self._on_point_changed)
        self.variables.changed.connect(self._on_variable_changed)

        # Fires *before* the C++ layers are destroyed — the one moment we can
        # still identify them and drop our references safely.
        QgsProject.instance().layersWillBeRemoved.connect(
            self._on_layers_will_be_removed)

        # Closing or replacing a project also removes every layer, and that is
        # emphatically not the user saying "delete my drawing". Bracket it so
        # the removal handler can tell the two apart.
        for signal, slot in self._clear_hooks():
            try:
                signal.connect(slot)
            except (AttributeError, TypeError):   # pragma: no cover
                pass

    def _clear_hooks(self):
        """``(signal, slot)`` pairs bracketing a whole-project clear."""
        project = QgsProject.instance()
        hooks = []
        for name, slot in (("aboutToBeCleared", self._on_project_clearing),
                           ("cleared", self._on_project_cleared)):
            signal = getattr(project, name, None)
            if signal is not None:
                hooks.append((signal, slot))
        return hooks

    def _on_project_clearing(self):
        """The project is being emptied — flush, and stop asking questions."""
        self._project_clearing = True
        try:
            self.document.commit()
        except (RuntimeError, AttributeError):
            pass

    def _on_project_cleared(self):
        self._project_clearing = False

    def _on_layers_will_be_removed(self, layer_ids):
        """Release references to drawing tables the user is deleting."""
        was_open = bool(self.document._tables)
        storage = self.document.storage_path()
        self.document.on_layers_removed(layer_ids)

        if was_open and not self.document.is_open:
            self.runner.cancel()
            self.preview.clear()
            self.pointer.reset()
            if not self._project_clearing:
                self._confirm_discard(storage)

    def _confirm_discard(self, storage):
        """Ask whether removing the tables also means deleting the drawing.

        Reopening deliberately recovers a drawing whose layers were removed:
        the entities are still in the GeoPackage, and quietly writing empty
        tables over them would turn one mis-click in the layer tree into lost
        work. The cost of that safety net is that deleting the layers looks
        like it does nothing — everything reappears on the next toggle.

        So ask, once, at the only moment the answer is knowable. The question
        is posted rather than raised inline because we are inside
        ``layersWillBeRemoved`` and the layers are not gone yet.
        """
        if not storage or not os.path.exists(storage):
            # Nothing on disk to resurrect; the removal already stuck.
            self.document.discard(delete_storage=False)
            return

        QTimer.singleShot(0, lambda: self._ask_discard(storage))

    def _ask_discard(self, storage):
        answer = QMessageBox.question(
            self.iface.mainWindow(), "AutoQAD",
            "The AutoQAD drawing layers were removed from the project.\n\n"
            "Delete the drawing itself as well?\n\n"
            "Delete — erases {0} and starts empty.\n"
            "Keep — the drawing reopens the next time AutoQAD runs.".format(
                os.path.basename(storage)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)

        if answer != QMessageBox.StandardButton.Yes:
            self._write("Drawing kept. The next command reopens it from {0}."
                        .format(os.path.basename(storage)))
            return

        ok, message = self.document.discard(delete_storage=True)
        self._write(message)
        if not ok:
            QMessageBox.warning(self.iface.mainWindow(), "AutoQAD", message)

    # ---- lifecycle ----

    @property
    def is_active(self):
        return self._active

    def activate(self):
        """Show the docks, open the drawing and take over the canvas."""
        if self._active:
            return True

        if not self.document.ensure_open(self.canvas.mapSettings().destinationCrs()):
            QMessageBox.warning(
                self.iface.mainWindow(), "AutoQAD",
                "Could not create the drawing tables.\n\n"
                "Check that the project folder is writable, or save the "
                "project first.")
            return False

        main_window = self.iface.mainWindow()
        main_window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,
                                  self.palette)
        main_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                                  self.command_bar)
        self.palette.show()
        self.command_bar.show()

        self._enter_cad_mode()
        self._attach_designer_hooks()

        self.canvas.setMapTool(self.map_tool)
        self.cmd_input.set_enabled(True)
        self.command_bar.set_current_layer(self.variables.get("CLAYER"))
        self.command_bar.focus_input()

        self._active = True
        self.activeChanged.emit(True)
        self._write("AutoQAD ready. Type a command, or pick a tool.")
        return True

    def deactivate(self):
        """Hide the docks, flush the drawing and release the canvas."""
        if not self._active:
            return
        self.runner.cancel()
        self.document.commit()
        self.preview.clear()
        self.crosshair.set_visible(False)
        self.dyninput.set_visible(False)
        self.cmd_input.set_enabled(False)
        self.pointer.reset()

        if self.canvas.mapTool() is self.map_tool:
            self.canvas.unsetMapTool(self.map_tool)

        self.palette.hide()
        self.command_bar.hide()
        self._exit_cad_mode()
        self._detach_designer_hooks()

        self._active = False
        self.activeChanged.emit(False)

    def toggle(self, enabled):
        return self.activate() if enabled else self.deactivate()

    # ---- commands ----

    def run_command(self, name, selection=None):
        """Start a command by name. Returns True if it started."""
        if not self._active and not self.activate():
            return False
        if selection is None:
            selection = self.map_tool.selection
        started = self.runner.start(name, initial_selection=selection)
        if started:
            self.map_tool.clear_selection()
            self.map_tool.sync_to_prompt()
        return started

    def _on_key_typed(self, text):
        """Route a canvas keystroke to whichever command line is in play."""
        if self.cmd_input.type_text(text, self.pointer.current_screen):
            return
        self.command_bar.type_text(text)

    def _on_cmd_input_submitted(self, text):
        """A line entered in the cursor box. Same path as the dock's input.

        The dock still records it, so the history the Up arrow walks is one
        list however the command was typed.
        """
        if text.strip():
            self.command_bar.remember(text)
            self.command_bar.write(text)
        self._handle_input(text)
        # Focus belongs back on the canvas: the next keystroke should reopen
        # the box at the cursor, not land in the dock.
        self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_cmd_input_shown(self, visible):
        self.dyninput.set_reserved_height(
            self.cmd_input.reserved_height() if visible else 0)

    def _on_submitted(self, text):
        self._handle_input(text)
        self.command_bar.focus_input()

    def _handle_input(self, text):
        if not self.runner.is_running:
            stripped = text.strip()
            if stripped:
                self.map_tool.set_selection(self.map_tool.selection)
        self.runner.supply_text(text)
        self.map_tool.sync_to_prompt()

    def _on_cancelled(self):
        self.runner.escape()
        self.cmd_input.close()
        self.preview.clear()
        self.pointer.reset()
        self.map_tool.clear_selection()

    def _on_prompt_changed(self, text):
        self.command_bar.set_prompt(text)
        # The cursor box serves this prompt too: it decides from the prompt
        # what Space means and which keywords to suggest.
        self.cmd_input.set_prompt(self.runner.prompt)
        self.map_tool.sync_to_prompt()

    def _on_command_started(self, _name):
        self.pointer.set_enabled(True)

    def _on_command_ended(self, _name, _completed):
        self.preview.clear()
        self.pointer.reset()
        self.map_tool.clear_selection()
        self.command_bar.set_prompt("Command:")
        self.document.refresh()

    # ---- feedback ----

    def _write(self, text):
        # The dock outlives this call only until ``cleanup`` deletes it, and
        # deferred work (the discard question) can land after that.
        try:
            self.command_bar.write(text)
        except RuntimeError:
            pass

    def _on_point_changed(self, point):
        self.command_bar.set_coordinates(
            point, int(self.variables.get("LUPREC")))

    def _on_variable_changed(self, name):
        if name in ("CANVASCOLOR", "*") and self._active:
            # Changing the background flips how ACI 7 resolves, so every
            # ByLayer colour has to be recomputed.
            self._enter_cad_mode()
        if name in ("LWDISPLAY", "LTSCALE", "CANVASCOLOR", "*"):
            self.document.restyle_all()
            self.document.refresh()
        if name in ("CLAYER", "*"):
            layer_name = self.variables.get("CLAYER")
            self.document.layers.set_current(layer_name)
            self.command_bar.set_current_layer(layer_name)
        if name in ("RUBBERCOLOR", "TRACKCOLOR", "AUTOSNAPCOLOR",
                    "HIGHLIGHTCOLOR", "*"):
            self.preview.apply_colours()
        if name in ("CURSORCOLOR", "PICKBOXCOLOR", "AUTOSNAPCOLOR", "*"):
            self.crosshair.apply_colours()
        if name in ("CROSSHAIR", "*") and self._active:
            self.crosshair.set_visible(bool(self.variables.get("CROSSHAIR")))
        if name in ("DYNMODE", "*"):
            self.dyninput.set_visible(
                self._active and bool(self.variables.get("DYNMODE")))
        if name in ("DYNCMDINPUT", "*") and not self.variables.get(
                "DYNCMDINPUT"):
            self.cmd_input.close()

    # ---- dialogs ----

    def open_dialog(self, name):
        """Open one of AutoQAD's dialogs by key."""
        opener = {
            "layers": self._open_layer_manager,
            "dsettings": self._open_drafting_settings,
            "options": self._open_drafting_settings,
            "patterns": self._open_layer_manager,
            "dxfout": self._export_dxf,
            "plot": self._open_plot,
        }.get(name)
        if opener is None:
            self._write("No dialog named '{0}'.".format(name))
            return
        opener()

    def _open_layer_manager(self):
        from .ui.layer_dialog import LayerManagerDialog
        dialog = self._dialogs.get("layers")
        if dialog is None:
            dialog = LayerManagerDialog(self.document, self.variables,
                                        self.iface.mainWindow())
            self._dialogs["layers"] = dialog
        dialog.reload()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _open_drafting_settings(self):
        from .ui.dsettings_dialog import DraftingSettingsDialog
        dialog = self._dialogs.get("dsettings")
        if dialog is None:
            dialog = DraftingSettingsDialog(self.variables,
                                            self.iface.mainWindow())
            self._dialogs["dsettings"] = dialog
        dialog.reload()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _export_dxf(self):
        from .io import dxf_export

        self.document.commit()
        project_path = QgsProject.instance().fileName()
        if project_path:
            suggestion = os.path.splitext(project_path)[0] + ".dxf"
        else:
            suggestion = "drawing.dxf"

        path, _filter = QFileDialog.getSaveFileName(
            self.iface.mainWindow(), "Export drawing to DXF", suggestion,
            "AutoCAD DXF (*.dxf)")
        if not path:
            return

        ok, message = dxf_export.export(self.document, path)
        self._write(message)
        if not ok:
            QMessageBox.warning(self.iface.mainWindow(), "AutoQAD", message)
        elif not dxf_export.is_available():
            self._write("Backend: " + dxf_export.describe_backend())

    # ---- plotting ----
    #
    # A plot is committed first, always. The tables' edit buffers hold entities
    # the renderer can see but a fresh QgsFeatureRequest from a layout item may
    # not, and a plot that silently omits the last five minutes of drawing is
    # the worst possible failure mode here.

    def _open_plot(self):
        from .ui.plot_dialog import PlotDialog

        if not self.document.is_open:
            self._write("No drawing is open — nothing to plot.")
            return

        self.document.commit()
        dialog = self._dialogs.get("plot")
        if dialog is None:
            dialog = PlotDialog(self.document, self.variables, self.canvas,
                                self.iface.mainWindow())
            dialog.windowPickRequested.connect(self._pick_plot_window)
            # Connected once, at construction. Connecting on every open would
            # stack handlers and plot the same sheet several times over.
            dialog.finished.connect(self._on_plot_finished)
            self._dialogs["plot"] = dialog
        dialog.reload()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_plot_finished(self, result):
        dialog = self._dialogs.get("plot")
        if dialog is None:
            return
        if not result:
            self._write("Plot cancelled.")
            return
        self._run_plot(dialog.settings())

    def _run_plot(self, settings):
        from .io import plot as plot_io

        settings.save_to_variables(self.variables)
        ok, message = plot_io.plot(
            self.document, settings, canvas=self.canvas, iface=self.iface,
            parent=self.iface.mainWindow())
        self._write(message)
        if not ok:
            QMessageBox.warning(self.iface.mainWindow(), "AutoQAD", message)

    def _pick_plot_window(self):
        """Let the user drag the plot window on the canvas.

        Uses QGIS's own ``QgsMapToolExtent`` rather than a hand-rolled rubber
        band: it already draws the box, handles Escape, and behaves the way a
        QGIS user expects. The AutoQAD map tool is put back either way, so a
        cancelled pick cannot strand the session without its canvas tool.
        """
        try:
            from qgis.gui import QgsMapToolExtent
        except ImportError:                       # pragma: no cover
            self._write("This QGIS build cannot pick a plot window. Plot the "
                        "display or the drawing extents instead.")
            return

        dialog = self._dialogs.get("plot")
        if dialog is None:
            return

        self._pick_previous_tool = self.canvas.mapTool()
        self._pick_tool = QgsMapToolExtent(self.canvas)
        self._pick_tool.extentChanged.connect(self._on_plot_window_picked)
        # ``extentChanged`` fires on release but the tool stays active, so
        # deactivation is what tells us a cancelled pick is over.
        self._pick_tool.deactivated.connect(self._end_window_pick)

        dialog.hide()
        self.canvas.setMapTool(self._pick_tool)
        self._write("Pick the first corner of the plot window, then the "
                    "opposite corner. Escape cancels.")

    def _on_plot_window_picked(self, extent):
        dialog = self._dialogs.get("plot")
        if dialog is not None and extent is not None and not extent.isEmpty():
            dialog.set_window((extent.xMinimum(), extent.yMinimum(),
                               extent.xMaximum(), extent.yMaximum()))
            self._write("Plot window set.")
        self._restore_after_pick()

    def _end_window_pick(self):
        # Deactivation without a pick means Escape or a tool change.
        if self._pick_tool is not None:
            self._restore_after_pick()

    def _restore_after_pick(self):
        tool = self._pick_tool
        self._pick_tool = None
        if tool is not None:
            for signal, slot in ((tool.extentChanged,
                                  self._on_plot_window_picked),
                                 (tool.deactivated, self._end_window_pick)):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass

        previous = self._pick_previous_tool or self.map_tool
        self._pick_previous_tool = None
        try:
            self.canvas.setMapTool(previous)
        except RuntimeError:                      # pragma: no cover
            self.canvas.setMapTool(self.map_tool)

        dialog = self._dialogs.get("plot")
        if dialog is not None:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

    # ---- QGIS layout designer ----

    def _attach_designer_hooks(self):
        """Make QGIS's own layout designer plot the drawing correctly.

        Without this, a map frame in the built-in designer inherits model
        space's white-on-black and prints as a blank sheet. Registering the
        map theme as well means the fix is reachable from the designer's own
        "Follow map theme" control, not only from AutoQAD's plot dialog.
        """
        from .style import plot_render, plotstyle
        from .ui.designer_hooks import DesignerHooks

        if self._designer_hooks is None:
            self._designer_hooks = DesignerHooks(
                self.iface, self.document, self.variables, self._write, self)
        else:
            self._designer_hooks.document = self.document
        self._designer_hooks.attach()

        if self.document.is_open:
            try:
                plot_render.register_plot_theme(
                    self.document,
                    plotstyle.PlotStyle.from_variables(self.variables))
            except (RuntimeError, AttributeError):    # pragma: no cover
                pass

    def _detach_designer_hooks(self):
        if self._designer_hooks is not None:
            self._designer_hooks.detach()

    # ---- project hooks ----

    def on_project_read(self):
        """Re-adopt a saved drawing when a project opens."""
        self.variables.load_from_project(QgsProject.instance())
        self.document.load_state()
        if self._active:
            self.document.ensure_open(
                self.canvas.mapSettings().destinationCrs())
            self.command_bar.set_current_layer(self.variables.get("CLAYER"))

    def on_project_write(self):
        """Persist the drawing's configuration into the project."""
        self.variables.save_to_project(QgsProject.instance())
        if self.document.is_open:
            # Saving the project means saving the drawing: flush the edit
            # buffers the commands have been accumulating.
            self.document.commit()
            self.document.save_state()
            self.document.materialise()

    def on_new_project(self):
        self.runner.cancel()
        self.document = DrawingDocument(self.variables)
        self.context.document = self.document
        self.snap_engine.document = self.document
        self.map_tool.document = self.document
        self.variables.reset_all()

        # Anything holding the old document would keep a dead drawing alive and
        # plot from it. The plot dialog is dropped rather than repointed: its
        # remembered window rectangle belongs to the project that just closed.
        if self._designer_hooks is not None:
            self._designer_hooks.document = self.document
        dialog = self._dialogs.pop("plot", None)
        if dialog is not None:
            try:
                dialog.close()
                dialog.deleteLater()
            except (RuntimeError, AttributeError):
                pass

    # ---- teardown ----

    def cleanup(self):
        """Release every canvas item, dock and dialog.

        The project instance outlives this controller, so the connection made
        in ``_wire`` must come off or it fires into a deleted object on the
        next layer removal.
        """
        try:
            QgsProject.instance().layersWillBeRemoved.disconnect(
                self._on_layers_will_be_removed)
        except (TypeError, RuntimeError):
            pass

        for signal, slot in self._clear_hooks():
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError, AttributeError):
                pass

        self.deactivate()
        for overlay in (self.preview, self.crosshair, self.dyninput,
                        self.cmd_input):
            try:
                overlay.dispose()
            except (RuntimeError, AttributeError):
                pass

        for dialog in self._dialogs.values():
            try:
                dialog.close()
                dialog.deleteLater()
            except (RuntimeError, AttributeError):
                pass
        self._dialogs = {}

        main_window = self.iface.mainWindow()
        for dock in (self.palette, self.command_bar):
            try:
                main_window.removeDockWidget(dock)
                dock.deleteLater()
            except (RuntimeError, AttributeError):
                pass
