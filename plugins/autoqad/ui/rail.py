# -*- coding: utf-8 -*-
"""The tool rail — AutoQAD's left icon dock.

A slim icon-only column, the same chrome the sibling plugins use: tinted SVG
glyphs, tooltips doubling as accessible names, thin dividers between groups.

The rail holds no behaviour of its own. Each button simply runs a command by
name through the same runner the command line uses, so clicking *Line* and
typing ``L`` are literally the same code path — there is no separate
click-handling branch that can drift out of step.
"""

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QDockWidget, QFrame, QLabel, QScrollArea, QToolButton, QVBoxLayout,
)

from . import theme
from .icons import logo_pixmap, monochrome_icon

RAIL_WIDTH = 56
BUTTON_SIZE = 40
ICON_SIZE = 22
LOGO_SIZE = 32

#: ``(icon, command, tooltip)`` per group; ``None`` inserts a divider.
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
    None,
    ("export", "DXFOUT", "Export to DXF"),
    ("settings", "OPTIONS", "Options (OP)"),
    ("help", "HELP", "Command reference"),
)


class ToolRailDock(QDockWidget):
    """Icon-only command rail."""

    #: A rail button was pressed; carries the command name.
    commandRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("AutoQAD Tools", parent)
        self.setObjectName("aqToolRail")
        self._buttons = []
        self._build()
        theme.apply(self)

    def _build(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        rail = QFrame(scroll)
        rail.setObjectName("aqRail")
        rail.setFixedWidth(RAIL_WIDTH)

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(8, 10, 8, 12)
        layout.setSpacing(5)

        logo = QLabel(rail)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        logo.setPixmap(logo_pixmap(LOGO_SIZE))
        logo.setToolTip("AutoQAD")
        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._separator(rail), 0,
                         Qt.AlignmentFlag.AlignHCenter)

        for entry in LAYOUT:
            if entry is None:
                layout.addWidget(self._separator(rail), 0,
                                 Qt.AlignmentFlag.AlignHCenter)
                continue
            icon_key, command, tooltip = entry
            layout.addWidget(self._button(rail, icon_key, command, tooltip), 0,
                             Qt.AlignmentFlag.AlignHCenter)

        layout.addStretch(1)

        scroll.setWidget(rail)
        self.setWidget(scroll)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea
                             | Qt.DockWidgetArea.RightDockWidgetArea)

    def _button(self, parent, icon_key, command, tooltip):
        button = QToolButton(parent)
        button.setObjectName("aqRailButton")
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        button.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

        icon = monochrome_icon(icon_key, theme.PALETTE["text"], ICON_SIZE)
        if icon.isNull():
            button.setText(command[:2])
        else:
            button.setIcon(icon)

        button.clicked.connect(
            lambda _checked=False, name=command:
            self.commandRequested.emit(name))
        self._buttons.append((button, icon_key))
        return button

    @staticmethod
    def _separator(parent):
        line = QFrame(parent)
        line.setObjectName("aqRailSep")
        line.setFixedHeight(1)
        line.setFixedWidth(BUTTON_SIZE - 12)
        return line
