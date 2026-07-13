# -*- coding: utf-8 -*-
"""Export-to-HTML entry point: file picker + large-data guard.

Opened from the Settings hub. Picks an output path, warns if any bound layer is
too large to embed sanely for browser viewing (offering to proceed, skip those
layers, or cancel), then writes the single self-contained ``index.html`` via
:mod:`export.html_export`.
"""

import os

from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from qgis.core import QgsProject

from .export.html_export import export_dashboard, oversize_layers

# A bound layer above either threshold triggers the embed warning.
MAX_FEATURES = 100000
MAX_BYTES = 50 * 1024 * 1024


def _default_name():
    name = os.path.splitext(os.path.basename(
        QgsProject.instance().fileName()))[0]
    return (name or "dashboard") + ".html"


def _format_warning(big):
    lines = ["These bound layers are large to embed in a single HTML file for "
             "browser viewing:\n"]
    for _lid, name, count, est in big:
        lines.append("  • {}: {:,} features (~{:.0f} MB)".format(
            name, count, est / (1024.0 * 1024.0)))
    lines.append("\nLarge GeoPackage/Shapefile data embedded client-side can "
                 "make the file slow or unopenable in a browser.")
    return "\n".join(lines)


def prompt_and_export(window, parent=None):
    """Run the interactive export flow against *window*."""
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export dashboard to HTML", _default_name(),
        "HTML files (*.html)")
    if not path:
        return
    if not path.lower().endswith(".html"):
        path += ".html"

    skip_layers = set()
    big = oversize_layers(window, MAX_FEATURES, MAX_BYTES)
    if big:
        box = QMessageBox(parent)
        box.setWindowTitle("Large data")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(_format_warning(big))
        box.addButton("Export anyway", QMessageBox.ButtonRole.AcceptRole)
        skip = box.addButton(
            "Skip these layers",
            QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel:
            return
        if clicked is skip:
            skip_layers = {lid for lid, _n, _c, _e in big}

    try:
        out = export_dashboard(window, path, skip_layers=skip_layers)
    except Exception as exc:   # surface a clear error, never half-write silently
        QMessageBox.critical(parent, "Export failed",
                             "Could not export the dashboard:\n{}".format(exc))
        return

    QMessageBox.information(
        parent, "Export complete",
        "Saved dashboard to:\n{}\n\nDouble-click it to open in your browser."
        .format(out))
