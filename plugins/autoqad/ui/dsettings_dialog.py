# -*- coding: utf-8 -*-
"""Drafting Settings — object snaps, grid snap and polar tracking.

Mirrors AutoCAD's DSETTINGS dialog. Every control is bound directly to a system
variable, so the dialog holds no state of its own and cannot fall out of step
with what the pointer pipeline is actually reading.
"""

from qgis.PyQt.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from ..core.variables import OSNAP_MODES
from . import theme


class DraftingSettingsDialog(QDialog):
    """Snap, grid, polar tracking and object-snap configuration."""

    def __init__(self, variables, parent=None):
        super().__init__(parent)
        self.variables = variables
        self._osnap_boxes = {}

        self.setWindowTitle("Drafting Settings")
        self.resize(520, 500)
        self._build()
        theme.apply(self)
        self.reload()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tabs = QTabWidget(self)
        tabs.addTab(self._snap_tab(), "Snap and Grid")
        tabs.addTab(self._osnap_tab(), "Object Snap")
        tabs.addTab(self._polar_tab(), "Polar Tracking")
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---- tabs ----

    def _snap_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        snap_group = QGroupBox("Snap", page)
        snap_layout = QGridLayout(snap_group)
        self.snap_on = QCheckBox("Snap on (F9)", snap_group)
        self.snap_on.toggled.connect(
            lambda value: self.variables.set("SNAPMODE", value))
        snap_layout.addWidget(self.snap_on, 0, 0, 1, 2)

        snap_layout.addWidget(QLabel("Snap spacing", snap_group), 1, 0)
        self.snap_spacing = QDoubleSpinBox(snap_group)
        self.snap_spacing.setRange(0.0001, 1e6)
        self.snap_spacing.setDecimals(4)
        self.snap_spacing.valueChanged.connect(
            lambda value: self.variables.set("SNAPUNIT", value))
        snap_layout.addWidget(self.snap_spacing, 1, 1)
        layout.addWidget(snap_group)

        grid_group = QGroupBox("Grid", page)
        grid_layout = QGridLayout(grid_group)
        self.grid_on = QCheckBox("Grid on (F7)", grid_group)
        self.grid_on.toggled.connect(
            lambda value: self.variables.set("GRIDMODE", value))
        grid_layout.addWidget(self.grid_on, 0, 0, 1, 2)

        grid_layout.addWidget(QLabel("Grid spacing", grid_group), 1, 0)
        self.grid_spacing = QDoubleSpinBox(grid_group)
        self.grid_spacing.setRange(0.0001, 1e6)
        self.grid_spacing.setDecimals(4)
        self.grid_spacing.valueChanged.connect(
            lambda value: self.variables.set("GRIDUNIT", value))
        grid_layout.addWidget(self.grid_spacing, 1, 1)
        layout.addWidget(grid_group)

        layout.addStretch(1)
        return page

    def _osnap_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self.osnap_on = QCheckBox("Object snap on (F3)", page)
        self.osnap_on.toggled.connect(
            lambda value: self.variables.set("OSNAPON", value))
        layout.addWidget(self.osnap_on)

        group = QGroupBox("Object snap modes", page)
        grid = QGridLayout(group)
        for index, (flag, short, label) in enumerate(OSNAP_MODES):
            box = QCheckBox("{0}  ({1})".format(label, short), group)
            box.toggled.connect(
                lambda value, f=flag: self.variables.set_osnap(f, value))
            grid.addWidget(box, index // 2, index % 2)
            self._osnap_boxes[flag] = box
        layout.addWidget(group)

        row = QHBoxLayout()
        select_all = QPushButton("Select all", page)
        select_all.setProperty("variant", "secondary")
        select_all.clicked.connect(lambda: self._set_all_osnaps(True))
        row.addWidget(select_all)

        clear_all = QPushButton("Clear all", page)
        clear_all.setProperty("variant", "secondary")
        clear_all.clicked.connect(lambda: self._set_all_osnaps(False))
        row.addWidget(clear_all)
        row.addStretch(1)
        layout.addLayout(row)

        aperture_row = QHBoxLayout()
        aperture_row.addWidget(QLabel("Aperture size (pixels)", page))
        self.aperture = QSpinBox(page)
        self.aperture.setRange(2, 50)
        self.aperture.valueChanged.connect(
            lambda value: self.variables.set("APERTURE", value))
        aperture_row.addWidget(self.aperture)
        aperture_row.addStretch(1)
        layout.addLayout(aperture_row)

        layout.addStretch(1)
        return page

    def _polar_tab(self):
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self.polar_on = QCheckBox("Polar tracking on (F10)", page)
        self.polar_on.toggled.connect(
            lambda value: self.variables.set("POLARMODE", value))
        layout.addWidget(self.polar_on)

        group = QGroupBox("Polar angle settings", page)
        grid = QGridLayout(group)
        grid.addWidget(QLabel("Increment angle", group), 0, 0)
        self.polar_angle = QDoubleSpinBox(group)
        self.polar_angle.setRange(0.0, 180.0)
        self.polar_angle.setDecimals(2)
        self.polar_angle.setSuffix(" °")
        self.polar_angle.valueChanged.connect(
            lambda value: self.variables.set("POLARANG", value))
        grid.addWidget(self.polar_angle, 0, 1)
        layout.addWidget(group)

        self.ortho_on = QCheckBox("Ortho mode (F8)", page)
        self.ortho_on.toggled.connect(
            lambda value: self.variables.set("ORTHOMODE", value))
        layout.addWidget(self.ortho_on)

        note = QLabel(
            "Ortho takes precedence over polar tracking when both are on.",
            page)
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        layout.addStretch(1)
        return page

    # ---- state ----

    def _set_all_osnaps(self, enabled):
        for flag, box in self._osnap_boxes.items():
            box.setChecked(enabled)

    def reload(self):
        self.snap_on.setChecked(bool(self.variables.get("SNAPMODE")))
        self.snap_spacing.setValue(float(self.variables.get("SNAPUNIT")))
        self.grid_on.setChecked(bool(self.variables.get("GRIDMODE")))
        self.grid_spacing.setValue(float(self.variables.get("GRIDUNIT")))

        self.osnap_on.setChecked(bool(self.variables.get("OSNAPON")))
        for flag, box in self._osnap_boxes.items():
            box.setChecked(self.variables.osnap_active(flag))
        self.aperture.setValue(int(self.variables.get("APERTURE")))

        self.polar_on.setChecked(bool(self.variables.get("POLARMODE")))
        self.polar_angle.setValue(float(self.variables.get("POLARANG")))
        self.ortho_on.setChecked(bool(self.variables.get("ORTHOMODE")))
