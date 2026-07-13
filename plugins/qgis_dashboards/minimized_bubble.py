# -*- coding: utf-8 -*-
"""Floating minimized puck for the dashboard window.

When the dashboard window is minimized we hide it and show this small circular
puck instead — the plugin logo in a round container that floats on top of QGIS
and can be dragged to any of the four screen corners. Clicking it restores the
window.

This replaces Qt's default behaviour for a *parented* top-level window: on
minimize Qt draws a tiny non-movable "minimize stub" (a title-bar tab showing
the icon + title) pinned to the bottom-left of the parent's client area, right
over the QGIS status bar / search tool. The puck is movable and out of the way.
"""

from qgis.PyQt.QtWidgets import QWidget, QApplication
from qgis.PyQt.QtCore import Qt, QPoint, QRect, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QColor, QBrush, QPen

from .icons import logo_pixmap

_DIAMETER = 60      # puck size in logical px
_MARGIN = 18        # gap from the screen edges when snapped to a corner
# px of movement before a press counts as a drag (not a click)
_DRAG_SLOP = 6

# corner indices
_TOP_LEFT, _TOP_RIGHT, _BOTTOM_LEFT, _BOTTOM_RIGHT = 0, 1, 2, 3


class MinimizedBubble(QWidget):
    """A round, draggable, always-on-top puck shown while the window is minimized.

    Drag it anywhere — on release it snaps to the nearest screen corner. A plain
    click (no drag) emits :attr:`restoreRequested` so the owner can reopen the
    window. Parent it to the QGIS main window (not the dashboard window) so it
    stays visible while the dashboard itself is hidden.
    """

    restoreRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_DIAMETER, _DIAMETER)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Restore the dashboard")

        self._logo = logo_pixmap(_DIAMETER - 20)
        self._corner = _BOTTOM_RIGHT
        self._press_global = None   # cursor pos at press (global)
        self._press_origin = None   # widget top-left at press
        self._dragging = False

    # ---- placement ----

    def _screen_rect(self):
        screen = self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry()

    def _corner_point(self, corner):
        r = self._screen_rect()
        d, m = _DIAMETER, _MARGIN
        if corner == _TOP_LEFT:
            return QPoint(r.left() + m, r.top() + m)
        if corner == _TOP_RIGHT:
            return QPoint(r.right() - m - d, r.top() + m)
        if corner == _BOTTOM_LEFT:
            return QPoint(r.left() + m, r.bottom() - m - d)
        return QPoint(r.right() - m - d, r.bottom() - m - d)

    def _nearest_corner(self):
        r = self._screen_rect()
        c = self.geometry().center()
        left = c.x() < r.center().x()
        top = c.y() < r.center().y()
        if top and left:
            return _TOP_LEFT
        if top and not left:
            return _TOP_RIGHT
        if not top and left:
            return _BOTTOM_LEFT
        return _BOTTOM_RIGHT

    def show_at_corner(self, corner=None):
        """Show the puck snapped to ``corner`` (or its last remembered corner)."""
        if corner is not None:
            self._corner = corner
        self.move(self._corner_point(self._corner))
        self.show()
        self.raise_()

    # ---- painting ----

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        d = _DIAMETER
        ring = QRect(2, 2, d - 5, d - 5)
        # white puck with a soft hairline ring (the same #e2e6ec used for
        # chrome)
        p.setPen(QPen(QColor("#e2e6ec"), 1))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(ring)
        # logo centered. The pixmap is supersampled and DPR-tagged, so
        # width()/height() report *physical* px — divide by the device-pixel
        # ratio to get the logical size drawPixmap actually paints at.
        dpr = self._logo.devicePixelRatio() or 1.0
        lw = self._logo.width() / dpr
        lh = self._logo.height() / dpr
        lx = int((d - lw) / 2)
        ly = int((d - lh) / 2)
        p.drawPixmap(lx, ly, self._logo)
        p.end()

    # ---- drag to a corner / click to restore ----

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global = event.globalPos()
            self._press_origin = self.pos()
            self._dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press_global is None:
            return
        delta = event.globalPos() - self._press_global
        if not self._dragging and delta.manhattanLength() < _DRAG_SLOP:
            return
        self._dragging = True
        self.move(self._press_origin + delta)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._dragging:
            self._corner = self._nearest_corner()
            self.move(self._corner_point(self._corner))
        else:
            self.restoreRequested.emit()
        self._press_global = None
        self._press_origin = None
        self._dragging = False
        event.accept()
