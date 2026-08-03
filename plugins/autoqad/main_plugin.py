# -*- coding: utf-8 -*-
"""AutoQAD plugin entry point.

Copyright (C) 2026 Isaac Enage (byZenterra)
Licensed under the GNU General Public License v3.0 or later.

Registers one checkable toolbar/menu action that switches the CAD session on
and off, and connects the project save/open/new hooks so a drawing travels with
its ``.qgz``.

Also re-exposes the scripting facade so an automation client — QGIS MCP driving
an LLM, or a plain PyQGIS script — can reach AutoQAD with
``plugins['autoqad'].command("LINE 0,0 10,0")`` without the GUI being involved.
"""

import os.path

from qgis.PyQt.QtCore import QCoreApplication, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProject

# QAction lives in QtWidgets on Qt5 but moved to QtGui on Qt6; import
# defensively so the plugin works across QGIS 3.22 - 4.99.
try:                                          # Qt6 / PyQt6
    from qgis.PyQt.QtGui import QAction
except ImportError:                           # pragma: no cover - Qt5 / PyQt5
    from qgis.PyQt.QtWidgets import QAction

from .ui.icons import logo_icon


class AutoQadPlugin:
    """QGIS plugin implementation for AutoQAD."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        locale = QSettings().value("locale/userLocale")
        locale = locale[0:2] if locale else "en"
        locale_path = os.path.join(self.plugin_dir, "i18n",
                                   "autoqad_{0}.qm".format(locale))
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr("&AutoQAD")
        self.action = None
        self.controller = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Translate *message* through the Qt translation API."""
        return QCoreApplication.translate("AutoQAD", message)

    def _icon(self):
        logo = logo_icon()
        if not logo.isNull():
            return logo
        return QIcon(os.path.join(self.plugin_dir, "icon.png"))

    # ---- QGIS plugin interface ----

    def initGui(self):
        """Add the toolbar button and menu entry."""
        self.action = QAction(self._icon(), self.tr("AutoQAD"),
                              self.iface.mainWindow())
        self.action.setCheckable(True)
        self.action.setToolTip(
            self.tr("AutoQAD — CAD drawing tools with an AutoCAD command line"))
        self.action.triggered.connect(self.toggle)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu(self.menu, self.action)
        self.actions.append(self.action)

        QgsProject.instance().writeProject.connect(self._on_write)
        self.iface.projectRead.connect(self._on_read)
        self.iface.newProjectCreated.connect(self._on_new)

    def unload(self):
        """Remove the plugin's UI and every connection it made.

        The project instance and ``iface`` outlive the plugin, so a connection
        left behind after unload/reload fires into deleted objects on the next
        project save — surfacing as ``RuntimeError: wrapped C/C++ object has
        been deleted``.
        """
        for signal, slot in (
                (QgsProject.instance().writeProject, self._on_write),
                (self.iface.projectRead, self._on_read),
                (self.iface.newProjectCreated, self._on_new)):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

        if self.controller is not None:
            self.controller.cleanup()
            self.controller = None

    # ---- session ----

    def _ensure_controller(self):
        if self.controller is None:
            from .controller import AutoQadController
            self.controller = AutoQadController(self.iface)
            self.controller.activeChanged.connect(self._on_active_changed)
        return self.controller

    def _on_active_changed(self, active):
        if self.action is not None and self.action.isChecked() != active:
            self.action.setChecked(active)

    def toggle(self, checked):
        controller = self._ensure_controller()
        if checked:
            if not controller.activate() and self.action is not None:
                self.action.setChecked(False)
        else:
            controller.deactivate()

    # ---- project hooks ----

    def _on_write(self, _doc=None):
        if self.controller is not None:
            self.controller.on_project_write()

    def _on_read(self):
        if self.controller is not None:
            self.controller.on_project_read()

    def _on_new(self):
        if self.controller is not None:
            self.controller.on_new_project()

    # ---- scripting facade (QGIS MCP / PyQGIS automation) ----
    #
    # Thin wrappers over ``scripting.py`` so an agent can drive AutoQAD with
    # ``plugins['autoqad'].<method>(...)``. Each ensures a session exists, so a
    # single call works from a cold start.

    def command(self, text, show=True):
        """Run one command macro string, e.g. ``"LINE 0,0 10,0 10,8 C"``."""
        from .scripting import run_macro
        controller = self._ensure_session(show)
        return run_macro(controller, text)

    def draw(self, spec, show=True):
        """Build a whole drawing from a spec dict. See :meth:`api_reference`."""
        from .scripting import build_drawing
        controller = self._ensure_session(show)
        return build_drawing(controller, spec)

    def list_layers(self):
        """List the drawing's CAD layers and their properties."""
        from .scripting import list_layers
        return list_layers(self._ensure_session(False))

    def list_commands(self):
        """List every command with its aliases and description."""
        from .scripting import list_commands
        return list_commands(self._ensure_session(False))

    def list_patterns(self):
        """List the available hatch patterns and linetypes."""
        from .scripting import list_patterns
        return list_patterns(self._ensure_session(False))

    def get_variable(self, name):
        return self._ensure_session(False).variables.get(name)

    def set_variable(self, name, value):
        return self._ensure_session(False).variables.set(name, value)

    def export_dxf(self, path):
        """Write the drawing to *path*. Returns ``(ok, message)``."""
        from .io import dxf_export
        return dxf_export.export(self._ensure_session(False).document, path)

    def api_reference(self):
        """Return the scripting API reference (spec schema, commands, types)."""
        from .scripting import api_reference
        return api_reference(self._ensure_session(False))

    def _ensure_session(self, show):
        controller = self._ensure_controller()
        if show:
            controller.activate()
            if self.action is not None:
                self.action.setChecked(True)
        elif not controller.document.is_open:
            controller.document.ensure_open(
                self.iface.mapCanvas().mapSettings().destinationCrs())
        return controller
