# -*- coding: utf-8 -*-
"""Rubber-band previews, snap markers and tracking lines.

Every preview here is a :class:`QgsRubberBand` or :class:`QgsVertexMarker` — a
**canvas item**, not a layer. Canvas items repaint without re-rendering any
layer, which is why moving the cursor during a command costs a repaint rather
than a full map render. Nothing in this module ever calls ``canvas.refresh()``.

The manager translates the plain-data :mod:`~..engine.prompt` rubber
descriptors into canvas items, so commands stay free of any Qt dependency and
can run head­less through the scripting facade with the previews simply absent.
"""

import math

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsGeometry, QgsPointXY, QgsWkbTypes
from qgis.gui import QgsRubberBand, QgsVertexMarker

from ..engine import prompt as prompts
from ..geom import build, construct
from . import snap as snap_module


def _geometry_type(name):
    """Resolve a geometry-type enum across QGIS 3.22 - 4.x."""
    try:
        from qgis.core import Qgis
        return getattr(Qgis.GeometryType, name)
    except (ImportError, AttributeError):
        return getattr(QgsWkbTypes, name + "Geometry")


GEOM_LINE = _geometry_type("Line")
GEOM_POLYGON = _geometry_type("Polygon")


class PreviewManager(object):
    """Owns every transient canvas item AutoQAD draws during a command."""

    def __init__(self, canvas, variables):
        self.canvas = canvas
        self.variables = variables

        self._rubber = self._make_band(GEOM_LINE, "RUBBERCOLOR", width=2)
        self._ghost = self._make_band(GEOM_LINE, "RUBBERCOLOR", width=1,
                                      dashed=True)
        self._tracking = self._make_band(GEOM_LINE, "TRACKCOLOR", width=1,
                                         dashed=True)
        self._marker = self._make_band(GEOM_LINE, "AUTOSNAPCOLOR", width=2)
        self._highlight = self._make_band(GEOM_LINE, "HIGHLIGHTCOLOR", width=3)

        self._cursor_marker = QgsVertexMarker(canvas)
        self._cursor_marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self._cursor_marker.setColor(QColor(self.variables.get("AUTOSNAPCOLOR")))
        self._cursor_marker.setIconSize(12)
        self._cursor_marker.setPenWidth(2)
        self._cursor_marker.hide()

        self._descriptor = None
        #: Anchor the tracking ray is drawn through — the command's base point,
        #: not the cursor, or the ray would slide along with the mouse.
        self._tracking_base = None
        self._items = [self._rubber, self._ghost, self._tracking,
                       self._marker, self._highlight]

    # ---- construction ----

    def _make_band(self, geometry_type, colour_var, width=1, dashed=False):
        band = QgsRubberBand(self.canvas, geometry_type)
        band.setColor(QColor(self.variables.get(colour_var)))
        band.setWidth(width)
        if dashed:
            band.setLineStyle(Qt.PenStyle.DashLine)
        band.setBrushStyle(Qt.BrushStyle.NoBrush)
        band.hide()
        return band

    def apply_colours(self):
        """Re-read colours after the user changes them in Options."""
        self._rubber.setColor(QColor(self.variables.get("RUBBERCOLOR")))
        self._ghost.setColor(QColor(self.variables.get("RUBBERCOLOR")))
        self._tracking.setColor(QColor(self.variables.get("TRACKCOLOR")))
        self._marker.setColor(QColor(self.variables.get("AUTOSNAPCOLOR")))
        self._highlight.setColor(QColor(self.variables.get("HIGHLIGHTCOLOR")))
        self._cursor_marker.setColor(QColor(self.variables.get("AUTOSNAPCOLOR")))

    # ---- descriptor ----

    def set_descriptor(self, descriptor):
        """Adopt the preview a prompt asked for (or clear it with ``None``)."""
        self._descriptor = descriptor
        if descriptor is None:
            self._rubber.hide()
            self._ghost.hide()

    # ---- per-move update ----

    def update(self, point, tracking_angle=None, snap_result=None):
        """Redraw everything that follows the cursor. Called once per frame."""
        self._update_rubber(point)
        self._update_tracking(point, tracking_angle)
        self._update_marker(snap_result)

    def _update_rubber(self, point):
        descriptor = self._descriptor
        if descriptor is None or point is None:
            return

        if isinstance(descriptor, prompts.RubberLine):
            self._draw_line([descriptor.anchor, point])

        elif isinstance(descriptor, prompts.RubberPolyline):
            points = list(descriptor.points)
            if points:
                self._draw_line(points + [point],
                                closed=descriptor.closed)

        elif isinstance(descriptor, prompts.RubberRectangle):
            self._draw_line(
                construct.rectangle_points(descriptor.anchor, point))

        elif isinstance(descriptor, prompts.RubberCircle):
            radius = descriptor.radius
            if radius is None:
                radius = construct.distance(descriptor.center, point)
            if radius > 0:
                self._draw_line(
                    construct.circle_points(descriptor.center, radius))

        elif isinstance(descriptor, prompts.RubberArc):
            if descriptor.second is None:
                self._draw_line([descriptor.start, point])
            else:
                arc = construct.arc_three_points(
                    descriptor.start, descriptor.second, point)
                if arc is None:
                    self._draw_line([descriptor.start, descriptor.second,
                                     point])
                else:
                    centre, radius, start_a, end_a, ccw = arc
                    self._draw_line(construct.arc_points(
                        centre, radius, start_a, end_a, ccw))

        elif isinstance(descriptor, prompts.RubberGeometry):
            self._draw_geometries(descriptor, point)

        else:
            self._rubber.hide()

    def _draw_line(self, points, closed=False):
        if len(points) < 2:
            self._rubber.hide()
            return
        ring = list(points)
        if closed and ring[0] != ring[-1]:
            ring.append(ring[0])
        self._rubber.setToGeometry(
            QgsGeometry.fromPolylineXY([QgsPointXY(p[0], p[1]) for p in ring]),
            None)
        self._rubber.show()

    def _draw_geometries(self, descriptor, point):
        """Preview a whole selection being moved, rotated or scaled."""
        anchor = descriptor.anchor
        if anchor is None or not descriptor.geometries:
            self._rubber.hide()
            return

        dx = point[0] - anchor[0]
        dy = point[1] - anchor[1]

        combined = None
        for geometry in descriptor.geometries:
            clone = QgsGeometry(geometry)
            if descriptor.mode == "translate":
                clone.translate(dx, dy)
            elif descriptor.mode == "rotate":
                angle = math.degrees(math.atan2(dy, dx))
                clone.rotate(-angle, QgsPointXY(anchor[0], anchor[1]))
            elif descriptor.mode == "scale":
                # The factor is the cursor's distance from the base point,
                # which is exactly what the runner sends a DistancePrompt when
                # the click lands — so the preview and the result agree.
                # (This branch used to assign an unused attribute, so SCALE
                # previewed nothing at all.)
                factor = math.hypot(dx, dy)
                scaled = build.scaled(clone, anchor, factor)
                if scaled is None:
                    continue
                clone = scaled
            combined = clone if combined is None else combined.combine(clone)

        if combined is None or combined.isEmpty():
            self._rubber.hide()
            return
        self._rubber.setToGeometry(combined, None)
        self._rubber.show()

    def _update_tracking(self, point, angle):
        if angle is None or point is None:
            self._tracking.hide()
            return
        # Draw the tracking ray well past the cursor so it reads as infinite.
        extent = self.canvas.extent()
        reach = max(extent.width(), extent.height())
        base = self._tracking_base or point
        far = construct.point_at(base, angle, reach)
        near = construct.point_at(base, angle, -reach)
        self._tracking.setToGeometry(
            QgsGeometry.fromPolylineXY(
                [QgsPointXY(*near), QgsPointXY(*far)]), None)
        self._tracking.show()

    def set_tracking_base(self, point):
        self._tracking_base = point

    def _update_marker(self, snap_result):
        if snap_result is None or not self.variables.get("SNAPMARKERS"):
            self._marker.hide()
            self._cursor_marker.hide()
            return

        size_pixels = max(4, int(self.variables.get("AUTOSNAPSIZE")))
        size_map = self.canvas.mapUnitsPerPixel() * size_pixels

        rings = snap_module.snap_marker_points(snap_result, size_map)
        if not rings:
            self._marker.hide()
        else:
            self._marker.reset(GEOM_LINE)
            for index, ring in enumerate(rings):
                points = [QgsPointXY(p[0], p[1]) for p in ring]
                self._marker.addGeometry(
                    QgsGeometry.fromPolylineXY(points), None)
            self._marker.show()

        self._cursor_marker.setCenter(
            QgsPointXY(snap_result.point[0], snap_result.point[1]))
        self._cursor_marker.hide()      # the glyph above is the marker

    # ---- selection highlight ----

    def highlight(self, geometries):
        """Outline the current selection."""
        self._highlight.reset(GEOM_LINE)
        if not geometries:
            self._highlight.hide()
            return
        for geometry in geometries:
            if geometry is not None and not geometry.isEmpty():
                self._highlight.addGeometry(geometry, None)
        self._highlight.show()

    def clear_highlight(self):
        self._highlight.reset(GEOM_LINE)
        self._highlight.hide()

    # ---- teardown ----

    def clear(self):
        for band in self._items:
            band.reset(GEOM_LINE)
            band.hide()
        self._cursor_marker.hide()
        self._descriptor = None

    def dispose(self):
        """Detach every canvas item — called when the plugin unloads."""
        scene = self.canvas.scene()
        for item in self._items + [self._cursor_marker]:
            try:
                item.hide()
                if scene is not None:
                    scene.removeItem(item)
            except (RuntimeError, AttributeError):
                pass
        self._items = []
