# -*- coding: utf-8 -*-
"""Dashboard canvas — free-form drag/resize layout (no grid).

Modelled on the Summarizer plugin's canvas: tiles are absolutely-positioned
children of the canvas that remember their placement in **logical pixels**
(``x, y, w, h`` at zoom 1.0) — there are no cells, no ``cols``/``rows``, and no
``QGridLayout``. The canvas applies the page's zoom factor when placing a tile
(``display = logical x zoom``) and grows its own surface to contain every tile
so the surrounding scroll area can pan it.

The user drags a tile by its header strip and resizes via the 8 handles; on
release the rect is snapped to an 8px step, clamped so the origin stays on the
surface, and **reverts if it would overlap** another tile (the one spatial
constraint kept from the old grid). Zoom is owned per-page by :class:`PageView`,
which calls :meth:`DashboardCanvas.set_zoom`.
"""

from qgis.PyQt.QtCore import Qt, QPoint, QPointF, QRect, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QColor, QPen, QPixmap
from qgis.PyQt.QtWidgets import QWidget, QFrame, QVBoxLayout, QToolButton, QMenu

from .tile_snap import snap_rect, nearest_free
from .layout_util import region_scale_factor, scale_rect

HEADER_H = 20        # px drag strip height
GRIP = 16            # px resize grip square
SNAP = 8             # px snap step applied on drag/resize release
SNAP_PULL = 16       # logical px range an edge is magnetically pulled to a neighbour
MARGIN = 12          # px breathing room kept around content when growing
MIN_TILE = 120       # px minimum tile width/height (logical)
DEFAULT_W = 320      # px default new-tile size (logical)
DEFAULT_H = 240
MAP_W = 480          # px default size for the (larger) map tile
MAP_H = 380
# px default height for a new header tile (spans region width)
HEADER_BAND_H = 80
# the export/print region (the "page") in logical px; the canvas draws a hairline
# frame around it, Reset Zoom fits it, and PNG/PDF export render exactly
# this rect
DEFAULT_REGION_W = 1280
DEFAULT_REGION_H = 720
MIN_REGION = 320     # px floor for the region width/height


def _snap(px, step=SNAP):
    step = step or 1
    return int(round(px / float(step))) * step


def _proposed_resize(edge, start_geom, dx, dy, min_px=40):
    """Return the new (x, y, w, h) for a tile dragged by ``(dx, dy)``.

    ``edge`` is a compass tag (n/s/e/w and the diagonals ne/nw/se/sw). Edges
    containing 'w'/'n' move the tile's origin; 'e'/'s' only grow size. Width
    and height are floored at ``min_px`` without letting a moving origin cross
    the opposite, fixed edge.
    """
    x, y, w, h = start_geom
    if "w" in edge:
        new_w = max(w - dx, min_px)
        x = x + (w - new_w)
        w = new_w
    if "e" in edge:
        w = max(w + dx, min_px)
    if "n" in edge:
        new_h = max(h - dy, min_px)
        y = y + (h - new_h)
        h = new_h
    if "s" in edge:
        h = max(h + dy, min_px)
    return (x, y, w, h)


DRAG_THRESHOLD = 3   # px the pointer must travel before a press becomes a move


class _DragHandle(QWidget):
    """Transparent overlay that moves the host tile when dragged.

    In Build mode it covers the **whole tile** so a drag anywhere on the card
    moves it — the contents are inert in Build mode, so there is nothing to grab
    underneath. (The map drives its own body drag, so its handle stays a thin top
    strip; see ``GridTile.resizeEvent``.) The handle is invisible; only the move
    cursor reveals it, and it is hidden in Use mode so contents become interactive.

    A press only becomes a move once the pointer travels past ``DRAG_THRESHOLD``,
    so a plain click or a double-click never nudges the tile — that keeps
    double-click-to-edit (text tiles) working, forwarded via
    :meth:`mouseDoubleClickEvent`.
    """

    def __init__(self, tile):
        super().__init__(tile)
        self._tile = tile
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("Drag to move")
        self._origin = None
        self._moving = False

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin = e.globalPos()
            self._moving = False
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._origin is None:
            return
        delta = e.globalPos() - self._origin
        if not self._moving:
            if abs(delta.x()) + abs(delta.y()) < DRAG_THRESHOLD:
                return
            self._moving = True
            self._tile.begin_move()
        self._tile.move_by(delta)

    def mouseReleaseEvent(self, e):
        if self._moving:
            self._tile.end_move()
        self._origin = None
        self._moving = False

    def mouseDoubleClickEvent(self, e):
        # the overlay covers the whole tile in Build mode, so route a body
        # double-click to the element (text tiles edit on double-click)
        self._tile.element.on_tile_double_click()


EDGE_CURSORS = {
    "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
    "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
}


