# -*- coding: utf-8 -*-
"""Modify commands — ERASE, MOVE, COPY, ROTATE, SCALE, MIRROR, OFFSET, TRIM …

Where a transformation exists in GEOS, it is used: OFFSET goes through
``QgsGeometry.offsetCurve``, TRIM/EXTEND through ``intersection``, and every
affine move through ``QgsGeometry.translate``/``rotate``. Only the closed-form
constructions GEOS does not provide — fillet arcs, chamfer endpoints — come
from :mod:`..geom.construct`.
"""

import math

from qgis.core import QgsGeometry, QgsPointXY

from ..engine.command import Command
from ..engine.prompt import (
    ENTER, AnglePrompt, DistancePrompt, IntegerPrompt, KeywordPrompt,
    PointPrompt, RubberGeometry, RubberLine, SelectionPrompt,
)
from ..geom import build, construct


class _SelectionCommand(Command):
    """Shared plumbing for commands that operate on a selection."""

    needs_selection = True

    def features_of(self, selection):
        """Return ``[(table_name, feature)]`` for a selection list."""
        result = []
        for table_name, feature_id in selection or []:
            layer = self.document.table(table_name)
            if layer is None:
                continue
            try:
                feature = layer.getFeature(feature_id)
            except (RuntimeError, KeyError):
                continue
            if feature is not None and feature.isValid():
                result.append((table_name, feature))
        return result

    def geometries_of(self, selection):
        return [f.geometry() for _t, f in self.features_of(selection)
                if f.geometry() is not None and not f.geometry().isEmpty()]

    def apply_geometry(self, table_name, feature_id, geometry):
        """Replace one entity's geometry."""
        return self.document.set_geometry(table_name, feature_id, geometry)

    def transform_selection(self, selection, transform):
        """Apply *transform(geometry) -> geometry* to every selected entity."""
        touched = 0
        for table_name, feature in self.features_of(selection):
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            new_geometry = transform(QgsGeometry(geometry))
            if new_geometry is not None and self.apply_geometry(
                    table_name, feature.id(), new_geometry):
                touched += 1
        self.document.refresh()
        return touched

    def copy_selection(self, selection, transform):
        """Copy every selected entity through *transform*."""
        made = 0
        for table_name, feature in self.features_of(selection):
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            new_geometry = transform(QgsGeometry(geometry))
            if new_geometry is None:
                continue
            if self._clone(table_name, feature, new_geometry) is not None:
                made += 1
        self.document.refresh()
        return made

    def _clone(self, table_name, feature, geometry):
        """Add a copy of *feature* carrying *geometry* and its original style."""
        return self.document.add_entity(
            table_name, geometry,
            feature.attribute("aq_type") or "LINE",
            layer_name=feature.attribute("aq_layer"),
            color=feature.attribute("aq_color"),
            linetype=feature.attribute("aq_ltype"),
            lineweight=feature.attribute("aq_lw"),
            ltscale=feature.attribute("aq_ltscale"))


class EraseCommand(_SelectionCommand):
    name = "ERASE"
    aliases = ("E", "DELETE")
    description = "Delete selected objects."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to erase")
        if self.is_finished(selection) or not selection:
            return

        by_table = {}
        for table_name, feature_id in selection:
            by_table.setdefault(table_name, []).append(feature_id)

        removed = sum(self.document.delete(table, ids)
                      for table, ids in by_table.items())
        self.write("{0} object(s) erased.".format(removed))


class MoveCommand(_SelectionCommand):
    name = "MOVE"
    aliases = ("M",)
    description = "Move selected objects."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to move")
        if self.is_finished(selection) or not selection:
            return

        base = yield PointPrompt("Specify base point")
        if self.is_finished(base):
            return

        target = yield PointPrompt(
            "Specify second point of displacement",
            rubber=RubberGeometry(self.geometries_of(selection), base),
            base_point=base)
        if self.is_finished(target):
            return

        dx = target[0] - base[0]
        dy = target[1] - base[1]

        def translate(geometry):
            geometry.translate(dx, dy)
            return geometry

        moved = self.transform_selection(selection, translate)
        self.write("{0} object(s) moved.".format(moved))


