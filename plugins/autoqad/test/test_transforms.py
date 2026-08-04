# -*- coding: utf-8 -*-
"""Tests for the affine transforms and mixed-segment polyline building.

SCALE and MIRROR used to rebuild their result from ``vertices_of`` — which is
fine for a straight polyline and destroys everything else. A circle is stored
as two circular strings, so it has five vertices; scaling it by hand produced
a four-segment scribble. These pin the curve-preserving behaviour.

Needs QGIS on the path. From the plugin directory::

    python test/test_transforms.py
"""

import math
import os
import sys
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))

from qgis.core import QgsApplication, QgsWkbTypes    # noqa: E402

from autoqad.geom import build, construct            # noqa: E402

_APP = QgsApplication([], False)
_APP.initQgis()


def _bbox(geometry):
    box = geometry.boundingBox()
    return (box.xMinimum(), box.yMinimum(), box.xMaximum(), box.yMaximum())


def _close(a, b, tolerance=1e-6):
    return all(abs(x - y) < tolerance for x, y in zip(a, b))


class TestScaled(unittest.TestCase):

    def test_a_circle_stays_a_curve(self):
        circle = build.circle((0.0, 0.0), 5.0)
        scaled = build.scaled(circle, (0.0, 0.0), 2.0)
        self.assertEqual(QgsWkbTypes.flatType(scaled.wkbType()),
                         QgsWkbTypes.CompoundCurve)

    def test_a_circle_keeps_its_radius_relationship(self):
        circle = build.circle((0.0, 0.0), 5.0)
        scaled = build.scaled(circle, (0.0, 0.0), 2.0)
        self.assertTrue(_close(_bbox(scaled), (-10.0, -10.0, 10.0, 10.0)),
                        _bbox(scaled))

    def test_a_circle_is_not_reduced_to_a_handful_of_vertices(self):
        circle = build.circle((0.0, 0.0), 5.0)
        scaled = build.scaled(circle, (0.0, 0.0), 2.0)
        # The old vertex-rebuild path produced a closed 5-point polyline whose
        # area is that of a square, not a circle.
        self.assertGreater(scaled.length(), 2.0 * math.pi * 10.0 * 0.99)

    def test_scaling_about_an_offset_base_point(self):
        square = build.polyline([(0, 0), (2, 0), (2, 2), (0, 2)], closed=True)
        scaled = build.scaled(square, (2.0, 2.0), 2.0)
        self.assertTrue(_close(_bbox(scaled), (-2.0, -2.0, 2.0, 2.0)),
                        _bbox(scaled))

    def test_a_zero_factor_is_refused(self):
        line = build.line((0, 0), (1, 1))
        self.assertIsNone(build.scaled(line, (0, 0), 0))


class TestMirrored(unittest.TestCase):

    def test_reflection_across_the_x_axis(self):
        line = build.line((1.0, 2.0), (4.0, 6.0))
        flipped = build.mirrored(line, (0.0, 0.0), (1.0, 0.0))
        points = build.vertices_of(flipped)
        self.assertTrue(_close(points[0], (1.0, -2.0)), points)
        self.assertTrue(_close(points[1], (4.0, -6.0)), points)

    def test_reflection_across_a_diagonal_swaps_the_axes(self):
        line = build.line((3.0, 0.0), (3.0, 1.0))
        flipped = build.mirrored(line, (0.0, 0.0), (1.0, 1.0))
        points = build.vertices_of(flipped)
        self.assertTrue(_close(points[0], (0.0, 3.0)), points)
        self.assertTrue(_close(points[1], (1.0, 3.0)), points)

    def test_a_circle_stays_a_curve(self):
        circle = build.circle((4.0, 4.0), 2.0)
        flipped = build.mirrored(circle, (0.0, 0.0), (1.0, 0.0))
        self.assertEqual(QgsWkbTypes.flatType(flipped.wkbType()),
                         QgsWkbTypes.CompoundCurve)
        self.assertTrue(_close(_bbox(flipped), (2.0, -6.0, 6.0, -2.0)),
                        _bbox(flipped))

    def test_a_degenerate_axis_is_refused(self):
        line = build.line((0, 0), (1, 1))
        self.assertIsNone(build.mirrored(line, (2.0, 2.0), (2.0, 2.0)))


class TestCompoundCurve(unittest.TestCase):
    """PLINE's Arc option has to produce arcs, not chords."""

    def test_straight_segments_match_the_plain_polyline_builder(self):
        points = [(0, 0), (1, 0), (1, 1)]
        segments = [("line", (1, 0)), ("line", (1, 1))]
        built = build.compound_curve((0, 0), segments)
        self.assertEqual(built.asWkt(3), build.polyline(points).asWkt(3))

    def test_an_arc_segment_becomes_a_circular_string(self):
        segments = [("arc", (1.0, 1.0), (2.0, 0.0))]
        built = build.compound_curve((0.0, 0.0), segments)
        self.assertIn("CIRCULARSTRING", built.asWkt().upper())

    def test_an_arc_segment_actually_bulges(self):
        segments = [("arc", (1.0, 1.0), (2.0, 0.0))]
        built = build.compound_curve((0.0, 0.0), segments)
        # A straight chord would be 2.0 long; a semicircle on it is pi.
        self.assertAlmostEqual(built.length(), math.pi, places=3)

    def test_mixed_runs_keep_both_kinds(self):
        segments = [("line", (1.0, 0.0)),
                    ("arc", (2.0, 1.0), (3.0, 0.0)),
                    ("line", (4.0, 0.0))]
        wkt = build.compound_curve((0.0, 0.0), segments).asWkt().upper()
        self.assertIn("CIRCULARSTRING", wkt)
        self.assertIn("COMPOUNDCURVE", wkt)

    def test_a_collinear_arc_degrades_to_straight_segments(self):
        # No arc passes through three collinear points; emitting an invalid
        # circular string would be worse than a line.
        segments = [("arc", (1.0, 0.0), (2.0, 0.0))]
        built = build.compound_curve((0.0, 0.0), segments)
        self.assertNotIn("CIRCULARSTRING", built.asWkt().upper())
        self.assertAlmostEqual(built.length(), 2.0, places=6)

    def test_no_segments_builds_nothing(self):
        self.assertIsNone(build.compound_curve((0, 0), []))

    def test_the_closing_segment_closes_the_run(self):
        segments = [("line", (1.0, 0.0)), ("line", (1.0, 1.0)),
                    ("line", (0.0, 0.0))]
        built = build.compound_curve((0.0, 0.0), segments)
        points = build.vertices_of(built)
        self.assertTrue(construct.are_coincident(points[0], points[-1]))


if __name__ == "__main__":
    unittest.main()
