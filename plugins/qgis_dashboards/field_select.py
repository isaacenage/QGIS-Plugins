# -*- coding: utf-8 -*-
"""FieldListSelector — a checkable, order-preserving multi-field picker.

Replaces the comma-separated "type the field names" text inputs on the List and
Filter tiles with a real per-layer column picker: it lists the bound layer's
fields as checkable rows and returns the checked ones in layer order. The value
shape (a list of field-name strings) matches the existing ``display_fields`` /
``fields`` config keys, so persistence is unchanged.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QListWidget, QListWidgetItem


class FieldListSelector(QListWidget):
    """Checkable list of a layer's fields; ``selected()`` is in layer order."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layer = None
        self.setUniformItemSizes(True)
        # keep the picker compact inside the narrow inspector panel
        self.setMaximumHeight(160)
        self.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, _item):
        self.changed.emit()

    def set_layer(self, layer):
        checked = set(self.selected())        # preserve by name across relayer
        self._layer = layer
        self.blockSignals(True)
        self.clear()
        if layer is not None:
            for field in layer.fields():
                name = field.name()
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if name in checked
                                   else Qt.CheckState.Unchecked)
                self.addItem(item)
        self.blockSignals(False)

    def set_selected(self, names):
        wanted = set(names or ())
        self.blockSignals(True)
        for i in range(self.count()):
            item = self.item(i)
            item.setCheckState(Qt.CheckState.Checked if item.text() in wanted
                               else Qt.CheckState.Unchecked)
        self.blockSignals(False)

    def selected(self):
        out = []
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                out.append(item.text())
        return out
