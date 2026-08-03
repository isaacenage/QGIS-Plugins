# -*- coding: utf-8 -*-
"""Typed coordinate entry — the AutoCAD command-line coordinate grammar.

Pure module: no Qt, no QGIS. Points are plain ``(x, y)`` float tuples.

AutoCAD accepts several coordinate forms at any "specify a point" prompt, and
reproducing them exactly is most of what makes typed input feel like CAD:

======================  ==========================================
Input                   Meaning
======================  ==========================================
``10,20``               absolute cartesian
``@10,20``              relative to the last point
``10<45``               absolute polar: distance from origin, angle
``@10<45``              relative polar: distance and angle from last point
``@10<45,3``            3D relative polar (Z accepted and ignored in 2D)
``#10,20``              force absolute (used when dynamic input defaults to
                        relative)
``*10,20``              force World coordinates
``10``                  direct distance entry — distance along the current
                        cursor direction
======================  ==========================================

Angles honour the drawing's angle base and direction (AutoCAD's ANGBASE and
ANGDIR), so a drawing set to "north = 0, clockwise" — the survey convention
this plugin's sibling Title Plotter uses — parses bearings correctly.

:func:`parse` returns a :class:`ParsedCoordinate` describing *what was typed*;
:func:`resolve` turns that into an absolute point given the drawing context.
Splitting the two keeps parsing testable without any drawing state.
"""

import math
import re

# What kind of value the user typed.
CARTESIAN = "cartesian"
POLAR = "polar"
DISTANCE = "distance"

_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_CARTESIAN_RE = re.compile(
    r"^({n})\s*,\s*({n})(?:\s*,\s*({n}))?$".format(n=_NUMBER))
_POLAR_RE = re.compile(
    r"^({n})\s*<\s*({n})(?:\s*,\s*({n}))?$".format(n=_NUMBER))
_DISTANCE_RE = re.compile(r"^({n})$".format(n=_NUMBER))


class ParsedCoordinate(object):
    """The structured result of parsing one coordinate string."""

    __slots__ = ("kind", "relative", "world", "a", "b", "z")

    def __init__(self, kind, relative=False, world=False, a=0.0, b=0.0, z=0.0):
        #: One of :data:`CARTESIAN`, :data:`POLAR`, :data:`DISTANCE`.
        self.kind = kind
        #: True when the value is relative to the last point (``@``).
        self.relative = relative
        #: True when the value was forced to World coordinates (``*``).
        self.world = world
        #: x / distance depending on *kind*.
        self.a = a
        #: y / angle depending on *kind*.
        self.b = b
        #: Z ordinate, parsed and carried but unused by the 2D engine.
        self.z = z

    def __eq__(self, other):                  # pragma: no cover - test aid
        return (isinstance(other, ParsedCoordinate)
                and self.kind == other.kind
                and self.relative == other.relative
                and self.world == other.world
                and abs(self.a - other.a) < 1e-12
                and abs(self.b - other.b) < 1e-12)

    def __repr__(self):                       # pragma: no cover - debug aid
        return "<Parsed {0}{1} {2},{3}>".format(
            "@" if self.relative else "", self.kind, self.a, self.b)


def parse(text, default_relative=False):
    """Parse coordinate *text*, or return ``None`` if it is not a coordinate.

    *default_relative* reflects dynamic input's behaviour, where a bare
    ``10,20`` at a "next point" prompt is treated as relative unless prefixed
    with ``#``.

    Returning ``None`` rather than raising is deliberate: the command runner
    tries a coordinate parse first and falls through to keyword matching, so
    "not a coordinate" is an ordinary, expected outcome.
    """
    if text is None:
        return None
    value = text.strip()
    if not value:
        return None

    relative = default_relative
    world = False

    while value and value[0] in "@#*":
        prefix = value[0]
        if prefix == "@":
            relative = True
        elif prefix == "#":
            relative = False
        elif prefix == "*":
            world = True
            relative = False
        value = value[1:].strip()

    if not value:
        return None

    match = _POLAR_RE.match(value)
    if match:
        return ParsedCoordinate(
            POLAR, relative, world,
            float(match.group(1)), float(match.group(2)),
            float(match.group(3) or 0.0))

    match = _CARTESIAN_RE.match(value)
    if match:
        return ParsedCoordinate(
            CARTESIAN, relative, world,
            float(match.group(1)), float(match.group(2)),
            float(match.group(3) or 0.0))

    match = _DISTANCE_RE.match(value)
    if match:
        # A bare number is direct distance entry, which is inherently relative.
        return ParsedCoordinate(DISTANCE, True, world, float(match.group(1)))

    return None


