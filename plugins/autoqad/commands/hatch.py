# -*- coding: utf-8 -*-
"""Hatch and fill commands — HATCH, SOLID, BHATCH.

Boundary detection uses GEOS: candidate curves near the pick point are noded
together with ``unaryUnion`` and then polygonised, and the resulting face
containing the pick point becomes the hatch boundary. That is exactly the job
``QgsGeometry`` already does well, so there is no boundary-walking algorithm
here to go slow or wrong.
"""

from qgis.core import QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsRectangle

from ..engine.command import Command
from ..engine.prompt import (
    ENTER, AnglePrompt, DistancePrompt, PointPrompt, SelectionPrompt,
    StringPrompt,
)
from ..geom import build
from ..style import hatches


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
            geometry = yield from self._boundary_from_selection()
        else:
            geometry = yield from self._boundary_from_pick()

        if geometry is None:
            return

        self.document.add_hatch(geometry, pattern=pattern,
                                pattern_scale=scale,
                                pattern_angle=angle_degrees)
        self.write("Hatch created with pattern {0}.".format(pattern))

    def _boundary_from_selection(self):
        selection = yield SelectionPrompt("Select boundary objects")
        if self.is_finished(selection) or not selection:
            return None

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
                    geometries.append(build.segmentised(QgsGeometry(geometry)))

        return self._polygonise(geometries, None)

    def _boundary_from_pick(self):
        point = yield PointPrompt("Pick internal point")
        if self.is_finished(point):
            return None

        geometries = self._candidates_near(point)
        if not geometries:
            self.write("No enclosing boundary found at that point.")
            return None

        result = self._polygonise(geometries, point)
        if result is None:
            self.write("That point is not inside a closed boundary.")
        return result

    def _candidates_near(self, point, reach_pixels=2000):
        """Collect curve geometries near the pick point.

        Bounded by a generous window around the pick rather than the whole
        drawing, so a large plan does not pay for every wall when hatching one
        room.
        """
        curves = self.document.table("aq_curves")
        if curves is None:
            return []

        canvas = self.context.canvas
        if canvas is not None:
            reach = canvas.mapUnitsPerPixel() * reach_pixels
        else:
            reach = 1000.0

        window = QgsRectangle(point[0] - reach, point[1] - reach,
                              point[0] + reach, point[1] + reach)
        request = QgsFeatureRequest().setFilterRect(window)
        request.setSubsetOfAttributes(["aq_layer"], curves.fields())

        geometries = []
        for feature in curves.getFeatures(request):
            cad = self.document.layers.get(feature.attribute("aq_layer"))
            if cad is not None and not cad.is_visible:
                continue
            geometry = feature.geometry()
            if geometry is not None and not geometry.isEmpty():
                geometries.append(build.segmentised(QgsGeometry(geometry)))
        return geometries

    @staticmethod
    def _polygonise(geometries, point):
        """Node the candidate curves and return the face containing *point*.

        With no point, returns the union of every face found — which is what
        the Select-boundary path wants.
        """
        if not geometries:
            return None

        try:
            noded = QgsGeometry.unaryUnion(geometries)
        except (AttributeError, RuntimeError):
            return None
        if noded is None or noded.isEmpty():
            return None

        try:
            faces = noded.polygonize()
        except (AttributeError, RuntimeError):
            faces = None

        if faces is None or faces.isEmpty():
            # Already-closed rings polygonise to nothing; try converting them.
            closed = [g for g in geometries if g.isGeosValid()]
            for geometry in closed:
                vertices = build.vertices_of(geometry)
                if len(vertices) > 3 and vertices[0] == vertices[-1]:
                    candidate = build.polygon(vertices)
                    if candidate is None:
                        continue
                    if point is None or candidate.contains(
                            QgsGeometry.fromPointXY(
                                QgsPointXY(point[0], point[1]))):
                        return candidate
            return None

        if point is None:
            return faces

        probe = QgsGeometry.fromPointXY(QgsPointXY(point[0], point[1]))
        parts = (faces.asGeometryCollection()
                 if faces.isMultipart() else [faces])

        # Smallest containing face — the room, not the building.
        best = None
        for part in parts:
            if part is None or part.isEmpty():
                continue
            if part.contains(probe):
                area = part.area()
                if best is None or area < best[0]:
                    best = (area, part)
        return best[1] if best else None


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
        geometry = helper._polygonise(geometries, point)
        if geometry is None:
            self.write("That point is not inside a closed boundary.")
            return

        self.document.add_hatch(geometry, pattern=hatches.SOLID,
                                pattern_scale=1.0, pattern_angle=0.0)
        self.write("Solid fill created.")


HATCH_COMMANDS = (HatchCommand, SolidCommand)
