"""Live on-map preview of the lot being plotted.

Replaces the old embedded "Lot Preview" panel: while the user types the
technical description, the lot polygon (boundary lines), its corner vertices
and the corner/tie-point labels are drawn directly on the main QGIS map
canvas as transient canvas items (rubber bands, a vertex marker and text
annotations). Nothing is added to the project's layer tree, so the preview
cannot pollute the user's project and it disappears cleanly when the plotter
dialog is closed.

Coordinates are treated as map-canvas coordinates - the same assumption
``plot_on_map`` makes when it builds the final memory layers.
"""

import math

from qgis.PyQt.QtCore import QSizeF
from qgis.PyQt.QtGui import QColor, QTextDocument
from qgis.core import (
    QgsFillSymbol,
    QgsGeometry,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsRectangle,
    QgsTextAnnotation,
)
from qgis.gui import QgsMapCanvasAnnotationItem, QgsRubberBand, QgsVertexMarker

# Preview colors mirror the plotted-lot style (red boundary and vertices)
# with the plugin's teal accent reserved for the tie point.
OUTLINE_COLOR = QColor(255, 0, 0)
FILL_COLOR = QColor(255, 0, 0, 25)
VERTEX_FILL_COLOR = QColor(255, 0, 0)
VERTEX_OUTLINE_COLOR = QColor(255, 255, 255)
LABEL_COLOR = QColor(198, 40, 40)
TIE_POINT_COLOR = QColor(20, 87, 91)


def _geometry_type(name):
    """Resolve a geometry-type enum across QGIS 3.22 - 4.x APIs."""
    try:
        from qgis.core import Qgis
        return getattr(Qgis.GeometryType, name)
    except (ImportError, AttributeError):
        from qgis.core import QgsWkbTypes
        return getattr(QgsWkbTypes, name + "Geometry")


def _enum_member(owner, scope_name, member_name):
    """Resolve a class enum member across QGIS 3.22 - 4.x APIs
    (unscoped on older builds, nested enum scope on newer ones)."""
    try:
        return getattr(owner, member_name)
    except AttributeError:
        return getattr(getattr(owner, scope_name), member_name)


