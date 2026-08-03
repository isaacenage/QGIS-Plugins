# -*- coding: utf-8 -*-
"""Ortho and polar tracking — the cursor constraint solver.

Pure module: no Qt, no QGIS. Points are ``(x, y)`` float tuples.

This runs on **every** processed mouse move, so it is deliberately branch-light
and allocation-free: a handful of trig calls and no object construction beyond
the returned tuple. It is the first stage of the pointer pipeline precisely
because it is this cheap — constraining before snapping means the snap search
starts from an already-correct direction.

Three modes, matching AutoCAD:

* **Ortho** (ORTHOMODE) locks movement to the nearest axis — 0/90/180/270 from
  the base point, expressed in the drawing's angle frame.
* **Polar** (POLARMODE) locks to the nearest multiple of a increment angle,
  plus any user-defined additional angles.
* **Off** passes the cursor through untouched.

Ortho wins when both are on, which is what AutoCAD does.
"""

import math

#: Angular tolerance (radians) within which polar tracking engages. Outside it
#: the cursor is free, so polar does not fight the user at wide angles.
DEFAULT_POLAR_TOLERANCE = math.radians(3.0)


def constrain_ortho(base_point, cursor_point, angle_base=0.0):
    """Lock *cursor_point* to the nearest axis through *base_point*.

    Returns ``(point, angle_radians)``. *angle_base* rotates the axis cross so
    ortho follows a rotated drawing frame (AutoCAD's SNAPANG).
    """
    dx = cursor_point[0] - base_point[0]
    dy = cursor_point[1] - base_point[1]
    if dx == 0.0 and dy == 0.0:
        return (base_point, 0.0)

    base = float(angle_base)
    angle = math.atan2(dy, dx) - base
    quadrant = round(angle / (math.pi / 2.0))
    locked = quadrant * (math.pi / 2.0) + base

    length = math.hypot(dx, dy) * abs(math.cos(angle - quadrant * (math.pi / 2.0)))
    return ((base_point[0] + length * math.cos(locked),
             base_point[1] + length * math.sin(locked)), locked)


def constrain_polar(base_point, cursor_point, increment_degrees=45.0,
                    additional_angles=None, angle_base=0.0,
                    tolerance=DEFAULT_POLAR_TOLERANCE):
    """Lock *cursor_point* to the nearest polar tracking ray.

    Returns ``(point, angle_radians)`` when a ray is within *tolerance*, and
    ``(cursor_point, None)`` when the cursor is free. Projecting onto the ray
    (rather than rotating the cursor onto it) preserves the distance the user
    is expressing along that direction, which is how AutoCAD behaves.
    """
    dx = cursor_point[0] - base_point[0]
    dy = cursor_point[1] - base_point[1]
    length = math.hypot(dx, dy)
    if length < 1e-12:
        return (base_point, None)

    base = float(angle_base)
    cursor_angle = math.atan2(dy, dx)

    candidates = []
    increment = math.radians(float(increment_degrees or 0.0))
    if increment > 1e-9:
        step = round((cursor_angle - base) / increment)
        candidates.append(step * increment + base)
    for extra in (additional_angles or ()):
        candidates.append(math.radians(float(extra)) + base)

    if not candidates:
        return (cursor_point, None)

    def angular_gap(candidate):
        return abs(math.atan2(math.sin(cursor_angle - candidate),
                              math.cos(cursor_angle - candidate)))

    best = min(candidates, key=angular_gap)
    if angular_gap(best) > tolerance:
        return (cursor_point, None)

    # Project onto the ray, keeping the component along it.
    projected = length * math.cos(cursor_angle - best)
    return ((base_point[0] + projected * math.cos(best),
             base_point[1] + projected * math.sin(best)), best)


def apply(base_point, cursor_point, ortho=False, polar=False,
          increment_degrees=45.0, additional_angles=None, angle_base=0.0,
          tolerance=DEFAULT_POLAR_TOLERANCE):
    """Apply whichever constraint is active.

    Returns ``(point, angle_radians_or_None)``. Ortho takes precedence over
    polar, matching AutoCAD. With no base point, or with both modes off, the
    cursor passes through unchanged.
    """
    if base_point is None:
        return (cursor_point, None)
    if ortho:
        return constrain_ortho(base_point, cursor_point, angle_base)
    if polar:
        return constrain_polar(base_point, cursor_point, increment_degrees,
                               additional_angles, angle_base, tolerance)
    return (cursor_point, None)


def snap_angle_label(angle_radians, angle_base=0.0, clockwise=False):
    """Format a tracking angle the way the polar tooltip shows it."""
    degrees = math.degrees(angle_radians) - math.degrees(float(angle_base))
    if clockwise:
        degrees = -degrees
    return "{0:.0f}°".format(degrees % 360.0)


def point_at_distance(base_point, angle_radians, distance):
    """Return the point *distance* away from *base_point* along an angle."""
    return (base_point[0] + distance * math.cos(angle_radians),
            base_point[1] + distance * math.sin(angle_radians))
