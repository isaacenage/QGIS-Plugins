# -*- coding: utf-8 -*-
"""Unit tests for elements/chart_data (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_chart_data.py

chart_data.py only imports from ``collections``, so it is imported standalone
(via the ``elements`` dir on the path) to avoid loading elements/__init__,
which pulls in qgis.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "elements"))

import chart_data  # noqa: E402


class TestAggregateSeries(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"region": "N", "year": "2020", "sales": 10},
            {"region": "N", "year": "2021", "sales": 20},
            {"region": "S", "year": "2020", "sales": 5},
            {"region": "S", "year": "2021", "sales": 7},
            {"region": "N", "year": "2020", "sales": 3},
        ]

    def test_sum_matrix(self):
        out = chart_data.aggregate_series(
            self.rows, "region", "year", "sales", "sum")
        self.assertEqual(set(out["categories"]), {"N", "S"})
        self.assertEqual(set(out["series"]), {"2020", "2021"})
        # N total (10+20+3=33) > S total (12) -> N ordered first
        self.assertEqual(out["categories"][0], "N")
        n_i = out["categories"].index("N")
        y2020 = out["series"].index("2020")
        self.assertEqual(out["matrix"][n_i][y2020], 13)   # 10 + 3

    def test_count_stat(self):
        out = chart_data.aggregate_series(
            self.rows, "region", "year", None, "count")
        n_i = out["categories"].index("N")
        y2020 = out["series"].index("2020")
        self.assertEqual(out["matrix"][n_i][y2020], 2)

    def test_missing_fields_empty(self):
        out = chart_data.aggregate_series(
            self.rows, None, "year", "sales", "sum")
        self.assertEqual(out, {"categories": [], "series": [], "matrix": []})

    def test_category_cap(self):
        rows = [{"c": str(i), "s": "x", "v": i} for i in range(20)]
        out = chart_data.aggregate_series(
            rows, "c", "s", "v", "sum", cat_cap=5)
        self.assertEqual(len(out["categories"]), 5)


class TestCollectPoints(unittest.TestCase):
    def test_xy(self):
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}, {"a": "x", "b": 5}]
        out = chart_data.collect_points(rows, "a", "b")
        self.assertEqual(out, [(1.0, 2.0, ""), (3.0, 4.0, "")])

    def test_xyz_drops_missing_size(self):
        rows = [{"a": 1, "b": 2, "s": 9}, {"a": 3, "b": 4, "s": None}]
        out = chart_data.collect_points(rows, "a", "b", "s")
        self.assertEqual(out, [(1.0, 2.0, 9.0, "")])

    def test_cap(self):
        rows = [{"a": i, "b": i} for i in range(100)]
        out = chart_data.collect_points(rows, "a", "b", cap=10)
        self.assertEqual(len(out), 10)


class TestHistogram(unittest.TestCase):
    def test_basic_bins(self):
        vals = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        out = chart_data.histogram_bins(vals, 5)
        self.assertEqual(len(out), 5)
        total = sum(c for _, c, _, _ in out)
        self.assertEqual(total, len(vals))     # every value counted once
        # max value (10) lands in the last bin, not a 6th overflow bin
        self.assertEqual(out[-1][1], 3)        # 8, 9, 10

    def test_degenerate_single_value(self):
        out = chart_data.histogram_bins([5, 5, 5], 4)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][1], 3)

    def test_empty(self):
        self.assertEqual(chart_data.histogram_bins([None, "x"], 5), [])


class TestOhlc(unittest.TestCase):
    def test_aggregation(self):
        rows = [
            {"d": "Mon", "o": 10, "h": 12, "l": 9, "c": 11},
            {"d": "Mon", "o": 11, "h": 15, "l": 8, "c": 14},
            {"d": "Tue", "o": 14, "h": 16, "l": 13, "c": 15},
        ]
        out = chart_data.aggregate_ohlc(rows, "d", "o", "h", "l", "c")
        self.assertEqual(out[0][0], "Mon")
        # open = first (10), high = max (15), low = min (8), close = last (14)
        self.assertEqual(out[0], ("Mon", 10.0, 15.0, 8.0, 14.0))
        self.assertEqual(out[1], ("Tue", 14.0, 16.0, 13.0, 15.0))

    def test_skips_non_numeric(self):
        rows = [{"d": "Mon", "o": "x", "h": 1, "l": 0, "c": 1}]
        self.assertEqual(
            chart_data.aggregate_ohlc(
                rows, "d", "o", "h", "l", "c"), [])


class TestSquarify(unittest.TestCase):
    def test_areas_proportional(self):
        rects = chart_data.squarify([4, 2, 2], 0, 0, 100, 100)
        self.assertEqual(len(rects), 3)
        areas = [rw * rh for _i, _x, _y, rw, rh in rects]
        # first value is twice the others -> roughly twice the area
        self.assertAlmostEqual(areas[0], areas[1] + areas[2], delta=1.0)
        total = sum(areas)
        self.assertAlmostEqual(total, 100 * 100, delta=1.0)

    def test_skips_nonpositive(self):
        rects = chart_data.squarify([5, 0, -3], 0, 0, 50, 50)
        self.assertEqual(len(rects), 1)

    def test_empty(self):
        self.assertEqual(chart_data.squarify([], 0, 0, 10, 10), [])


if __name__ == "__main__":
    unittest.main()
