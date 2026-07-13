# -*- coding: utf-8 -*-
"""Pure tests for auto_layout.compute_auto_layout (no QGIS needed).

Run directly (the test package __init__ imports qgis):
    PYTHONPATH=$(pwd) python test/test_auto_layout.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_layout import compute_auto_layout, shape_for  # noqa: E402


def _overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _assert_exact_tiling(test, rects, W, H):
    area = 0
    for (x, y, w, h) in rects:
        test.assertGreaterEqual(x, 0)
        test.assertGreaterEqual(y, 0)
        test.assertGreater(w, 0)
        test.assertGreater(h, 0)
        test.assertLessEqual(x + w, W)
        test.assertLessEqual(y + h, H)
        area += w * h
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            test.assertFalse(_overlap(rects[i], rects[j]),
                             "tiles %d and %d overlap" % (i, j))
    test.assertEqual(area, W * H)   # no gap, no spill


class AutoLayoutTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(compute_auto_layout([], 800, 600), [])

    def test_single_fills_page(self):
        self.assertEqual(
            compute_auto_layout([("chart", "bar")], 800, 600),
            [(0, 0, 800, 600)])

    def test_exact_tiling_mixed(self):
        items = [("header", None), ("indicator", None), ("indicator", None),
                 ("map", None), ("chart", "line"), ("chart", "pie"),
                 ("list", None)]
        W, H = 1280, 720
        rects = compute_auto_layout(items, W, H)
        self.assertEqual(len(rects), len(items))
        _assert_exact_tiling(self, rects, W, H)

    def test_indicators_equal_and_adjacent(self):
        items = [("indicator", None), ("indicator", None), ("indicator", None)]
        W, H = 900, 300
        rects = compute_auto_layout(items, W, H)
        _assert_exact_tiling(self, rects, W, H)
        # all same height, same width (±1px rounding), laid left to right
        ys = {r[1] for r in rects}
        hs = {r[3] for r in rects}
        self.assertEqual(len(ys), 1)
        self.assertEqual(len(hs), 1)
        widths = sorted(r[2] for r in rects)
        self.assertLessEqual(widths[-1] - widths[0], 1)
        xs = sorted(r[0] for r in rects)
        self.assertEqual(xs[0], 0)
        # adjacency: each next x equals previous x + width
        ordered = sorted(rects, key=lambda r: r[0])
        for a, b in zip(ordered, ordered[1:]):
            self.assertEqual(b[0], a[0] + a[2])

    def test_map_is_biggest(self):
        items = [("indicator", None), ("map", None),
                 ("chart", "bar"), ("chart", "donut"), ("list", None)]
        W, H = 1280, 720
        rects = compute_auto_layout(items, W, H)
        _assert_exact_tiling(self, rects, W, H)
        map_rect = rects[1]
        map_area = map_rect[2] * map_rect[3]
        for k, r in enumerate(rects):
            if k == 1:
                continue
            self.assertGreaterEqual(map_area, r[2] * r[3],
                                    "map should be the biggest tile")

    def test_list_is_portrait(self):
        items = [("list", None), ("list", None)]
        W, H = 600, 800
        rects = compute_auto_layout(items, W, H)
        _assert_exact_tiling(self, rects, W, H)
        for r in rects:
            self.assertGreater(r[3], r[2], "list tiles should be portrait")

    def test_shape_for_rules(self):
        self.assertEqual(shape_for("map")[1], 3.0)           # heaviest
        self.assertLess(shape_for("list")[0], 1.0)           # portrait
        self.assertEqual(shape_for("chart", "pie")[0], 1.0)  # square
        self.assertGreater(shape_for("chart", "line")[0], 1.0)  # wide

    def test_indicators_wrap_to_two_rows(self):
        items = [("indicator", None)] * 7
        W, H = 1400, 360
        rects = compute_auto_layout(items, W, H)
        _assert_exact_tiling(self, rects, W, H)
        ys = sorted({r[1] for r in rects})
        self.assertEqual(len(ys), 2, "7 indicators should wrap to two rows")
        # each row's cells are equal width and adjacent
        for row_y in ys:
            row = sorted(
                (r for r in rects if r[1] == row_y),
                key=lambda r: r[0])
            widths = [r[2] for r in row]
            self.assertLessEqual(max(widths) - min(widths), 1)
            for a, b in zip(row, row[1:]):
                self.assertEqual(b[0], a[0] + a[2])


if __name__ == "__main__":
    unittest.main()
