# -*- coding: utf-8 -*-
"""The PLOT dialog — AutoCAD's plot sheet, not QGIS's layout designer.

Everything a draughtsman answers before a sheet comes out of the plotter, in the
order AutoCAD asks it: where it goes, what size the paper is, what part of the
drawing to plot, at what scale, and through which plot style table. Nothing
else. The QGIS layout designer remains one click away — "Open in QGIS Layout
designer" is one of the output targets — for anyone who wants a title block.

The dialog is a **collector**, not a doer: :meth:`PlotDialog.settings` returns a
:class:`..io.plot.PlotSettings` and the controller performs the plot. That keeps
the dialog testable-by-inspection and means the identical plot can be driven
from a script with no dialog involved.

Live scale feedback is the one piece of real behaviour here. The fit scale
depends on the sheet, the orientation, the margin *and* the plot area, so any of
those changing has to recompute it — otherwise "Fit to paper" is a promise the
dialog cannot show the user it is keeping.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..io import plot, plot_geometry
from ..style import plotstyle
from . import theme


class PlotDialog(QDialog):
    """Collects one plot's settings.

    *canvas* is optional but strongly wanted: without it there is no Display
    area and no way to pick a Window.
    """

    #: Emitted when the user asks to pick the plot window on the canvas. The
    #: controller runs the pick and calls :meth:`set_window` with the result —
    #: the dialog never touches a map tool itself.
    windowPickRequested = pyqtSignal()

    def __init__(self, document, variables, canvas=None, parent=None):
        super().__init__(parent)
        self.document = document
        self.variables = variables
        self.canvas = canvas
        self._window = None
        self._loading = False

        self.setWindowTitle("Plot")
        self.setMinimumWidth(460)
        theme.apply(self)

        self._build()
        self.reload()

    # ---- construction ----

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        outer.addWidget(self._build_output_group())
        outer.addWidget(self._build_paper_group())
        outer.addWidget(self._build_area_group())
        outer.addWidget(self._build_style_group())

        self.scale_note = QLabel("")
        self.scale_note.setProperty("role", "muted")
        self.scale_note.setWordWrap(True)
        outer.addWidget(self.scale_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, self)
        self.plot_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.plot_button.setText("Plot")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _build_output_group(self):
        group = QGroupBox("Printer / plotter", self)
        form = QFormLayout(group)

        self.target_combo = QComboBox(group)
        for key, label, _extension in plot.TARGETS:
            self.target_combo.addItem(label, key)
        self.target_combo.currentIndexChanged.connect(self._on_target_changed)
        form.addRow("Send to", self.target_combo)

        self.path_row = QWidget(group)
        row = QHBoxLayout(self.path_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.path_edit = QLineEdit(self.path_row)
        self.path_edit.setPlaceholderText("Output file")
        row.addWidget(self.path_edit, 1)
        browse = QPushButton("Browse…", self.path_row)
        browse.setProperty("variant", "secondary")
        browse.clicked.connect(self._browse)
        row.addWidget(browse, 0)
        self.path_label = QLabel("File")
        form.addRow(self.path_label, self.path_row)

        self.dpi_spin = QSpinBox(group)
        self.dpi_spin.setRange(48, 2400)
        self.dpi_spin.setSingleStep(50)
        self.dpi_spin.setSuffix(" dpi")
        form.addRow("Resolution", self.dpi_spin)
        return group

    def _build_paper_group(self):
        group = QGroupBox("Paper size", self)
        form = QFormLayout(group)

        self.sheet_combo = QComboBox(group)
        for name in plot_geometry.sheet_names():
            self.sheet_combo.addItem(name, name)
        self.sheet_combo.currentIndexChanged.connect(self._refresh_scale_note)
        form.addRow("Sheet", self.sheet_combo)

        self.orientation_combo = QComboBox(group)
        self.orientation_combo.addItem("Landscape", True)
        self.orientation_combo.addItem("Portrait", False)
        self.orientation_combo.currentIndexChanged.connect(
            self._refresh_scale_note)
        form.addRow("Orientation", self.orientation_combo)

        self.margin_spin = QDoubleSpinBox(group)
        self.margin_spin.setRange(0.0, 100.0)
        self.margin_spin.setDecimals(1)
        self.margin_spin.setSingleStep(1.0)
        self.margin_spin.setSuffix(" mm")
        self.margin_spin.valueChanged.connect(self._refresh_scale_note)
        form.addRow("Margin", self.margin_spin)
        return group

    def _build_area_group(self):
        group = QGroupBox("Plot area and scale", self)
        form = QFormLayout(group)

        area_row = QWidget(group)
        row = QHBoxLayout(area_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.area_combo = QComboBox(area_row)
        for key, label, help_text in plot.AREAS:
            self.area_combo.addItem(label, key)
            self.area_combo.setItemData(self.area_combo.count() - 1,
                                        help_text, Qt.ItemDataRole.ToolTipRole)
        self.area_combo.currentIndexChanged.connect(self._on_area_changed)
        row.addWidget(self.area_combo, 1)
        self.window_button = QPushButton("Pick window…", area_row)
        self.window_button.setProperty("variant", "secondary")
        self.window_button.clicked.connect(self._request_window)
        row.addWidget(self.window_button, 0)
        form.addRow("What to plot", area_row)

        self.fit_check = QCheckBox("Fit to paper", group)
        self.fit_check.toggled.connect(self._on_fit_toggled)
        form.addRow("", self.fit_check)

        scale_row = QWidget(group)
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        scale_layout.setSpacing(6)
        scale_layout.addWidget(QLabel("1:", scale_row), 0)
        self.scale_combo = QComboBox(scale_row)
        self.scale_combo.setEditable(True)
        for value in plot_geometry.STANDARD_SCALES:
            if value >= 1.0:
                self.scale_combo.addItem(
                    plot_geometry.format_number(value), float(value))
        self.scale_combo.currentTextChanged.connect(self._refresh_scale_note)
        scale_layout.addWidget(self.scale_combo, 1)
        self.scale_row = scale_row
        form.addRow("Scale", scale_row)
        return group

    def _build_style_group(self):
        group = QGroupBox("Plot style table", self)
        form = QFormLayout(group)

        self.style_combo = QComboBox(group)
        for key, label, help_text in plotstyle.MODES:
            self.style_combo.addItem(label, key)
            self.style_combo.setItemData(self.style_combo.count() - 1,
                                         help_text,
                                         Qt.ItemDataRole.ToolTipRole)
        self.style_combo.currentIndexChanged.connect(self._on_style_changed)
        form.addRow("Table", self.style_combo)

        self.style_note = QLabel("")
        self.style_note.setProperty("role", "muted")
        self.style_note.setWordWrap(True)
        form.addRow("", self.style_note)

        self.lineweight_check = QCheckBox("Plot object lineweights", group)
        form.addRow("", self.lineweight_check)

        self.min_width_spin = QDoubleSpinBox(group)
        self.min_width_spin.setRange(0.0, 2.0)
        self.min_width_spin.setDecimals(2)
        self.min_width_spin.setSingleStep(0.01)
        self.min_width_spin.setSuffix(" mm")
        self.min_width_spin.setToolTip(
            "Thinnest line the plot will produce. A weight that reads fine on "
            "screen can vanish on paper; 0 leaves every weight as drawn.")
        form.addRow("Minimum width", self.min_width_spin)
        return group

    # ---- state ----

    def reload(self):
        """Refill every control from the PLOT* system variables."""
        self._loading = True
        try:
            settings = plot.PlotSettings.from_variables(self.variables)
            self._apply(settings)
        finally:
            self._loading = False
        self._on_target_changed()
        self._on_area_changed()
        self._on_style_changed()
        self._on_fit_toggled(self.fit_check.isChecked())

    def _apply(self, settings):
        self._select(self.sheet_combo, settings.sheet)
        self._select(self.orientation_combo, settings.landscape)
        self.margin_spin.setValue(settings.margin_mm)
        self._select(self.area_combo, settings.area)
        self.fit_check.setChecked(settings.fit_to_paper)
        if not settings.fit_to_paper:
            self.scale_combo.setCurrentText(
                plot_geometry.format_number(settings.scale))
        self._select(self.style_combo, settings.style_mode)
        self.lineweight_check.setChecked(settings.lineweights)
        self.min_width_spin.setValue(settings.minimum_width_mm)
        self.dpi_spin.setValue(settings.dpi)
        self._select(self.target_combo, settings.target)
        self.path_edit.setText(settings.path)

    @staticmethod
    def _select(combo, value):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def set_window(self, extent):
        """Record a picked plot window. *extent* is ``(xmin,ymin,xmax,ymax)``."""
        self._window = plot_geometry.normalise_extent(extent)
        if self._window is not None:
            self._select(self.area_combo, plot.AREA_WINDOW)
        self._refresh_scale_note()

    def settings(self):
        """Return the :class:`PlotSettings` the controls describe."""
        return plot.PlotSettings(
            sheet=self.sheet_combo.currentData(),
            landscape=bool(self.orientation_combo.currentData()),
            margin_mm=self.margin_spin.value(),
            area=self.area_combo.currentData(),
            window=self._window,
            scale=0.0 if self.fit_check.isChecked() else self._scale_value(),
            style_mode=self.style_combo.currentData(),
            lineweights=self.lineweight_check.isChecked(),
            minimum_width_mm=self.min_width_spin.value(),
            target=self.target_combo.currentData(),
            path=self.path_edit.text().strip(),
            dpi=self.dpi_spin.value())

    def _scale_value(self):
        """Read the scale combo, tolerating anything typed into it."""
        data = self.scale_combo.currentData()
        text = self.scale_combo.currentText().strip().replace("1:", "")
        try:
            value = float(text)
        except (TypeError, ValueError):
            value = float(data) if data else 0.0
        return value if value > 0.0 else 0.0

    # ---- reactions ----

    def _on_target_changed(self, _index=None):
        target = self.target_combo.currentData()
        needs_file = plot.writes_a_file(target)
        self.path_row.setVisible(needs_file)
        self.path_label.setVisible(needs_file)
        # Only a raster export is really governed by DPI, but PDF and SVG use it
        # for the resolution any rasterised fill falls back to, so it stays live
        # for everything that writes a file.
        self.dpi_spin.setEnabled(needs_file)
        if needs_file and not self.path_edit.text().strip():
            self.path_edit.setText(self._suggested_path(target))
        self._refresh_scale_note()

    def _on_area_changed(self, _index=None):
        area = self.area_combo.currentData()
        self.window_button.setEnabled(
            area == plot.AREA_WINDOW and self.canvas is not None)
        if area != plot.AREA_WINDOW:
            self._window = None
        self._refresh_scale_note()

    def _on_fit_toggled(self, checked):
        self.scale_row.setEnabled(not checked)
        self._refresh_scale_note()

    def _on_style_changed(self, _index=None):
        self.style_note.setText(
            plotstyle.describe(self.style_combo.currentData()))

    def _request_window(self):
        if self.canvas is None:
            return
        self.windowPickRequested.emit()

    def _browse(self):
        target = self.target_combo.currentData()
        extension = plot.target_extension(target)
        filters = {
            plot.TARGET_PDF: "PDF document (*.pdf)",
            plot.TARGET_PNG: "PNG image (*.png)",
            plot.TARGET_SVG: "SVG drawing (*.svg)",
        }.get(target, "All files (*)")

        path, _selected = QFileDialog.getSaveFileName(
            self, "Plot to file",
            self.path_edit.text().strip() or self._suggested_path(target),
            filters)
        if not path:
            return
        if extension and not path.lower().endswith(extension):
            path += extension
        self.path_edit.setText(path)

    def _suggested_path(self, target):
        """Offer the project's own name and folder, as DXFOUT does."""
        import os

        from qgis.core import QgsProject

        extension = plot.target_extension(target) or ".pdf"
        project_path = QgsProject.instance().fileName()
        if project_path:
            return os.path.splitext(project_path)[0] + extension
        return "plot" + extension

    def _refresh_scale_note(self, *_args):
        """Recompute the live 'this plots at 1:N' line."""
        if self._loading:
            return
        try:
            settings = self.settings()
            frame_w, frame_h = settings.frame_size()
            suggestion = plot.suggested_scale(self.document, settings,
                                              self.canvas)
        except (RuntimeError, AttributeError, ValueError):
            self.scale_note.setText("")
            return

        page_w, page_h = settings.page_size()
        parts = ["Sheet {0:.0f} x {1:.0f} mm, drawing frame {2:.0f} x {3:.0f} "
                 "mm.".format(page_w, page_h, frame_w, frame_h)]

        if settings.fit_to_paper:
            parts.append("Fits at about {0} (nearest standard {1}).".format(
                plot_geometry.format_scale(suggestion),
                plot_geometry.format_scale(
                    plot_geometry.nearest_standard_scale(suggestion))))
        else:
            parts.append("Plotting at {0}; a fit would be about {1}.".format(
                plot_geometry.format_scale(settings.scale),
                plot_geometry.format_scale(suggestion)))

        if settings.area == plot.AREA_WINDOW and self._window is None:
            parts.append("No window picked yet — using the drawing extents.")

        self.scale_note.setText(" ".join(parts))

    # ---- validation ----

    def accept(self):
        """Refuse to plot into nowhere; everything else has a usable default."""
        settings = self.settings()
        if plot.writes_a_file(settings.target) and not settings.path:
            self.scale_note.setText(
                "Choose an output file before plotting.")
            self.path_edit.setFocus()
            return
        super().accept()
