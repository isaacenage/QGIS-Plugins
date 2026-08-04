# -*- coding: utf-8 -*-
"""Drawing commands — LINE, PLINE, ARC, CIRCLE, RECTANG, POLYGON, ELLIPSE …

Every command reads as its prompt sequence, top to bottom, because a command is
a generator: ``yield`` a prompt, receive the answer, carry on. There is no step
counter and no dispatch table — the control flow *is* the AutoCAD prompt flow.
"""

import math

from ..core.document import LINES
from ..engine.command import Command
from ..engine.prompt import (
    CANCEL, ENTER, AnglePrompt, DistancePrompt, IntegerPrompt, KeywordPrompt,
    PointPrompt, RubberArc, RubberCircle, RubberLine, RubberPolyline,
    RubberRectangle, StringPrompt,
)
from ..geom import build, construct


class LineCommand(Command):
    """Draw a run of straight segments, each a separate entity."""

    name = "LINE"
    aliases = ("L",)
    description = "Draw straight line segments."
    group = "draw"

    def run(self):
        start = yield PointPrompt("Specify first point")
        if self.is_finished(start):
            return

        first = start
        previous = start
        drawn = []

        while True:
            options = ["Undo"] + (["Close"] if len(drawn) >= 2 else [])
            answer = yield PointPrompt(
                "Specify next point or", options=options,
                rubber=RubberLine(previous), base_point=previous)

            if self.is_finished(answer):
                return

            if answer == "Undo":
                if drawn:
                    self.document.delete(LINES, [drawn.pop()])
                    previous = first if not drawn else previous
                    if drawn:
                        previous = self._end_of(drawn[-1])
                    else:
                        previous = first
                else:
                    self.write("Nothing to undo.")
                continue

            if answer == "Close":
                geometry = build.line(previous, first)
                feature_id = self.document.add_curve(geometry, "LINE")
                if feature_id is not None:
                    drawn.append(feature_id)
                return

            geometry = build.line(previous, answer)
            feature_id = self.document.add_curve(geometry, "LINE")
            if feature_id is not None:
                drawn.append(feature_id)
            previous = answer

    def _end_of(self, feature_id):
        layer = self.document.table(LINES)
        feature = layer.getFeature(feature_id)
        ends = build.endpoints_of(feature.geometry())
        return ends[1] if ends else None


class PolylineCommand(Command):
    """Draw a connected polyline, optionally with arc segments."""

    name = "PLINE"
    aliases = ("PL",)
    description = "Draw a polyline with straight and arc segments."
    group = "draw"

    def run(self):
        start = yield PointPrompt("Specify start point")
        if self.is_finished(start):
            return

        # Segments, not just vertices: an arc segment carries its own
        # through-point, which is what lets it be built as a true circular
        # arc instead of a straight chord bent through that point.
        segments = []
        arc_mode = False

        while True:
            points = self._vertices(start, segments)
            options = ["Arc" if not arc_mode else "Line", "Undo"]
            if len(segments) >= 2:
                options.append("Close")

            message = ("Specify next point of arc or" if arc_mode
                       else "Specify next point or")
            answer = yield PointPrompt(
                message, options=options,
                rubber=RubberPolyline(points), base_point=points[-1])

            if self.is_finished(answer):
                break

            if answer == "Arc":
                arc_mode = True
                continue
            if answer == "Line":
                arc_mode = False
                continue
            if answer == "Undo":
                if segments:
                    segments.pop()
                else:
                    self.write("Nothing to undo.")
                continue
            if answer == "Close":
                segments.append(self._segment(arc_mode, points, start))
                break

            segments.append(self._segment(arc_mode, points, answer))

        if not segments:
            return

        vertices = self._vertices(start, segments)
        closed = construct.are_coincident(vertices[0], vertices[-1])
        geometry = build.compound_curve(start, segments)
        if geometry is not None:
            self.document.add_curve(geometry, "PLINE", closed=closed)

    def _segment(self, arc_mode, points, target):
        """Build one polyline segment ending at *target*."""
        if not arc_mode:
            return ("line", target)
        # A polyline arc leaves the previous segment tangentially; the tangent
        # through-point is what makes the run continuous.
        return ("arc", self._tangent_through(points, target), target)

    @staticmethod
    def _vertices(start, segments):
        """Every vertex walked so far — what the rubber-band preview draws."""
        points = [start]
        for segment in segments:
            points.extend(segment[1:])
        return points

    @staticmethod
    def _tangent_through(points, target):
        """Mid-point of an arc leaving the previous segment tangentially."""
        if len(points) < 2:
            return construct.midpoint(points[-1], target)
        previous = points[-1]
        direction = construct.angle_of(points[-2], previous)
        chord = construct.angle_of(previous, target)
        sweep = 2.0 * (chord - direction)
        length = construct.distance(previous, target)
        if abs(math.sin(sweep / 2.0)) < 1e-9:
            return construct.midpoint(previous, target)
        radius = abs(length / (2.0 * math.sin(sweep / 2.0)))
        centre_angle = direction + math.pi / 2.0
        centre = construct.point_at(previous, centre_angle, radius)
        start_angle = construct.angle_of(centre, previous)
        end_angle = construct.angle_of(centre, target)
        return construct.arc_midpoint(centre, radius, start_angle, end_angle,
                                      sweep > 0)


