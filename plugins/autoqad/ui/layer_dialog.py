# -*- coding: utf-8 -*-
"""The Layer Manager — AutoCAD's layer table, in QGIS.

CAD layers are attributes rather than QGIS layers, so the QGIS layer tree
cannot express them: it has no notion of freeze, lock, a plot flag, an ACI
colour, a linetype or a lineweight. This dialog is where those live.

Editing a layer's colour, linetype or lineweight triggers exactly one bounded
refresh — :meth:`DrawingDocument.restyle_layer` recomputes the denormalised
render fields for that layer's entities and nothing else. That is the explicit
write that keeps the fast render path honest.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from qgis.PyQt.QtGui import QColor

from ..style import aci, cad_layer, linetypes, lineweights
from . import theme
from .icons import swatch_pixmap

COLUMNS = ("Name", "On", "Freeze", "Lock", "Plot", "Colour", "Linetype",
           "Lineweight")

COL_NAME, COL_ON, COL_FREEZE, COL_LOCK, COL_PLOT, COL_COLOUR, \
    COL_LINETYPE, COL_LINEWEIGHT = range(len(COLUMNS))


class LayerManagerDialog(QDialog):
    """Create, delete and configure the drawing's CAD layers."""

    def __init__(self, document, variables, parent=None):
        super().__init__(parent)
        self.document = document
        self.variables = variables
        self._loading = False

        self.setWindowTitle("Layer Manager")
        self.resize(820, 460)
        self._build()
        theme.apply(self)
        self.reload()

    # ---- construction ----

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.new_button = QPushButton("New layer", self)
        self.new_button.clicked.connect(self._new_layer)
        toolbar.addWidget(self.new_button)

        self.delete_button = QPushButton("Delete", self)
        self.delete_button.setProperty("variant", "secondary")
        self.delete_button.clicked.connect(self._delete_layer)
        toolbar.addWidget(self.delete_button)

        self.current_button = QPushButton("Set current", self)
        self.current_button.setProperty("variant", "secondary")
        self.current_button.clicked.connect(self._set_current)
        toolbar.addWidget(self.current_button)

        toolbar.addStretch(1)

        self.current_label = QLabel("", self)
        self.current_label.setProperty("role", "muted")
        toolbar.addWidget(self.current_label)

        layout.addLayout(toolbar)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME,
                                    QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(COLUMNS)):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    # ---- population ----

    def reload(self):
        self._loading = True
        try:
            layers = self.document.layers.all()
            self.table.setRowCount(len(layers))
            for row, layer in enumerate(layers):
                self._populate_row(row, layer)
        finally:
            self._loading = False
        self.current_label.setText(
            "Current layer: {0}".format(self.document.layers.current_name))

    def _populate_row(self, row, layer):
        name_item = QTableWidgetItem(layer.name)
        if layer.is_default:
            name_item.setFlags(name_item.flags()
                               & ~Qt.ItemFlag.ItemIsEditable)
        if layer.name == self.document.layers.current_name:
            font = name_item.font()
            font.setBold(True)
            name_item.setFont(font)
        self.table.setItem(row, COL_NAME, name_item)

        self._set_check(row, COL_ON, layer.on)
        self._set_check(row, COL_FREEZE, layer.frozen)
        self._set_check(row, COL_LOCK, layer.locked)
        self._set_check(row, COL_PLOT, layer.plottable)

        colour_item = QTableWidgetItem(aci.name(layer.color))
        colour_item.setFlags(colour_item.flags()
                             & ~Qt.ItemFlag.ItemIsEditable)
        colour_item.setIcon(
            self._colour_icon(layer.hex_color(theme.background_is_dark())))
        self.table.setItem(row, COL_COLOUR, colour_item)

        self.table.setCellWidget(
            row, COL_LINETYPE, self._linetype_combo(row, layer))
        self.table.setCellWidget(
            row, COL_LINEWEIGHT, self._lineweight_combo(row, layer))

    @staticmethod
    def _colour_icon(hex_colour):
        from qgis.PyQt.QtGui import QIcon
        return QIcon(swatch_pixmap(hex_colour, 14))

    def _set_check(self, row, column, checked):
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable
                      | Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(Qt.CheckState.Checked if checked
                           else Qt.CheckState.Unchecked)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, column, item)

    def _linetype_combo(self, row, layer):
        combo = QComboBox(self.table)
        names = linetypes.names(self.document.linetype_table)
        combo.addItems(names)
        if layer.linetype in names:
            combo.setCurrentIndex(names.index(layer.linetype))
        combo.currentTextChanged.connect(
            lambda value, r=row: self._set_linetype(r, value))
        return combo

    def _lineweight_combo(self, row, layer):
        combo = QComboBox(self.table)
        for label, value in lineweights.choices(include_sentinels=False):
            combo.addItem(label, value)
        combo.addItem(lineweights.label(lineweights.DEFAULT),
                      lineweights.DEFAULT)
        index = combo.findData(layer.lineweight)
        if index >= 0:
            combo.setCurrentIndex(index)
        combo.currentIndexChanged.connect(
            lambda _index, r=row, c=combo: self._set_lineweight(
                r, c.currentData()))
        return combo

    # ---- editing ----

    def _layer_at(self, row):
        item = self.table.item(row, COL_NAME)
        if item is None:
            return None
        return self.document.layers.get(item.text())

    def _selected_layer(self):
        row = self.table.currentRow()
        return self._layer_at(row) if row >= 0 else None

    def _on_item_changed(self, item):
        if self._loading:
            return
        row = item.row()
        column = item.column()

        if column == COL_NAME:
            self._rename(row, item.text())
            return

        layer = self._layer_at(row)
        if layer is None:
            return

        checked = item.checkState() == Qt.CheckState.Checked
        if column == COL_ON:
            layer.on = checked
        elif column == COL_FREEZE:
            if checked and layer.name == self.document.layers.current_name:
                QMessageBox.information(
                    self, "Layer Manager",
                    "The current layer cannot be frozen.")
                self.reload()
                return
            layer.frozen = checked
        elif column == COL_LOCK:
            layer.locked = checked
        elif column == COL_PLOT:
            layer.plottable = checked
        else:
            return

        self._commit()

    def _rename(self, row, new_name):
        layer = self.document.layers.all()[row] if row < len(
            self.document.layers) else None
        if layer is None:
            return
        if layer.name == new_name:
            return

        resolved = self.document.layers.rename(layer.name, new_name)
        if resolved is None:
            QMessageBox.warning(
                self, "Layer Manager",
                "'{0}' is not a valid or available layer name.".format(
                    new_name))
            self.reload()
            return

        # Entities carry the layer name, so they must follow the rename.
        self._rename_entities(layer.name, resolved)
        self._commit()

    def _rename_entities(self, old_name, new_name):
        expression = '"aq_layer" = \'{0}\''.format(old_name.replace("'", "''"))
        for table in self.document.all_tables():
            index = table.fields().indexOf("aq_layer")
            if index < 0:
                continue
            updates = {f.id(): {index: new_name}
                       for f in table.getFeatures(expression)}
            if updates:
                table.dataProvider().changeAttributeValues(updates)

    def _on_double_click(self, row, column):
        if column != COL_COLOUR:
            return
        layer = self._layer_at(row)
        if layer is None:
            return

        initial = QColor(layer.hex_color(theme.background_is_dark()))
        chosen = QColorDialog.getColor(initial, self, "Select layer colour")
        if not chosen.isValid():
            return
        layer.color = aci.nearest_index(chosen.red(), chosen.green(),
                                        chosen.blue())
        self._restyle(layer.name)

    def _set_linetype(self, row, value):
        if self._loading:
            return
        layer = self._layer_at(row)
        if layer is None:
            return
        layer.linetype = str(value).upper()
        self._restyle(layer.name)

    def _set_lineweight(self, row, value):
        if self._loading or value is None:
            return
        layer = self._layer_at(row)
        if layer is None:
            return
        layer.lineweight = int(value)
        self._restyle(layer.name)

    # ---- actions ----

    def _new_layer(self):
        base = "Layer"
        index = 1
        while "{0}{1}".format(base, index) in self.document.layers:
            index += 1
        name = "{0}{1}".format(base, index)

        self.document.layers.add(cad_layer.CadLayer(name))
        self._commit()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_NAME)
            if item is not None and item.text() == name:
                self.table.setCurrentCell(row, COL_NAME)
                self.table.editItem(item)
                break

    def _delete_layer(self):
        layer = self._selected_layer()
        if layer is None:
            return
        if layer.is_default:
            QMessageBox.information(self, "Layer Manager",
                                    "Layer '0' cannot be deleted.")
            return

        count = self._entity_count(layer.name)
        if count:
            answer = QMessageBox.question(
                self, "Layer Manager",
                "Layer '{0}' holds {1} object(s).\n\n"
                "Delete the layer and everything on it?".format(
                    layer.name, count),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._delete_entities(layer.name)

        self.document.layers.remove(layer.name)
        self._commit()

    def _entity_count(self, name):
        expression = '"aq_layer" = \'{0}\''.format(name.replace("'", "''"))
        return sum(len(list(table.getFeatures(expression)))
                   for table in self.document.all_tables())

    def _delete_entities(self, name):
        expression = '"aq_layer" = \'{0}\''.format(name.replace("'", "''"))
        for table in self.document.all_tables():
            ids = [f.id() for f in table.getFeatures(expression)]
            if ids:
                table.dataProvider().deleteFeatures(ids)

    def _set_current(self):
        layer = self._selected_layer()
        if layer is None:
            return
        if layer.frozen:
            QMessageBox.information(self, "Layer Manager",
                                    "A frozen layer cannot be made current.")
            return
        self.document.layers.set_current(layer.name)
        self.variables.set("CLAYER", layer.name)
        self._commit()

    # ---- persistence ----

    def _restyle(self, layer_name):
        self.document.restyle_layer(layer_name)
        self._commit()

    def _commit(self):
        self.document.apply_renderers()
        self.document.save_state()
        self.document.refresh()
        self.reload()
