# -*- coding: utf-8 -*-
"""InspectorPanel — a right-edge editor panel, à la ArcGIS Experience Builder.

The tile editors (Configure / Connections / Tile appearance) and the header
editor no longer open as modal dialogs that block the canvas. They are hosted,
one at a time, in this panel which **overlays the right strip of the canvas**
(it is a manually-positioned child of the window's central area, raised above
the page view, never in a layout). The left icon rail is always clear of it.

Commit model (the window supplies the callbacks):
  * **OK** runs ``on_commit`` — keep the live edits.
  * **Cancel** / the header **✕** / closing runs ``on_cancel`` — revert.
  * Opening another editor while one is open implicitly **commits** the open
    one first (its live changes are already visible, so moving on keeps them).
  * If the edited subject (a tile) is removed, the panel is dropped *without*
    running either callback (they would touch a destroyed object).
"""

from qgis.PyQt.QtCore import (
    Qt, QPoint, QRect, QEasingCurve, QPropertyAnimation, pyqtSignal,
)
from qgis.PyQt.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QPushButton,
    QWidget,
)

from .theme import CHROME

PANEL_WIDTH = 360
PANEL_MIN_WIDTH = 300
GRIP_WIDTH = 6


class _ResizeGrip(QWidget):
    """A thin left-edge handle that drags the panel wider/narrower."""

    def __init__(self, panel):
        super().__init__(panel)
        self._panel = panel
        self.setObjectName("inspectorGrip")
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def mousePressEvent(self, event):
        event.accept()   # claim the press so the moves below are delivered here

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._panel._resize_from_grip(event.globalPos().x())


