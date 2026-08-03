# -*- coding: utf-8 -*-
"""Object snapping — AutoCAD osnaps built on QGIS's C++ point locator.

The single most important performance decision in this plugin lives here.

Prior art in this space reads QGIS's snapping *configuration* and then performs
its own snap search in Python, iterating features layer by layer on every mouse
move. That is what makes a CAD plugin lag: an interpreted per-feature scan
inside a 60 Hz loop.

AutoQAD instead goes through :class:`QgsPointLocator`, obtained from the
canvas's own :class:`QgsSnappingUtils`. QGIS builds and maintains that R-tree in
C++, keeps it warm across mouse moves, and invalidates it on edits — so vertex,
edge, centroid and area queries are indexed lookups, not scans.

The osnaps QGIS has no native equivalent for — perpendicular, tangent,
quadrant, extension — are computed **analytically on the one entity the locator
already matched**. That is the structural difference: O(1) closed-form maths on
a single known entity, instead of an O(features) search per snap type.

Priority follows AutoCAD: endpoint beats midpoint beats centre, and so on down
to nearest, which only ever wins if nothing else is in range.
"""

import math

from qgis.core import QgsPointXY, QgsWkbTypes

from ..core.variables import (
    OSNAP_CEN, OSNAP_END, OSNAP_EXT, OSNAP_INT, OSNAP_MID, OSNAP_NEA,
    OSNAP_NODE, OSNAP_PER, OSNAP_QUA, OSNAP_TAN,
)
from ..geom import construct

#: Snap types in resolution priority order — first match within range wins.
PRIORITY = (
    (OSNAP_END, "END", "Endpoint"),
    (OSNAP_MID, "MID", "Midpoint"),
    (OSNAP_CEN, "CEN", "Center"),
    (OSNAP_NODE, "NOD", "Node"),
    (OSNAP_QUA, "QUA", "Quadrant"),
    (OSNAP_INT, "INT", "Intersection"),
    (OSNAP_PER, "PER", "Perpendicular"),
    (OSNAP_TAN, "TAN", "Tangent"),
    (OSNAP_EXT, "EXT", "Extension"),
    (OSNAP_NEA, "NEA", "Nearest"),
)


class SnapResult(object):
    """One resolved snap: where, what kind, and on which entity."""

    __slots__ = ("point", "snap_type", "label", "layer", "feature_id",
                 "distance")

    def __init__(self, point, snap_type, label, layer=None, feature_id=None,
                 distance=0.0):
        self.point = point
        self.snap_type = snap_type
        self.label = label
        self.layer = layer
        self.feature_id = feature_id
        self.distance = distance

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<Snap {0} {1}>".format(self.label, self.point)