class _ResizeHandle(QWidget):
    """A grab point on one side/corner of a tile; press-drag resizes it."""

    def __init__(self, tile, edge):
        super().__init__(tile)
        self._tile = tile
        self.edge = edge
        self.setCursor(EDGE_CURSORS[edge])
        self._origin = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin = e.globalPos()
            self._tile.begin_resize()

    def mouseMoveEvent(self, e):
        if self._origin is not None:
            d = e.globalPos() - self._origin
            self._tile.resize_by(self.edge, d.x(), d.y())

    def mouseReleaseEvent(self, e):
        if self._origin is not None:
            self._origin = None
            self._tile.end_resize()

    def paintEvent(self, _e):
        if self.edge != "se":
            return
        p = QPainter(self)
        p.setPen(QColor("#b6bfc8"))
        for off in (3, 7, 11):
            p.drawLine(self.width() - off, self.height() - 2,
                       self.width() - 2, self.height() - off)
        p.end()


class GridTile(QFrame):
    """A draggable / resizable container wrapping one dashboard element.

    Stores its placement in logical pixels (``x_px, y_px, w_px, h_px``); the
    canvas scales these by the active zoom when placing the widget.
    """

    closeRequested = pyqtSignal(object)        # emits the wrapped element
    styleRequested = pyqtSignal(object)        # emits the wrapped element
    connectionsRequested = pyqtSignal(object)  # emits the wrapped element
    configureRequested = pyqtSignal(object)    # emits the wrapped element
    geometryCommitted = pyqtSignal()           # pixel rect changed (persist)

    def __init__(self, canvas, element, pixel_rect):
        super().__init__(canvas)
        self.canvas = canvas
        self.element = element
        # back-reference so an element can reach its host tile (e.g. to drive its
        # own move via the tile API) — kept as a general hook for full-bleed
        # tiles
        setattr(element, "_grid_tile", self)
        self.x_px, self.y_px, self.w_px, self.h_px = pixel_rect
        self._prev = tuple(pixel_rect)
        self.setObjectName("tileWrap")
        self.setStyleSheet("#tileWrap { background:transparent; }")

        # the element fills the card; chrome is overlaid on top
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(element)
        self._content_lay = lay   # the global "element gap" is applied here

        self.header = _DragHandle(self)   # transparent top strip, drag to move

        # No corner ✕ button: removing a tile is deliberate, via the right-click
        # menu's "Remove tile" only, so a stray click can't delete a tile.
        self.style_btn = QToolButton(self)
        self.style_btn.setObjectName("tileClose")
        self.style_btn.setText("⚙")
        self.style_btn.setAutoRaise(True)
        self.style_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.style_btn.setToolTip("Tile appearance")
        self.style_btn.clicked.connect(
            lambda: self.styleRequested.emit(
                self.element))

        self._handles = {edge: _ResizeHandle(self, edge)
                         for edge in ("n", "s", "e", "w",
                                      "nw", "ne", "sw", "se")}
        self._locked = False   # layout lock: when True, no move/resize
        self._active = False   # a move/resize gesture is in progress

    def contextMenuEvent(self, event):
        """Right-click a tile to configure / wire / restyle / remove it.

        Build-only: in Use mode (locked) the configuration menu is suppressed so
        the tile is purely interactive. Unlock to edit.
        """
        if self._locked:
            return
        menu = QMenu(self)
        menu.addAction("Configure").triggered.connect(
            lambda: self.configureRequested.emit(self.element))
        menu.addAction("Connections").triggered.connect(
            lambda: self.connectionsRequested.emit(self.element))
        menu.addAction("Tile appearance").triggered.connect(
            lambda: self.styleRequested.emit(self.element))
        menu.addSeparator()
        menu.addAction("Remove tile").triggered.connect(
            lambda: self.closeRequested.emit(self.element))
        menu.exec(event.globalPos())

    def grid_rect(self):
        """The tile's logical pixel placement ``(x, y, w, h)``."""
        return (self.x_px, self.y_px, self.w_px, self.h_px)

    def set_inset(self, px):
        """Inset the element card within the tile footprint by *px* display px.

        This is how the global element-gap setting is rendered: the tile
        footprint is unchanged (drag / resize / overlap still act on it), but
        the card shrinks inside it, leaving transparent breathing room around
        every element so adjacent cards never visually touch. ``px`` is already
        scaled for the current zoom by the canvas (see ``DashboardCanvas``).
        """
        px = max(0, int(px))
        self._content_lay.setContentsMargins(px, px, px, px)

    def set_chrome_visible(self, on):
        """Show/hide the editing chrome (drag strip, buttons, resize handles).

        Hidden while the canvas is grabbed for a PNG/PDF export so the saved
        image shows only the clean tiles, not the editing affordances. The whole
        editing chrome (drag strip, ⚙ button, resize handles) only reappears
        when the layout is not locked (Build mode).
        """
        editing = on and not self._locked
        self.style_btn.setVisible(editing)
        self.header.setVisible(editing)
        for h in self._handles.values():
            h.setVisible(editing)

    def set_locked(self, locked):
        """Switch the tile between Build (unlocked) and Use (locked) modes.

        **Build mode** (unlocked): the drag strip, resize handles and ⚙
        button are shown so the tile can be moved/resized/configured, and the
        element's contents are inert. **Use mode** (locked): that editing chrome
        is hidden, the tile is fixed, and the element's contents become
        interactive (chart click → filter, map pan/identify, …).
        """
        self._locked = bool(locked)
        editing = not self._locked
        self.header.setVisible(editing)
        self.style_btn.setVisible(editing)
        for h in self._handles.values():
            h.setVisible(editing)
        # contents interact only in Use mode
        self.element.set_interactive(self._locked)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # Build-mode drag overlay: it covers the whole tile so a drag anywhere on
        # the (inert) card body moves it. The map drives its own body drag, so its
        # handle stays a thin top strip leaving room for the corner button.
        # The resize handles + ⚙ button are raised above it (below) so they
        # stay grabbable through the overlay.
        if getattr(self.element, "handles_own_body_drag", False):
            self.header.setGeometry(6, 2, max(self.width() - 30, 1), HEADER_H)
        else:
            self.header.setGeometry(0, 0, self.width(), self.height())
        self.style_btn.move(self.width() - 24, 3)
        self._place_handles()
        self.header.raise_()
        for h in self._handles.values():
            h.raise_()
        self.style_btn.raise_()

    def _place_handles(self):
        w, h, t = self.width(), self.height(), GRIP
        mid_x, mid_y = (w - t) // 2, (h - t) // 2
        geom = {
            "nw": (0, 0), "n": (mid_x, 0), "ne": (w - t, 0),
            "w": (0, mid_y), "e": (w - t, mid_y),
            "sw": (0, h - t), "s": (mid_x, h - t), "se": (w - t, h - t),
        }
        for edge, (hx, hy) in geom.items():
            self._handles[edge].setGeometry(hx, hy, t, t)

    # ---- move ----
    # ``_active`` gates the whole gesture so every entry point — the drag
    # handle *and* the map tile's own canvas (which calls these directly) —
    # respects the layout lock.

    def begin_move(self):
        if self._locked:
            self._active = False
            return
        self._active = True
        self._prev = self.grid_rect()
        self._start_pos = self.pos()
        self.raise_()
        self.canvas.show_guides(True)

    def move_by(self, delta):
        if not self._active:
            return
        # clamp the live drag so the tile can never leave the canvas surface —
        # it stops at the gutter edge (``pad``) instead of disappearing
        pad = self.canvas._pad()
        target = self._start_pos + delta
        max_x = max(self.canvas.width() - pad - self.width(), pad)
        max_y = max(self.canvas.height() - pad - self.height(), pad)
        self.move(min(max(target.x(), pad), max_x),
                  min(max(target.y(), pad), max_y))
        # live feedback: show where the tile will snap to (yellow if it fits
        # there, red if not). The widget itself keeps following the cursor.
        cand = self._snapped_candidate()
        valid = self.canvas.rect_free(cand, ignore=self)
        self.canvas.set_drop_preview(cand, valid)

    def _snapped_candidate(self):
        """The magnetically-snapped logical rect for the tile's live position."""
        z = self.canvas.zoom() or 1.0
        pad = self.canvas._pad()
        lw, lh = self.w_px, self.h_px
        lx = max(_snap((self.x() - pad) / z), 0)
        ly = max(_snap((self.y() - pad) / z), 0)
        return self.canvas.snap_for((lx, ly, lw, lh), ignore=self)

    def end_move(self):
        if not self._active:
            return
        self._active = False
        self.canvas.set_drop_preview(None, True)
        self.canvas.show_guides(False)
        # snap to neighbours/page edges; if that still overlaps, slide to the
        # nearest free slot — never revert to the drag-start position.
        cand = self._snapped_candidate()
        if not self.canvas.rect_free(cand, ignore=self):
            cand = self.canvas.fit_for(cand, ignore=self)
        self._commit_move(cand)

    def _commit_move(self, new_rect):
        """Place the tile at *new_rect* (logical) and persist — no revert path.

        Even when the rect could not be freed (a fully packed page), the tile is
        placed where it landed rather than snapping back to its origin.
        """
        self.x_px, self.y_px, self.w_px, self.h_px = new_rect
        self.canvas.place(self)
        self.canvas.sync_size()
        if new_rect != self._prev:
            self.geometryCommitted.emit()

    # ---- resize ----

    def begin_resize(self):
        if self._locked:
            self._active = False
            return
        self._active = True
        self._prev = self.grid_rect()
        self._start_geom = (self.x(), self.y(), self.width(), self.height())
        self.raise_()
        self.canvas.show_guides(True)

    def resize_by(self, edge, dx, dy):
        if not self._active:
            return
        # work in display pixels; floor at the tile minimum scaled by zoom
        z = self.canvas.zoom() or 1.0
        min_disp = max(GRIP, int(round(MIN_TILE * z)))
        x, y, w, h = _proposed_resize(
            edge, self._start_geom, dx, dy, min_px=min_disp)
        self.setGeometry(x, y, w, h)

    def end_resize(self):
        if not self._active:
            return
        self._active = False
        z = self.canvas.zoom() or 1.0
        pad = self.canvas._pad()
        lx = max(0, _snap((self.x() - pad) / z))
        ly = max(0, _snap((self.y() - pad) / z))
        lw = max(MIN_TILE, _snap(self.width() / z))
        lh = max(MIN_TILE, _snap(self.height() / z))
        self._commit_or_revert((lx, ly, lw, lh))

    def _commit_or_revert(self, new_rect):
        self.canvas.show_guides(False)
        if self.canvas.rect_free(new_rect, ignore=self):
            self.x_px, self.y_px, self.w_px, self.h_px = new_rect
            self.canvas.place(self)
            self.canvas.sync_size()
            if new_rect != self._prev:
                self.geometryCommitted.emit()
        else:
            self.canvas.place(self)   # snap back to current pixel rect

    def set_width_px(self, w):
        """Resize the tile to logical width *w* px, keeping its origin/height.

        A numeric stand-in for dragging the east edge, used by the Tile
        Appearance "Tile size" control. Clamped to the content width (the page
        minus its edge margins) and **reverted on overlap** (unlike height,
        which pushes the stack), so a width bump never collides with a neighbour
        or spills into the page margin. Returns ``True`` when applied.
        """
        content_w = self.canvas.content_size()[0]
        lw = max(SNAP, int(w))
        lw = min(lw, max(SNAP, content_w - self.x_px))
        if lw == self.w_px:
            return True
        new_rect = (self.x_px, self.y_px, lw, self.h_px)
        if not self.canvas.rect_free(new_rect, ignore=self):
            return False
        self._prev = self.grid_rect()
        self.w_px = lw
        self.canvas.place(self)
        self.canvas.sync_size()
        self.geometryCommitted.emit()
        return True

    def set_size_px(self, w, h):
        """Resize the tile to logical *w* × *h* px (origin kept).

        Width is applied first (clamped to the region, reverting on overlap),
        then height (which keeps the existing accordion-push behaviour). Used by
        the generic "Tile size" control in the Tile Appearance panel.
        """
        self.set_width_px(w)
        return self.set_height_px(h)

    def set_height_px(self, h):
        """Resize the tile to logical height *h* px, keeping its origin/width.

        A numeric stand-in for dragging the south edge, used by the header
        tile's "Banner height" config control. Unlike a handle drag it keeps the
        **exact** height (no grid snap, no :data:`MIN_TILE` floor) — a banner is
        meant to be a thin band, often shorter than a normal tile — clamped only
        by a tiny safety minimum.

        Rather than reverting when tiles sit below it, the banner **pushes the
        whole stack below it**: every other tile whose top is at or below the
        banner's current bottom is shifted by the height delta (down as it grows,
        back up as it shrinks), so the layout below moves as one accordion and no
        overlap is ever created (any same-column tile below necessarily starts at
        or after the banner's bottom, since overlaps are disallowed). Always
        applied; returns ``True`` (kept for the prior call-site contract).
        """
        lh = max(SNAP, int(h))
        old_h = self.h_px
        if lh == old_h:
            return True
        delta = lh - old_h
        old_bottom = self.y_px + old_h
        for t in self.canvas.tiles():
            if t is self:
                continue
            if t.y_px >= old_bottom - 1:          # below the banner band
                t.y_px = max(0, t.y_px + delta)
        self._prev = self.grid_rect()
        self.h_px = lh
        self.canvas.reflow()                       # re-place every tile (self + pushed)
        self.canvas.sync_size()
        self.geometryCommitted.emit()
        return True