class LotMapPreview:
    """Draws, updates and clears the transient lot preview on the map canvas."""

    def __init__(self, canvas):
        self.canvas = canvas
        # Canvas items are created lazily on the first update() so a dialog
        # instance that is never used leaves nothing behind on the canvas.
        self._polygon_band = None
        self._vertex_band = None
        self._tie_marker = None
        self._labels = []  # [(QgsTextAnnotation, QgsMapCanvasAnnotationItem)]
        self._extent = None

    def _ensure_items(self):
        if self._polygon_band is not None:
            return

        self._polygon_band = QgsRubberBand(self.canvas, _geometry_type("Polygon"))
        self._polygon_band.setColor(OUTLINE_COLOR)
        self._polygon_band.setFillColor(FILL_COLOR)
        self._polygon_band.setWidth(2)

        self._vertex_band = QgsRubberBand(self.canvas, _geometry_type("Point"))
        self._vertex_band.setIcon(
            _enum_member(QgsRubberBand, "IconType", "ICON_CIRCLE"))
        self._vertex_band.setIconSize(10)
        self._vertex_band.setColor(VERTEX_OUTLINE_COLOR)
        self._vertex_band.setFillColor(VERTEX_FILL_COLOR)
        self._vertex_band.setWidth(1)

        self._tie_marker = QgsVertexMarker(self.canvas)
        self._tie_marker.setIconType(
            _enum_member(QgsVertexMarker, "IconType", "ICON_BOX"))
        self._tie_marker.setColor(TIE_POINT_COLOR)
        self._tie_marker.setIconSize(12)
        self._tie_marker.setPenWidth(3)
        self._tie_marker.hide()

    def update(self, coords, tie_point=None):
        """Redraw the preview for corner coords ``[(easting, northing), ...]``."""
        if not coords or len(coords) < 2:
            self.clear()
            return

        self._ensure_items()
        self._clear_labels()

        points = [QgsPointXY(x, y) for x, y in coords]
        self._polygon_band.setToGeometry(
            QgsGeometry.fromPolygonXY([points]), None)
        self._vertex_band.setToGeometry(
            QgsGeometry.fromMultiPointXY(points), None)

        if tie_point is not None:
            self._tie_marker.setCenter(QgsPointXY(tie_point[0], tie_point[1]))
            self._tie_marker.show()
        else:
            self._tie_marker.hide()

        self._extent = self._compute_extent(coords, tie_point)
        self._add_labels(coords, tie_point)

    def clear(self):
        """Take every preview item off the canvas (items stay reusable)."""
        if self._polygon_band is not None:
            self._polygon_band.reset(_geometry_type("Polygon"))
        if self._vertex_band is not None:
            self._vertex_band.reset(_geometry_type("Point"))
        if self._tie_marker is not None:
            self._tie_marker.hide()
        self._clear_labels()
        self._extent = None

    def extent(self):
        """Extent of the previewed lot in map units, or None when empty."""
        return QgsRectangle(self._extent) if self._extent is not None else None

    def zoom_to(self):
        """Zoom the map canvas to the previewed lot, with padding."""
        if self._extent is None:
            return
        rect = QgsRectangle(self._extent)
        if rect.width() <= 0 and rect.height() <= 0:
            rect.grow(5.0)  # degenerate lot: frame a ~10 m box around it
        else:
            rect.scale(1.3)
        self.canvas.setExtent(rect)
        self.canvas.refresh()

    @staticmethod
    def _compute_extent(coords, tie_point):
        points = list(coords) + ([tie_point] if tie_point is not None else [])
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        return QgsRectangle(min(xs), min(ys), max(xs), max(ys))

    def _add_labels(self, coords, tie_point):
        # Labels are decoration: an annotation API hiccup must never break
        # the polygon/vertex preview, so a failure only loses the labels.
        try:
            xs = [c[0] for c in coords]
            ys = [c[1] for c in coords]
            # 1% of the lot diagonal keeps labels proportionally close to
            # their markers for small and large lots alike (the same rule
            # the old embedded preview used).
            offset = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) * 0.01
            for i, (x, y) in enumerate(coords):
                self._add_label(str(i + 1), x + offset, y + offset, LABEL_COLOR)
            if tie_point is not None:
                self._add_label(
                    "TP", tie_point[0] + offset, tie_point[1] + offset,
                    TIE_POINT_COLOR)
        except Exception as exc:
            print(f"Title Plotter live preview labels error: {exc}")

    def _add_label(self, text, x, y, color):
        annotation = QgsTextAnnotation()
        document = QTextDocument()
        document.setHtml(
            '<span style="color:{}; font-family:Arial; font-size:9pt; '
            'font-weight:bold;">{}</span>'.format(color.name(), text))
        annotation.setDocument(document)
        annotation.setMapPosition(QgsPointXY(x, y))
        annotation.setMapPositionCrs(
            self.canvas.mapSettings().destinationCrs())
        annotation.setHasFixedMapPosition(True)
        annotation.setFrameSizeMm(QSizeF(14.0, 6.0))
        # No frame box and no anchor marker: just the floating text.
        annotation.setFillSymbol(QgsFillSymbol.createSimple(
            {"style": "no", "outline_style": "no"}))
        annotation.setMarkerSymbol(QgsMarkerSymbol.createSimple(
            {"name": "circle", "size": "0", "color": "255,255,255,0",
             "outline_style": "no"}))
        # The canvas item renders the annotation; keep both referenced so
        # Python garbage collection cannot delete them while on the canvas.
        item = QgsMapCanvasAnnotationItem(annotation, self.canvas)
        self._labels.append((annotation, item))

    def _clear_labels(self):
        scene = self.canvas.scene()
        for _annotation, item in self._labels:
            if scene is not None:
                scene.removeItem(item)
        self._labels = []
