# -*- coding: utf-8 -*-
"""The AutoCAD crosshair cursor.

AutoCAD does not use a small ``+`` mouse pointer — it draws a **crosshair**
whose arms span a configurable percentage of the screen (the CURSORSIZE
variable, 5 % by default, 100 % for full-screen arms), with a square **pickbox**
at the intersection. Reading a drawing depends on it: the long arms let you
judge alignment against distant geometry, which a 16-pixel pointer cannot do.

Implemented as four ``QgsRubberBand`` arms plus a pickbox band — canvas items,
so moving the cursor repaints without re-rendering any layer. The OS pointer is
hidden (``BlankCursor``) while the crosshair is live, so the two do not fight;
it is restored the moment the tool deactivates.

The arms are drawn as two separate segments per axis rather than one line
through the middle, leaving the pickbox interior clear — which is what makes
the pickbox readable against dense geometry.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import QgsGeometry, QgsPointXY
from qgis.gui import QgsRubberBand

from ..core.compat import GEOM_LINE


class CrosshairCursor(object):
    """The crosshair, pickbox and (optionally) the snap aperture box."""

    def __init__(self, canvas, variables):
        self.canvas = canvas
        self.variables = variables
        self._visible = False

        self._arms = [self._band(width=1) for _ in range(4)]
        self._pickbox = self._band(width=1)
        self._aperture = self._band(width=1, dashed=True)

        self.apply_colours()

    # ---- construction ----

    def _band(self, width=1, dashed=False):
        band = QgsRubberBand(self.canvas, GEOM_LINE)
        band.setWidth(width)
        band.setBrushStyle(Qt.BrushStyle.NoBrush)
        if dashed:
            band.setLineStyle(Qt.PenStyle.DotLine)
        band.hide()
        return band

    def apply_colours(self):
        """Re-read colours after the user changes them in Options."""
        crosshair = QColor(self.variables.get("CURSORCOLOR"))
        pickbox = QColor(self.variables.get("PICKBOXCOLOR"))
        for arm in self._arms:
            arm.setColor(crosshair)
        self._pickbox.setColor(pickbox)
        self._aperture.setColor(QColor(self.variables.get("AUTOSNAPCOLOR")))

    # ---- geometry ----

    def _arm_length_pixels(self):
        """Half-arm length in pixels, from CURSORSIZE as a percent of screen.

        Below 100 % the percentage applies to *half* the screen, so 5 % gives
        the short arms AutoCAD ships with; 100 % gives arms that cross the
        whole canvas.
        """
        try:
            from qgis.PyQt.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            rect = screen.geometry()
            extent = max(rect.width(), rect.height())
        except (ImportError, AttributeError, RuntimeError):
            extent = max(self.canvas.width(), self.canvas.height()) or 1000

        percent = max(1, min(100, int(self.variables.get("CURSORSIZE"))))
        if percent < 100:
            extent = extent / 2.0
        return extent * percent / 100.0

    # ---- display ----

    def set_visible(self, visible):
        """Show or hide the crosshair, and swap the OS pointer accordingly."""
        self._visible = bool(visible)
        if not self._visible:
            self.hide()
            try:
                self.canvas.unsetCursor()
            except (AttributeError, RuntimeError):
                pass
        else:
            # Hide the OS pointer so only the crosshair is visible, exactly as
            # AutoCAD does. Restored in hide()/set_visible(False).
            try:
                self.canvas.setCursor(Qt.CursorShape.BlankCursor)
            except (AttributeError, RuntimeError):
                pass

    def hide(self):
        for band in self._arms + [self._pickbox, self._aperture]:
            band.hide()

    def move_to(self, map_point):
        """Redraw the crosshair centred on *map_point*. Called once per frame."""
        if not self._visible or map_point is None:
            return

        units_per_pixel = self.canvas.mapUnitsPerPixel()
        x, y = map_point[0], map_point[1]

        pick = max(1, int(self.variables.get("PICKBOX"))) * units_per_pixel
        arm = self._arm_length_pixels() * units_per_pixel

        # Four arms, each starting at the pickbox edge so its interior stays
        # clear — left, right, down, up.
        segments = (
            ((x - arm, y), (x - pick, y)),
            ((x + pick, y), (x + arm, y)),
            ((x, y - arm), (x, y - pick)),
            ((x, y + pick), (x, y + arm)),
        )
        for band, (start, end) in zip(self._arms, segments):
            band.setToGeometry(
                QgsGeometry.fromPolylineXY(
                    [QgsPointXY(*start), QgsPointXY(*end)]), None)
            band.show()

        self._draw_box(self._pickbox, x, y, pick)

        # The aperture box appears only while object snaps are live, which is
        # how AutoCAD signals that snapping is armed.
        if self.variables.osnap_enabled:
            aperture = (max(1, int(self.variables.get("APERTURE")))
                        * units_per_pixel)
            self._draw_box(self._aperture, x, y, aperture)
        else:
            self._aperture.hide()

    @staticmethod
    def _draw_box(band, x, y, half):
        band.setToGeometry(
            QgsGeometry.fromPolylineXY([
                QgsPointXY(x - half, y - half),
                QgsPointXY(x + half, y - half),
                QgsPointXY(x + half, y + half),
                QgsPointXY(x - half, y + half),
                QgsPointXY(x - half, y - half),
            ]), None)
        band.show()

    # ---- teardown ----

    def dispose(self):
        """Detach every canvas item and restore the OS pointer."""
        try:
            self.canvas.unsetCursor()
        except (AttributeError, RuntimeError):
            pass
        scene = self.canvas.scene()
        for band in self._arms + [self._pickbox, self._aperture]:
            try:
                band.hide()
                if scene is not None:
                    scene.removeItem(band)
            except (RuntimeError, AttributeError):
                pass
        self._arms = []
