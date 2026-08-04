# -*- coding: utf-8 -*-
"""Hatch and fill commands — HATCH, SOLID, BHATCH.

Boundary detection uses GEOS: candidate lines near the pick point are noded
together with ``unaryUnion`` and then polygonised, and the resulting face
containing the pick point becomes the hatch boundary. That is exactly the job
``QgsGeometry`` already does well, so there is no boundary-walking algorithm
here to go slow or wrong.

Two GEOS details the boundary code has to respect, both of which used to break
HATCH outright:

* ``QgsGeometry.polygonize`` is a **static** method taking the linework as a
  list — ``noded.polygonize()`` raises ``TypeError: not enough arguments``.
* Polygonising returns a *collection* of faces, while ``aq_polygons`` is a
  single-part ``Polygon`` table. Faces are therefore stored one hatch per
  face rather than as one multipart geometry the provider would reject.
"""

from qgis.core import QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsRectangle

from ..core.compat import GEOM_POLYGON
from ..core.document import LINES
from ..engine.command import Command
from ..engine.prompt import (
    ENTER, AnglePrompt, DistancePrompt, PointPrompt, SelectionPrompt,
    StringPrompt,
)
from ..geom import build
from ..style import hatches


def polygon_parts(geometry):
    """Flatten *geometry* into the single-part polygons the table can hold.

    ``polygonize`` hands back a geometry collection; a collection or a
    multipolygon written into a single-part ``Polygon`` layer is dropped by the
    provider, which is why this splitting is not optional.

    Type is tested with ``type()`` rather than ``asPolygon()``: the latter
    *raises* on anything that is not a polygon rather than returning nothing,
    so it cannot be used to ask the question.
    """
    if geometry is None or geometry.isEmpty():
        return []

    parts = []
    pending = [geometry]
    while pending:
        current = pending.pop(0)
        if current is None or current.isEmpty():
            continue
        if current.isMultipart():
            pending.extend(current.asGeometryCollection() or [])
        elif current.type() == GEOM_POLYGON:
            parts.append(current)
    return parts


def rings_as_polygons(geometries):
    """Turn already-closed rings straight into polygons.

    The fallback for linework GEOS declines to polygonise — a single closed
    rectangle or circle drawn as one entity, for instance.
    """
    polygons = []
    for geometry in geometries:
        vertices = build.vertices_of(geometry)
        if len(vertices) > 3 and vertices[0] == vertices[-1]:
            candidate = build.polygon(vertices)
            if candidate is not None and not candidate.isEmpty():
                polygons.append(candidate)
    return polygons


def as_linework(geometry):
    """Return *geometry* as linework — a polygon contributes its boundary.

    The polygonizer only ever sees ``LineString`` components, so selecting an
    existing hatch as a boundary object would otherwise contribute nothing.
    """
    if geometry is None or geometry.isEmpty():
        return geometry
    if geometry.type() != GEOM_POLYGON:
        return geometry
    try:
        boundary = geometry.constGet().boundary()
    except (AttributeError, RuntimeError):
        return geometry
    if boundary is None:
        return geometry
    return QgsGeometry(boundary)


