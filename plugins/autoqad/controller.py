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

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from qgis.core import QgsProject

from .commands import build_registry
from .core.document import DrawingDocument
from .core.variables import VariableStore
from .engine.command import CommandContext
from .engine.runner import CommandRunner
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

        self.map_tool = AutoQadMapTool(
            self.canvas, self.runner, self.pointer, self.preview,
            self.variables, self.document,
            crosshair=self.crosshair, dyninput=self.dyninput)

        self.command_bar = CommandBarDock(self.variables, self.registry,
                                          iface.mainWindow())
        self.palette = ToolPaletteDock(iface.mainWindow())

        self._dialogs = {}
        self._active = False
        self._wire()

    # ---- wiring ----

    def _wire(self):
        self.command_bar.submitted.connect(self._on_submitted)
        self.command_bar.cancelled.connect(self._on_cancelled)
        self.command_bar.toggled.connect(self._on_toggle)
        self.palette.commandRequested.connect(self.run_command)

        self.runner.promptChanged.connect(self._on_prompt_changed)
        self.runner.messaged.connect(self._write)
        self.runner.rubberChanged.connect(self.preview.set_descriptor)
        self.runner.commandStarted.connect(self._on_command_started)
        self.runner.commandEnded.connect(self._on_command_ended)

        self.pointer.pointChanged.connect(self._on_point_changed)
        self.variables.changed.connect(self._on_variable_changed)

        # Fires *before* the C++ layers are destroyed — the one moment we can
        # still identify them and drop our references safely.
        QgsProject.instance().layersWillBeRemoved.connect(
            self._on_layers_will_be_removed)

    def _on_layers_will_be_removed(self, layer_ids):
        """Release references to drawing tables the user is deleting."""
        was_open = bool(self.document._tables)
        self.document.on_layers_removed(layer_ids)

        if was_open and not self.document.is_open:
            self.runner.cancel()
            self.preview.clear()
            self.pointer.reset()
            if self._active:
                self._write(
                    "Drawing tables were removed. The next command reopens "
                    "them from the GeoPackage if it still exists.")

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

        self.canvas.setMapTool(self.map_tool)
        self.command_bar.set_current_layer(self.variables.get("CLAYER"))
        self.command_bar.focus_input()

        self._active = True
        self.activeChanged.emit(True)
        self._write("AutoQAD ready. Type a command, or pick a tool.")
        return True

    def deactivate(self):
        """Hide the docks and release the canvas."""
        if not self._active:
            return
        self.runner.cancel()
        self.preview.clear()
        self.crosshair.set_visible(False)
        self.dyninput.set_visible(False)
        self.pointer.reset()

        if self.canvas.mapTool() is self.map_tool:
            self.canvas.unsetMapTool(self.map_tool)

        self.palette.hide()
        self.command_bar.hide()

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

    def _on_submitted(self, text):
        if not self.runner.is_running:
            stripped = text.strip()
            if stripped:
                self.map_tool.set_selection(self.map_tool.selection)
        self.runner.supply_text(text)
        self.map_tool.sync_to_prompt()
        self.command_bar.focus_input()

    def _on_cancelled(self):
        self.runner.escape()
        self.preview.clear()
        self.pointer.reset()
        self.map_tool.clear_selection()

    def _on_prompt_changed(self, text):
        self.command_bar.set_prompt(text)
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
        self.command_bar.write(text)

    def _on_point_changed(self, point):
        self.command_bar.set_coordinates(
            point, int(self.variables.get("LUPREC")))

    def _on_toggle(self, variable):
        self.variables.toggle(variable)

    def _on_variable_changed(self, name):
        if name in ("LWDISPLAY", "LTSCALE", "*"):
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

    # ---- dialogs ----

    def open_dialog(self, name):
        """Open one of AutoQAD's dialogs by key."""
        opener = {
            "layers": self._open_layer_manager,
            "dsettings": self._open_drafting_settings,
            "options": self._open_drafting_settings,
            "patterns": self._open_layer_manager,
            "dxfout": self._export_dxf,
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
            self.document.save_state()
            self.document.materialise()

    def on_new_project(self):
        self.runner.cancel()
        self.document = DrawingDocument(self.variables)
        self.context.document = self.document
        self.snap_engine.document = self.document
        self.map_tool.document = self.document
        self.variables.reset_all()

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

        self.deactivate()
        for overlay in (self.preview, self.crosshair, self.dyninput):
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
