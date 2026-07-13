# -*- coding: utf-8 -*-
"""The Add-element picker — a slim left-docked panel, à la AGOL Experience Builder.

Adding a tile is a single choice: *which kind*. The picker mirrors the chrome of
the right-edge :class:`~side_panel.InspectorPanel` (flat, full-height, a soft
hairline border, a title + ✕ header) but is **thinner** and docks on the **left**
— an in-window overlay child pinned flush against the right edge of the icon
rail, with no gap. It shows one tinted ``el_<type_name>`` glyph per registered
element type, each with the element's name captioned beneath it. Clicking one
emits :attr:`elementChosen` and closes — the tile is added with sensible
defaults and configured afterward from its right-click ``Configure…`` menu
(which uses the inspector-panel editors).

It enters with a short slide-out from behind the rail. Picking a glyph or the ✕
closes it; calling :meth:`open_beside` again while open toggles it shut.
"""

from qgis.PyQt.QtCore import (
    Qt, QPoint, QRect, QSize, QEasingCurve, QPropertyAnimation, pyqtSignal,
)
from qgis.PyQt.QtWidgets import (
    QFrame,
    QToolButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QWidget,
    QScrollArea,
)

from .icons import monochrome_icon
from .elements import ELEMENT_LABELS
from .theme import CHROME

PANEL_WIDTH = 200       # slim left-docked panel (thinner than the inspector)
GRID_COLS = 2           # icon tiles per row
TILE_W = 84             # picker tile width
TILE_H = 82             # picker tile height (room for a wrapping name caption)
ICON_PX = 26            # glyph size inside a tile


class _PickerTile(QFrame):
    """A clickable icon + wrapping name caption for one element type.

    A plain :class:`QToolButton` can't word-wrap a multi-word label
    ("Category selector", "Header (brand banner)"), so each tile is a small
    frame with an icon over a wrapping :class:`QLabel`. The whole frame is the
    click target.
    """

    clicked = pyqtSignal(str)   # emits the element type_name

    def __init__(self, key, label, parent=None):
        super().__init__(parent)
        self.setObjectName("pickerTile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(TILE_W, TILE_H)
        self.key = key

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(4)
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setObjectName("pickerTileIcon")
        self.caption = QLabel(label)
        self.caption.setObjectName("pickerTileText")
        self.caption.setWordWrap(True)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignHCenter
                                  | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.icon_label)
        lay.addWidget(self.caption, 1)
        self.set_icon_tint(CHROME["text"])

    def set_icon_tint(self, color):
        """(Re)paint the glyph in *color*; fall back to caption-only if absent."""
        icon = monochrome_icon("el_" + self.key, color, size=ICON_PX)
        if icon.isNull():               # QtSvg missing → caption is enough
            self.icon_label.hide()
        else:
            self.icon_label.setPixmap(icon.pixmap(QSize(ICON_PX, ICON_PX)))
            self.icon_label.show()

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.pos())):
            self.clicked.emit(self.key)
        super().mouseReleaseEvent(event)


class ElementPicker(QFrame):
    """A slim, left-docked overlay for choosing the element type to add."""

    elementChosen = pyqtSignal(str)   # emits the element type_name

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.setObjectName("elementPickerPanel")
        self._theme = theme
        self._anim = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- header: title + close ✕ (mirrors InspectorPanel) ----
        header = QFrame()
        header.setObjectName("pickerHeader")
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(14, 12, 8, 12)
        title = QLabel("Add element")
        title.setObjectName("pickerTitle")
        hrow.addWidget(title, 1)
        self._close_btn = QToolButton()
        self._close_btn.setObjectName("pickerClose")
        self._close_btn.setText("✕")
        self._close_btn.setAutoRaise(True)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("Close")
        self._close_btn.clicked.connect(self.hide)
        hrow.addWidget(self._close_btn)
        root.addWidget(header)

        # ---- glyph grid (scrolls if it ever overflows the height) ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(8, 10, 8, 10)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        self._tiles = []
        for i, (key, label) in enumerate(ELEMENT_LABELS.items()):
            tile = self._tile(key, label)
            self._tiles.append(tile)
            grid.addWidget(
                tile,
                i //
                GRID_COLS,
                i %
                GRID_COLS,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(grid_host)
        root.addWidget(scroll, 1)

        self.apply_theme(theme)
        self.hide()

    # ---- tiles ----------------------------------------------------------

    def _tile(self, key, label):
        tile = _PickerTile(key, label, self)
        tile.clicked.connect(self._choose)
        return tile

    def _choose(self, key):
        self.hide()
        self.elementChosen.emit(key)

    # ---- open / position ------------------------------------------------

    def open_beside(self, rail):
        """Show the panel flush against *rail*'s right edge, full height.

        If already open, this toggles it shut (the rail button acts as a
        toggle)."""
        if self.isVisible():
            self.hide()
            return
        self.reposition(rail)
        self.show()
        self.raise_()
        self._animate_in(rail)

    def reposition(self, rail):
        p = self.parentWidget()
        if p is None or rail is None:
            return
        x = rail.x() + rail.width()           # flush to the rail's right edge
        self.setGeometry(QRect(x, 0, PANEL_WIDTH, p.height()))

    def _animate_in(self, rail):
        x = rail.x() + rail.width()
        end = QPoint(x, 0)
        start = QPoint(x - PANEL_WIDTH, 0)    # slide out from behind the rail
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(170)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim          # keep a reference so it isn't GC'd

    # ---- theming --------------------------------------------------------

    def apply_theme(self, theme):
        # The picker is CHROME (it docks to the rail and is part of the plugin
        # UI), so it uses the fixed CHROME palette — the dashboard theme styles
        # the canvas only and must not recolor this panel or its glyphs.
        self._theme = theme
        self._retint_tiles(theme)   # keep glyphs at the fixed chrome tint
        self.setStyleSheet("""
#elementPickerPanel {{ background:{chrome}; border-right:1px solid {border}; }}
#pickerHeader {{ background:{chrome}; border-bottom:1px solid {border}; }}
#pickerTitle {{ color:{text}; font-weight:700; }}
QToolButton#pickerClose {{
    border:none; background:transparent; border-radius:6px; padding:2px 6px;
    color:{muted}; font-size:15px;
}}
QToolButton#pickerClose:hover {{ background:{brand_soft}; color:{accent}; }}
#pickerTile {{
    background:transparent; border:1px solid transparent; border-radius:10px;
}}
#pickerTile:hover {{ background:{brand_soft}; border-color:{border}; }}
#pickerTileText {{ color:{text}; font-size:10px; background:transparent; }}
#pickerTileIcon {{ background:transparent; }}
""".format(chrome=CHROME["bg"], border=CHROME["border"], text=CHROME["text"],
           muted=CHROME["muted"], accent=CHROME["accent"],
           brand_soft=CHROME["brand_soft"]))

    def _retint_tiles(self, theme):
        """Repaint each glyph in the fixed chrome tint (theme-independent)."""
        for tile in getattr(self, "_tiles", []):
            tile.set_icon_tint(CHROME["text"])
