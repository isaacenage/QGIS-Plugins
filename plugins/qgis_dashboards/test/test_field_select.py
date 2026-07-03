# coding=utf-8
"""Tests for FieldListSelector (checkable multi-field picker)."""
import unittest

from utilities import get_qgis_app
from field_select import FieldListSelector

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


def _layer():
    from qgis.core import QgsVectorLayer
    return QgsVectorLayer(
        "None?field=owner:string&field=area:double&field=zone:string",
        "parcels", "memory")


class FieldListSelectorTest(unittest.TestCase):
    def test_lists_layer_fields_unchecked(self):
        w = FieldListSelector(PARENT)
        w.set_layer(_layer())
        self.assertEqual(w.selected(), [])

    def test_set_selected_returns_in_layer_order(self):
        w = FieldListSelector(PARENT)
        w.set_layer(_layer())
        w.set_selected(["zone", "owner"])          # input order differs
        self.assertEqual(w.selected(), ["owner", "zone"])   # layer order

    def test_unknown_names_ignored(self):
        w = FieldListSelector(PARENT)
        w.set_layer(_layer())
        w.set_selected(["owner", "nope"])
        self.assertEqual(w.selected(), ["owner"])

    def test_checks_preserved_across_relayer(self):
        w = FieldListSelector(PARENT)
        w.set_layer(_layer())
        w.set_selected(["area"])
        w.set_layer(_layer())                      # same schema, new layer
        self.assertEqual(w.selected(), ["area"])

    def test_none_layer_clears(self):
        w = FieldListSelector(PARENT)
        w.set_layer(_layer())
        w.set_selected(["owner"])
        w.set_layer(None)
        self.assertEqual(w.selected(), [])


if __name__ == "__main__":
    unittest.main()
