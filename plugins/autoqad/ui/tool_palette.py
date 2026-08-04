# -*- coding: utf-8 -*-
"""The tool palette — AutoQAD's dockable grid of command buttons.

A **wrapping** palette, not a fixed vertical rail: tools flow left to right and
wrap onto as many rows as the dock's width allows. Docked narrow against the
left edge it reads as a single column; dragged wider, or floated, it fills out
into a grid. The narrowest it can ever be squeezed is exactly one column, which
:class:`~.flow_layout.FlowLayout` enforces through its ``minimumSize``.

The palette is **deliberately dark and fixed** (:data:`~.theme.TOOL_PALETTE`),
independent of whatever theme QGIS is running. Glyphs are tinted white. CAD
tool palettes look like this everywhere they exist, and a palette that flips
appearance with the host theme reads as unfinished.

The palette owns no behaviour: each button runs a command *by name* through the
same runner the command line uses, so clicking a tool and typing its alias are
literally the same code path.
"""

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget, QFrame, QScrollArea, QToolButton, QWidget,
)

from . import theme
from .flow_layout import FlowLayout, make_separator
from .icons import monochrome_icon

BUTTON_SIZE = 34
ICON_SIZE = 20
SPACING = 4
MARGIN = 6
#: Room for the vertical scrollbar, so one column never triggers a horizontal
#: one. Keeps the "narrowest is one column" promise honest.
SCROLLBAR_ALLOWANCE = 12

#: ``(icon, command, tooltip)`` per entry; ``None`` inserts a group divider.
LAYOUT = (
    ("line", "LINE", "Line (L)"),
    ("polyline", "PLINE", "Polyline (PL)"),
    ("rectangle", "RECTANG", "Rectangle (REC)"),
    ("circle", "CIRCLE", "Circle (C)"),
    ("arc", "ARC", "Arc (A)"),
    ("polygon", "POLYGON", "Polygon (POL)"),
    ("ellipse", "ELLIPSE", "Ellipse (EL)"),
    ("point", "POINT", "Point (PO)"),
    ("text", "TEXT", "Text (DT)"),
    ("hatch", "HATCH", "Hatch (H)"),
    None,
    ("move", "MOVE", "Move (M)"),
    ("copy", "COPY", "Copy (CO)"),
    ("rotate", "ROTATE", "Rotate (RO)"),
    ("scale", "SCALE", "Scale (SC)"),
    ("mirror", "MIRROR", "Mirror (MI)"),
    ("offset", "OFFSET", "Offset (O)"),
    ("trim", "TRIM", "Trim (TR)"),
    ("extend", "EXTEND", "Extend (EX)"),
    ("fillet", "FILLET", "Fillet (F)"),
    ("array", "ARRAY", "Array (AR)"),
    ("explode", "EXPLODE", "Explode (X)"),
    ("join", "JOIN", "Join (J)"),
    ("erase", "ERASE", "Erase (E)"),
    None,
    ("layers", "LAYER", "Layer Manager (LA)"),
    ("snap", "DSETTINGS", "Drafting Settings (DS)"),
    ("measure", "DIST", "Measure distance (DI)"),
    ("undo", "UNDO", "Undo (U)"),
    ("redo", "REDO", "Redo"),
    ("erase", "ERASEALL", "Erase everything (ERASEALL)"),
    None,
    ("plot", "PLOT", "Plot (PRINT)"),
    ("export", "DXFOUT", "Export to DXF"),
    ("settings", "OPTIONS", "Options (OP)"),
    ("help", "HELP", "Command reference"),
)


class _PaletteScroll(QScrollArea):
    """Scroll area that drives its body's height from the flow layout.

    ``heightForWidth`` does propagate through nested layouts in principle, but
    through a ``QScrollArea`` it is unreliable enough to be worth sidestepping:
    the body ends up either clipped or unscrollable depending on Qt version.
    Asking the layout directly on every resize is deterministic.
    """

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_body_height()

    def _sync_body_height(self):
        body = self.widget()
        if body is None:
            return
        layout = body.layout()
        if layout is None or not layout.hasHeightForWidth():
            return
        needed = layout.heightForWidth(self.viewport().width())
        if needed > 0 and body.minimumHeight() != needed:
            body.setMinimumHeight(needed)


class ToolPaletteDock(QDockWidget):
    """Dockable, wrapping grid of command buttons."""

    #: A tool was pressed; carries the command name.
    commandRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("AutoQAD Tools", parent)
        self.setObjectName("aqToolPalette")
        self._buttons = []
        self._build()
        # The fixed dark stylesheet — deliberately NOT theme.apply(), which is
        # the light chrome used by the dialogs.
        self.setStyleSheet(theme.tool_palette_qss())

    # ---- construction ----

    def _build(self):
        scroll = _PaletteScroll(self)
        scroll.setObjectName("aqPaletteScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # Never a horizontal scrollbar: the layout wraps instead, which is the
        # whole point of the palette.
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget(scroll)
        body.setObjectName("aqPaletteBody")

        # The flow layout is the body's own layout, so the scroll area can ask
        # it for a height directly.
        flow = FlowLayout(body, margin=MARGIN, spacing=SPACING)

        for entry in LAYOUT:
            if entry is None:
                flow.addWidget(make_separator(
                    body, BUTTON_SIZE, theme.TOOL_PALETTE["separator"]))
                continue
            icon_key, command, tooltip = entry
            flow.addWidget(self._button(body, icon_key, command, tooltip))

        scroll.setWidget(body)
        self.setWidget(scroll)

        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea
                             | Qt.DockWidgetArea.TopDockWidgetArea
                             | Qt.DockWidgetArea.BottomDockWidgetArea)

        # One column is the floor. Qt refuses to shrink a dock below its
        # widget's minimum, so this is what stops the palette collapsing.
        self.setMinimumWidth(BUTTON_SIZE + 2 * MARGIN + SCROLLBAR_ALLOWANCE)

    def _button(self, parent, icon_key, command, tooltip):
        button = QToolButton(parent)
        button.setObjectName("aqToolButton")
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

        icon = monochrome_icon(icon_key, theme.TOOL_PALETTE["icon"], ICON_SIZE)
        if icon.isNull():
            button.setText(command[:2])
        else:
            button.setIcon(icon)

        button.clicked.connect(
            lambda _checked=False, name=command:
            self.commandRequested.emit(name))
        self._buttons.append((button, icon_key))
        return button

    # ---- appearance ----

    def refresh_icons(self):
        """Re-tint every glyph — used if the palette colours ever change."""
        for button, icon_key in self._buttons:
            icon = monochrome_icon(icon_key, theme.TOOL_PALETTE["icon"],
                                   ICON_SIZE)
            if not icon.isNull():
                button.setIcon(icon)
