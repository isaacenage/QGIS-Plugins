# -*- coding: utf-8 -*-
"""A wrapping (flow) layout.

Qt ships no flow layout, so the tool palette needs one: items are placed left
to right and wrap to a new row when they run out of width, the way a real
toolbar or a tool palette behaves.

Two properties matter for the palette:

* :meth:`heightForWidth` — the layout's height depends on how wide it is
  allowed to be, which is what lets the dock grow taller as the user narrows
  it instead of clipping.
* :meth:`minimumSize` — reports the widest single item plus margins, so the
  narrowest the palette can ever be squeezed is exactly **one column** of
  tools. Below that Qt simply refuses to shrink it further.

Qt-only; no QGIS dependency.
"""

from qgis.PyQt.QtCore import QPoint, QRect, QSize, Qt
from qgis.PyQt.QtWidgets import QLayout


class FlowLayout(QLayout):
    """Lays out items left-to-right, wrapping to new rows as width allows."""

    def __init__(self, parent=None, margin=0, spacing=4):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    # ---- QLayout plumbing ----

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        # Neither direction expands: the palette hugs its content and wraps.
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._layout(QRect(0, 0, width, 0), apply_geometry=False)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect, apply_geometry=True)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        """The widest single item plus margins — i.e. one column of tools.

        This is what enforces the floor on how narrow the palette can be
        dragged: Qt will not shrink a dock below its widget's minimum.
        """
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())

        margins = self.contentsMargins()
        return QSize(size.width() + margins.left() + margins.right(),
                     size.height() + margins.top() + margins.bottom())

    # ---- the layout pass ----

    def _layout(self, rect, apply_geometry):
        """Place every item; return the total height used.

        Runs twice per resize — once from ``heightForWidth`` to measure, once
        from ``setGeometry`` to place — so it must not mutate anything except
        item geometry, and only when *apply_geometry* is set. The placement
        arithmetic lives in :func:`flow_positions` so it can be tested
        without Qt.
        """
        margins = self.contentsMargins()
        sizes = [(item.sizeHint().width(), item.sizeHint().height())
                 for item in self._items]

        positions, height = flow_positions(
            sizes,
            left=rect.x() + margins.left(),
            top=rect.y() + margins.top(),
            right=rect.right() - margins.right(),
            spacing=self._spacing)

        if apply_geometry:
            for item, (x, y), (width, item_height) in zip(
                    self._items, positions, sizes):
                item.setGeometry(QRect(QPoint(x, y), QSize(width,
                                                           item_height)))

        return height - rect.y() + margins.bottom()


def flow_positions(sizes, left, top, right, spacing):
    """Place ``(width, height)`` *sizes* in a wrapping row layout.

    Pure arithmetic: no Qt. Returns ``(positions, bottom)`` where *positions*
    is one ``(x, y)`` per size and *bottom* is the y coordinate just past the
    last row.

    The one rule that matters for correctness: **the first item of a row never
    wraps.** Without that guard, a palette narrower than a single button would
    wrap forever and place nothing.
    """
    positions = []
    x, y = left, top
    row_height = 0

    for width, height in sizes:
        if row_height > 0 and x + width - 1 > right:
            x = left
            y += row_height + spacing
            row_height = 0

        positions.append((x, y))
        x += width + spacing
        row_height = max(row_height, height)

    return positions, y + row_height


def make_separator(parent, height, colour, width=1):
    """Return a thin vertical divider that flows inline with the tools.

    A horizontal rule cannot work in a wrapping layout — it would consume a
    whole row. A vertical hairline flows alongside the buttons the way a
    toolbar separator does, and simply lands at the start of a row when the
    palette wraps there.
    """
    from qgis.PyQt.QtWidgets import QFrame

    line = QFrame(parent)
    line.setObjectName("aqPaletteSep")
    line.setFixedSize(width, height)
    line.setStyleSheet("background:{0}; border:none;".format(colour))
    return line
