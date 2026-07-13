# -*- coding: utf-8 -*-
"""Pure unit tests for tile_snap (no QGIS/Qt).

Run directly so the test package __init__ (which imports qgis) is not loaded:

    cd qgis_dashboards && PYTHONPATH=$(pwd) python test/test_tile_snap.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tile_snap import rects_overlap, snap_rect, nearest_free  # noqa: E402


class TestRectsOverlap(unittest.TestCase):
    def test_clear_overlap(self):
        self.assertTrue(rects_overlap((0, 0, 100, 100), (50, 50, 100, 100)))

    def test_touching_edges_do_not_overlap(self):
        # right edge of A flush against left edge of B
        self.assertFalse(rects_overlap((0, 0, 100, 100), (100, 0, 100, 100)))

    def test_disjoint(self):
        self.assertFalse(rects_overlap((0, 0, 50, 50), (200, 200, 50, 50)))


class TestSnapRect(unittest.TestCase):
    def setUp(self):
        self.region = (1000, 800)

    def test_left_edge_snaps_to_neighbor_right_plus_gap(self):
        # neighbor occupies x:[0,300]; gap=10. A tile near x=305 should snap so
        # its left edge sits at 300+10 = 310.
        other = (0, 0, 300, 200)
        rect = (306, 0, 200, 200)
        snapped = snap_rect(rect, [other], self.region, gap=10, threshold=20)
        self.assertEqual(snapped, (310, 0, 200, 200))

    def test_right_edge_snaps_to_page_edge(self):
        # tile right edge near the region's right edge (1000) snaps flush to
        # it.
        # right edge at 990, within threshold of 1000
        rect = (790, 0, 200, 200)
        snapped = snap_rect(rect, [], self.region, gap=10, threshold=20)
        self.assertEqual(snapped, (800, 0, 200, 200))  # x moved so x+w == 1000

    def test_top_edge_snaps_to_zero(self):
        rect = (400, 6, 200, 200)   # top near page top (0)
        snapped = snap_rect(rect, [], self.region, gap=10, threshold=20)
        self.assertEqual(snapped, (400, 0, 200, 200))

    def test_no_snap_when_outside_threshold(self):
        rect = (500, 500, 100, 100)
        snapped = snap_rect(rect, [], self.region, gap=10, threshold=20)
        self.assertEqual(snapped, (500, 500, 100, 100))

    def test_closer_edge_wins_per_axis(self):
        # left neighbor right+gap = 110; right neighbor left-gap = 690.
        # tile is 100 wide near x=105 -> left edge (105 vs 110, dist 5) wins over
        # right edge (205 vs 690, far). Size unchanged.
        left = (0, 0, 100, 200)      # right=100
        right = (700, 0, 100, 200)   # left=700
        rect = (105, 0, 100, 200)
        snapped = snap_rect(rect, [left, right],
                            self.region, gap=10, threshold=20)
        self.assertEqual(snapped, (110, 0, 100, 200))


class TestNearestFree(unittest.TestCase):
    def setUp(self):
        self.region = (1000, 800)

    def test_returns_input_when_already_free(self):
        rect = (400, 400, 100, 100)
        out = nearest_free(rect, [], self.region, step=8)
        self.assertEqual(out, rect)

    def test_finds_nearby_slot_when_overlapping(self):
        blocker = (300, 300, 200, 200)   # occupies x:[300,500], y:[300,500]
        rect = (320, 320, 100, 100)      # overlaps blocker
        out = nearest_free(rect, [blocker], self.region, step=8)
        self.assertFalse(rects_overlap(out, blocker))
        # same size, in bounds
        self.assertEqual((out[2], out[3]), (100, 100))
        self.assertGreaterEqual(out[0], 0)
        self.assertGreaterEqual(out[1], 0)

    def test_returns_input_when_fully_packed(self):
        # one giant blocker covering the whole region -> nothing free
        blocker = (0, 0, 1000, 800)
        rect = (100, 100, 100, 100)
        out = nearest_free(rect, [blocker], self.region, step=8)
        self.assertEqual(out, rect)


if __name__ == "__main__":
    unittest.main()