class RectangleCommand(Command):
    """Draw an axis-aligned rectangle from two opposite corners."""

    name = "RECTANG"
    aliases = ("REC", "RECTANGLE")
    description = "Draw a rectangle from two corners."
    group = "draw"

    def run(self):
        first = yield PointPrompt("Specify first corner point or",
                                  options=["Dimensions"])
        if self.is_finished(first):
            return

        if first == "Dimensions":
            corner = yield PointPrompt("Specify first corner point")
            if self.is_finished(corner):
                return
            width = yield DistancePrompt("Specify width", base_point=corner)
            if self.is_finished(width):
                return
            height = yield DistancePrompt("Specify height", base_point=corner)
            if self.is_finished(height):
                return
            ring = construct.rectangle_from_dimensions(corner, width, height)
        else:
            second = yield PointPrompt(
                "Specify other corner point",
                rubber=RubberRectangle(first), base_point=first)
            if self.is_finished(second):
                return
            ring = construct.rectangle_points(first, second)

        geometry = build.polyline(ring, closed=True)
        if geometry is not None:
            self.document.add_curve(geometry, "RECTANGLE", closed=True)


class CircleCommand(Command):
    """Draw a circle by centre-radius, diameter, or two/three points."""

    name = "CIRCLE"
    aliases = ("C",)
    description = "Draw a circle."
    group = "draw"

    def run(self):
        answer = yield PointPrompt(
            "Specify center point for circle or",
            options=["3P", "2P", "Ttr"])
        if self.is_finished(answer):
            return

        if answer == "3P":
            geometry = yield from self._three_point()
        elif answer == "2P":
            geometry = yield from self._two_point()
        elif answer == "Ttr":
            geometry = yield from self._tangent_tangent_radius()
        else:
            geometry = yield from self._center_radius(answer)

        if geometry is not None:
            self.document.add_curve(geometry, "CIRCLE", closed=True)

    def _center_radius(self, center):
        answer = yield DistancePrompt(
            "Specify radius of circle or", options=["Diameter"],
            rubber=RubberCircle(center), base_point=center)
        if self.is_finished(answer):
            return None
        if answer == "Diameter":
            diameter = yield DistancePrompt(
                "Specify diameter of circle",
                rubber=RubberCircle(center), base_point=center)
            if self.is_finished(diameter):
                return None
            radius = float(diameter) / 2.0
        else:
            radius = float(answer)
        return build.circle(center, radius) if radius > 0 else None

    def _two_point(self):
        first = yield PointPrompt("Specify first end point of diameter")
        if self.is_finished(first):
            return None
        second = yield PointPrompt("Specify second end point of diameter",
                                   rubber=RubberLine(first), base_point=first)
        if self.is_finished(second):
            return None
        center, radius = construct.circle_from_two_points(first, second)
        return build.circle(center, radius) if radius > 0 else None

    def _three_point(self):
        first = yield PointPrompt("Specify first point on circle")
        if self.is_finished(first):
            return None
        second = yield PointPrompt("Specify second point on circle",
                                   rubber=RubberLine(first), base_point=first)
        if self.is_finished(second):
            return None
        third = yield PointPrompt("Specify third point on circle",
                                  rubber=RubberArc(first, second),
                                  base_point=second)
        if self.is_finished(third):
            return None
        result = construct.circle_from_three_points(first, second, third)
        if result is None:
            self.write("Those points are collinear — no circle exists.")
            return None
        center, radius = result
        return build.circle(center, radius)

    def _tangent_tangent_radius(self):
        # Tangent-tangent-radius needs entity picks; approximate with the
        # points the user indicates on each object, which is enough to place a
        # circle of the requested radius touching both.
        first = yield PointPrompt("Specify point on first tangent object")
        if self.is_finished(first):
            return None
        second = yield PointPrompt("Specify point on second tangent object",
                                   rubber=RubberLine(first), base_point=first)
        if self.is_finished(second):
            return None
        radius = yield DistancePrompt("Specify radius of circle")
        if self.is_finished(radius) or float(radius) <= 0:
            return None

        candidates = construct.circle_circle_intersection(
            first, float(radius), second, float(radius))
        if not candidates:
            self.write("No circle of that radius touches both points.")
            return None
        return build.circle(candidates[0], float(radius))