class InspectorPanel(QFrame):
    """A right-edge overlay hosting one editor form at a time."""

    closed = pyqtSignal()

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.setObjectName("inspectorPanel")
        self._theme = theme
        self._content = None
        self._subject = None
        self._on_commit = None
        self._on_cancel = None
        self._anim = None
        self._width = PANEL_WIDTH

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- header: title + close ✕ ----
        header = QFrame()
        header.setObjectName("inspectorHeader")
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(16, 12, 10, 12)
        self._title = QLabel("")
        self._title.setObjectName("inspectorTitle")
        hrow.addWidget(self._title, 1)
        self._close_btn = QToolButton()
        self._close_btn.setObjectName("inspectorClose")
        self._close_btn.setText("✕")
        self._close_btn.setAutoRaise(True)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("Close (discard changes)")
        self._close_btn.clicked.connect(self._cancel)
        hrow.addWidget(self._close_btn)
        root.addWidget(header)

        # ---- content slot ----
        self._content_host = QWidget()
        self._content_layout = QVBoxLayout(self._content_host)
        # Default padding around an editor body; an editor may override it (e.g.
        # Settings opens flush so its right-edge rail touches the panel edge).
        self._default_content_margins = (16, 14, 16, 14)
        self._content_layout.setContentsMargins(*self._default_content_margins)
        root.addWidget(self._content_host, 1)

        # ---- footer: Cancel | OK ----
        self._footer = QFrame()
        self._footer.setObjectName("inspectorFooter")
        frow = QHBoxLayout(self._footer)
        frow.setContentsMargins(16, 10, 16, 12)
        frow.addStretch(1)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setProperty("variant", "secondary")
        self._cancel_btn.clicked.connect(self._cancel)
        frow.addWidget(self._cancel_btn)
        self._ok_btn = QPushButton("OK")
        self._ok_btn.clicked.connect(self._commit)
        frow.addWidget(self._ok_btn)
        root.addWidget(self._footer)

        # left-edge drag handle to resize the panel width (raised over content)
        self._grip = _ResizeGrip(self)

        self.apply_theme(theme)
        self.hide()

    # ---- opening / closing ---------------------------------------------

    def open_editor(self, title, content, on_commit=None, on_cancel=None,
                    subject=None, commit_label="OK", footer=True, width=None,
                    content_margins=None):
        """Show *content* in the panel, replacing any open editor (committing
        it first).

        *footer* shows/hides the Cancel|OK row (Settings applies live, so it
        opens with the footer hidden — only the ✕ closes it). *width* sets the
        panel's pixel width on open (e.g. a wider Settings panel); when omitted
        the last width is kept. *content_margins* (l, t, r, b) overrides the
        body padding for this editor — e.g. Settings opens flush ``(0,0,0,0)``
        so its right-edge section rail touches the panel edge; the default
        padding is restored on close.
        """
        # implicit-commit the editor that's already open
        self._finish(commit=True)

        self._title.setText(title)
        self._ok_btn.setText(commit_label)
        self._footer.setVisible(footer)
        self._content_layout.setContentsMargins(
            *(content_margins if content_margins is not None
              else self._default_content_margins))
        if width is not None:
            self._width = max(PANEL_MIN_WIDTH, int(width))
        self._content = content
        self._subject = subject
        self._on_commit = on_commit
        self._on_cancel = on_cancel
        self._content_layout.addWidget(content)

        self.show()
        self.raise_()
        self.reposition()
        self._animate_in()

    def close_active(self, commit=True):
        """Close the open editor (used on page switch / dashboard reset)."""
        self._finish(commit=commit)

    def discard_if_subject(self, subject):
        """Drop the panel without running callbacks if it edits *subject*
        (its underlying object is being destroyed)."""
        if self._content is not None and self._subject is subject:
            self._on_commit = None
            self._on_cancel = None
            self._finish(commit=False)

    def _commit(self):
        self._finish(commit=True)

    def _cancel(self):
        self._finish(commit=False)

    def _finish(self, commit):
        if self._content is None:
            return
        cb = self._on_commit if commit else self._on_cancel
        content = self._content
        # clear state first so a re-entrant open_editor() lands cleanly and the
        # callback can't be run twice
        self._content = None
        self._subject = None
        self._on_commit = None
        self._on_cancel = None
        try:
            if callable(cb):
                cb()
        finally:
            self._content_layout.removeWidget(content)
            content.setParent(None)
            content.deleteLater()
            # restore default body padding for the next editor
            self._content_layout.setContentsMargins(
                *self._default_content_margins)
            self.hide()
            self.closed.emit()

    # ---- geometry / animation ------------------------------------------

    def _clamped_width(self):
        p = self.parentWidget()
        if p is None:
            return self._width
        return max(PANEL_MIN_WIDTH, min(self._width, int(p.width() * 0.95)))

    def reposition(self):
        """Pin to the right edge of the parent (over the canvas), full height."""
        p = self.parentWidget()
        if p is None:
            return
        w = self._clamped_width()
        self.setGeometry(QRect(p.width() - w, 0, w, p.height()))
        # keep the resize handle pinned to the panel's left edge, on top
        self._grip.setGeometry(0, 0, GRIP_WIDTH, self.height())
        self._grip.raise_()

    def _resize_from_grip(self, global_x):
        """Drag the left edge: widen as the handle moves left, clamp, re-pin."""
        p = self.parentWidget()
        if p is None:
            return
        local_x = p.mapFromGlobal(QPoint(int(global_x), 0)).x()
        self._width = p.width() - local_x   # clamped in reposition()
        self.reposition()

    def _animate_in(self):
        p = self.parentWidget()
        if p is None:
            return
        w = self._clamped_width()
        end = QPoint(p.width() - w, 0)
        start = QPoint(p.width(), 0)
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(180)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim   # keep a reference so it isn't GC'd

    # ---- theming -------------------------------------------------------

    def apply_theme(self, theme):
        # The inspector is CHROME — it must read identical no matter which
        # dashboard theme/preset is active, so it uses the fixed CHROME palette
        # rather than the (canvas-only) theme colors.
        self._theme = theme
        self.setStyleSheet("""
#inspectorPanel {{ background:{chrome}; border-left:1px solid {border}; }}
#inspectorHeader {{ background:{chrome}; border-bottom:1px solid {border}; }}
#inspectorTitle {{ color:{text}; font-weight:700; }}
#inspectorFooter {{ background:{chrome}; border-top:1px solid {border}; }}
QToolButton#inspectorClose {{
    border:none; background:transparent; border-radius:6px; padding:2px 6px;
    color:{muted}; font-size:15px;
}}
QToolButton#inspectorClose:hover {{ background:{brand_soft}; color:{accent}; }}
#inspectorGrip {{ background:transparent; }}
#inspectorGrip:hover {{ background:{border}; }}
""".format(chrome=CHROME["bg"], border=CHROME["border"], text=CHROME["text"],
           muted=CHROME["muted"], accent=CHROME["accent"],
           brand_soft=CHROME["brand_soft"]))
