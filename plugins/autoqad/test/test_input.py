# -*- coding: utf-8 -*-
"""Tests for the pure precision-input modules — coordinates and constraints.

Runs without QGIS. From the plugin directory::

    python test/test_input.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from input import coords, ortho_polar   # noqa: E402


class TestCoordinateParsing(unittest.TestCase):

    def test_absolute_cartesian(self):
        parsed = coords.parse("10,20")
        self.assertEqual(parsed.kind, coords.CARTESIAN)
        self.assertFalse(parsed.relative)
        self.assertEqual((parsed.a, parsed.b), (10.0, 20.0))

    def test_relative_cartesian(self):
        parsed = coords.parse("@10,20")
        self.assertEqual(parsed.kind, coords.CARTESIAN)
        self.assertTrue(parsed.relative)

    def test_absolute_polar(self):
        parsed = coords.parse("10<45")
        self.assertEqual(parsed.kind, coords.POLAR)
        self.assertEqual((parsed.a, parsed.b), (10.0, 45.0))

    def test_relative_polar(self):
        parsed = coords.parse("@10<45")
        self.assertEqual(parsed.kind, coords.POLAR)
        self.assertTrue(parsed.relative)

    def test_direct_distance_entry(self):
        parsed = coords.parse("5")
        self.assertEqual(parsed.kind, coords.DISTANCE)
        self.assertTrue(parsed.relative)
        self.assertEqual(parsed.a, 5.0)

    def test_hash_forces_absolute(self):
        parsed = coords.parse("#10,20", default_relative=True)
        self.assertFalse(parsed.relative)

    def test_star_forces_world(self):
        parsed = coords.parse("*10,20")
        self.assertTrue(parsed.world)

    def test_default_relative_mode(self):
        self.assertTrue(coords.parse("10,20", default_relative=True).relative)
        self.assertFalse(coords.parse("10,20").relative)

    def test_whitespace_and_signs(self):
        parsed = coords.parse("  -10.5 , +20 ")
        self.assertEqual((parsed.a, parsed.b), (-10.5, 20.0))

    def test_three_dimensional_input_keeps_z(self):
        parsed = coords.parse("1,2,3")
        self.assertEqual((parsed.a, parsed.b, parsed.z), (1.0, 2.0, 3.0))

    def test_scientific_notation(self):
        parsed = coords.parse("1e3,2e-2")
        self.assertEqual((parsed.a, parsed.b), (1000.0, 0.02))

    def test_non_coordinates_return_none(self):
        # Keywords must not parse as coordinates — the runner relies on this
        # to fall through to option matching.
        for text in ("", "   ", None, "Close", "C", "U", "abc", "10,",
                     ",", "10<", "<45", "10,,20"):
            self.assertIsNone(coords.parse(text),
                              "{0!r} should not parse".format(text))


class TestCoordinateResolution(unittest.TestCase):

    def test_absolute_cartesian_ignores_last_point(self):
        point = coords.parse_and_resolve("10,20", last_point=(5.0, 5.0))
        self.assertEqual(point, (10.0, 20.0))

    def test_relative_cartesian_offsets(self):
        point = coords.parse_and_resolve("@10,20", last_point=(5.0, 5.0))
        self.assertEqual(point, (15.0, 25.0))

    def test_relative_polar_east(self):
        point = coords.parse_and_resolve("@10<0", last_point=(1.0, 1.0))
        self.assertAlmostEqual(point[0], 11.0)
        self.assertAlmostEqual(point[1], 1.0)

    def test_relative_polar_north(self):
        point = coords.parse_and_resolve("@10<90", last_point=(0.0, 0.0))
        self.assertAlmostEqual(point[0], 0.0)
        self.assertAlmostEqual(point[1], 10.0)

    def test_direct_distance_follows_cursor_direction(self):
        # Cursor lies north-east; a typed 10 walks 10 units that way.
        point = coords.parse_and_resolve(
            "10", last_point=(0.0, 0.0), cursor_point=(3.0, 4.0))
        self.assertAlmostEqual(point[0], 6.0)
        self.assertAlmostEqual(point[1], 8.0)

    def test_relative_without_last_point_is_none(self):
        self.assertIsNone(coords.parse_and_resolve("@10,20"))

    def test_direct_distance_without_cursor_is_none(self):
        self.assertIsNone(
            coords.parse_and_resolve("10", last_point=(0.0, 0.0)))

    def test_direct_distance_with_degenerate_cursor_is_none(self):
        self.assertIsNone(coords.parse_and_resolve(
            "10", last_point=(1.0, 1.0), cursor_point=(1.0, 1.0)))

    def test_survey_bearing_frame(self):
        # ANGBASE = 90 (north is zero), ANGDIR clockwise: a bearing of 90
        # degrees points due east.
        point = coords.parse_and_resolve(
            "@10<90", last_point=(0.0, 0.0), angle_base=90.0, clockwise=True)
        self.assertAlmostEqual(point[0], 10.0, places=9)
        self.assertAlmostEqual(point[1], 0.0, places=9)

    def test_survey_bearing_north(self):
        point = coords.parse_and_resolve(
            "@10<0", last_point=(0.0, 0.0), angle_base=90.0, clockwise=True)
        self.assertAlmostEqual(point[0], 0.0, places=9)
        self.assertAlmostEqual(point[1], 10.0, places=9)

    def test_angle_round_trip(self):
        for degrees in (0.0, 45.0, 90.0, 217.5, 359.0):
            radians = coords.to_math_angle(degrees, 90.0, True)
            back = coords.from_math_angle(radians, 90.0, True)
            self.assertAlmostEqual(back, degrees % 360.0, places=9)

    def test_parse_distance_and_angle(self):
        self.assertEqual(coords.parse_distance("12.5"), 12.5)
        self.assertIsNone(coords.parse_distance("Close"))
        self.assertAlmostEqual(coords.parse_angle("90"), math.pi / 2.0)
        self.assertIsNone(coords.parse_angle("Undo"))

    def test_format_point(self):
        self.assertEqual(coords.format_point((1.0, 2.0), precision=2),
                         "1.00,2.00")


class TestOrthoConstraint(unittest.TestCase):

    def test_locks_to_horizontal(self):
        point, angle = ortho_polar.constrain_ortho((0.0, 0.0), (10.0, 2.0))
        self.assertAlmostEqual(point[0], 10.0)
        self.assertAlmostEqual(point[1], 0.0)
        self.assertAlmostEqual(angle, 0.0)

    def test_locks_to_vertical(self):
        point, _ = ortho_polar.constrain_ortho((0.0, 0.0), (2.0, 10.0))
        self.assertAlmostEqual(point[0], 0.0)
        self.assertAlmostEqual(point[1], 10.0)

    def test_locks_to_negative_axis(self):
        point, _ = ortho_polar.constrain_ortho((0.0, 0.0), (-10.0, 1.0))
        self.assertAlmostEqual(point[0], -10.0)
        self.assertAlmostEqual(point[1], 0.0)

    def test_preserves_distance_along_the_axis(self):
        # Ortho keeps the component along the axis, it does not rotate the
        # full cursor distance onto it.
        point, _ = ortho_polar.constrain_ortho((0.0, 0.0), (10.0, 10.0))
        self.assertAlmostEqual(math.hypot(*point), 10.0)

    def test_degenerate_move_returns_base(self):
        point, _ = ortho_polar.constrain_ortho((5.0, 5.0), (5.0, 5.0))
        self.assertEqual(point, (5.0, 5.0))

    def test_rotated_frame(self):
        # With the frame rotated 45 degrees, a cursor at 45 degrees is on-axis.
        point, angle = ortho_polar.constrain_ortho(
            (0.0, 0.0), (10.0, 10.0), angle_base=math.radians(45.0))
        self.assertAlmostEqual(angle % (2 * math.pi), math.radians(45.0))
        self.assertAlmostEqual(point[0], 10.0)
        self.assertAlmostEqual(point[1], 10.0)


class TestPolarConstraint(unittest.TestCase):

    def test_snaps_to_increment(self):
        point, angle = ortho_polar.constrain_polar(
            (0.0, 0.0), (10.0, 9.8), increment_degrees=45.0)
        self.assertAlmostEqual(angle, math.radians(45.0))
        self.assertAlmostEqual(point[0], point[1])

    def test_outside_tolerance_stays_free(self):
        cursor = (10.0, 4.0)          # about 21.8 degrees, far from 0 or 45
        point, angle = ortho_polar.constrain_polar(
            (0.0, 0.0), cursor, increment_degrees=45.0)
        self.assertIsNone(angle)
        self.assertEqual(point, cursor)

    def test_additional_angles_are_honoured(self):
        # 30 degrees is not a multiple of 45, but is offered explicitly.
        cursor = (math.cos(math.radians(30.5)) * 10.0,
                  math.sin(math.radians(30.5)) * 10.0)
        point, angle = ortho_polar.constrain_polar(
            (0.0, 0.0), cursor, increment_degrees=90.0,
            additional_angles=[30.0])
        self.assertIsNotNone(angle)
        self.assertAlmostEqual(math.degrees(angle), 30.0, places=6)
        self.assertAlmostEqual(math.hypot(*point), 10.0, places=3)

    def test_projection_preserves_along_ray_distance(self):
        point, _ = ortho_polar.constrain_polar(
            (0.0, 0.0), (10.0, 10.2), increment_degrees=45.0)
        expected = (10.0 * math.cos(math.radians(45.0))
                    + 10.2 * math.sin(math.radians(45.0)))
        self.assertAlmostEqual(math.hypot(*point), expected, places=6)

    def test_zero_increment_with_no_extras_is_free(self):
        cursor = (3.0, 4.0)
        point, angle = ortho_polar.constrain_polar(
            (0.0, 0.0), cursor, increment_degrees=0.0)
        self.assertIsNone(angle)
        self.assertEqual(point, cursor)

    def test_degenerate_move_returns_base(self):
        point, angle = ortho_polar.constrain_polar((2.0, 2.0), (2.0, 2.0))
        self.assertEqual(point, (2.0, 2.0))
        self.assertIsNone(angle)


class TestApply(unittest.TestCase):

    def test_ortho_beats_polar(self):
        point, _ = ortho_polar.apply(
            (0.0, 0.0), (10.0, 9.0), ortho=True, polar=True)
        self.assertAlmostEqual(point[1], 0.0)

    def test_both_off_passes_through(self):
        cursor = (3.0, 7.0)
        point, angle = ortho_polar.apply((0.0, 0.0), cursor)
        self.assertEqual(point, cursor)
        self.assertIsNone(angle)

    def test_no_base_point_passes_through(self):
        cursor = (3.0, 7.0)
        point, angle = ortho_polar.apply(None, cursor, ortho=True)
        self.assertEqual(point, cursor)
        self.assertIsNone(angle)

    def test_polar_only(self):
        point, angle = ortho_polar.apply(
            (0.0, 0.0), (10.0, 9.9), polar=True, increment_degrees=45.0)
        self.assertIsNotNone(angle)
        self.assertAlmostEqual(point[0], point[1])


class TestHelpers(unittest.TestCase):

    def test_point_at_distance(self):
        point = ortho_polar.point_at_distance((1.0, 1.0), 0.0, 5.0)
        self.assertAlmostEqual(point[0], 6.0)
        self.assertAlmostEqual(point[1], 1.0)

    def test_angle_label(self):
        self.assertEqual(ortho_polar.snap_angle_label(0.0), "0°")
        self.assertEqual(
            ortho_polar.snap_angle_label(math.radians(90.0)), "90°")


if __name__ == "__main__":
    unittest.main(verbosity=2)
