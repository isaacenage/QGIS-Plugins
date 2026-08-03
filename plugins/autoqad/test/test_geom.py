# -*- coding: utf-8 -*-
"""Tests for the analytic geometry constructors.

Runs without QGIS. From the plugin directory::

    python test/test_geom.py
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geom import construct as g   # noqa: E402


class TestBasics(unittest.TestCase):

    def test_distance_and_angle(self):
        self.assertAlmostEqual(g.distance((0, 0), (3, 4)), 5.0)
        self.assertAlmostEqual(g.angle_of((0, 0), (1, 1)), math.pi / 4)

    def test_point_at(self):
        point = g.point_at((1, 1), 0.0, 5.0)
        self.assertAlmostEqual(point[0], 6.0)
        self.assertAlmostEqual(point[1], 1.0)

    def test_midpoint(self):
        self.assertEqual(g.midpoint((0, 0), (4, 6)), (2.0, 3.0))


class TestCircles(unittest.TestCase):

    def test_circle_through_three_points(self):
        # Unit circle sampled at 0, 90 and 180 degrees.
        center, radius = g.circle_from_three_points((1, 0), (0, 1), (-1, 0))
        self.assertAlmostEqual(center[0], 0.0)
        self.assertAlmostEqual(center[1], 0.0)
        self.assertAlmostEqual(radius, 1.0)

    def test_collinear_points_have_no_circle(self):
        self.assertIsNone(
            g.circle_from_three_points((0, 0), (1, 1), (2, 2)))

    def test_circle_from_diameter(self):
        center, radius = g.circle_from_two_points((0, 0), (4, 0))
        self.assertEqual(center, (2.0, 0.0))
        self.assertAlmostEqual(radius, 2.0)

    def test_quadrant_points(self):
        points = g.quadrant_points((0, 0), 2.0)
        self.assertEqual(len(points), 4)
        self.assertIn((2.0, 0.0), points)
        self.assertIn((0.0, -2.0), points)

    def test_circle_points_ring_is_closed(self):
        ring = g.circle_points((0, 0), 1.0, segments=12)
        self.assertEqual(len(ring), 13)
        self.assertEqual(ring[0], ring[-1])
        for point in ring:
            self.assertAlmostEqual(math.hypot(*point), 1.0)


class TestArcs(unittest.TestCase):

    def test_three_point_arc_counter_clockwise(self):
        result = g.arc_three_points((1, 0), (0, 1), (-1, 0))
        self.assertIsNotNone(result)
        center, radius, start, end, ccw = result
        self.assertAlmostEqual(radius, 1.0)
        self.assertTrue(ccw)
        self.assertAlmostEqual(start, 0.0)
        self.assertAlmostEqual(abs(end), math.pi)

    def test_three_point_arc_clockwise(self):
        result = g.arc_three_points((1, 0), (0, -1), (-1, 0))
        self.assertIsNotNone(result)
        self.assertFalse(result[4])

    def test_collinear_arc_is_none(self):
        self.assertIsNone(g.arc_three_points((0, 0), (1, 0), (2, 0)))

    def test_arc_midpoint_lies_on_the_arc(self):
        center, radius, start, end, ccw = g.arc_three_points(
            (1, 0), (0, 1), (-1, 0))
        mid = g.arc_midpoint(center, radius, start, end, ccw)
        self.assertAlmostEqual(g.distance(center, mid), radius)
        # For this arc the midpoint is the top of the circle.
        self.assertAlmostEqual(mid[0], 0.0, places=9)
        self.assertAlmostEqual(mid[1], 1.0, places=9)

    def test_arc_points_span_start_to_end(self):
        points = g.arc_points((0, 0), 1.0, 0.0, math.pi, True, segments=8)
        self.assertEqual(len(points), 9)
        self.assertAlmostEqual(points[0][0], 1.0)
        self.assertAlmostEqual(points[-1][0], -1.0, places=9)

    def test_bulge_round_trip(self):
        start, end = (0.0, 0.0), (10.0, 0.0)
        for bulge in (0.25, 0.5, 1.0, -0.5):
            arc = g.bulge_to_arc(start, end, bulge)
            self.assertIsNotNone(arc)
            center, radius, ccw = arc
            self.assertAlmostEqual(g.distance(center, start), radius, places=6)
            self.assertAlmostEqual(g.distance(center, end), radius, places=6)
            back = g.arc_to_bulge(center, start, end, ccw)
            self.assertAlmostEqual(back, bulge, places=6)

    def test_zero_bulge_is_straight(self):
        self.assertIsNone(g.bulge_to_arc((0, 0), (1, 0), 0.0))

    def test_bulge_sign_picks_the_correct_side(self):
        # Independent of the round trip: a positive bulge is counter-clockwise,
        # so travelling +x the arc bows to -y and its centre lies at +y.
        center, _radius, ccw = g.bulge_to_arc((0, 0), (10, 0), 0.25)
        self.assertTrue(ccw)
        self.assertGreater(center[1], 0.0)

        center, _radius, ccw = g.bulge_to_arc((0, 0), (10, 0), -0.25)
        self.assertFalse(ccw)
        self.assertLess(center[1], 0.0)

    def test_major_arc_bulge_round_trip(self):
        # |bulge| > 1 sweeps past a semicircle; the centre crosses the chord.
        for bulge in (1.5, -2.0):
            center, radius, ccw = g.bulge_to_arc((0, 0), (10, 0), bulge)
            self.assertAlmostEqual(g.distance(center, (0, 0)), radius, places=6)
            self.assertAlmostEqual(g.distance(center, (10, 0)), radius,
                                   places=6)
            back = g.arc_to_bulge(center, (0, 0), (10, 0), ccw)
            self.assertAlmostEqual(back, bulge, places=6)

    def test_semicircle_bulge(self):
        # bulge 1 is a half circle: radius = chord / 2.
        center, radius, ccw = g.bulge_to_arc((0, 0), (10, 0), 1.0)
        self.assertAlmostEqual(radius, 5.0, places=6)
        self.assertAlmostEqual(center[0], 5.0, places=6)
        self.assertAlmostEqual(center[1], 0.0, places=6)


class TestIntersections(unittest.TestCase):

    def test_line_intersection(self):
        point = g.line_intersection((0, 0), (10, 0), (5, -5), (5, 5))
        self.assertAlmostEqual(point[0], 5.0)
        self.assertAlmostEqual(point[1], 0.0)

    def test_parallel_lines_do_not_intersect(self):
        self.assertIsNone(
            g.line_intersection((0, 0), (10, 0), (0, 1), (10, 1)))

    def test_infinite_lines_cross_outside_segments(self):
        point = g.line_intersection((0, 0), (1, 0), (5, -5), (5, 5))
        self.assertAlmostEqual(point[0], 5.0)
        self.assertIsNone(g.line_intersection(
            (0, 0), (1, 0), (5, -5), (5, 5), segment_only=True))

    def test_circle_line_two_points(self):
        points = g.circle_line_intersection((0, 0), 1.0, (-2, 0), (2, 0))
        self.assertEqual(len(points), 2)
        xs = sorted(p[0] for p in points)
        self.assertAlmostEqual(xs[0], -1.0)
        self.assertAlmostEqual(xs[1], 1.0)

    def test_circle_line_tangent_is_one_point(self):
        points = g.circle_line_intersection((0, 0), 1.0, (-2, 1), (2, 1))
        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0][1], 1.0)

    def test_circle_line_miss(self):
        self.assertEqual(
            g.circle_line_intersection((0, 0), 1.0, (-2, 5), (2, 5)), [])

    def test_circle_circle_two_points(self):
        points = g.circle_circle_intersection((0, 0), 1.0, (1, 0), 1.0)
        self.assertEqual(len(points), 2)
        for point in points:
            self.assertAlmostEqual(g.distance(point, (0, 0)), 1.0)
            self.assertAlmostEqual(g.distance(point, (1, 0)), 1.0)

    def test_circle_circle_separate(self):
        self.assertEqual(
            g.circle_circle_intersection((0, 0), 1.0, (10, 0), 1.0), [])

    def test_circle_circle_tangent(self):
        points = g.circle_circle_intersection((0, 0), 1.0, (2, 0), 1.0)
        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0][0], 1.0)


class TestProjections(unittest.TestCase):

    def test_perpendicular_foot(self):
        foot = g.perpendicular_foot((5, 5), (0, 0), (10, 0))
        self.assertAlmostEqual(foot[0], 5.0)
        self.assertAlmostEqual(foot[1], 0.0)

    def test_perpendicular_foot_beyond_segment(self):
        # Unclamped falls outside; clamped snaps to the endpoint.
        self.assertAlmostEqual(
            g.perpendicular_foot((20, 5), (0, 0), (10, 0))[0], 20.0)
        self.assertAlmostEqual(
            g.perpendicular_foot((20, 5), (0, 0), (10, 0), clamp=True)[0], 10.0)

    def test_degenerate_line_returns_start(self):
        self.assertEqual(
            g.perpendicular_foot((5, 5), (1, 1), (1, 1)), (1, 1))

    def test_tangent_points(self):
        points = g.tangent_points((2, 0), (0, 0), 1.0)
        self.assertEqual(len(points), 2)
        for point in points:
            self.assertAlmostEqual(g.distance(point, (0, 0)), 1.0)
            # Tangent means the radius is perpendicular to the tangent line.
            radius_angle = g.angle_of((0, 0), point)
            tangent_angle = g.angle_of(point, (2, 0))
            delta = abs(math.cos(radius_angle - tangent_angle))
            self.assertAlmostEqual(delta, 0.0, places=9)

    def test_tangent_from_inside_is_empty(self):
        self.assertEqual(g.tangent_points((0.5, 0), (0, 0), 1.0), [])

    def test_tangent_from_on_circle_is_single(self):
        self.assertEqual(len(g.tangent_points((1, 0), (0, 0), 1.0)), 1)


class TestPolygons(unittest.TestCase):

    def test_rectangle_ring(self):
        ring = g.rectangle_points((0, 0), (4, 3))
        self.assertEqual(len(ring), 5)
        self.assertEqual(ring[0], ring[-1])
        self.assertIn((4, 0), ring)
        self.assertIn((0, 3), ring)

    def test_inscribed_polygon(self):
        ring = g.polygon_points((0, 0), 1.0, 6)
        self.assertEqual(len(ring), 7)
        for point in ring:
            self.assertAlmostEqual(math.hypot(*point), 1.0)

    def test_circumscribed_polygon_is_larger(self):
        inscribed = g.polygon_points((0, 0), 1.0, 6, inscribed=True)
        circumscribed = g.polygon_points((0, 0), 1.0, 6, inscribed=False)
        self.assertGreater(math.hypot(*circumscribed[0]),
                           math.hypot(*inscribed[0]))

    def test_polygon_from_edge_has_correct_edge_length(self):
        ring = g.polygon_from_edge((0, 0), (10, 0), 5)
        self.assertIsNotNone(ring)
        self.assertEqual(len(ring), 6)
        self.assertAlmostEqual(g.distance(ring[0], ring[1]), 10.0, places=6)

    def test_polygon_from_degenerate_edge_is_none(self):
        self.assertIsNone(g.polygon_from_edge((0, 0), (0, 0), 5))


class TestFilletChamfer(unittest.TestCase):

    def test_fillet_of_a_right_angle(self):
        # Horizontal then vertical, meeting at the origin.
        result = g.fillet_arc((10, 0), (0, 0), (0, 0), (0, 10), 2.0)
        self.assertIsNotNone(result)
        center, t1, t2, _ccw = result
        # Tangent points sit exactly the radius from the corner along each leg.
        self.assertAlmostEqual(g.distance((0, 0), t1), 2.0, places=6)
        self.assertAlmostEqual(g.distance((0, 0), t2), 2.0, places=6)
        # And the centre is the radius from each tangent point.
        self.assertAlmostEqual(g.distance(center, t1), 2.0, places=6)
        self.assertAlmostEqual(g.distance(center, t2), 2.0, places=6)

    def test_fillet_of_parallel_lines_is_none(self):
        self.assertIsNone(
            g.fillet_arc((0, 0), (10, 0), (0, 5), (10, 5), 1.0))

    def test_fillet_with_zero_radius_is_none(self):
        self.assertIsNone(g.fillet_arc((10, 0), (0, 0), (0, 0), (0, 10), 0.0))

    def test_chamfer_endpoints(self):
        result = g.chamfer_points((10, 0), (0, 0), (0, 0), (0, 10), 3.0)
        self.assertIsNotNone(result)
        p1, p2 = result
        self.assertAlmostEqual(g.distance((0, 0), p1), 3.0, places=6)
        self.assertAlmostEqual(g.distance((0, 0), p2), 3.0, places=6)

    def test_chamfer_unequal_distances(self):
        p1, p2 = g.chamfer_points((10, 0), (0, 0), (0, 0), (0, 10), 3.0, 5.0)
        self.assertAlmostEqual(g.distance((0, 0), p1), 3.0, places=6)
        self.assertAlmostEqual(g.distance((0, 0), p2), 5.0, places=6)


class TestTransforms(unittest.TestCase):

    def test_translate(self):
        self.assertEqual(g.translate([(0, 0), (1, 1)], 2, 3),
                         [(2, 3), (3, 4)])

    def test_rotate_ninety_degrees(self):
        rotated = g.rotate([(1, 0)], (0, 0), math.pi / 2)
        self.assertAlmostEqual(rotated[0][0], 0.0, places=9)
        self.assertAlmostEqual(rotated[0][1], 1.0, places=9)

    def test_scale_uniform_and_non_uniform(self):
        self.assertEqual(g.scale([(2, 2)], (0, 0), 2.0), [(4.0, 4.0)])
        self.assertEqual(g.scale([(2, 2)], (0, 0), 2.0, 3.0), [(4.0, 6.0)])

    def test_mirror_across_x_axis(self):
        mirrored = g.mirror([(3, 4)], (0, 0), (1, 0))
        self.assertAlmostEqual(mirrored[0][0], 3.0)
        self.assertAlmostEqual(mirrored[0][1], -4.0)

    def test_mirror_across_diagonal_swaps(self):
        mirrored = g.mirror([(3, 0)], (0, 0), (1, 1))
        self.assertAlmostEqual(mirrored[0][0], 0.0, places=9)
        self.assertAlmostEqual(mirrored[0][1], 3.0, places=9)

    def test_mirror_across_degenerate_axis_is_identity(self):
        self.assertEqual(g.mirror([(3, 4)], (1, 1), (1, 1)), [(3, 4)])


class TestDivide(unittest.TestCase):

    def test_divide_a_straight_line(self):
        points = g.divide_points([(0, 0), (10, 0)], 5)
        self.assertEqual(len(points), 4)
        self.assertAlmostEqual(points[0][0], 2.0)
        self.assertAlmostEqual(points[-1][0], 8.0)

    def test_divide_across_segments(self):
        # An L: 10 across then 10 up. Halving lands exactly on the corner.
        points = g.divide_points([(0, 0), (10, 0), (10, 10)], 2)
        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0][0], 10.0)
        self.assertAlmostEqual(points[0][1], 0.0)

    def test_divide_degenerate_input(self):
        self.assertEqual(g.divide_points([(0, 0)], 5), [])
        self.assertEqual(g.divide_points([(0, 0), (0, 0)], 5), [])
        self.assertEqual(g.divide_points([(0, 0), (1, 0)], 1), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