class ArcCommand(Command):
    """Draw an arc through three points, or by centre and angles."""

    name = "ARC"
    aliases = ("A",)
    description = "Draw a circular arc."
    group = "draw"

    def run(self):
        answer = yield PointPrompt("Specify start point of arc or",
                                   options=["Center"])
        if self.is_finished(answer):
            return

        if answer == "Center":
            geometry = yield from self._center_start_end()
        else:
            geometry = yield from self._three_point(answer)

        if geometry is not None:
            self.document.add_curve(geometry, "ARC")

    def _three_point(self, start):
        second = yield PointPrompt(
            "Specify second point of arc or", options=["Center", "End"],
            rubber=RubberLine(start), base_point=start)
        if self.is_finished(second):
            return None

        if second in ("Center", "End"):
            self.write("Use ARC Center for centre-based construction.")
            return None

        third = yield PointPrompt("Specify end point of arc",
                                  rubber=RubberArc(start, second),
                                  base_point=second)
        if self.is_finished(third):
            return None
        return build.arc_three_points(start, second, third)

    def _center_start_end(self):
        center = yield PointPrompt("Specify center point of arc")
        if self.is_finished(center):
            return None
        start = yield PointPrompt("Specify start point of arc",
                                  rubber=RubberCircle(center),
                                  base_point=center)
        if self.is_finished(start):
            return None
        radius = construct.distance(center, start)
        if radius <= 0:
            return None

        answer = yield AnglePrompt(
            "Specify end point or included angle", options=["Angle"],
            rubber=RubberCircle(center, radius), base_point=center)
        if self.is_finished(answer):
            return None

        start_angle = construct.angle_of(center, start)

        if answer == "Angle":
            # The keyword arrives as its own name; running it through float()
            # raised ValueError and killed the command mid-prompt.
            included = yield AnglePrompt("Specify included angle",
                                         base_point=center)
            if self.is_finished(included):
                return None
            end_angle = start_angle + float(included)
        else:
            end_angle = float(answer)

        return build.arc(center, radius, start_angle, end_angle, True)