class CopyCommand(_SelectionCommand):
    name = "COPY"
    aliases = ("CO", "CP")
    description = "Copy selected objects."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to copy")
        if self.is_finished(selection) or not selection:
            return

        base = yield PointPrompt("Specify base point")
        if self.is_finished(base):
            return

        made = 0
        while True:
            target = yield PointPrompt(
                "Specify second point or", options=["Exit"],
                rubber=RubberGeometry(self.geometries_of(selection), base),
                base_point=base)
            if self.is_finished(target) or target == "Exit":
                break

            dx = target[0] - base[0]
            dy = target[1] - base[1]

            def translate(geometry, dx=dx, dy=dy):
                geometry.translate(dx, dy)
                return geometry

            made += self.copy_selection(selection, translate)

        self.write("{0} copy/copies made.".format(made))


class RotateCommand(_SelectionCommand):
    name = "ROTATE"
    aliases = ("RO",)
    description = "Rotate selected objects about a base point."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to rotate")
        if self.is_finished(selection) or not selection:
            return

        base = yield PointPrompt("Specify base point")
        if self.is_finished(base):
            return

        angle = yield AnglePrompt(
            "Specify rotation angle or", options=["Copy"],
            rubber=RubberGeometry(self.geometries_of(selection), base,
                                  mode="rotate"),
            base_point=base)
        if self.is_finished(angle):
            return

        make_copy = angle == "Copy"
        if make_copy:
            angle = yield AnglePrompt("Specify rotation angle",
                                      base_point=base)
            if self.is_finished(angle):
                return

        degrees = math.degrees(float(angle))
        anchor = QgsPointXY(base[0], base[1])

        def rotate(geometry):
            # QgsGeometry.rotate takes clockwise degrees.
            geometry.rotate(-degrees, anchor)
            return geometry

        count = (self.copy_selection(selection, rotate) if make_copy
                 else self.transform_selection(selection, rotate))
        self.write("{0} object(s) rotated.".format(count))


class ScaleCommand(_SelectionCommand):
    name = "SCALE"
    aliases = ("SC",)
    description = "Scale selected objects about a base point."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to scale")
        if self.is_finished(selection) or not selection:
            return

        base = yield PointPrompt("Specify base point")
        if self.is_finished(base):
            return

        factor = yield DistancePrompt(
            "Specify scale factor", base_point=base,
            rubber=RubberGeometry(self.geometries_of(selection), base,
                                  mode="scale"))
        if self.is_finished(factor) or float(factor) <= 0:
            return

        ratio = float(factor)

        def scale(geometry):
            return build.scaled(geometry, base, ratio)

        count = self.transform_selection(selection, scale)
        self.write("{0} object(s) scaled.".format(count))


class MirrorCommand(_SelectionCommand):
    name = "MIRROR"
    aliases = ("MI",)
    description = "Mirror selected objects across an axis."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to mirror")
        if self.is_finished(selection) or not selection:
            return

        first = yield PointPrompt("Specify first point of mirror line")
        if self.is_finished(first):
            return
        second = yield PointPrompt("Specify second point of mirror line",
                                   rubber=RubberLine(first), base_point=first)
        if self.is_finished(second):
            return

        erase = yield KeywordPrompt("Erase source objects?", ["Yes", "No"],
                                    default="No")
        if self.is_cancelled(erase):
            return
        delete_source = erase == "Yes"

        def reflect(geometry):
            return build.mirrored(geometry, first, second)

        count = self.copy_selection(selection, reflect)

        if delete_source:
            by_table = {}
            for table_name, feature_id in selection:
                by_table.setdefault(table_name, []).append(feature_id)
            for table, ids in by_table.items():
                self.document.delete(table, ids)

        self.write("{0} object(s) mirrored.".format(count))


