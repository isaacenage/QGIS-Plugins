# -*- coding: utf-8 -*-
"""Unit tests for layout_util (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_layout_util.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from layout_util import default_locked, region_scale_factor, scale_rect  # noqa: E402


class TestDefaultLocked(unittest.TestCase):
    def test_empty_blob_is_unlocked(self):
        self.assertFalse(default_locked({}))

    def test_pages_with_no_elements_is_unlocked(self):
        blob = {"pages": [{"id": "a", "elements": []},
                          {"id": "b", "elements": []}]}
        self.assertFalse(default_locked(blob))

    def test_any_page_with_elements_is_locked(self):
        blob = {"pages": [{"id": "a", "elements": []},
                          {"id": "b", "elements": [{"__type__": "chart"}]}]}
        self.assertTrue(default_locked(blob))

    def test_first_page_with_elements_is_locked(self):
        blob = {
            "pages": [{"id": "a", "elements": [{"__type__": "indicator"}]}]}
        self.assertTrue(default_locked(blob))


class TestRegionScaleFactor(unittest.TestCase):
    def test_identity_when_unchanged(self):
        self.assertEqual(region_scale_factor(1280, 720, 1280, 720), 1.0)

    def test_same_aspect_halving(self):
        # both axes halve -> uniform 0.5
        self.assertAlmostEqual(region_scale_factor(1280, 720, 640, 360), 0.5)

    def test_same_aspect_doubling(self):
        self.assertAlmostEqual(region_scale_factor(640, 360, 1280, 720), 2.0)

    def test_aspect_change_uses_min_ratio(self):
        # 1280x720 -> A4 portrait 2480x3508: sx=1.9375, sy=4.872 -> min (fit)
        f = region_scale_factor(1280, 720, 2480, 3508)
        self.assertAlmostEqual(f, 2480 / 1280.0)

    def test_zero_old_dims_do_not_divide_by_zero(self):
        # floored at 1; just assert it returns a finite number
        self.assertTrue(region_scale_factor(0, 0, 100, 100) > 0)

    def test_scaled_tiles_always_fit_new_region(self):
        # the fit factor must keep every tile inside the new region for any
        # aspect-ratio change, so nothing is ever cropped on export.
        old = (1280, 720)
        tiles = [(0, 0, 1280, 720), (1000, 600, 280, 120), (640, 0, 640, 720)]
        for new in [(640, 360), (1920, 1080), (2480, 3508), (3508, 2480),
                    (320, 2000), (2000, 320)]:
            f = region_scale_factor(old[0], old[1], new[0], new[1])
            for rect in tiles:
                x, y, w, h = scale_rect(rect, f)
                self.assertLessEqual(x + w, new[0] + 1,   # +1 px rounding slack
                                     "%r overflows width of %r" % (rect, new))
                self.assertLessEqual(y + h, new[1] + 1,
                                     "%r overflows height of %r" % (rect, new))


class TestScaleRect(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(scale_rect((10, 20, 100, 80), 1.0), (10, 20, 100, 80))

    def test_uniform_scaling_preserves_aspect(self):
        x, y, w, h = scale_rect((10, 20, 100, 80), 2.0)
        self.assertEqual((x, y, w, h), (20, 40, 200, 160))
        self.assertAlmostEqual(w / float(h), 100 / 80.0)   # aspect kept

    def test_rounding(self):
        self.assertEqual(scale_rect((3, 3, 3, 3), 0.5), (2, 2, 2, 2))

    def test_width_height_floored_at_one(self):
        x, y, w, h = scale_rect((0, 0, 2, 2), 0.01)
        self.assertEqual((w, h), (1, 1))


if __name__ == "__main__":
    unittest.main()