class PolygonCommand(Command):
    """Draw a regular polygon, inscribed or circumscribed."""

    name = "POLYGON"
    aliases = ("POL",)
    description = "Draw a regular polygon."
    group = "draw"

    def run(self):
        sides = yield IntegerPrompt("Enter number of sides", minimum=3,
                                    maximum=1024, default=4)
        if self.is_cancelled(sides):
            return
        sides = 4 if sides is ENTER else int(sides)

        answer = yield PointPrompt("Specify center of polygon or",
                                   options=["Edge"])
        if self.is_finished(answer):
            return

        if answer == "Edge":
            first = yield PointPrompt("Specify first endpoint of edge")
            if self.is_finished(first):
                return
            second = yield PointPrompt("Specify second endpoint of edge",
                                       rubber=RubberLine(first),
                                       base_point=first)
            if self.is_finished(second):
                return
            ring = construct.polygon_from_edge(first, second, sides)
        else:
            # A keyword prompt, not a point prompt: this question has no
            # answer a canvas click could give, and asking for a point meant a
            # stray click silently chose "Inscribed" by being a coordinate
            # that is not the string "Circumscribed".
            mode = yield KeywordPrompt(
                "Enter an option", ["Inscribed", "Circumscribed"],
                default="Inscribed")
            if self.is_cancelled(mode):
                return
            inscribed = mode != "Circumscribed"

            radius = yield DistancePrompt(
                "Specify radius of circle", rubber=RubberCircle(answer),
                base_point=answer)
            if self.is_finished(radius):
                return
            ring = construct.polygon_points(answer, float(radius), sides,
                                            inscribed=inscribed)

        if not ring:
            return
        geometry = build.polyline(ring, closed=True)
        if geometry is not None:
            self.document.add_curve(geometry, "POLYGON", closed=True)


class EllipseCommand(Command):
    """Draw an ellipse from its axis endpoints."""

    name = "ELLIPSE"
    aliases = ("EL",)
    description = "Draw an ellipse."
    group = "draw"

    def run(self):
        first = yield PointPrompt("Specify axis endpoint of ellipse")
        if self.is_finished(first):
            return
        second = yield PointPrompt("Specify other endpoint of axis",
                                   rubber=RubberLine(first), base_point=first)
        if self.is_finished(second):
            return

        center = construct.midpoint(first, second)
        major = construct.distance(first, second) / 2.0
        rotation = construct.angle_of(first, second)

        minor = yield DistancePrompt("Specify distance to other axis",
                                     base_point=center)
        if self.is_finished(minor):
            return

        geometry = build.ellipse(center, major, float(minor), rotation)
        if geometry is not None:
            self.document.add_curve(geometry, "ELLIPSE", closed=True)


class PointCommand(Command):
    """Place a point node."""

    name = "POINT"
    aliases = ("PO",)
    description = "Place a point."
    group = "draw"

    def run(self):
        while True:
            position = yield PointPrompt("Specify a point")
            if self.is_finished(position):
                return
            self.document.add_point(build.point(position), "POINT")


class TextCommand(Command):
    """Place a single line of text."""

    name = "TEXT"
    aliases = ("DT", "MTEXT", "T")
    description = "Place a single line of text."
    group = "annotate"

    def run(self):
        position = yield PointPrompt("Specify start point of text")
        if self.is_finished(position):
            return

        height = yield DistancePrompt("Specify height",
                                      default=self.var("TEXTSIZE"),
                                      base_point=position)
        if height is CANCEL:
            return
        height = self.var("TEXTSIZE") if height is ENTER else float(height)

        rotation = yield AnglePrompt("Specify rotation angle of text",
                                     default=0, base_point=position)
        if rotation is CANCEL:
            return
        rotation = 0.0 if rotation is ENTER else float(rotation)

        content = yield StringPrompt("Enter text")
        if self.is_finished(content) or not str(content).strip():
            return

        self.set_var("TEXTSIZE", height)
        self.document.add_point(
            build.point(position), "TEXT", text=str(content),
            height=height, rotation=math.degrees(rotation))


DRAW_COMMANDS = (
    LineCommand, PolylineCommand, RectangleCommand, CircleCommand,
    ArcCommand, PolygonCommand, EllipseCommand, PointCommand, TextCommand,
)
