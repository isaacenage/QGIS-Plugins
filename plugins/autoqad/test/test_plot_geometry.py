# -*- coding: utf-8 -*-
"""Tests for the plot scale and sheet maths.

Runs without QGIS. From the plugin directory::

    python test/test_plot_geometry.py

The module under test lives in the plugin's ``io`` package, whose name shadows
the standard library's. It is loaded straight off disk rather than imported, so
running these tests can never leave a broken ``io`` in ``sys.modules``.
"""

import importlib.util
import os
import sys
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, relative_path):
    path = os.path.join(_PLUGIN_DIR, relative_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pg = _load("aq_plot_geometry", os.path.join("io", "plot_geometry.py"))


class TestSheets(unittest.TestCase):

    def test_sheets_are_stored_portrait(self):
        for candidate in pg.SHEETS:
            self.assertLessEqual(candidate.width, candidate.height,
                                 candidate.name)

    def test_a3_is_a3(self):
        found = pg.sheet("ISO A3")
        self.assertAlmostEqual(found.width, 297.0)
        self.assertAlmostEqual(found.height, 420.0)

    def test_lookup_is_forgiving(self):
        self.assertEqual(pg.sheet("iso a3").name, "ISO A3")
        self.assertEqual(pg.sheet("  A3 ").name, "ISO A3")

    def test_unknown_sheet_falls_back_to_the_default(self):
        self.assertEqual(pg.sheet("B7").name, pg.DEFAULT_SHEET)
        self.assertEqual(pg.sheet(None).name, pg.DEFAULT_SHEET)

    def test_landscape_swaps_the_axes(self):
        self.assertEqual(pg.page_size("ISO A3", landscape=True), (420.0, 297.0))
        self.assertEqual(pg.page_size("ISO A3", landscape=False), (297.0, 420.0))

    def test_frame_subtracts_both_margins(self):
        width, height = pg.frame_size("ISO A3", True, 10.0)
        self.assertAlmostEqual(width, 400.0)
        self.assertAlmostEqual(height, 277.0)

    def test_absurd_margin_is_clamped_not_inverted(self):
        width, height = pg.frame_size("ISO A4", True, 500.0)
        self.assertGreaterEqual(width, pg.MIN_FRAME_MM)
        self.assertGreaterEqual(height, pg.MIN_FRAME_MM)

    def test_negative_margin_is_treated_as_none(self):
        self.assertEqual(pg.frame_size("ISO A3", True, -5.0),
                         pg.frame_size("ISO A3", True, 0.0))

    def test_frame_origin_centres_the_frame(self):
        x, y = pg.frame_origin("ISO A3", True, 10.0)
        self.assertAlmostEqual(x, 10.0)
        self.assertAlmostEqual(y, 10.0)


class TestScale(unittest.TestCase):
    """1 mm on paper at 1:S is S mm on the ground."""

    def test_paper_to_ground(self):
        # 200 mm at 1:500 is 100 m, and the CRS is metric.
        self.assertAlmostEqual(
            pg.paper_mm_to_map_units(200.0, 500.0, 1.0), 100.0)

    def test_ground_to_paper_is_the_inverse(self):
        self.assertAlmostEqual(
            pg.map_units_to_paper_mm(100.0, 500.0, 1.0), 200.0)

    def test_foot_based_crs(self):
        # A foot CRS has ~3.28084 units per metre, so the same paper distance
        # covers proportionally more units.
        units = pg.paper_mm_to_map_units(200.0, 500.0, 3.28084)
        self.assertAlmostEqual(units, 100.0 * 3.28084, places=4)

    def test_millimetre_drawing_units(self):
        # A drawing authored in millimetres: 1000 units per metre, so 1:1 makes
        # one paper millimetre exactly one drawing unit.
        self.assertAlmostEqual(
            pg.paper_mm_to_map_units(1.0, 1.0, 1000.0), 1.0)

    def test_fit_takes_the_binding_axis(self):
        # 100 x 10 into a 200 x 200 frame: width binds.
        scale = pg.fit_scale(100.0, 10.0, 200.0, 200.0, 1.0, padding=0.0)
        self.assertAlmostEqual(scale, 500.0)

    def test_fit_takes_the_binding_axis_vertically(self):
        scale = pg.fit_scale(10.0, 100.0, 200.0, 200.0, 1.0, padding=0.0)
        self.assertAlmostEqual(scale, 500.0)

    def test_fit_padding_enlarges_the_denominator(self):
        tight = pg.fit_scale(100.0, 100.0, 200.0, 200.0, 1.0, padding=0.0)
        padded = pg.fit_scale(100.0, 100.0, 200.0, 200.0, 1.0, padding=0.10)
        self.assertAlmostEqual(padded, tight * 1.10)

    def test_fit_round_trips_through_extent_size(self):
        scale = pg.fit_scale(100.0, 40.0, 200.0, 200.0, 1.0, padding=0.0)
        width, _height = pg.extent_size(200.0, 200.0, scale, 1.0)
        self.assertAlmostEqual(width, 100.0)

    def test_degenerate_inputs_do_not_divide_by_zero(self):
        self.assertEqual(pg.fit_scale(10.0, 10.0, 0.0, 100.0), 1.0)
        self.assertEqual(pg.fit_scale(10.0, 10.0, 100.0, 0.0), 1.0)
        self.assertEqual(pg.fit_scale(0.0, 0.0, 100.0, 100.0), 1.0)
        self.assertEqual(pg.fit_scale(10.0, 10.0, 100.0, 100.0, 0.0), 1.0)


class TestStandardScales(unittest.TestCase):

    def test_list_is_sorted_and_contains_the_classics(self):
        self.assertEqual(list(pg.STANDARD_SCALES), sorted(pg.STANDARD_SCALES))
        for expected in (1.0, 2.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0):
            self.assertIn(expected, pg.STANDARD_SCALES)

    def test_round_up_never_crops(self):
        # Rounding a fit scale up can only pull the drawing further inside the
        # frame; rounding down would clip it.
        self.assertEqual(pg.nearest_standard_scale(432.0), 500.0)
        self.assertEqual(pg.nearest_standard_scale(100.0), 100.0)

    def test_round_nearest_may_go_either_way(self):
        self.assertEqual(pg.nearest_standard_scale(96.0, round_up=False), 100.0)
        self.assertEqual(pg.nearest_standard_scale(104.0, round_up=False), 100.0)

    def test_beyond_the_list_returns_the_largest(self):
        self.assertEqual(pg.nearest_standard_scale(1e9),
                         pg.STANDARD_SCALES[-1])

    def test_non_positive_is_passed_through(self):
        self.assertEqual(pg.nearest_standard_scale(0.0), 0.0)

    def test_formatting(self):
        self.assertEqual(pg.format_scale(100.0), "1:100")
        self.assertEqual(pg.format_scale(1.0), "1:1")
        self.assertEqual(pg.format_scale(0.5), "2:1")
        self.assertEqual(pg.format_scale(0.0), "1:1")


class TestExtents(unittest.TestCase):

    def test_normalise_orders_the_corners(self):
        self.assertEqual(pg.normalise_extent((10.0, 20.0, 0.0, 5.0)),
                         (0.0, 5.0, 10.0, 20.0))

    def test_normalise_rejects_junk(self):
        self.assertIsNone(pg.normalise_extent(None))
        self.assertIsNone(pg.normalise_extent((1.0, 2.0)))
        self.assertIsNone(pg.normalise_extent(("a", "b", "c", "d")))

    def test_centre_and_dimensions(self):
        self.assertEqual(pg.extent_centre((0.0, 0.0, 10.0, 20.0)), (5.0, 10.0))
        self.assertEqual(pg.extent_dimensions((0.0, 0.0, 10.0, 20.0)),
                         (10.0, 20.0))

    def test_centred_extent(self):
        self.assertEqual(pg.centred_extent(5.0, 5.0, 10.0, 4.0),
                         (0.0, 3.0, 10.0, 7.0))

    def test_a_single_point_gets_an_area(self):
        # A drawing holding one point has a zero-area box; plotting it would
        # ask for an infinite scale.
        bounds = pg.ensure_area((5.0, 5.0, 5.0, 5.0))
        width, height = pg.extent_dimensions(bounds)
        self.assertGreater(width, 0.0)
        self.assertGreater(height, 0.0)
        self.assertEqual(pg.extent_centre(bounds), (5.0, 5.0))

    def test_a_horizontal_line_keeps_its_width(self):
        bounds = pg.ensure_area((0.0, 5.0, 10.0, 5.0))
        width, height = pg.extent_dimensions(bounds)
        self.assertAlmostEqual(width, 10.0)
        self.assertGreater(height, 0.0)

    def test_ensure_area_leaves_a_real_extent_alone(self):
        bounds = (0.0, 0.0, 10.0, 20.0)
        self.assertEqual(pg.ensure_area(bounds), bounds)

    def test_inflate_keeps_the_centre(self):
        bounds = pg.inflate((0.0, 0.0, 10.0, 10.0), 0.10)
        self.assertEqual(pg.extent_centre(bounds), (5.0, 5.0))
        self.assertAlmostEqual(pg.extent_dimensions(bounds)[0], 11.0)

    def test_fit_to_aspect_only_grows(self):
        # A tall extent into a wide frame grows horizontally, never shrinks.
        bounds = pg.fit_to_aspect((0.0, 0.0, 10.0, 100.0), 400.0, 200.0)
        width, height = pg.extent_dimensions(bounds)
        self.assertAlmostEqual(height, 100.0)
        self.assertAlmostEqual(width, 200.0)

    def test_fit_to_aspect_grows_vertically_for_a_wide_extent(self):
        bounds = pg.fit_to_aspect((0.0, 0.0, 100.0, 10.0), 200.0, 200.0)
        width, height = pg.extent_dimensions(bounds)
        self.assertAlmostEqual(width, 100.0)
        self.assertAlmostEqual(height, 100.0)

    def test_fit_to_aspect_matches_the_frame_ratio(self):
        bounds = pg.fit_to_aspect((0.0, 0.0, 30.0, 30.0), 400.0, 277.0)
        width, height = pg.extent_dimensions(bounds)
        self.assertAlmostEqual(width / height, 400.0 / 277.0, places=6)


class TestPlotExtent(unittest.TestCase):

    def test_fixed_scale_sizes_the_extent_exactly(self):
        bounds, scale = pg.plot_extent((0.0, 0.0, 10.0, 10.0),
                                       400.0, 200.0, denominator=100.0)
        self.assertAlmostEqual(scale, 100.0)
        width, height = pg.extent_dimensions(bounds)
        self.assertAlmostEqual(width, 40.0)     # 400 mm at 1:100 = 40 m
        self.assertAlmostEqual(height, 20.0)

    def test_fixed_scale_keeps_the_subject_centred(self):
        bounds, _scale = pg.plot_extent((0.0, 0.0, 10.0, 10.0),
                                        400.0, 200.0, denominator=100.0)
        self.assertEqual(pg.extent_centre(bounds), (5.0, 5.0))

    def test_fit_reports_the_scale_it_used(self):
        bounds, scale = pg.plot_extent((0.0, 0.0, 100.0, 50.0),
                                       400.0, 200.0, padding=0.0)
        self.assertAlmostEqual(scale, 250.0)
        width, _height = pg.extent_dimensions(bounds)
        self.assertAlmostEqual(width, 100.0)

    def test_fit_result_matches_the_frame_aspect(self):
        bounds, _scale = pg.plot_extent((0.0, 0.0, 100.0, 5.0),
                                        400.0, 277.0, padding=0.0)
        width, height = pg.extent_dimensions(bounds)
        self.assertAlmostEqual(width / height, 400.0 / 277.0, places=6)

    def test_fit_contains_the_original_extent(self):
        original = (0.0, 0.0, 100.0, 5.0)
        bounds, _scale = pg.plot_extent(original, 400.0, 277.0, padding=0.0)
        self.assertLessEqual(bounds[0], original[0])
        self.assertLessEqual(bounds[1], original[1])
        self.assertGreaterEqual(bounds[2], original[2])
        self.assertGreaterEqual(bounds[3], original[3])

    def test_zero_denominator_falls_back_to_fit(self):
        _bounds, scale = pg.plot_extent((0.0, 0.0, 100.0, 50.0),
                                        400.0, 200.0, denominator=0.0,
                                        padding=0.0)
        self.assertAlmostEqual(scale, 250.0)

    def test_empty_drawing_still_produces_a_plot(self):
        bounds, scale = pg.plot_extent((0.0, 0.0, 0.0, 0.0), 400.0, 200.0)
        self.assertGreater(scale, 0.0)
        width, height = pg.extent_dimensions(bounds)
        self.assertGreater(width, 0.0)
        self.assertGreater(height, 0.0)


if __name__ == "__main__":
    unittest.main()
