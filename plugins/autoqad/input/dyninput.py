# -*- coding: utf-8 -*-
"""Dynamic input — the readout that follows the cursor while you draw.

This is the single biggest contributor to "it feels like AutoCAD". Without it
you are dragging a rubber band and guessing; with it, the geometry you are
about to commit is stated numerically, next to the cursor, updating live.

What shows depends on what the prompt wants, exactly as in AutoCAD:

* **First point** (no anchor yet) — absolute ``X`` and ``Y``.
* **Next point** (an anchor exists) — the **distance** from the anchor and the
  **angle**, which is the polar readout users actually steer by.
* **Distance prompt** — distance alone. **Angle prompt** — angle alone.

Two extra cues, also AutoCAD's:

* the **prompt text** rides just under the cursor, so the current question is
  where the eye already is rather than down in the command line;
* the angle field **highlights** when ortho or polar tracking has locked the
  direction, so a locked angle is visually distinct from a free one.

The boxes are plain ``QLabel`` children of the canvas positioned in screen
coordinates — no layout, no repaint of the map, and they follow the same
once-per-frame update as everything else in the pointer pipeline.
"""

import math

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QLabel

from ..ui import theme
from .coords import from_math_angle

#: Offset from the cursor to the readout block, in pixels.
OFFSET_X = 18
OFFSET_Y = 18
#: Vertical gap between stacked boxes.
GAP = 3


def _box_style(locked=False, muted=False):
    """AutoCAD-ish field styling, in the plugin's palette."""
    if muted:
        background, border, colour = "#f6f8fb", theme.PALETTE["border"], \
            theme.PALETTE["muted"]
    elif locked:
        # A locked direction gets the accent treatment, so ortho/polar is
        # unmistakable at a glance.
        background, border, colour = "#eaf1fa", theme.PALETTE["accent"], \
            theme.PALETTE["accent"]
    else:
        background, border, colour = "#ffffff", theme.PALETTE["border"], \
            theme.PALETTE["text"]

    return (
        "background:{0}; border:1px solid {1}; color:{2};"
        "border-radius:3px; padding:1px 6px;"
        "font-family:{3}; font-size:12px;"
    ).format(background, border, colour, theme.MONO_FONT_STACK)


class DynamicInput(object):
    """The floating distance / angle / coordinate readout."""

    def __init__(self, canvas, variables):
        self.canvas = canvas
        self.variables = variables
        self._visible = False

        self._primary = self._label()
        self._secondary = self._label()
        self._prompt = self._label(muted=True)

    def _label(self, muted=False):
        label = QLabel(self.canvas)
        label.setStyleSheet(_box_style(muted=muted))
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                           True)
        label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        label.hide()
        return label

    # ---- visibility ----

    def set_visible(self, visible):
        self._visible = bool(visible) and bool(self.variables.get("DYNMODE"))
        if not self._visible:
            self.hide()

    def hide(self):
        for label in (self._primary, self._secondary, self._prompt):
            label.hide()

    # ---- update ----

    def update(self, screen_pos, point, base_point=None, locked_angle=None,
               prompt_text="", kind="point"):
        """Redraw the readout. Called once per processed frame.

        *screen_pos* positions the boxes; *point* is the resolved cursor
        position; *base_point* is the command's anchor, whose presence decides
        between the coordinate and the distance/angle readout.
        """
        if not self._visible or point is None or screen_pos is None:
            self.hide()
            return
        if not self.variables.get("DYNMODE"):
            self.hide()
            return

        precision = int(self.variables.get("LUPREC"))
        angle_precision = int(self.variables.get("AUPREC"))

        primary, secondary = self._fields(
            point, base_point, locked_angle, kind, precision, angle_precision)

        self._apply(self._primary, primary, locked=False)
        self._apply(self._secondary, secondary,
                    locked=locked_angle is not None)
        self._apply(self._prompt, self._trim(prompt_text), muted=True)

        self._position(screen_pos)

    def _fields(self, point, base_point, locked_angle, kind, precision,
                angle_precision):
        """Return the two field strings for the current prompt."""
        angle_base = self.variables.get("ANGBASE")
        clockwise = self.variables.clockwise_angles

        if base_point is None or kind == "first":
            return ("X  {0:.{p}f}".format(point[0], p=precision),
                    "Y  {0:.{p}f}".format(point[1], p=precision))

        dx = point[0] - base_point[0]
        dy = point[1] - base_point[1]
        distance = math.hypot(dx, dy)

        if kind == "angle":
            radians = locked_angle if locked_angle is not None \
                else math.atan2(dy, dx)
            return (self._angle_text(radians, angle_base, clockwise,
                                     angle_precision), "")

        distance_text = "{0:.{p}f}".format(distance, p=precision)
        if kind == "distance":
            return (distance_text, "")

        radians = locked_angle if locked_angle is not None \
            else math.atan2(dy, dx)
        return (distance_text,
                self._angle_text(radians, angle_base, clockwise,
                                 angle_precision))

    @staticmethod
    def _angle_text(radians, angle_base, clockwise, precision):
        degrees = from_math_angle(radians, angle_base, clockwise)
        return "{0:.{p}f}°".format(degrees, p=precision)

    @staticmethod
    def _trim(text, limit=48):
        text = (text or "").strip()
        if text.endswith(":"):
            text = text[:-1]
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def _apply(self, label, text, locked=False, muted=False):
        if not text:
            label.hide()
            return
        label.setStyleSheet(_box_style(locked=locked, muted=muted))
        label.setText(text)
        label.adjustSize()
        label.show()
        label.raise_()

    def _position(self, screen_pos):
        """Stack the visible boxes below-right of the cursor, kept on-canvas."""
        try:
            x = int(screen_pos.x()) + OFFSET_X
            y = int(screen_pos.y()) + OFFSET_Y
        except AttributeError:
            x = int(screen_pos[0]) + OFFSET_X
            y = int(screen_pos[1]) + OFFSET_Y

        visible = [lbl for lbl in (self._primary, self._secondary,
                                   self._prompt) if lbl.isVisible()]
        if not visible:
            return

        width = max(lbl.width() for lbl in visible)
        height = sum(lbl.height() for lbl in visible) + GAP * (len(visible) - 1)

        # Flip to the other side of the cursor rather than run off the canvas.
        if x + width > self.canvas.width():
            x = max(0, int(screen_pos.x() if hasattr(screen_pos, "x")
                           else screen_pos[0]) - OFFSET_X - width)
        if y + height > self.canvas.height():
            y = max(0, self.canvas.height() - height)

        top = y
        for label in visible:
            label.move(x, top)
            top += label.height() + GAP

    # ---- teardown ----

    def dispose(self):
        for label in (self._primary, self._secondary, self._prompt):
            try:
                label.hide()
                label.setParent(None)
                label.deleteLater()
            except (RuntimeError, AttributeError):
                pass