class OffsetCommand(_SelectionCommand):
    """Offset a curve by a distance — GEOS does the hard part."""

    name = "OFFSET"
    aliases = ("O",)
    description = "Create parallel copies of a curve at a distance."
    group = "modify"

    def run(self):
        distance = yield DistancePrompt("Specify offset distance")
        if self.is_finished(distance) or float(distance) <= 0:
            return
        distance = float(distance)

        while True:
            selection = yield SelectionPrompt(
                "Select object to offset", single=True)
            if self.is_finished(selection) or not selection:
                return

            features = self.features_of(selection)
            if not features:
                continue
            table_name, feature = features[0]

            side = yield PointPrompt("Specify point on side to offset")
            if self.is_finished(side):
                return

            geometry = feature.geometry()
            offset = self._offset(geometry, distance, side)
            if offset is None:
                self.write("Unable to offset that object.")
                continue

            self._clone(table_name, feature, offset)
            self.document.refresh()

    @staticmethod
    def _offset(geometry, distance, side_point):
        """Offset *geometry*, choosing the side nearest *side_point*."""
        source = build.segmentised(QgsGeometry(geometry))
        cursor = QgsPointXY(side_point[0], side_point[1])

        best = None
        for signed in (distance, -distance):
            try:
                candidate = source.offsetCurve(signed, 8, 1, 5.0)
            except (AttributeError, RuntimeError):
                candidate = None
            if candidate is None or candidate.isEmpty():
                continue
            gap = candidate.distance(QgsGeometry.fromPointXY(cursor))
            if best is None or gap < best[0]:
                best = (gap, candidate)
        return best[1] if best else None


class FilletCommand(_SelectionCommand):
    """Round the corner between two lines with an arc."""

    name = "FILLET"
    aliases = ("F",)
    description = "Round a corner between two lines."
    group = "modify"

    def run(self):
        answer = yield DistancePrompt(
            "Specify fillet radius or", options=["Radius"], default=0)
        if self.is_cancelled(answer):
            return
        if answer is ENTER:
            radius = 0.0
        elif answer == "Radius":
            answer = yield DistancePrompt("Specify fillet radius")
            if self.is_finished(answer):
                return
            radius = float(answer)
        else:
            radius = float(answer)

        first = yield SelectionPrompt("Select first object", single=True)
        if self.is_finished(first) or not first:
            return
        second = yield SelectionPrompt("Select second object", single=True)
        if self.is_finished(second) or not second:
            return

        features_a = self.features_of(first)
        features_b = self.features_of(second)
        if not features_a or not features_b:
            return

        table_a, feature_a = features_a[0]
        table_b, feature_b = features_b[0]

        ends_a = build.endpoints_of(feature_a.geometry())
        ends_b = build.endpoints_of(feature_b.geometry())
        if ends_a is None or ends_b is None:
            self.write("FILLET needs two line objects.")
            return

        if radius <= 0:
            # A zero radius simply extends both lines to their intersection.
            corner = construct.line_intersection(
                ends_a[0], ends_a[1], ends_b[0], ends_b[1])
            if corner is None:
                self.write("Those objects are parallel.")
                return
            self._trim_to(table_a, feature_a, ends_a, corner)
            self._trim_to(table_b, feature_b, ends_b, corner)
            self.document.refresh()
            return

        result = construct.fillet_arc(ends_a[0], ends_a[1],
                                      ends_b[0], ends_b[1], radius)
        if result is None:
            self.write("Unable to fillet with that radius.")
            return

        center, tangent_a, tangent_b, ccw = result
        self._trim_to(table_a, feature_a, ends_a, tangent_a)
        self._trim_to(table_b, feature_b, ends_b, tangent_b)

        through = construct.arc_midpoint(
            center, radius,
            construct.angle_of(center, tangent_a),
            construct.angle_of(center, tangent_b), ccw)
        arc = build.arc_three_points(tangent_a, through, tangent_b)
        if arc is not None:
            self._clone(table_a, feature_a, arc)
        self.document.refresh()

    def _trim_to(self, table_name, feature, ends, corner):
        """Move whichever endpoint is nearer *corner* onto it."""
        start, end = ends
        if construct.distance(start, corner) < construct.distance(end, corner):
            new_points = [corner, end]
        else:
            new_points = [start, corner]
        self.apply_geometry(table_name, feature.id(),
                            build.polyline(new_points))


