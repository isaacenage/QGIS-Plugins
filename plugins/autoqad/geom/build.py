# -*- coding: utf-8 -*-
"""Turn analytic constructions into :class:`QgsGeometry`.

The bridge between :mod:`.construct` (pure maths, plain tuples) and QGIS.

Arcs are built as ``CircularString`` / ``CompoundCurve`` rather than being
segmentised, so a circle drawn in AutoQAD stays a true circle through save,
reload and DXF export instead of degrading into a many-sided polygon. Where a
QGIS build cannot construct a curve, the helpers fall back to a dense
segmentisation rather than failing — a slightly heavier geometry beats a
command that does not work.
"""

from qgis.core import (
    QgsCircularString,
    QgsCompoundCurve,
    QgsCurvePolygon,
    QgsGeometry,
    QgsLineString,
    QgsPoint,
    QgsPointXY,
)

from . import construct


def _points(pairs):
    return [QgsPoint(p[0], p[1]) for p in pairs]


def _points_xy(pairs):
    return [QgsPointXY(p[0], p[1]) for p in pairs]


# --- lines and polylines -----------------------------------------------------

def line(start, end):
    """A two-point line as a compound curve."""
    return polyline([start, end])


def polyline(points, closed=False):
    """A straight-segment polyline, as a ``CompoundCurve``."""
    ring = list(points)
    if len(ring) < 2:
        return None
    if closed and ring[0] != ring[-1]:
        ring.append(ring[0])

    curve = QgsCompoundCurve()
    curve.addCurve(QgsLineString(_points(ring)))
    return QgsGeometry(curve)


def polyline_simple(points, closed=False):
    """A plain ``LineString`` — used where curves are not needed."""
    ring = list(points)
    if len(ring) < 2:
        return None
    if closed and ring[0] != ring[-1]:
        ring.append(ring[0])
    return QgsGeometry.fromPolylineXY(_points_xy(ring))


# --- arcs and circles --------------------------------------------------------

def arc_three_points(start, through, end):
    """A true circular arc through three points.

    Falls back to a segmentised polyline when the points are collinear (no arc
    exists) so the caller always gets usable geometry.
    """
    if construct.arc_three_points(start, through, end) is None:
        return polyline([start, through, end])

    curve = QgsCompoundCurve()
    curve.addCurve(QgsCircularString(
        QgsPoint(start[0], start[1]),
        QgsPoint(through[0], through[1]),
        QgsPoint(end[0], end[1])))
    return QgsGeometry(curve)


def arc(center, radius, start_angle, end_angle, counter_clockwise=True):
    """A circular arc given centre, radius and sweep."""
    start = construct.point_at(center, start_angle, radius)
    end = construct.point_at(center, end_angle, radius)
    through = construct.arc_midpoint(center, radius, start_angle, end_angle,
                                     counter_clockwise)
    return arc_three_points(start, through, end)


def circle(center, radius, as_polygon=False):
    """A true circle, built as two half-arcs so it closes exactly.

    A ``CircularString`` needs three distinct points and cannot express a full
    revolution in one arc, so a circle is always two semicircles.
    """
    if radius <= 0:
        return None

    east = (center[0] + radius, center[1])
    west = (center[0] - radius, center[1])
    north = (center[0], center[1] + radius)
    south = (center[0], center[1] - radius)

    curve = QgsCompoundCurve()
    curve.addCurve(QgsCircularString(
        QgsPoint(*east), QgsPoint(*north), QgsPoint(*west)))
    curve.addCurve(QgsCircularString(
        QgsPoint(*west), QgsPoint(*south), QgsPoint(*east)))

    if not as_polygon:
        return QgsGeometry(curve)

    polygon = QgsCurvePolygon()
    polygon.setExteriorRing(curve)
    return QgsGeometry(polygon)


def ellipse(center, major_radius, minor_radius, rotation=0.0, segments=72):
    """An ellipse. Segmentised — QGIS has no native ellipse curve type."""
    import math
    points = []
    for index in range(segments):
        theta = 2.0 * math.pi * index / float(segments)
        x = major_radius * math.cos(theta)
        y = minor_radius * math.sin(theta)
        points.append((
            center[0] + x * math.cos(rotation) - y * math.sin(rotation),
            center[1] + x * math.sin(rotation) + y * math.cos(rotation)))
    points.append(points[0])
    return polyline(points)


# --- closed shapes -----------------------------------------------------------

def rectangle(corner_a, corner_b, as_polygon=False):
    ring = construct.rectangle_points(corner_a, corner_b)
    return polygon(ring) if as_polygon else polyline(ring)


def regular_polygon(center, radius, sides, start_angle=0.0, inscribed=True,
                    as_polygon=False):
    ring = construct.polygon_points(center, radius, sides, start_angle,
                                    inscribed)
    return polygon(ring) if as_polygon else polyline(ring)


def polygon(ring, holes=None):
    """A polygon from a closed ring (plus optional holes)."""
    points = list(ring)
    if len(points) < 3:
        return None
    if points[0] != points[-1]:
        points.append(points[0])

    rings = [_points_xy(points)]
    for hole in (holes or []):
        hole_points = list(hole)
        if len(hole_points) < 3:
            continue
        if hole_points[0] != hole_points[-1]:
            hole_points.append(hole_points[0])
        rings.append(_points_xy(hole_points))
    return QgsGeometry.fromPolygonXY(rings)


def point(position):
    return QgsGeometry.fromPointXY(QgsPointXY(position[0], position[1]))


# --- extraction --------------------------------------------------------------

def vertices_of(geometry):
    """Return a geometry's vertices as plain ``(x, y)`` tuples."""
    if geometry is None or geometry.isEmpty():
        return []
    try:
        return [(v.x(), v.y()) for v in geometry.vertices()]
    except (AttributeError, RuntimeError):
        polyline_points = geometry.asPolyline()
        if polyline_points:
            return [(p.x(), p.y()) for p in polyline_points]
        return []


def endpoints_of(geometry):
    """Return ``(start, end)`` of a curve geometry, or ``None``."""
    points = vertices_of(geometry)
    if len(points) < 2:
        return None
    return (points[0], points[-1])


def is_closed(geometry):
    points = vertices_of(geometry)
    return len(points) > 2 and construct.are_coincident(points[0], points[-1])


def segmentised(geometry, tolerance=None):
    """Return a straight-segment copy of a curved geometry.

    Used where an operation genuinely needs vertices — offset previews, area
    maths — while the stored geometry keeps its true curves.
    """
    if geometry is None or geometry.isEmpty():
        return geometry
    try:
        abstract = geometry.constGet()
        if abstract is not None and hasattr(abstract, "segmentize"):
            return QgsGeometry(abstract.segmentize())
    except (AttributeError, RuntimeError):
        pass
    return geometry
