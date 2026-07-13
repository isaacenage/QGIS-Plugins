# -*- coding: utf-8 -*-
"""Pivot / matrix element.

A cross-tab tile: group features by a row field and an optional column field,
aggregate a value field per cell (count/sum/mean/min/max), with grand totals.
Built on the pandas-free :mod:`pivot_engine`.

It is both a target (recomputes under the dashboard filter) and a SOURCE:
clicking a data cell pushes ``"rowfield = r AND colfield = c"`` onto the bus;
clicking a row's header cell filters by that row value only; clicking a column
header filters by that column value only. Clicking the same target again clears.
"""

from qgis.PyQt.QtWidgets import (
    QTableWidget, QTableWidgetItem, QAbstractItemView,
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import Qt

from .base import DashboardElement
from .pivot_engine import compute_pivot, NULL_KEY
from .chart_specs import filter_literal
from .table_style import table_qss

TOTAL_LABEL = "Total"


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        if v == int(v):
            return "{:,}".format(int(v))
        return "{:,.2f}".format(v)
    if isinstance(v, int):
        return "{:,}".format(v)
    return str(v)


class PivotElement(DashboardElement):
    type_name = "pivot"
    is_filter_source = True
    accepts_filter = True

    def __init__(self, bus, config=None, parent=None):
        super().__init__(bus, config, parent)
        self.table = QTableWidget()
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self._on_cell)
        self.table.horizontalHeader().sectionClicked.connect(self._on_header)
        self.body.addWidget(self.table)
        self._result = None
        self._selected = None   # the active filter key tuple, for toggle
        self.apply_theme()
        self.refresh()

    def _restyle(self):
        self.table.setStyleSheet(table_qss(self, self.effective_theme(),
                                           selection=False))

    # ---- data ----

    def refresh(self):
        cfg = self.config
        show_totals = cfg.get("show_totals", True)
        result = compute_pivot(
            self.iter_features(),
            row_field=cfg.get("row_field"),
            col_field=cfg.get("col_field") or None,
            value_field=cfg.get("value_field"),
            statistic=cfg.get("statistic", "count"),
            max_rows=int(self.style_get("rows_shown", 50) or 50),
            max_cols=int(self.style_get("cols_shown", 20) or 20),
        )
        self._result = result
        self._populate(result, show_totals)

    def _populate(self, result, show_totals):
        t = self.table
        t.clear()
        show_totals = show_totals and bool(result.row_keys)
        has_cols = bool(result.col_keys)
        value_header = (self.config.get("statistic", "count").title()
                        if not has_cols else None)

        # columns: [row field] + (col keys | single value col) + [Total?]
        headers = [result.row_field or "(rows)"]
        if has_cols:
            headers += list(result.col_keys)
        else:
            headers.append(value_header)
        totals_col = has_cols and show_totals
        if totals_col:
            headers.append(TOTAL_LABEL)
        t.setColumnCount(len(headers))
        t.setHorizontalHeaderLabels(headers)

        n_rows = len(result.row_keys) + (1 if show_totals else 0)
        t.setRowCount(n_rows)

        for r, rk in enumerate(result.row_keys):
            t.setItem(r, 0, self._cell_item(rk, header=True))
            if has_cols:
                for c, ck in enumerate(result.col_keys):
                    val = result.cells.get((rk, ck))
                    t.setItem(r, c + 1, self._cell_item(_fmt(val)))
                if totals_col:
                    t.setItem(r, len(result.col_keys) + 1,
                              self._cell_item(_fmt(result.row_totals.get(rk)),
                                              bold=True))
            else:
                t.setItem(
                    r, 1, self._cell_item(
                        _fmt(
                            result.row_totals.get(rk))))

        if show_totals:
            tr = len(result.row_keys)
            t.setItem(tr, 0, self._cell_item(TOTAL_LABEL, bold=True))
            if has_cols:
                for c, ck in enumerate(result.col_keys):
                    t.setItem(tr, c + 1,
                              self._cell_item(_fmt(result.col_totals.get(ck)),
                                              bold=True))
                if totals_col:
                    t.setItem(tr, len(result.col_keys) +
                              1, self._cell_item(_fmt(result.grand_total), bold=True))
            else:
                t.setItem(tr, 1,
                          self._cell_item(_fmt(result.grand_total), bold=True))

        t.resizeColumnsToContents()

    def _cell_item(self, text, bold=False, header=False):
        item = QTableWidgetItem(text)
        if bold or header:
            f = item.font()
            f.setBold(True)
            if bold:   # a totals cell — honor the Totals appearance role
                weight = int(self.style_get("total_weight", 700))
                f.setBold(weight >= 600)
                item.setForeground(QColor(self.style_get(
                    "total_color", self.effective_theme().text)))
            item.setFont(f)
        if header:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        else:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return item

    # ---- interactivity (source) ----

    def _on_filters_cleared(self):
        self._selected = None

    def _is_total_row(self, row):
        res = self._result
        return res is not None and row >= len(res.row_keys)

    def _on_cell(self, row, col):
        if not self._interactive:   # Build mode: clicks don't cross-filter
            return
        res = self._result
        if res is None or self._is_total_row(row):
            return
        if row >= len(res.row_keys):
            return
        row_key = res.row_keys[row]
        row_field = self.config.get("row_field")
        has_cols = bool(res.col_keys)

        if col == 0:
            # row header cell -> filter by row value only
            self._toggle(("row", row_key),
                         self._row_expr(row_field, row_key))
        elif has_cols and 1 <= col <= len(res.col_keys):
            col_key = res.col_keys[col - 1]
            col_field = self.config.get("col_field")
            self._toggle(("cell", row_key, col_key),
                         self._cell_expr(row_field, row_key,
                                         col_field, col_key))
        elif not has_cols and col == 1:
            self._toggle(("row", row_key),
                         self._row_expr(row_field, row_key))
        # clicks on a Total column do nothing

    def _on_header(self, idx):
        if not self._interactive:   # Build mode: clicks don't cross-filter
            return
        res = self._result
        if res is None or not res.col_keys:
            return
        if 1 <= idx <= len(res.col_keys):
            col_key = res.col_keys[idx - 1]
            col_field = self.config.get("col_field")
            self._toggle(("col", col_key),
                         self._row_expr(col_field, col_key))

    def _toggle(self, key, expr):
        if expr is None:
            return
        if self._selected == key:
            self._selected = None
            self.bus.set_filter(self.id, None)
        else:
            self._selected = key
            self.bus.set_filter(self.id, expr)

    @staticmethod
    def _row_expr(field, key):
        if not field or key == NULL_KEY:
            return None
        return filter_literal(field, key)

    def _cell_expr(self, row_field, row_key, col_field, col_key):
        a = self._row_expr(row_field, row_key)
        b = self._row_expr(col_field, col_key)
        if a is None or b is None:
            return None
        return "({}) AND ({})".format(a, b)
