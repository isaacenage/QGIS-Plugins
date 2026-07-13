# coding=utf-8
"""Tests for the pure zoom-fit helpers (no QGIS runtime needed).

Run directly so the test package ``__init__`` (which imports qgis) is not
loaded::

    cd qgis_dashboards && PYTHONPATH=$(pwd) python test/test_zoom_fit.py
"""

__author__ = 'isaacenagework@gmail.com'
__date__ = '2026-06-16'
__copyright__ = 'Copyright 2026, Isaac Enage'

import os
import sys
import unittest

# Import the pure helper directly from the plugin dir so the package and
# page_view (which import qgis) are not loaded.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zoom_fit import fit_zoom, clamp_zoom, ZOOM_MIN, ZOOM_MAX, FIT_MARGIN  # noqa: E402


class ClampZoomTest(unittest.TestCase):
    def test_within_range_unchanged(self):
        self.assertAlmostEqual(clamp_zoom(1.0), 1.0)

    def test_floor_and_ceiling(self):
        self.assertAlmostEqual(clamp_zoom(0.001), ZOOM_MIN)
        self.assertAlmostEqual(clamp_zoom(99.0), ZOOM_MAX)


class FitZoomTest(unittest.TestCase):
    """The factor that frames the export/print region in the viewport."""

    def test_region_smaller_than_viewport_scales_up(self):
        # region 600x400 in a 1240x840 viewport (minus 12px margins -> 1216x816)
        # width ratio 2.026, height ratio 2.04 -> width-bound 2.026
        z = fit_zoom((600, 400), (1240, 840))
        self.assertAlmostEqual(z, (1240 - 2 * FIT_MARGIN) / 600.0, places=6)

    def test_height_bound_when_taller(self):
        # tall region: height is the limiting dimension
        z = fit_zoom((400, 1000), (1000, 600))
        self.assertAlmostEqual(z, (600 - 2 * FIT_MARGIN) / 1000.0, places=6)

    def test_large_region_scales_down(self):
        z = fit_zoom((4000, 3000), (1000, 700))
        self.assertLess(z, 1.0)
        self.assertGreaterEqual(z, ZOOM_MIN)

    def test_clamped_to_max(self):
        # tiny region in a big viewport would exceed ZOOM_MAX -> clamped
        self.assertAlmostEqual(fit_zoom((320, 320), (8000, 8000)), ZOOM_MAX)

    def test_degenerate_inputs_fall_back_to_one(self):
        self.assertEqual(fit_zoom((0, 0), (1000, 600)), 1.0)
        self.assertEqual(fit_zoom((600, 400), (0, 0)), 1.0)
        # viewport smaller than twice the margin -> no room, fall back
        self.assertEqual(fit_zoom((600, 400), (10, 10)), 1.0)


if __name__ == "__main__":
    unittest.main()
