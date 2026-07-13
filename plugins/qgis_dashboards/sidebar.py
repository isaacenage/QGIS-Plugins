# -*- coding: utf-8 -*-
"""The dashboard's left navigation rail.

A slim, icon-only vertical rail (à la VS Code / Linear / the Summarizer
plugin) that replaces the old horizontal toolbar. The branded gradient logo
sits at the top; below it are the tool actions — grouped by thin dividers —
each an :class:`QToolButton` carrying a tinted SVG glyph and a tooltip (the
tooltip doubles as the accessible name, since the buttons show no text).

The rail owns no behavior of its own: callers register ``(icon, tooltip,
callback)`` triples via :meth:`add_action`. Icon colors follow the active
:class:`~theme.Theme` and are recomputed in :meth:`apply_theme`; hover and
pressed feedback come from the window stylesheet (``theme.window_qss``).
"""

from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QFrame, QLabel, QToolButton, QVBoxLayout

from .icons import logo_pixmap, monochrome_icon
from .theme import CHROME

RAIL_WIDTH = 56
BUTTON_SIZE = 40
ICON_SIZE = 22
LOGO_SIZE = 34


class Sidebar(QFrame):
    """Icon-only navigation rail for :class:`~window.DashboardWindow`."""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.setObjectName("dashSidebar")
        self.setFixedWidth(RAIL_WIDTH)
        self._theme = theme
        self._buttons = []          # list of (QToolButton, icon_key)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 10, 8, 12)
        self._layout.setSpacing(6)

        self._logo = QLabel(self)
        self._logo.setObjectName("dashSidebarLogo")
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self._logo.setPixmap(logo_pixmap(LOGO_SIZE))
        self._logo.setToolTip("QGIS Dashboard")
        self._layout.addWidget(self._logo, 0, Qt.AlignmentFlag.AlignHCenter)
        self.add_separator()

    # ---- builders ----

    def add_action(self, icon_key, tooltip, callback):
        """Append an icon button that invokes *callback* (no args) on click."""
        btn = QToolButton(self)
        btn.setObjectName("dashRailButton")
        btn.setToolTip(tooltip)
        btn.setAccessibleName(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setAutoRaise(True)
        btn.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        btn.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        # Rail icons are CHROME: a fixed tint that the dashboard theme never
        # touches (the theme styles the canvas only).
        icon = monochrome_icon(icon_key, CHROME["text"])
        if icon.isNull():
            # graceful fallback if QtSvg is missing
            btn.setText(tooltip[:2])
        else:
            btn.setIcon(icon)
        btn.clicked.connect(lambda _checked=False, cb=callback: cb())
        self._layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        self._buttons.append((btn, icon_key))
        return btn

    def add_separator(self):
        line = QFrame(self)
        line.setObjectName("dashRailSep")
        line.setFixedHeight(1)
        line.setFixedWidth(BUTTON_SIZE - 12)
        self._layout.addWidget(line, 0, Qt.AlignmentFlag.AlignHCenter)
        return line

    def add_stretch(self):
        self._layout.addStretch(1)

    # ---- theming ----

    def apply_theme(self, theme):
        """Kept for API symmetry; the rail is fixed chrome, so a theme change
        does not re-tint its glyphs (they use the constant ``CHROME`` tint)."""
        self._theme = theme
        self._logo.setPixmap(logo_pixmap(LOGO_SIZE))
        for btn, icon_key in self._buttons:
            icon = monochrome_icon(icon_key, CHROME["text"])
            if not icon.isNull():
                btn.setIcon(icon)