class _DropOverlay(QWidget):
    """Full-canvas, mouse-transparent overlay painting the live drop preview.

    A rect painted in :meth:`DashboardCanvas.paintEvent` would be hidden behind
    the opaque tile widgets, so the drag feedback (yellow landing zone / red
    "won't fit") is drawn here instead — this overlay is raised above every tile
    while a move is in progress and hidden the rest of the time.
    """

    def __init__(self, canvas):
        super().__init__(canvas)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._rect = None        # display-px (x, y, w, h) or None
        self._valid = True
        self.hide()

    def show_preview(self, display_rect, valid):
        self._rect = display_rect
        self._valid = valid
        self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        self.show()
        self.raise_()
        self.update()

    def clear_preview(self):
        self._rect = None
        self.hide()

    def paintEvent(self, _e):
        if self._rect is None:
            return
        x, y, w, h = self._rect
        if w <= 0 or h <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._valid:
            # translucent yellow landing zone
            fill = QColor(255, 214, 0, 70)
            edge = QColor(214, 180, 0, 200)
        else:
            fill = QColor(229, 57, 53, 80)      # translucent red "won't fit"
            edge = QColor(198, 40, 40, 210)
        p.fillRect(x, y, w, h, fill)
        pen = QPen(edge)
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(x, y, max(w - 1, 1), max(h - 1, 1))
        p.end()


