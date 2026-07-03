# coding=utf-8
"""Tests for ListElement sorting by a configured field."""
import unittest

from utilities import get_qgis_app
from bus import DashboardBus
from elements import create_element

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


def _layer():
    from qgis.core import QgsVectorLayer, QgsFeature, QgsProject
    lyr = QgsVectorLayer("None?field=name:string&field=area:double",
                         "parcels", "memory")
    feats = []
    for name, area in [("B", 20.0), ("A", 5.0), ("C", 12.0)]:
        ft = QgsFeature(lyr.fields())
        ft.setAttributes([name, area])
        feats.append(ft)
    lyr.dataProvider().addFeatures(feats)
    lyr.updateExtents()
    QgsProject.instance().addMapLayer(lyr)
    return lyr


def _col_values(table, col):
    return [table.item(r, col).text() for r in range(table.rowCount())]


class ListSortTest(unittest.TestCase):
    def _list(self, extra):
        lyr = _layer()
        cfg = {"layer_id": lyr.id(), "display_fields": ["name", "area"]}
        cfg.update(extra)
        return create_element("list", DashboardBus(IFACE), cfg, PARENT)

    def test_sort_ascending_by_area(self):
        el = self._list({"sort_field": "area", "sort_dir": "asc"})
        self.assertEqual(_col_values(el.table, 0), ["A", "C", "B"])

    def test_sort_descending_by_area(self):
        el = self._list({"sort_field": "area", "sort_dir": "desc"})
        self.assertEqual(_col_values(el.table, 0), ["B", "C", "A"])

    def test_unknown_field_leaves_order_unsorted(self):
        el = self._list({"sort_field": "nope", "sort_dir": "asc"})
        self.assertEqual(len(_col_values(el.table, 0)), 3)   # no crash


if __name__ == "__main__":
    unittest.main()