def to_math_angle(angle_degrees, angle_base=0.0, clockwise=False):
    """Convert a drawing angle to a standard math angle in radians.

    A math angle is measured counter-clockwise from the positive X axis.
    *angle_base* is where zero points (AutoCAD's ANGBASE, in degrees CCW from
    east) and *clockwise* selects ANGDIR = 1 — together these express survey
    bearings ("north = 0, clockwise") as well as the CAD default.
    """
    value = -float(angle_degrees) if clockwise else float(angle_degrees)
    return math.radians(value + float(angle_base))


def from_math_angle(radians, angle_base=0.0, clockwise=False):
    """Inverse of :func:`to_math_angle`, returning degrees in ``[0, 360)``."""
    degrees = math.degrees(radians) - float(angle_base)
    if clockwise:
        degrees = -degrees
    return degrees % 360.0


def resolve(parsed, last_point=None, cursor_point=None,
            angle_base=0.0, clockwise=False):
    """Turn a :class:`ParsedCoordinate` into an absolute ``(x, y)`` point.

    *last_point* anchors relative input; *cursor_point* supplies the direction
    for direct distance entry. Returns ``None`` when the required context is
    missing (e.g. ``@10,20`` with no previous point), which the caller should
    surface as a prompt error rather than a crash.
    """
    if parsed is None:
        return None

    if parsed.kind == DISTANCE:
        if last_point is None or cursor_point is None:
            return None
        dx = cursor_point[0] - last_point[0]
        dy = cursor_point[1] - last_point[1]
        length = math.hypot(dx, dy)
        if length < 1e-12:
            return None
        scale = parsed.a / length
        return (last_point[0] + dx * scale, last_point[1] + dy * scale)

    if parsed.kind == POLAR:
        radians = to_math_angle(parsed.b, angle_base, clockwise)
        dx = parsed.a * math.cos(radians)
        dy = parsed.a * math.sin(radians)
        if parsed.relative:
            if last_point is None:
                return None
            return (last_point[0] + dx, last_point[1] + dy)
        return (dx, dy)

    # Cartesian.
    if parsed.relative:
        if last_point is None:
            return None
        return (last_point[0] + parsed.a, last_point[1] + parsed.b)
    return (parsed.a, parsed.b)


def parse_and_resolve(text, last_point=None, cursor_point=None,
                      angle_base=0.0, clockwise=False, default_relative=False):
    """Convenience wrapper: :func:`parse` then :func:`resolve`."""
    return resolve(parse(text, default_relative), last_point, cursor_point,
                   angle_base, clockwise)


def format_point(point, precision=4):
    """Format a point the way the command line echoes it."""
    return "{0:.{p}f},{1:.{p}f}".format(point[0], point[1], p=precision)


def parse_angle(text, angle_base=0.0, clockwise=False):
    """Parse an angle at an "specify angle" prompt, returning radians.

    Accepts a bare number in drawing angle units. Returns ``None`` if *text*
    is not a number.
    """
    if text is None:
        return None
    match = _DISTANCE_RE.match(text.strip())
    if not match:
        return None
    return to_math_angle(float(match.group(1)), angle_base, clockwise)


def parse_distance(text):
    """Parse a distance at a "specify distance" prompt. ``None`` if invalid."""
    if text is None:
        return None
    match = _DISTANCE_RE.match(text.strip())
    if not match:
        return None
    return float(match.group(1))
