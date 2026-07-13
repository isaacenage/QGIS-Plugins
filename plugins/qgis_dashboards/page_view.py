# -*- coding: utf-8 -*-
"""PageView — a page surface: a scroll-area-wrapped DashboardCanvas that owns
the page's zoom/pan.

``PageView`` is a thin container around a private :class:`_CanvasScroll` (a
``QScrollArea`` wrapping one :class:`~dashboard_canvas.DashboardCanvas`). The
canvas surface is the export/print region scaled by zoom; the scroll area is
centred so a page smaller than the viewport sits framed and overflows to
scrollbars (or middle-mouse drag) when zoomed in. Zoom is view-only, never
persisted. The header is now an ordinary canvas tile, so this no longer docks a
banner around the canvas.
"""

from qgis.PyQt.QtCore import Qt, QPoint
from qgis.PyQt.QtWidgets import QScrollArea, QWidget, QVBoxLayout

from .zoom_fit import ZOOM_MIN, ZOOM_MAX, clamp_zoom, fit_zoom  # noqa: F401

ZOOM_STEP = 1.2


class _CanvasScroll(QScrollArea):
    """Scroll area wrapping one canvas; manages its zoom level and panning."""

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        # Named so the canvas-background QSS rule can target this scroll area
        # (and only this one) — see Theme.window_qss.
        self.setObjectName("dashPageView")
        self.setWidget(canvas)
        # The canvas manages its own size (region/content extent x zoom), so we
        # never let the scroll area stretch it to the viewport.
        self.setWidgetResizable(False)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        # centre the page when it is smaller than the viewport (e.g. just after
        # a fit-to-region Reset Zoom), so the framed region sits centred.
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom = 1.0
        self._pan_origin = None
        self._pan_scroll = None

    def zoom(self):
        return self._zoom

    def set_zoom(self, z):
        self._zoom = clamp_zoom(z)
        self.canvas.set_zoom(self._zoom)
        return self._zoom

    def zoom_in(self):
        return self.set_zoom(self._zoom * ZOOM_STEP)

    def zoom_out(self):
        return self.set_zoom(self._zoom / ZOOM_STEP)

    def reset_zoom(self):
        """Fit the canvas's export/print region to the viewport.

        Reset Zoom frames the whole page (the region) in the viewport, so the
        user always lands on a view of the exact rectangle that will export.
        """
        region = self.canvas.region_size() if hasattr(
            self.canvas, "region_size") else (
            self.canvas.width(), self.canvas.height())
        vp = self.viewport()
        z = fit_zoom(region, (vp.width(), vp.height()))
        return self.set_zoom(z)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # the viewport changed — let the canvas refill it (it reads our
        # viewport size) without altering any tile's logical placement
        if hasattr(self.canvas, "sync_size"):
            self.canvas.sync_size()

    # ---- middle-mouse panning ----

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._pan_origin = e.pos()
            self._pan_scroll = QPoint(
                self.horizontalScrollBar().value(),
                self.verticalScrollBar().value())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan_origin is not None:
            d = e.pos() - self._pan_origin
            self.horizontalScrollBar().setValue(self._pan_scroll.x() - d.x())
            self.verticalScrollBar().setValue(self._pan_scroll.y() - d.y())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton and self._pan_origin is not None:
            self._pan_origin = None
            self.unsetCursor()
            return
        super().mouseReleaseEvent(e)


class PageView(QWidget):
    """One page: a scrolling canvas with view-only zoom/pan."""

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.setObjectName("dashPageWrap")
        # A custom QWidget subclass only paints a stylesheet background when this
        # attribute is set — see #dashPageWrap in Theme.window_qss.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._scroll = _CanvasScroll(canvas, self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._scroll, 1)

    # ---- zoom/pan delegation (preserves the original PageView API) ----

    @property
    def canvas(self):
        return self._scroll.canvas

    def zoom(self):
        return self._scroll.zoom()

    def set_zoom(self, z):
        return self._scroll.set_zoom(z)

    def zoom_in(self):
        return self._scroll.zoom_in()

    def zoom_out(self):
        return self._scroll.zoom_out()

    def reset_zoom(self):
        return self._scroll.reset_zoom()

    # ---- static export (PNG / PDF) ----

    def export_pixmap(self, scale=2.0):
        """Render the page to a high-res pixmap. The header is now a canvas
        tile, so this is exactly the canvas's region render."""
        return self.canvas.export_pixmap(scale)