class SnapEngine(object):
    """Resolves a cursor position to an object snap.

    Holds no index of its own — every spatial query is delegated to the
    canvas's :class:`QgsSnappingUtils`, so index lifetime, caching and edit
    invalidation are QGIS's job rather than this plugin's.
    """

    def __init__(self, canvas, variables, document):
        self.canvas = canvas
        self.variables = variables
        self.document = document

    # ---- tolerance ----

    def tolerance(self):
        """Snap aperture in map units, derived from the APERTURE pixel size."""
        pixels = max(1, int(self.variables.get("APERTURE")))
        return self.canvas.mapUnitsPerPixel() * pixels

    # ---- locators ----

    def _locators(self):
        """Yield a warm :class:`QgsPointLocator` per selectable CAD table."""
        if self.document is None or not self.document.is_open:
            return
        utils = self.canvas.snappingUtils()
        if utils is None:
            return
        for layer in self.document.all_tables():
            try:
                locator = utils.locatorForLayer(layer)
            except (AttributeError, RuntimeError):
                continue
            if locator is not None:
                yield layer, locator

    def _is_selectable(self, layer, feature_id):
        """Honour CAD layer freeze state — frozen entities are not snappable."""
        if feature_id is None or layer is None:
            return True
        try:
            feature = layer.getFeature(feature_id)
        except (RuntimeError, KeyError):
            return True
        if feature is None or not feature.isValid():
            return True
        name = feature.attribute("aq_layer")
        cad = self.document.layers.get(name) if name else None
        return cad is None or cad.is_selectable

    # ---- the public entry point ----

    def snap(self, map_point, base_point=None):
        """Return the best :class:`SnapResult` for *map_point*, or ``None``.

        *base_point* is the command's current anchor, needed by the snaps that
        are defined relative to it — perpendicular and tangent.
        """
        if not self.variables.osnap_enabled:
            return None

        point = QgsPointXY(map_point[0], map_point[1])
        tolerance = self.tolerance()
        mask = self.variables.get("OSMODE")

        candidates = []
        for layer, locator in self._locators():
            self._collect(candidates, layer, locator, point, tolerance,
                          mask, base_point)

        if not candidates:
            return None

        # Resolve by AutoCAD priority first, distance second.
        order = {flag: index for index, (flag, _s, _l) in enumerate(PRIORITY)}
        candidates.sort(key=lambda c: (order.get(c[0], 99), c[1].distance))
        return candidates[0][1]

    def _collect(self, out, layer, locator, point, tolerance, mask,
                 base_point):
        """Gather every enabled snap candidate for one layer."""
        geometry_type = layer.geometryType()

        # --- vertex-based: endpoint and node (indexed) ---
        if mask & (OSNAP_END | OSNAP_NODE):
            match = locator.nearestVertex(point, tolerance)
            if match.isValid() and self._is_selectable(layer, match.featureId()):
                is_point_layer = geometry_type == QgsWkbTypes.PointGeometry
                flag = OSNAP_NODE if is_point_layer else OSNAP_END
                if mask & flag:
                    out.append((flag, self._result(match, flag)))

        # --- midpoint (indexed where available, else from the matched edge) ---
        if mask & OSNAP_MID:
            match = self._middle_match(locator, point, tolerance)
            if match is not None:
                out.append((OSNAP_MID, match))

        # --- centroid / centre ---
        if mask & OSNAP_CEN:
            centre = self._centre_match(locator, layer, point, tolerance)
            if centre is not None:
                out.append((OSNAP_CEN, centre))

        # --- edge-derived snaps: nearest, perpendicular, tangent, quadrant ---
        needs_edge = mask & (OSNAP_NEA | OSNAP_PER | OSNAP_TAN | OSNAP_QUA
                             | OSNAP_EXT)
        if needs_edge:
            edge = locator.nearestEdge(point, tolerance)
            if edge.isValid() and self._is_selectable(layer, edge.featureId()):
                self._from_edge(out, edge, layer, point, mask, base_point,
                                tolerance)

        # --- intersection: bounded to the aperture box, then GEOS ---
        if mask & OSNAP_INT:
            crossing = self._intersection_match(locator, layer, point,
                                                tolerance)
            if crossing is not None:
                out.append((OSNAP_INT, crossing))

    # ---- individual snap producers ----

    @staticmethod
    def _label_for(flag):
        for candidate, short, label in PRIORITY:
            if candidate == flag:
                return short, label
        return "SNP", "Snap"

    def _result(self, match, flag, point=None, distance=None):
        short, label = self._label_for(flag)
        matched = match.point() if point is None else QgsPointXY(*point)
        return SnapResult(
            (matched.x(), matched.y()), short, label,
            layer=match.layer() if hasattr(match, "layer") else None,
            feature_id=match.featureId() if hasattr(match, "featureId") else None,
            distance=match.distance() if distance is None else distance)

    def _middle_match(self, locator, point, tolerance):
        """Midpoint of the nearest segment."""
        finder = getattr(locator, "nearestMiddleOfSegment", None)
        if finder is not None:
            try:
                match = finder(point, tolerance)
                if match.isValid():
                    return self._result(match, OSNAP_MID)
            except (RuntimeError, TypeError):
                pass

        edge = locator.nearestEdge(point, tolerance)
        if not edge.isValid():
            return None
        try:
            start, end = edge.edgePoints()
        except (RuntimeError, ValueError):
            return None
        middle = ((start.x() + end.x()) / 2.0, (start.y() + end.y()) / 2.0)
        distance = math.hypot(middle[0] - point.x(), middle[1] - point.y())
        if distance > tolerance:
            return None
        return self._result(edge, OSNAP_MID, middle, distance)

    def _centre_match(self, locator, layer, point, tolerance):
        """Centre of a circle/arc, or the centroid of an area."""
        finder = getattr(locator, "nearestCentroid", None)
        if finder is not None:
            try:
                match = finder(point, tolerance)
                if match.isValid():
                    return self._result(match, OSNAP_CEN)
            except (RuntimeError, TypeError):
                pass

        # Curves: derive the true centre analytically from the matched entity,
        # which is what makes CEN land on a circle's centre rather than the
        # centroid of its vertex cloud.
        edge = locator.nearestEdge(point, tolerance)
        if not edge.isValid():
            return None
        centre = self._curve_centre(layer, edge.featureId())
        if centre is None:
            return None
        distance = math.hypot(centre[0] - point.x(), centre[1] - point.y())
        if distance > tolerance:
            return None
        return self._result(edge, OSNAP_CEN, centre, distance)

    def _curve_centre(self, layer, feature_id):
        """Analytic centre of a closed curve entity, if it has one."""
        geometry = self._geometry_of(layer, feature_id)
        if geometry is None:
            return None
        points = self._vertices(geometry)
        if len(points) < 3:
            return None
        circle = construct.circle_from_three_points(
            points[0], points[len(points) // 3], points[2 * len(points) // 3])
        if circle is None:
            return None
        centre, radius = circle
        # Only accept it when the sampled points really do lie on that circle.
        for sample in points[::max(1, len(points) // 6)]:
            if abs(construct.distance(centre, sample) - radius) > radius * 0.02:
                return None
        return centre

    def _from_edge(self, out, edge, layer, point, mask, base_point, tolerance):
        """Produce nearest / perpendicular / tangent / quadrant from one edge.

        Everything here is closed-form maths on the single entity the locator
        already found — no further searching.
        """
        cursor = (point.x(), point.y())

        if mask & OSNAP_NEA:
            out.append((OSNAP_NEA, self._result(edge, OSNAP_NEA)))

        try:
            start, end = edge.edgePoints()
            segment = ((start.x(), start.y()), (end.x(), end.y()))
        except (RuntimeError, ValueError):
            segment = None

        if segment and (mask & OSNAP_PER) and base_point is not None:
            foot = construct.perpendicular_foot(
                base_point, segment[0], segment[1], clamp=False)
            distance = construct.distance(foot, cursor)
            if distance <= tolerance:
                out.append((OSNAP_PER,
                            self._result(edge, OSNAP_PER, foot, distance)))

        if segment and (mask & OSNAP_EXT):
            # Extension: the cursor projected onto the segment's infinite line,
            # offered only when it lies beyond the segment itself.
            foot = construct.perpendicular_foot(
                cursor, segment[0], segment[1], clamp=False)
            clamped = construct.perpendicular_foot(
                cursor, segment[0], segment[1], clamp=True)
            if construct.distance(foot, clamped) > 1e-9:
                distance = construct.distance(foot, cursor)
                if distance <= tolerance:
                    out.append((OSNAP_EXT,
                                self._result(edge, OSNAP_EXT, foot, distance)))

        if mask & (OSNAP_QUA | OSNAP_TAN):
            centre = self._curve_centre(layer, edge.featureId())
            if centre is not None:
                geometry = self._geometry_of(layer, edge.featureId())
                points = self._vertices(geometry) if geometry else []
                if points:
                    radius = construct.distance(centre, points[0])

                    if mask & OSNAP_QUA:
                        for candidate in construct.quadrant_points(centre,
                                                                   radius):
                            distance = construct.distance(candidate, cursor)
                            if distance <= tolerance:
                                out.append((OSNAP_QUA, self._result(
                                    edge, OSNAP_QUA, candidate, distance)))

                    if (mask & OSNAP_TAN) and base_point is not None:
                        for candidate in construct.tangent_points(
                                base_point, centre, radius):
                            distance = construct.distance(candidate, cursor)
                            if distance <= tolerance:
                                out.append((OSNAP_TAN, self._result(
                                    edge, OSNAP_TAN, candidate, distance)))

    def _intersection_match(self, locator, layer, point, tolerance):
        """Intersection of the two nearest edges, bounded by the aperture.

        ``edgesInRect`` is an indexed query over a box the size of the snap
        aperture, so the candidate set is tiny — a handful of edges at most —
        and the pairwise test that follows is cheap. This is the query that,
        done unbounded, is the classic source of CAD-plugin lag.
        """
        rect = self._aperture_rect(point, tolerance)
        try:
            matches = locator.edgesInRect(rect)
        except (AttributeError, RuntimeError):
            return None
        if not matches or len(matches) < 2:
            return None

        segments = []
        for match in matches[:8]:            # bounded: never more than 8 edges
            if not self._is_selectable(layer, match.featureId()):
                continue
            try:
                start, end = match.edgePoints()
            except (RuntimeError, ValueError):
                continue
            segments.append((((start.x(), start.y()), (end.x(), end.y())),
                             match))

        cursor = (point.x(), point.y())
        best = None
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                (a1, a2), match = segments[i]
                (b1, b2), _other = segments[j]
                crossing = construct.line_intersection(a1, a2, b1, b2,
                                                       segment_only=True)
                if crossing is None:
                    continue
                distance = construct.distance(crossing, cursor)
                if distance <= tolerance and (best is None
                                              or distance < best[0]):
                    best = (distance, crossing, match)

        if best is None:
            return None
        distance, crossing, match = best
        return self._result(match, OSNAP_INT, crossing, distance)

    # ---- helpers ----

    @staticmethod
    def _aperture_rect(point, tolerance):
        from qgis.core import QgsRectangle
        return QgsRectangle(point.x() - tolerance, point.y() - tolerance,
                            point.x() + tolerance, point.y() + tolerance)

    @staticmethod
    def _geometry_of(layer, feature_id):
        if layer is None or feature_id is None:
            return None
        try:
            feature = layer.getFeature(feature_id)
        except (RuntimeError, KeyError):
            return None
        if feature is None or not feature.isValid():
            return None
        geometry = feature.geometry()
        return None if geometry is None or geometry.isEmpty() else geometry

    @staticmethod
    def _vertices(geometry):
        """Return a geometry's vertices as plain tuples."""
        if geometry is None:
            return []
        try:
            return [(v.x(), v.y()) for v in geometry.vertices()]
        except (AttributeError, RuntimeError):
            polyline = geometry.asPolyline()
            return [(p.x(), p.y()) for p in polyline] if polyline else []


def snap_marker_points(result, size_map_units):
    """Return the polyline outline of a snap marker for *result*.

    Each osnap has its own AutoCAD glyph — a square for endpoint, a triangle
    for midpoint, a circle for centre, a cross for intersection — and drawing
    the right one is a surprisingly large part of the CAD feel.
    """
    if result is None:
        return []
    x, y = result.point
    half = size_map_units / 2.0
    kind = result.snap_type

    if kind == "END":
        return [[(x - half, y - half), (x + half, y - half),
                 (x + half, y + half), (x - half, y + half),
                 (x - half, y - half)]]
    if kind == "MID":
        return [[(x - half, y - half), (x + half, y - half),
                 (x, y + half), (x - half, y - half)]]
    if kind in ("CEN", "NOD"):
        return [construct.circle_points((x, y), half, segments=16)]
    if kind == "INT":
        return [[(x - half, y - half), (x + half, y + half)],
                [(x - half, y + half), (x + half, y - half)]]
    if kind == "PER":
        return [[(x - half, y + half), (x - half, y - half),
                 (x + half, y - half)],
                [(x - half, y), (x, y), (x, y - half)]]
    if kind == "TAN":
        return [construct.circle_points((x, y), half, segments=16),
                [(x - half, y + half), (x + half, y + half)]]
    if kind == "QUA":
        return [[(x, y - half), (x + half, y), (x, y + half),
                 (x - half, y), (x, y - half)]]
    if kind == "EXT":
        return [[(x - half, y), (x + half, y)]]
    # NEAREST and anything else: an hourglass.
    return [[(x - half, y - half), (x + half, y - half),
             (x - half, y + half), (x + half, y + half),
             (x - half, y - half)]]