class DashboardCanvas(QWidget):
    """Holds GridTiles in a free-form (overlap-free) pixel layout."""

    layoutChanged = pyqtSignal()         # a tile moved/resized/added/removed

    def __init__(self, bus, cols=12, rows=8, parent=None):
        super().__init__(parent)
        self.bus = bus
        # ``cols``/``rows`` are no longer used for layout (tiles are free-form
        # pixels); they are retained only as harmless persisted metadata so the
        # save/restore plumbing and older signatures keep working.
        self.cols = max(int(cols), 1)
        self.rows = max(int(rows), 1)
        self._tiles = []
        self._guides = False
        self._exporting = False   # suppress region frame/scrim while exporting
        self._zoom = 1.0
        self._locked = False
        # global element gap (logical px): transparent breathing room inset
        # around every tile's card. 0 == cards may sit edge to edge.
        self.gap = 0
        # the export/print region (the "page") in logical px — the canvas draws a
        # hairline frame around it, Reset Zoom fits it, and export renders it.
        self.region_w = DEFAULT_REGION_W
        self.region_h = DEFAULT_REGION_H
        self.setObjectName("dashCanvas")
        self.setMinimumSize(480, 360)
        self._drop_overlay = _DropOverlay(self)
        if bus is not None:
            bus.themeChanged.connect(self.update)

    # ---- layout lock ----

    def is_locked(self):
        return self._locked

    def set_locked(self, locked):
        """Lock/unlock moving + resizing of every tile on this canvas."""
        self._locked = bool(locked)
        for t in self._tiles:
            t.set_locked(self._locked)

    # ---- zoom ----

    def zoom(self):
        return self._zoom

    def set_zoom(self, z):
        self._zoom = max(0.05, float(z))
        self.reflow()
        self.sync_size()
        self.update()

    # ---- export/print region (the "page") ----

    def region_size(self):
        """The export/print region in logical (zoom-1.0) px ``(w, h)``."""
        return (self.region_w, self.region_h)

    def set_region(self, w, h):
        """Set the export/print region size (logical px) and repaint/regrow.

        The region defines the page the dashboard is laid out on: the canvas
        draws a hairline frame around it, Reset Zoom fits it to the viewport,
        and PNG/PDF export render exactly this rect. Tiles may still be dragged
        beyond it (they overflow the page and are cropped on export).
        """
        self.region_w = max(MIN_REGION, int(w))
        self.region_h = max(MIN_REGION, int(h))
        self.sync_size()
        self.update()

    def set_region_scaled(self, w, h):
        """Resize the page region *and* scale every tile to match.

        Unlike :meth:`set_region` (which only reframes the page, leaving tiles
        at their absolute pixel geometry — correct for the page-create and
        layout-load paths), this rescales every tile's logical rect by a single
        uniform factor so the whole layout grows/shrinks with the page while
        each tile keeps its own aspect ratio. The factor is the smaller of the
        two axis ratios (:func:`layout_util.region_scale_factor`) so the layout
        fits fully inside the new page — every tile stays within the region, so
        nothing is ever cropped on PNG/PDF export (a different aspect ratio just
        leaves even margin in the longer axis). The layout is anchored top-left,
        since tiles live in content-logical coords with the origin at the inner
        margin. Tiles may shrink below :data:`MIN_TILE` (that floor gates only
        manual resize, not proportional scaling).
        """
        new_w = max(MIN_REGION, int(w))
        new_h = max(MIN_REGION, int(h))
        factor = region_scale_factor(
            self.region_w, self.region_h, new_w, new_h)
        if abs(factor - 1.0) > 1e-9:
            for t in self._tiles:
                t.x_px, t.y_px, t.w_px, t.h_px = scale_rect(
                    t.grid_rect(), factor)
                t._prev = t.grid_rect()
        self.set_region(new_w, new_h)   # update region + regrow surface
        self.reflow()                   # re-place every (now rescaled) tile
        self.layoutChanged.emit()

    # ---- element gap (global spacing) ----

    def set_gap(self, px):
        """Set the global spacing (logical px) and re-apply it live.

        ``gap`` is a single *unified spacing* value S: it is the distance
        between two adjacent cards **and** the page margin from the page edge to
        the outermost cards — they are deliberately equal so the layout reads as
        evenly spaced no matter where a tile sits. Mechanically S is split in
        half twice (see :meth:`_margin` / :meth:`_tile_inset`): each card is
        inset by S/2 inside its footprint and the page reserves an S/2 margin
        inside each edge, so a card flush to the content edge ends up S from the
        page edge and two touching footprints show an S gap between their cards.
        Re-placing every tile picks up the new inset; the surface is re-grown.
        """
        self.gap = max(0, int(px))
        self.reflow()
        self.sync_size()
        self.update()

    def _tile_inset(self):
        """The per-card inset in display px — half the spacing, scaled by zoom.

        Each card is inset by S/2 inside its footprint, so two touching
        footprints leave a full S between their cards (S/2 from each).
        """
        return int(round((self.gap / 2.0) * (self._zoom or 1.0)))

    def _margin(self):
        """Inner page margin in LOGICAL px — half the spacing (S/2).

        The export/print region (the page) reserves this margin inside every
        edge. Combined with the per-card inset (also S/2), a card flush to the
        content edge ends up S from the page edge — equal to the S gap between
        two adjacent cards. Zero when the spacing is zero, so cards still reach
        the page edge.
        """
        return self.gap // 2

    def _pad(self):
        """Display-px offset applied to every tile = the inner page margin.

        Tiles are placed at ``pad + x*zoom`` so logical ``x=0`` lands one margin
        inside the page's left edge (and likewise the top); the per-card inset
        then adds the other half, so card-to-edge equals card-to-card. Equal to
        :meth:`_tile_inset` (both are S/2 scaled by zoom), kept as a separate
        name because they play conceptually distinct roles (margin vs inset).
        """
        return int(round(self._margin() * (self._zoom or 1.0)))

    def content_size(self):
        """Usable tile area inside the page (region minus the two edge margins).

        New tiles, snapping and the no-overlap fit all work in this
        *content-logical* space (origin at the inner top-left margin), so tiles
        stay framed by an even margin on every side of the page.
        """
        m2 = 2 * self._margin()
        return (max(MIN_REGION, self.region_w) - m2,
                max(MIN_REGION, self.region_h) - m2)

    # ---- geometry helpers ----

    def tiles(self):
        return list(self._tiles)

    def logical_size(self):
        """The canvas surface size in logical (zoom-1.0) pixels.

        Used to clamp tile placement so a tile stays fully on the surface. The
        outer gutter (``_pad`` on each side) is excluded so tiles never land in
        the gutter reserved to keep edge gaps even.
        """
        z = self._zoom or 1.0
        pad2 = 2 * self._pad()
        return max(self.width() - pad2, 0) / \
            z, max(self.height() - pad2, 0) / z

    def _content_extent(self):
        """Right/bottom extent of all tiles, in logical pixels."""
        max_r = max_b = 0
        for t in self._tiles:
            x, y, w, h = t.grid_rect()
            max_r = max(max_r, x + w)
            max_b = max(max_b, y + h)
        return max_r, max_b

    def rect_free(self, rect, ignore=None):
        """True if *rect* (logical px) is on-surface and overlaps no other tile."""
        x, y, w, h = rect
        if x < 0 or y < 0:
            return False
        for t in self._tiles:
            if t is ignore:
                continue
            ox, oy, ow, oh = t.grid_rect()
            if x < ox + ow and ox < x + w and y < oy + oh and oy < y + h:
                return False
        return True

    def _other_rects(self, ignore):
        """Logical rects of every tile except *ignore* (for snap/fit math)."""
        return [t.grid_rect() for t in self._tiles if t is not ignore]

    def snap_for(self, rect, ignore):
        """Magnetically snap a dragged tile's logical rect to its neighbours.

        Keeps the tile's size and pulls each edge to the nearest neighbour /
        content-edge snap line within :data:`SNAP_PULL`. Footprints snap to
        **touch** (``gap=0``): the visible spacing is rendered by the per-card
        inset, so two snapped cards always show exactly the unified spacing —
        the snap math no longer adds a separate gap that would double it.
        """
        return snap_rect(rect, self._other_rects(ignore),
                         self.content_size(),
                         gap=0, threshold=SNAP_PULL)

    def fit_for(self, rect, ignore):
        """Nearest same-size placement of *rect* that overlaps nothing.

        Used as the no-revert fallback when a drop lands on an occupied area:
        the tile slides to the closest free slot instead of flying back to its
        drag-start position.
        """
        return nearest_free(rect, self._other_rects(ignore),
                            self.content_size(), step=SNAP)

    def set_drop_preview(self, logical_rect, valid):
        """Show the live drag feedback at *logical_rect* (None clears it).

        ``valid`` picks the colour: a yellow landing zone when the tile fits
        there, red when it does not. The rect is converted to display pixels
        (logical x zoom, offset by the outer gutter) like a placed tile.
        """
        if logical_rect is None:
            self._drop_overlay.clear_preview()
            return
        z = self._zoom or 1.0
        pad = self._pad()
        x, y, w, h = logical_rect
        disp = (pad + int(round(x * z)), pad + int(round(y * z)),
                int(round(w * z)), int(round(h * z)))
        self._drop_overlay.show_preview(disp, valid)

    def first_free(self, w, h):
        """Find a non-overlapping origin for a *w*x*h* tile (logical px).

        Searches within the content area (the page minus its edge margins) so
        new tiles land on the page framed by an even margin.
        """
        step = 20
        cw, ch = self.content_size()
        max_x = max(int(cw - w), 0)
        max_y = max(int(ch - h), 0)
        y = 0
        while y <= max_y:
            x = 0
            while x <= max_x:
                if self.rect_free((x, y, w, h)):
                    return (x, y, w, h)
                x += step
            y += step
        # surface is packed: cascade from the origin so the new tile is visible
        n = len(self._tiles)
        off = MARGIN + (n * 28) % 240
        return (off, off, w, h)

    # ---- tile lifecycle ----

    def add_tile(self, element, pixel_rect=None):
        if pixel_rect is None:
            tname = getattr(element, "type_name", "")
            if tname == "map":
                pixel_rect = self.first_free(MAP_W, MAP_H)
            elif tname == "header":
                # a banner-shaped default: spans the content width, short
                # height
                pixel_rect = self.first_free(
                    self.content_size()[0], HEADER_BAND_H)
            else:
                pixel_rect = self.first_free(DEFAULT_W, DEFAULT_H)
        tile = GridTile(self, element, pixel_rect)
        tile.closeRequested.connect(self._on_close)
        tile.geometryCommitted.connect(self.layoutChanged)
        # honour the canvas's current lock state
        tile.set_locked(self._locked)
        self._tiles.append(tile)
        tile.show()
        self.place(tile)
        self.sync_size()
        self.layoutChanged.emit()
        return tile

    def _on_close(self, element):
        for t in list(self._tiles):
            if t.element is element:
                self._tiles.remove(t)
                element.teardown()
                t.setParent(None)
                t.deleteLater()
                if self.bus is not None:
                    self.bus.forget_element(getattr(element, "id", None))
                self.sync_size()
                self.layoutChanged.emit()
                return

    def clear(self):
        for t in self._tiles:
            t.element.teardown()
            t.setParent(None)
            t.deleteLater()
        self._tiles = []
        self.layoutChanged.emit()

    def place(self, tile):
        """Position one tile at ``pad + logical x zoom`` display pixels.

        The ``pad`` outer gutter (see :meth:`_pad`) offsets every tile inward so
        the gap at the canvas edges matches the gap between cards.
        """
        z = self._zoom or 1.0
        pad = self._pad()
        x, y, w, h = tile.grid_rect()
        tile.setGeometry(pad + int(round(x * z)), pad + int(round(y * z)),
                         max(int(round(w * z)), 1), max(int(round(h * z)), 1))
        tile.set_inset(self._tile_inset())

    def reflow(self):
        for t in self._tiles:
            self.place(t)

    def sync_size(self):
        """Grow the surface so it contains the region *and* every tile.

        The surface is the export/print region, expanded only when a tile has
        been dragged past the page edge so that off-page tile stays reachable
        (it is cropped on export). The region — not the viewport — drives the
        size now, so Reset Zoom can fit the page exactly.
        """
        z = self._zoom or 1.0
        m2 = 2 * self._margin()   # the page's two edge margins (logical px)
        max_r, max_b = self._content_extent()
        # the surface spans the page (region) or grows to hold a tile dragged
        # past the content edge, keeping a matching margin beyond it. ``max_r``
        # is in content-logical coords, so its page extent is ``max_r + m2``.
        lw = max(self.region_w, max_r + m2 + MARGIN)
        lh = max(self.region_h, max_b + m2 + MARGIN)
        w = int(round(lw * z))
        h = int(round(lh * z))
        if (self.minimumWidth(), self.minimumHeight()) != (w, h):
            self.setMinimumSize(w, h)
            self.resize(w, h)

    def set_grid(self, cols, rows):
        """Retained for compatibility: store metadata, re-place tiles.

        The grid no longer drives layout — tiles keep their pixel placement —
        so this only refreshes the stored ``cols``/``rows`` and reflows.
        """
        self.cols = max(int(cols), 1)
        self.rows = max(int(rows), 1)
        self.reflow()
        self.sync_size()
        self.update()
        self.layoutChanged.emit()

    def show_guides(self, on):
        self._guides = on
        self.update()

    # ---- export ----

    def export_pixmap(self, scale=2.0):
        """Render the export/print region to a high-res QPixmap.

        Exports exactly the region rect (the "page") at the logical layout
        (zoom 1.0) regardless of the current view zoom, with the editing chrome
        and the on-screen region frame/scrim hidden. Tiles outside the region
        are cropped; empty space inside it becomes intentional margin — so the
        result is always the clean rectangle the user defined, at *scale*x
        device resolution (crisp for PNG / PDF). The live view's zoom and chrome
        are restored afterwards.
        """
        old_zoom = self._zoom
        zoom_changed = abs(old_zoom - 1.0) > 1e-6
        self.show_guides(False)
        self._exporting = True
        for t in self._tiles:
            t.set_chrome_visible(False)
        try:
            if zoom_changed:
                self.set_zoom(1.0)   # reflows + grows the surface to content
            else:
                self.sync_size()
            # the page (region) is drawn from the surface origin (0, 0); its
            # edge margins are reserved inside it, so the crop is just the
            # region rect anchored at the top-left.
            scale = max(0.5, float(scale))
            theme = self.bus.theme if self.bus is not None else None
            bg = QColor(theme.window_bg) if theme else QColor("#f4f6f8")
            # render the full surface, then crop out exactly the region rect —
            # unambiguous regardless of any off-page tiles growing the surface
            full = QPixmap(max(int(round(self.width() * scale)), 1),
                           max(int(round(self.height() * scale)), 1))
            full.setDevicePixelRatio(scale)
            full.fill(bg)
            self.render(full, QPoint(0, 0))
            src = QRect(0, 0,
                        max(int(round(self.region_w * scale)), 1),
                        max(int(round(self.region_h * scale)), 1))
            pm = full.copy(src)
            pm.setDevicePixelRatio(scale)
            return pm
        finally:
            self._exporting = False
            for t in self._tiles:
                t.set_chrome_visible(True)
            if zoom_changed:
                self.set_zoom(old_zoom)

    # ---- painting ----

    def _region_display_rect(self):
        """The export/print region as a display-pixel ``(x, y, w, h)`` tuple.

        Anchored at the surface origin; the page's edge margins are reserved
        inside it (tiles are offset inward by :meth:`_pad`), so the frame is the
        true page boundary and the off-page scrim falls outside it.
        """
        z = self._zoom or 1.0
        return (0, 0,
                int(round(self.region_w * z)), int(round(self.region_h * z)))

    def _paint_region(self, p, theme):
        """Dim the off-page area and frame the region with a soft hairline."""
        rx, ry, rw, rh = self._region_display_rect()
        W, H = self.width(), self.height()
        # faint neutral scrim over the four bands outside the page (theme-neutral
        # so it dims a light canvas without darkening to black on a dark one)
        scrim = QColor(120, 128, 138, 38)
        for band in ((0, 0, W, ry),                       # top
                     (0, ry + rh, W, H - (ry + rh)),      # bottom
                     (0, ry, rx, rh),                     # left
                     (rx + rw, ry, W - (rx + rw), rh)):   # right
            bx, by, bw, bh = band
            if bw > 0 and bh > 0:
                p.fillRect(bx, by, bw, bh, scrim)
        # soft hairline frame (the same border colour the chrome uses)
        pen = QPen(QColor(theme.border) if theme else QColor("#e2e6ec"))
        pen.setCosmetic(True)
        pen.setWidth(1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rx, ry, max(rw - 1, 1), max(rh - 1, 1))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.reflow()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self.bus.theme if self.bus is not None else None
        # paint the canvas background ourselves (configurable via the theme's
        # "Canvas background" colour) so it never inherits the QGIS palette
        bg = QColor(theme.window_bg) if theme else QColor("#f4f6f8")
        p.fillRect(self.rect(), bg)
        # the export/print region (the "page"): dim everything outside it with a
        # faint neutral scrim and frame it with a soft hairline, so it reads
        # clearly as the page the dashboard will export to. Suppressed while
        # exporting (the saved image *is* the page — no frame inside it).
        if not self._exporting:
            self._paint_region(p, theme)
        # while a tile is being dragged/resized, hint the 8px snap with a faint
        # dot lattice (coarsely spaced) — otherwise the canvas stays clean
        if self._guides:
            dot = QColor(theme.grid_line) if theme else QColor("#c4ccd4")
            dot.setAlpha(150)
            step = SNAP * 5 * (self._zoom or 1.0)
            pad = self._pad()   # align the lattice with the gutter-offset tiles
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot)
            x = float(pad)
            while x <= self.width() - pad:
                y = float(pad)
                while y <= self.height() - pad:
                    p.drawEllipse(QPointF(x, y), 1.4, 1.4)
                    y += step
                x += step
        p.end()
