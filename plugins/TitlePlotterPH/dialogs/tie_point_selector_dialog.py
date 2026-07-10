# -*- coding: utf-8 -*-

import os

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QDialog, QTableWidgetItem, QGridLayout, QPushButton, QHeaderView,
    QAbstractItemView, QMessageBox,
)
from qgis.PyQt.QtCore import pyqtSignal, Qt

from .. import theme
from .. import tiepoint_service
from ..tiepoint_data import DEFAULT_LIMIT, filter_rows, merge_rows, provinces_from_rows
from .report_correction_dialog import ReportCorrectionDialog

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'forms', 'tie_point_selector_dialog_base.ui'))

TABLE_HEADERS = ["Tie Point Name", "Description", "Province", "Municipality", "Northing", "Easting"]


class TiePointSelectorDialog(QDialog, FORM_CLASS):
    # Signal to emit when a tie point is selected
    tie_point_selected = pyqtSignal(str, str)

    def __init__(self, parent=None):
        """Constructor."""
        super(TiePointSelectorDialog, self).__init__(parent)
        self.setupUi(self)

        # Apply the shared Title Plotter theme (neutral chrome + teal accent)
        theme.apply(self)

        # Offline cache of previously fetched tie points (QGIS profile dir).
        # Searches hit the online database first and fall back to this cache
        # so field work without internet still finds known tie points.
        self._cache = tiepoint_service.load_cache()

        # Setup custom UI layout and placeholders
        self.setup_custom_ui()

        # Additional table customization
        self.tiePointTable.setAlternatingRowColors(True)
        self.tiePointTable.setShowGrid(False)  # Cleaner look without full grid
        self.tiePointTable.verticalHeader().setVisible(False)  # Hide row numbers

        self.setup_connections()
        self.setup_table_headers()
        self.setup_province_combo()
        # Initialize empty table
        self.tiePointTable.setRowCount(0)
        self.tiePointTable.setColumnCount(len(TABLE_HEADERS))
        self.tiePointTable.setHorizontalHeaderLabels(TABLE_HEADERS)
        # Update status label
        cached_count = len(self._cache["rows"])
        if cached_count:
            self.statusLabel.setText(
                "Status: Use search to find tie points ({} available offline).".format(cached_count))
        else:
            self.statusLabel.setText("Status: No data loaded. Use search to find tie points.")

    def setup_connections(self):
        # Remove textChanged connections and add search button connection
        self.searchButton.clicked.connect(self.apply_filters)
        self.tiePointTable.itemDoubleClicked.connect(self.accept_selection)
        self.selectButton.clicked.connect(self.accept_selection)
        self.cancelButton.clicked.connect(self.reject)
        self.reportButton.clicked.connect(self.report_correction)

    def setup_province_combo(self):
        """Set up the province ComboBox: online list when available, cached
        list (or provinces of cached rows) when offline."""
        provinces, _error = tiepoint_service.fetch_provinces()
        if provinces:
            if provinces != self._cache["provinces"]:
                self._cache = {
                    "rows": self._cache["rows"],
                    "provinces": provinces,
                }
                tiepoint_service.save_cache(self._cache)
        else:
            provinces = self._cache["provinces"] or provinces_from_rows(
                self._cache["rows"].values())
        self.provinceComboBox.addItem("")  # Blank = no filter
        self.provinceComboBox.addItems(provinces)

    def setup_table_headers(self):
        """Set up table headers and tooltips"""
        self.tiePointTable.setColumnCount(len(TABLE_HEADERS))
        self.tiePointTable.setHorizontalHeaderLabels(TABLE_HEADERS)

        # Set header resize mode and enable sorting
        header = self.tiePointTable.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tiePointTable.setSortingEnabled(True)

        # Set tooltips for headers
        tooltips = [
            "Name of the tie point (case and space insensitive)",
            "Description of the tie point (partial match)",
            "Province where the tie point is located (select from list)",
            "Municipality where the tie point is located (partial match)",
            "Northing coordinate of the tie point",
            "Easting coordinate of the tie point"
        ]
        for i, tooltip in enumerate(tooltips):
            self.tiePointTable.horizontalHeaderItem(i).setToolTip(tooltip)

        # Allow single row selection
        self.tiePointTable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tiePointTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def populate_table(self, rows):
        """Populate table with a list of tie point dicts."""
        # Sorting must be off while inserting or items scatter mid-fill
        self.tiePointTable.setSortingEnabled(False)
        self.tiePointTable.clearContents()
        self.tiePointTable.setRowCount(len(rows))
        self.tiePointTable.setColumnCount(len(TABLE_HEADERS))
        self.tiePointTable.setHorizontalHeaderLabels(TABLE_HEADERS)

        for row_idx, row in enumerate(rows):
            name_item = QTableWidgetItem(str(row.get("name") or ""))
            # Keep the full record on the row so selection/reporting survive
            # user-triggered column sorting
            name_item.setData(Qt.ItemDataRole.UserRole, row)
            self.tiePointTable.setItem(row_idx, 0, name_item)
            self.tiePointTable.setItem(row_idx, 1, QTableWidgetItem(str(row.get("description") or "")))
            self.tiePointTable.setItem(row_idx, 2, QTableWidgetItem(str(row.get("province") or "")))
            self.tiePointTable.setItem(row_idx, 3, QTableWidgetItem(str(row.get("municipality") or "")))
            for col, key in ((4, "northing"), (5, "easting")):
                item = QTableWidgetItem()
                value = row.get(key)
                # DisplayRole with the float itself sorts numerically
                item.setData(Qt.ItemDataRole.DisplayRole, "" if value is None else value)
                self.tiePointTable.setItem(row_idx, col, item)

        self.tiePointTable.setSortingEnabled(True)
        # Resize columns to content after populating
        self.tiePointTable.resizeColumnsToContents()

    def apply_filters(self):
        """Search the online database; fall back to the offline cache."""
        filters = {
            "name": self.nameInput.text(),
            "description": self.descriptionInput.text(),
            "municipality": self.municipalityInput.text(),
            "province": self.provinceComboBox.currentText(),
        }

        rows, error = tiepoint_service.search_tiepoints(**filters)
        if rows is not None:
            self.populate_table(rows)
            suffix = " Refine your search to see more." if len(rows) >= DEFAULT_LIMIT else ""
            self.statusLabel.setText(
                "Status: {} tie points found (online).{}".format(len(rows), suffix))
            # Every successful search grows the offline cache for field work
            self._cache = {
                "rows": merge_rows(self._cache["rows"], rows),
                "provinces": self._cache["provinces"],
            }
            tiepoint_service.save_cache(self._cache)
            return

        cached = filter_rows(list(self._cache["rows"].values()), **filters)
        self.populate_table(cached)
        if self._cache["rows"]:
            self.statusLabel.setText(
                "Status: OFFLINE - showing {} cached tie points. ({})".format(
                    len(cached), error))
        else:
            self.statusLabel.setText(
                "Status: OFFLINE and no cached tie points yet. Connect to the "
                "internet once to search and build your offline cache.")

    def _row_data(self, table_row):
        """The full tie point dict stored on the given table row."""
        if table_row < 0:
            return None
        item = self.tiePointTable.item(table_row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def accept_selection(self):
        """Handle selection of a tie point"""
        row = self._row_data(self.tiePointTable.currentRow())
        if row is None:
            return
        if row.get("northing") is None or row.get("easting") is None:
            QMessageBox.warning(
                self, "No Coordinates",
                "This tie point has no coordinates recorded, so it cannot be "
                "used for plotting. If you know the correct values, please "
                "use 'Report Correction' to send them to the developer.")
            return
        self.selected_row = {
            'id': row.get('id'),
            'name': str(row.get('name') or ''),
            'description': str(row.get('description') or ''),
            'province': str(row.get('province') or ''),
            'municipality': str(row.get('municipality') or ''),
            'northing': float(row['northing']),
            'easting': float(row['easting'])
        }
        self.accept()

    def report_correction(self):
        """Open the correction-report form for the selected tie point."""
        row = self._row_data(self.tiePointTable.currentRow())
        if row is None:
            QMessageBox.information(
                self, "Report Correction",
                "Search for the tie point and select its row first, then "
                "click 'Report Correction'.")
            return
        dialog = ReportCorrectionDialog(row, self)
        dialog.exec()

    def setup_custom_ui(self):
        """Rearrange UI elements and add placeholders programmatically."""
        # 1. Add Placeholders
        self.nameInput.setPlaceholderText("e.g., BLLM 1, BLBM 10")
        self.municipalityInput.setPlaceholderText("e.g., Tagaytay City, Malolos City")
        self.descriptionInput.setPlaceholderText("e.g., Cadastral Survey")
        self.provinceComboBox.setToolTip("Select Province")

        # 2. Rearrange Widgets using a Grid Layout
        # Create a new grid layout
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 10)  # Add some bottom spacing
        grid.setSpacing(10)

        # Row 0: Top Left (Province) & Top Right (Municipality + Search)
        # Province
        grid.addWidget(self.label_3, 0, 0)  # Province Label
        grid.addWidget(self.provinceComboBox, 0, 1)

        # Municipality
        grid.addWidget(self.label_4, 0, 2)  # Municipality Label
        grid.addWidget(self.municipalityInput, 0, 3)

        # Search Button (Keep it accessible in the top row)
        grid.addWidget(self.searchButton, 0, 4)

        # Row 1: Lower Left (Name) & Lower Right (Description)
        # Name
        grid.addWidget(self.label, 1, 0)  # Name Label
        grid.addWidget(self.nameInput, 1, 1)

        # Description
        grid.addWidget(self.label_2, 1, 2)  # Description Label
        grid.addWidget(self.descriptionInput, 1, 3, 1, 2)  # Span 2 columns to align with search button edge

        # Remove the old horizontal layouts from the main vertical layout
        # Note: The widgets are automatically reparented to the grid when added,
        # so the old layouts are now empty. We just need to remove them.

        # The .ui file has 'verticalLayout' containing:
        # 0: horizontalLayout (Name, Desc)
        # 1: horizontalLayout_2 (Prov, Muni, Search)
        # 2: tiePointTable

        # Remove the first two items (the old layouts)
        item0 = self.verticalLayout.takeAt(0)  # horizontalLayout
        item1 = self.verticalLayout.takeAt(0)  # Now horizontalLayout_2 is at 0

        # Delete the old layout objects to clean up
        if item0.layout():
            item0.layout().deleteLater()
        if item1.layout():
            item1.layout().deleteLater()

        # Insert the new grid layout at the top
        self.verticalLayout.insertLayout(0, grid)

        # 3. Add the correction-report button on the left of the button row
        # (horizontalLayout_3 = [spacer, Select, Cancel] from the .ui file)
        self.reportButton = QPushButton("Report Correction…")
        self.reportButton.setToolTip(
            "Send corrected coordinates for the selected tie point to the "
            "developer (requires internet)")
        self.horizontalLayout_3.insertWidget(0, self.reportButton)

    def get_selected_row(self):
        """Return the selected tie point data"""
        return getattr(self, 'selected_row', None)
