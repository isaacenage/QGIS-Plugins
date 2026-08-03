# -*- coding: utf-8 -*-
"""Analytic constructors for CAD geometry.

Pure module: no Qt, no QGIS. Points are ``(x, y)`` float tuples.

This is deliberately *small*. The lesson from prior art in this space is that
hand-rolling a full geometry kernel in Python — intersections, buffers,
distance queries — and then calling it from the mouse-move loop is what makes a
CAD plugin lag. Everything GEOS can do (intersection, offset, buffer, nearest
point, containment) goes through ``QgsGeometry`` instead, in C++.

What lives here is only what GEOS does *not* offer: the analytic constructions
CAD needs to turn user input into geometry — three-point arcs, tangents,
perpendicular feet, fillet arcs, polygon construction. These are closed-form,
allocation-light, and unit-testable without a QGIS runtime.
"""

import math

#: Distances below this are treated as coincident.
EPSILON = 1e-9


def distance(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def angle_of(a, b):
    """Angle of the vector from *a* to *b*, in radians."""
    return math.atan2(b[1] - a[1], b[0] - a[0])


def point_at(origin, angle, length):
    return (origin[0] + length * math.cos(angle),
            origin[1] + length * math.sin(angle))


def midpoint(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def normalise_angle(angle):
    """Wrap *angle* into ``[0, 2pi)``."""
    return angle % (2.0 * math.pi)


def are_coincident(a, b, tolerance=EPSILON):
    return distance(a, b) <= tolerance


# --- circles and arcs --------------------------------------------------------

def circle_from_three_points(a, b, c):
    """Return ``(center, radius)`` through three points, or ``None``.

    Returns ``None`` when the points are collinear (no finite circle exists),
    which the caller should report rather than crash on.
    """
    ax, ay = a
    bx, by = b
    cx, cy = c

    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < EPSILON:
        return None

    a_sq = ax * ax + ay * ay
    b_sq = bx * bx + by * by
    c_sq = cx * cx + cy * cy

    ux = (a_sq * (by - cy) + b_sq * (cy - ay) + c_sq * (ay - by)) / d
    uy = (a_sq * (cx - bx) + b_sq * (ax - cx) + c_sq * (bx - ax)) / d

    center = (ux, uy)
    return (center, distance(center, a))


def circle_from_two_points(a, b):
    """Return ``(center, radius)`` for the circle with *a*-*b* as diameter."""
    return (midpoint(a, b), distance(a, b) / 2.0)


def arc_three_points(start, through, end):
    """Describe the arc through three points.

    Returns ``(center, radius, start_angle, end_angle, counter_clockwise)`` or
    ``None`` for collinear input. Angles are in radians.
    """
    circle = circle_from_three_points(start, through, end)
    if circle is None:
        return None
    center, radius = circle

    start_angle = angle_of(center, start)
    through_angle = angle_of(center, through)
    end_angle = angle_of(center, end)

    # The arc runs counter-clockwise when the mid point falls inside the CCW
    # sweep from start to end.
    ccw_sweep = normalise_angle(end_angle - start_angle)
    ccw_to_mid = normalise_angle(through_angle - start_angle)
    counter_clockwise = ccw_to_mid < ccw_sweep

    return (center, radius, start_angle, end_angle, counter_clockwise)


def arc_points(center, radius, start_angle, end_angle, counter_clockwise=True,
               segments=64):
    """Segmentise an arc into points — for previews and non-curve output."""
    if counter_clockwise:
        sweep = normalise_angle(end_angle - start_angle)
    else:
        sweep = -normalise_angle(start_angle - end_angle)
    if abs(sweep) < EPSILON:
        sweep = 2.0 * math.pi if counter_clockwise else -2.0 * math.pi

    count = max(2, int(segments))
    return [point_at(center, start_angle + sweep * (i / float(count)), radius)
            for i in range(count + 1)]


def circle_points(center, radius, segments=72):
    """Segmentise a full circle, closing the ring."""
    points = [point_at(center, 2.0 * math.pi * (i / float(segments)), radius)
              for i in range(segments)]
    points.append(points[0])
    return points


def arc_midpoint(center, radius, start_angle, end_angle,
                 counter_clockwise=True):
    """Return the point halfway along an arc — the through-point a
    ``CircularString`` needs."""
    if counter_clockwise:
        sweep = normalise_angle(end_angle - start_angle)
    else:
        sweep = -normalise_angle(start_angle - end_angle)
    if abs(sweep) < EPSILON:
        sweep = 2.0 * math.pi if counter_clockwise else -2.0 * math.pi
    return point_at(center, start_angle + sweep / 2.0, radius)


def bulge_to_arc(start, end, bulge):
    """Convert a DXF bulge value into ``(center, radius, ccw)``.

    A bulge is ``tan(sweep / 4)`` — the compact arc encoding DXF LWPOLYLINE
    uses. Returns ``None`` for a straight segment (bulge 0).
    """
    if abs(bulge) < EPSILON:
        return None
    chord = distance(start, end)
    if chord < EPSILON:
        return None

    sweep = 4.0 * math.atan(bulge)
    radius = abs(chord / (2.0 * math.sin(sweep / 2.0)))

    chord_angle = angle_of(start, end)
    apothem = radius * math.cos(sweep / 2.0)

    # Which side the centre falls on: a positive bulge is a counter-clockwise
    # traversal, which turns left — so for a minor arc the path bows to the
    # *right* of start->end and the centre sits to the left. Walking (0,0) to
    # (10,0) with bulge +0.25 therefore dips below y=0 around a centre above
    # it. For a major arc (|bulge| > 1) the sweep exceeds pi, cos goes
    # negative, and the apothem flips the centre across on its own.
    # Multiply by the sign rather than copysign() — copysign would replace the
    # apothem's own sign, which is exactly the part that flips the centre for
    # a major arc.
    normal = chord_angle + math.pi / 2.0
    center = point_at(midpoint(start, end), normal,
                      apothem * (1.0 if bulge > 0 else -1.0))
    return (center, radius, bulge > 0)


def arc_to_bulge(center, start, end, counter_clockwise=True):
    """Inverse of :func:`bulge_to_arc` — encode an arc as a DXF bulge."""
    start_angle = angle_of(center, start)
    end_angle = angle_of(center, end)
    if counter_clockwise:
        sweep = normalise_angle(end_angle - start_angle)
    else:
        sweep = -normalise_angle(start_angle - end_angle)
    return math.tan(sweep / 4.0)


# --- polygons and rectangles -------------------------------------------------

def rectangle_points(corner_a, corner_b):
    """Return the closed ring of an axis-aligned rectangle."""
    x0, y0 = corner_a
    x1, y1 = corner_b
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def rectangle_from_dimensions(corner, width, height):
    return rectangle_points(corner, (corner[0] + width, corner[1] + height))


def polygon_points(center, radius, sides, start_angle=0.0, inscribed=True):
    """Return the closed ring of a regular polygon.

    *inscribed* places vertices on the circle of *radius*; otherwise the circle
    is inscribed in the polygon (circumscribed construction), matching
    AutoCAD's POLYGON options.
    """
    count = max(3, int(sides))
    effective = radius if inscribed else radius / math.cos(math.pi / count)
    points = [point_at(center, start_angle + 2.0 * math.pi * (i / float(count)),
                       effective)
              for i in range(count)]
    points.append(points[0])
    return points


def polygon_from_edge(start, end, sides):
    """Return a regular polygon defined by one edge — AutoCAD's Edge option."""
    count = max(3, int(sides))
    edge_length = distance(start, end)
    if edge_length < EPSILON:
        return None
    radius = edge_length / (2.0 * math.sin(math.pi / count))
    edge_angle = angle_of(start, end)
    # Centre lies on the perpendicular bisector of the edge.
    apothem = radius * math.cos(math.pi / count)
    center = point_at(midpoint(start, end), edge_angle + math.pi / 2.0, apothem)
    return polygon_points(center, radius, count,
                          start_angle=angle_of(center, start))


# --- lines: intersection, perpendicular, tangent -----------------------------

def line_intersection(p1, p2, p3, p4, segment_only=False):
    """Intersect the infinite lines through *p1p2* and *p3p4*.

    With *segment_only*, returns ``None`` unless the crossing lies within both
    segments. Parallel lines return ``None``.
    """
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < EPSILON:
        return None

    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denominator

    if segment_only and not (0.0 <= t <= 1.0 and 0.0 <= u <= 1.0):
        return None
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def perpendicular_foot(point, line_start, line_end, clamp=False):
    """Return the perpendicular projection of *point* onto a line.

    With *clamp*, the result is confined to the segment — which is what the
    NEArest object snap wants, where PERpendicular wants the infinite line.
    """
    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]
    length_sq = dx * dx + dy * dy
    if length_sq < EPSILON:
        return line_start

    t = (((point[0] - line_start[0]) * dx
          + (point[1] - line_start[1]) * dy) / length_sq)
    if clamp:
        t = max(0.0, min(1.0, t))
    return (line_start[0] + t * dx, line_start[1] + t * dy)


def tangent_points(external_point, center, radius):
    """Return the two tangent points from an external point to a circle.

    Returns ``[]`` when the point lies inside the circle, and a single point
    when it lies on it.
    """
    gap = distance(external_point, center)
    if gap < radius - EPSILON:
        return []
    if abs(gap - radius) < EPSILON:
        return [tuple(external_point)]

    base_angle = angle_of(center, external_point)
    offset = math.acos(max(-1.0, min(1.0, radius / gap)))
    return [point_at(center, base_angle + offset, radius),
            point_at(center, base_angle - offset, radius)]


def quadrant_points(center, radius):
    """Return the four quadrant points — the QUAdrant object snap."""
    return [(center[0] + radius, center[1]),
            (center[0], center[1] + radius),
            (center[0] - radius, center[1]),
            (center[0], center[1] - radius)]


def circle_line_intersection(center, radius, p1, p2, segment_only=False):
    """Intersect a circle with the line through *p1p2*. Returns 0-2 points."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length_sq = dx * dx + dy * dy
    if length_sq < EPSILON:
        return []

    fx = p1[0] - center[0]
    fy = p1[1] - center[1]

    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - radius * radius
    discriminant = b * b - 4.0 * length_sq * c
    if discriminant < 0.0:
        return []

    root = math.sqrt(discriminant)
    results = []
    for t in ((-b - root) / (2.0 * length_sq), (-b + root) / (2.0 * length_sq)):
        if segment_only and not (0.0 <= t <= 1.0):
            continue
        results.append((p1[0] + t * dx, p1[1] + t * dy))

    if len(results) == 2 and are_coincident(results[0], results[1]):
        return [results[0]]
    return results


def circle_circle_intersection(c1, r1, c2, r2):
    """Intersect two circles. Returns 0-2 points."""
    gap = distance(c1, c2)
    if gap < EPSILON or gap > r1 + r2 + EPSILON or gap < abs(r1 - r2) - EPSILON:
        return []

    a = (r1 * r1 - r2 * r2 + gap * gap) / (2.0 * gap)
    height_sq = r1 * r1 - a * a
    if height_sq < 0.0:
        height_sq = 0.0
    height = math.sqrt(height_sq)

    base = (c1[0] + a * (c2[0] - c1[0]) / gap,
            c1[1] + a * (c2[1] - c1[1]) / gap)
    if height < EPSILON:
        return [base]

    offset_x = height * (c2[1] - c1[1]) / gap
    offset_y = height * (c2[0] - c1[0]) / gap
    return [(base[0] + offset_x, base[1] - offset_y),
            (base[0] - offset_x, base[1] + offset_y)]


# --- fillet and chamfer ------------------------------------------------------

def fillet_arc(p1, p2, p3, p4, radius):
    """Compute the fillet arc joining segment *p1p2* to segment *p3p4*.

    Returns ``(center, tangent_1, tangent_2, counter_clockwise)`` or ``None``
    when the lines are parallel or the radius does not fit.
    """
    corner = line_intersection(p1, p2, p3, p4)
    if corner is None or radius <= EPSILON:
        return None

    # Unit vectors pointing away from the corner along each line, choosing the
    # end furthest from it so the fillet lands on the drawn side.
    def away(a, b):
        far = a if distance(corner, a) > distance(corner, b) else b
        angle = angle_of(corner, far)
        return angle

    angle_1 = away(p1, p2)
    angle_2 = away(p3, p4)

    between = normalise_angle(angle_2 - angle_1)
    if between > math.pi:
        between -= 2.0 * math.pi
    half = abs(between) / 2.0
    if half < EPSILON or abs(half - math.pi / 2.0) < EPSILON * 0.0:
        return None

    tangent_distance = radius / math.tan(half)
    if math.isinf(tangent_distance) or math.isnan(tangent_distance):
        return None

    t1 = point_at(corner, angle_1, tangent_distance)
    t2 = point_at(corner, angle_2, tangent_distance)

    bisector = angle_1 + between / 2.0
    center_distance = radius / math.sin(half)
    center = point_at(corner, bisector, center_distance)

    counter_clockwise = between < 0
    return (center, t1, t2, counter_clockwise)


def chamfer_points(p1, p2, p3, p4, distance_1, distance_2=None):
    """Compute the two chamfer endpoints between two segments.

    Returns ``(point_1, point_2)`` or ``None`` for parallel lines.
    """
    corner = line_intersection(p1, p2, p3, p4)
    if corner is None:
        return None
    if distance_2 is None:
        distance_2 = distance_1

    def away(a, b):
        far = a if distance(corner, a) > distance(corner, b) else b
        return angle_of(corner, far)

    return (point_at(corner, away(p1, p2), distance_1),
            point_at(corner, away(p3, p4), distance_2))


# --- transforms --------------------------------------------------------------

def translate(points, dx, dy):
    return [(p[0] + dx, p[1] + dy) for p in points]


def rotate(points, origin, angle):
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    result = []
    for x, y in points:
        ox = x - origin[0]
        oy = y - origin[1]
        result.append((origin[0] + ox * cos_a - oy * sin_a,
                       origin[1] + ox * sin_a + oy * cos_a))
    return result


def scale(points, origin, factor_x, factor_y=None):
    if factor_y is None:
        factor_y = factor_x
    return [(origin[0] + (p[0] - origin[0]) * factor_x,
             origin[1] + (p[1] - origin[1]) * factor_y) for p in points]


def mirror(points, axis_start, axis_end):
    """Reflect *points* across the line through *axis_start*-*axis_end*."""
    dx = axis_end[0] - axis_start[0]
    dy = axis_end[1] - axis_start[1]
    length_sq = dx * dx + dy * dy
    if length_sq < EPSILON:
        return list(points)

    result = []
    for x, y in points:
        ox = x - axis_start[0]
        oy = y - axis_start[1]
        factor = 2.0 * (ox * dx + oy * dy) / length_sq
        result.append((axis_start[0] + factor * dx - ox,
                       axis_start[1] + factor * dy - oy))
    return result


def divide_points(points, count):
    """Return *count* - 1 points dividing a polyline into equal lengths."""
    if count < 2 or len(points) < 2:
        return []

    lengths = [distance(points[i], points[i + 1])
               for i in range(len(points) - 1)]
    total = sum(lengths)
    if total < EPSILON:
        return []

    step = total / float(count)
    results = []
    for index in range(1, int(count)):
        target = step * index
        travelled = 0.0
        for segment, length in enumerate(lengths):
            if travelled + length >= target - EPSILON:
                remaining = target - travelled
                ratio = remaining / length if length > EPSILON else 0.0
                a = points[segment]
                b = points[segment + 1]
                results.append((a[0] + (b[0] - a[0]) * ratio,
                                a[1] + (b[1] - a[1]) * ratio))
                break
            travelled += length
    return results


def measure_points(points, spacing):
    """Return points spaced *spacing* apart along a polyline."""
    if spacing <= EPSILON or len(points) < 2:
        return []
    lengths = [distance(points[i], points[i + 1])
               for i in range(len(points) - 1)]
    total = sum(lengths)
    if total < EPSILON:
        return []
    return divide_points(points, int(total / spacing) + 1)[:int(total / spacing)]