class TrimExtendCommand(_SelectionCommand):
    """Shared implementation for TRIM and EXTEND."""

    _extend = False

    def run(self):
        boundary = yield SelectionPrompt(
            "Select boundary edges" if not self._extend
            else "Select boundary edges for extension")
        if self.is_finished(boundary) or not boundary:
            return

        boundary_geometries = self.geometries_of(boundary)
        if not boundary_geometries:
            return

        while True:
            selection = yield SelectionPrompt(
                "Select object to trim" if not self._extend
                else "Select object to extend", single=True)
            if self.is_finished(selection) or not selection:
                return

            features = self.features_of(selection)
            if not features:
                continue
            table_name, feature = features[0]

            updated = self._apply(feature.geometry(), boundary_geometries)
            if updated is None:
                self.write("No intersection with the boundary.")
                continue
            self.apply_geometry(table_name, feature.id(), updated)
            self.document.refresh()

    def _apply(self, geometry, boundaries):
        ends = build.endpoints_of(geometry)
        if ends is None:
            return None
        start, end = ends

        crossings = []
        for boundary in boundaries:
            other = build.endpoints_of(boundary)
            if other is None:
                continue
            crossing = construct.line_intersection(
                start, end, other[0], other[1],
                segment_only=not self._extend)
            if crossing is not None:
                crossings.append(crossing)

        if not crossings:
            return None

        if self._extend:
            # Extend whichever end is nearer the boundary out to it.
            target = min(crossings,
                         key=lambda c: min(construct.distance(c, start),
                                           construct.distance(c, end)))
            if construct.distance(target, start) < construct.distance(target,
                                                                      end):
                return build.polyline([target, end])
            return build.polyline([start, target])

        # Trim: cut the segment back to the nearest crossing.
        target = min(crossings, key=lambda c: construct.distance(c, end))
        return build.polyline([start, target])


class TrimCommand(TrimExtendCommand):
    name = "TRIM"
    aliases = ("TR",)
    description = "Trim objects back to a boundary edge."
    group = "modify"
    _extend = False


class ExtendCommand(TrimExtendCommand):
    name = "EXTEND"
    aliases = ("EX",)
    description = "Extend objects out to a boundary edge."
    group = "modify"
    _extend = True


class ArrayCommand(_SelectionCommand):
    """Rectangular and polar arrays."""

    name = "ARRAY"
    aliases = ("AR",)
    description = "Create a rectangular or polar array of objects."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to array")
        if self.is_finished(selection) or not selection:
            return

        kind = yield KeywordPrompt("Enter array type",
                                   ["Rectangular", "POlar"],
                                   default="Rectangular")
        if self.is_cancelled(kind):
            return
        if kind is ENTER:
            kind = "Rectangular"

        if kind == "POlar":
            yield from self._polar(selection)
        else:
            yield from self._rectangular(selection)

    def _rectangular(self, selection):
        rows = yield IntegerPrompt("Enter number of rows", minimum=1,
                                   default=1)
        if self.is_cancelled(rows):
            return
        rows = 1 if rows is ENTER else int(rows)

        columns = yield IntegerPrompt("Enter number of columns", minimum=1,
                                      default=1)
        if self.is_cancelled(columns):
            return
        columns = 1 if columns is ENTER else int(columns)

        row_gap = yield DistancePrompt("Specify distance between rows")
        if self.is_finished(row_gap):
            return
        column_gap = yield DistancePrompt("Specify distance between columns")
        if self.is_finished(column_gap):
            return

        made = 0
        for row in range(rows):
            for column in range(columns):
                if row == 0 and column == 0:
                    continue
                dx = column * float(column_gap)
                dy = row * float(row_gap)

                def translate(geometry, dx=dx, dy=dy):
                    geometry.translate(dx, dy)
                    return geometry

                made += self.copy_selection(selection, translate)
        self.write("{0} object(s) created.".format(made))

    def _polar(self, selection):
        center = yield PointPrompt("Specify center point of array")
        if self.is_finished(center):
            return
        count = yield IntegerPrompt("Enter number of items", minimum=2,
                                    default=4)
        if self.is_cancelled(count):
            return
        count = 4 if count is ENTER else int(count)

        fill = yield AnglePrompt("Specify angle to fill", default=360)
        if self.is_cancelled(fill):
            return
        fill_angle = (2.0 * math.pi if fill is ENTER else float(fill))

        anchor = QgsPointXY(center[0], center[1])
        made = 0
        for index in range(1, count):
            degrees = math.degrees(fill_angle * index / float(count))

            def rotate(geometry, degrees=degrees):
                geometry.rotate(-degrees, anchor)
                return geometry

            made += self.copy_selection(selection, rotate)
        self.write("{0} object(s) created.".format(made))