class HatchCommand(Command):
    """Fill an enclosed area with an AutoCAD hatch pattern."""

    name = "HATCH"
    aliases = ("H", "BHATCH")
    description = "Fill an enclosed area with a hatch pattern."
    group = "draw"

    def run(self):
        pattern = yield StringPrompt(
            "Enter pattern name or", options=["?", "Select"],
            default=self.var("HPNAME"))

        if pattern == "?":
            self.write("Patterns: " + ", ".join(hatches.names(
                self.document.pattern_table)))
            return

        if self.is_cancelled(pattern):
            return

        pick_boundary = pattern == "Select"
        if pattern is ENTER or pick_boundary:
            pattern = self.var("HPNAME")
        pattern = str(pattern).upper()

        if pattern not in self.document.pattern_table:
            self.write("Unknown pattern '{0}'. Using {1}.".format(
                pattern, self.var("HPNAME")))
            pattern = self.var("HPNAME")

        scale = yield DistancePrompt("Specify pattern scale",
                                     default=self.var("HPSCALE"))
        if self.is_cancelled(scale):
            return
        scale = self.var("HPSCALE") if scale is ENTER else float(scale)

        angle = yield AnglePrompt("Specify pattern angle",
                                  default=self.var("HPANG"))
        if self.is_cancelled(angle):
            return
        import math
        angle_degrees = (self.var("HPANG") if angle is ENTER
                         else math.degrees(float(angle)))

        self.set_var("HPNAME", pattern)
        self.set_var("HPSCALE", scale)
        self.set_var("HPANG", angle_degrees)

        if pick_boundary:
            boundaries = yield from self._boundary_from_selection()
        else:
            boundaries = yield from self._boundary_from_pick()

        if not boundaries:
            return

        created = 0
        for boundary in boundaries:
            if self.document.add_hatch(boundary, pattern=pattern,
                                       pattern_scale=scale,
                                       pattern_angle=angle_degrees) is not None:
                created += 1

        if not created:
            self.write("Hatch failed — the boundary could not be stored. "
                       "Check that the current layer is unlocked.")
        elif created == 1:
            self.write("Hatch created with pattern {0}.".format(pattern))
        else:
            self.write("{0} hatches created with pattern {1}.".format(
                created, pattern))

    def _boundary_from_selection(self):
        selection = yield SelectionPrompt("Select boundary objects")
        if self.is_finished(selection) or not selection:
            return []

        geometries = []
        for table_name, feature_id in selection:
            layer = self.document.table(table_name)
            if layer is None:
                continue
            try:
                feature = layer.getFeature(feature_id)
            except (RuntimeError, KeyError):
                continue
            if feature is not None and feature.isValid():
                geometry = feature.geometry()
                if geometry is not None and not geometry.isEmpty():
                    geometries.append(as_linework(
                        build.segmentised(QgsGeometry(geometry))))

        boundaries = self._polygonise(geometries, None)
        if not boundaries:
            self.write("Those objects do not enclose an area.")
        return boundaries

    def _boundary_from_pick(self):
        point = yield PointPrompt("Pick internal point")
        if self.is_finished(point):
            return []

        geometries = self._candidates_near(point)
        if not geometries:
            self.write("No enclosing boundary found at that point.")
            return []

        boundaries = self._polygonise(geometries, point)
        if not boundaries:
            self.write("That point is not inside a closed boundary.")
        return boundaries

    def _candidates_near(self, point, reach_pixels=2000):
        """Collect line geometries near the pick point.

        Bounded by a generous window around the pick rather than the whole
        drawing, so a large plan does not pay for every wall when hatching one
        room.
        """
        lines = self.document.table(LINES)
        if lines is None:
            return []

        canvas = self.context.canvas
        if canvas is not None:
            reach = canvas.mapUnitsPerPixel() * reach_pixels
        else:
            reach = 1000.0

        window = QgsRectangle(point[0] - reach, point[1] - reach,
                              point[0] + reach, point[1] + reach)
        request = QgsFeatureRequest().setFilterRect(window)
        request.setSubsetOfAttributes(["aq_layer"], lines.fields())

        geometries = []
        for feature in lines.getFeatures(request):
            cad = self.document.layers.get(feature.attribute("aq_layer"))
            if cad is not None and not cad.is_visible:
                continue
            geometry = feature.geometry()
            if geometry is not None and not geometry.isEmpty():
                geometries.append(build.segmentised(QgsGeometry(geometry)))
        return geometries

    @staticmethod
    def _polygonise(geometries, point):
        """Node the candidate lines and return the enclosed faces.

        Returns a list of single-part polygons: the one face containing
        *point*, or — with no point — every face the linework encloses, which
        is what the Select-boundary path wants.

        ``polygonize`` is static and takes a list. Calling it on the unioned
        geometry (``noded.polygonize()``) raises ``TypeError: not enough
        arguments``, which is the failure this used to report; ``TypeError`` is
        caught alongside the rest so a future signature change degrades to
        "no boundary found" rather than aborting the command.
        """
        geometries = [g for g in geometries if g is not None and not g.isEmpty()]
        if not geometries:
            return []

        try:
            noded = QgsGeometry.unaryUnion(geometries)
        except (AttributeError, RuntimeError, TypeError):
            noded = None

        faces = None
        if noded is not None and not noded.isEmpty():
            try:
                # Static, and the linework goes in as a list. The union has
                # already noded every crossing, so one geometry is enough.
                faces = QgsGeometry.polygonize([noded])
            except (AttributeError, RuntimeError, TypeError):
                faces = None

        parts = polygon_parts(faces)
        if not parts:
            # Nothing to node — a lone closed ring, say. Convert it directly.
            parts = rings_as_polygons(geometries)
        if not parts or point is None:
            return parts

        probe = QgsGeometry.fromPointXY(QgsPointXY(point[0], point[1]))

        # Smallest containing face — the room, not the building.
        best = None
        for part in parts:
            if part.contains(probe):
                area = part.area()
                if best is None or area < best[0]:
                    best = (area, part)
        return [best[1]] if best else []


class SolidCommand(Command):
    """Fill an area with a solid colour."""

    name = "SOLID"
    aliases = ("SO",)
    description = "Fill an enclosed area with a solid colour."
    group = "draw"

    def run(self):
        point = yield PointPrompt("Pick internal point")
        if self.is_finished(point):
            return

        helper = HatchCommand(self.context)
        geometries = helper._candidates_near(point)
        boundaries = helper._polygonise(geometries, point)
        if not boundaries:
            self.write("That point is not inside a closed boundary.")
            return

        created = 0
        for boundary in boundaries:
            if self.document.add_hatch(boundary, pattern=hatches.SOLID,
                                       pattern_scale=1.0,
                                       pattern_angle=0.0) is not None:
                created += 1

        if created:
            self.write("Solid fill created.")
        else:
            self.write("Solid fill failed — the boundary could not be stored. "
                       "Check that the current layer is unlocked.")


HATCH_COMMANDS = (HatchCommand, SolidCommand)
