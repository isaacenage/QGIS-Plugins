# -*- coding: utf-8 -*-
"""List element.

ArcGIS list shows features as rows and can be a selector — clicking a row
filters/zooms other elements. Here each row is a feature; selecting a row
emits a featureAction so the map element can zoom/flash to it.
"""

from qgis.PyQt.QtWidgets import QTableWidget, QTableWidgetItem, QAbstractItemView
from .base import DashboardElement
from .table_style import table_qss


class ListElement(DashboardElement):
    type_name = "list"

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_row)
        self.body.addWidget(self.table)
        self._fids = []
        self.apply_theme()
        self.refresh()

    def _restyle(self):
        self.table.setStyleSheet(table_qss(self, self.effective_theme(),
                                           selection=True))

    def refresh(self):
        fields = self.config.get("display_fields", [])
        lyr = self.layer()
        if lyr and not fields:
            fields = [f.name() for f in lyr.fields()][:3]
        self.table.clear()
        self.table.setColumnCount(len(fields))
        self.table.setHorizontalHeaderLabels(fields)
        rows = list(self.iter_features())
        rows = self._sorted(rows)
        limit = int(self.style_get("rows_shown", 200))
        rows = rows[:limit]
        self._fids = [f.id() for f in rows]
        self.table.setRowCount(len(rows))
        for r, feat in enumerate(rows):
            for c, fld in enumerate(fields):
                self.table.setItem(r, c, QTableWidgetItem(str(feat[fld])))
        self.table.resizeColumnsToContents()

    def _sorted(self, rows):
        """Sort feature rows by the configured field; unsorted on any problem."""
        field = self.config.get("sort_field")
        if not field:
            return rows
        lyr = self.layer()
        if lyr is None or lyr.fields().indexOf(field) < 0:
            return rows
        descending = self.config.get("sort_dir", "asc") == "desc"
        try:
            return sorted(
                rows,
                key=lambda f: (f[field] is None, f[field]),
                reverse=descending)
        except TypeError:
            return rows            # uncomparable/mixed types -> leave as-is

    def _on_row(self):
        if not self._interactive:   # Build mode: row selection doesn't act
            return
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        if 0 <= idx < len(self._fids):
            self.bus.featureAction.emit([self._fids[idx]])
