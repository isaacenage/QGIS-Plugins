# -*- coding: utf-8 -*-
"""Unit tests for map_identify pure helpers (no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_map_identify.py
"""
import importlib.util
import os
import unittest

# Load elements/map_identify.py directly by path: importing it via the
# ``elements`` package would pull in elements/__init__, which imports qgis.
_PATH = os.path.join(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__))),
    "elements",
    "map_identify.py")
_spec = importlib.util.spec_from_file_location("map_identify", _PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
search_rect = _mod.search_rect
feature_summary = _mod.feature_summary


class TestSearchRect(unittest.TestCase):
    def test_square_around_point(self):
        self.assertEqual(search_rect(10.0, 20.0, 2.0), (8.0, 18.0, 12.0, 22.0))

    def test_negative_tolerance_degenerates_to_point(self):
        self.assertEqual(search_rect(5.0, 5.0, -3.0), (5.0, 5.0, 5.0, 5.0))


class TestFeatureSummary(unittest.TestCase):
    def test_pairs_names_and_values(self):
        rows = feature_summary(["a", "b"], [1, "x"])
        self.assertEqual(rows, [("a", "1"), ("b", "x")])

    def test_none_renders_empty(self):
        rows = feature_summary(["a", "b"], [None, 2])
        self.assertEqual(rows, [("a", ""), ("b", "2")])

    def test_limit_truncates(self):
        rows = feature_summary(["a", "b", "c"], [1, 2, 3], limit=2)
        self.assertEqual(rows, [("a", "1"), ("b", "2")])

    def test_extra_values_ignored(self):
        rows = feature_summary(["a"], [1, 2, 3])
        self.assertEqual(rows, [("a", "1")])


if __name__ == "__main__":
    unittest.main()
