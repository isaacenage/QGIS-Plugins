# coding=utf-8
"""Tests for the map element's pure extent-filter expression builder.

``elements/map_filter.py`` is Qt/QGIS-free, but it lives inside the ``elements``
package whose ``__init__`` imports QGIS. To keep this test runnable without a
QGIS env (like ``test_html_export.py``), the module is loaded directly from its
file path, bypassing the package import.
"""

import os
import unittest
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_PATH = os.path.join(os.path.dirname(_HERE), "elements", "map_filter.py")
_spec = importlib.util.spec_from_file_location("map_filter", _PATH)
map_filter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(map_filter)


class ExtentWktTest(unittest.TestCase):
    def test_closed_polygon_ring(self):
        wkt = map_filter.extent_wkt(0, 0, 10, 20)
        self.assertTrue(wkt.startswith("POLYGON((") and wkt.endswith("))"))
        coords = wkt[len("POLYGON(("):-2].split(", ")
        self.assertEqual(len(coords), 5)               # 4 corners + closing pt
        self.assertEqual(coords[0], coords[-1])        # ring is closed
        self.assertEqual(coords[0], "0.0 0.0")
        self.assertIn("10.0 0.0", coords)
        self.assertIn("10.0 20.0", coords)
        self.assertIn("0.0 20.0", coords)


class ExtentFilterExpressionTest(unittest.TestCase):
    def test_with_authid_transforms_geometry(self):
        expr = map_filter.extent_filter_expression(0, 0, 1, 1, "EPSG:3857")
        self.assertIn(
            "transform($geometry, layer_property(@layer, 'crs'), 'EPSG:3857')",
            expr)
        self.assertIn("geom_from_wkt('POLYGON((", expr)
        # null/absent geometry passes through (wiring a non-spatial table is a
        # no-op)
        self.assertTrue(expr.startswith("coalesce(intersects("))
        self.assertTrue(expr.endswith("), true)"))

    def test_without_authid_uses_geometry_directly(self):
        expr = map_filter.extent_filter_expression(0, 0, 1, 1, None)
        self.assertNotIn("transform(", expr)
        self.assertIn("intersects($geometry, geom_from_wkt(", expr)


if __name__ == "__main__":
    unittest.main()