class ExplodeCommand(_SelectionCommand):
    """Break a polyline into its individual segments."""

    name = "EXPLODE"
    aliases = ("X",)
    description = "Break polylines into separate segments."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to explode")
        if self.is_finished(selection) or not selection:
            return

        made = 0
        for table_name, feature in self.features_of(selection):
            points = build.vertices_of(feature.geometry())
            if len(points) < 3:
                continue
            for index in range(len(points) - 1):
                segment = build.line(points[index], points[index + 1])
                if segment is not None:
                    self._clone(table_name, feature, segment)
                    made += 1
            self.document.delete(table_name, [feature.id()])

        self.document.refresh()
        self.write("{0} segment(s) created.".format(made))


class JoinCommand(_SelectionCommand):
    """Join contiguous curves into one polyline."""

    name = "JOIN"
    aliases = ("J",)
    description = "Join contiguous curves into a single polyline."
    group = "modify"

    def run(self):
        selection = yield SelectionPrompt("Select objects to join")
        if self.is_finished(selection) or not selection:
            return

        features = self.features_of(selection)
        if len(features) < 2:
            self.write("Select at least two objects.")
            return

        chains = [build.vertices_of(f.geometry()) for _t, f in features]
        chains = [c for c in chains if len(c) >= 2]
        if not chains:
            return

        merged = chains.pop(0)
        tolerance = 1e-6
        progress = True
        while chains and progress:
            progress = False
            for index, chain in enumerate(list(chains)):
                if construct.are_coincident(merged[-1], chain[0], tolerance):
                    merged.extend(chain[1:])
                elif construct.are_coincident(merged[-1], chain[-1],
                                              tolerance):
                    merged.extend(list(reversed(chain))[1:])
                elif construct.are_coincident(merged[0], chain[-1], tolerance):
                    merged = chain[:-1] + merged
                elif construct.are_coincident(merged[0], chain[0], tolerance):
                    merged = list(reversed(chain))[:-1] + merged
                else:
                    continue
                chains.remove(chain)
                progress = True
                break

        if chains:
            self.write("Some objects were not contiguous and were skipped.")

        table_name, feature = features[0]
        closed = construct.are_coincident(merged[0], merged[-1])
        geometry = build.polyline(merged, closed=closed)
        if geometry is None:
            return

        self._clone(table_name, feature, geometry)
        for name, item in features:
            self.document.delete(name, [item.id()])
        self.document.refresh()


MODIFY_COMMANDS = (
    EraseCommand, MoveCommand, CopyCommand, RotateCommand, ScaleCommand,
    MirrorCommand, OffsetCommand, FilletCommand, TrimCommand, ExtendCommand,
    ArrayCommand, ExplodeCommand, JoinCommand,
)
