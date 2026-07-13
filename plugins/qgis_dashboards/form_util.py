# -*- coding: utf-8 -*-
"""Small layout helpers shared by the inspector-panel editor forms.

The Configure / Tile-appearance / Connections forms are embedded in the
fixed-width :class:`~side_panel.InspectorPanel` (360 px). Left to their
defaults, a ``QFormLayout`` keeps each label and its field on one line, and a
``QComboBox`` sizes itself to its widest entry — layer/field-name pickers, the
whole-system ``QFontComboBox`` list, or a long label such as the map's
"Filter connected tiles to visible extent". The form's minimum width then
exceeds the panel and a *horizontal* scrollbar appears, so dropdowns have to be
scrolled into view before they can be clicked.

These helpers make the forms wrap and shrink to the panel width instead, so
every control stays reachable without sideways scrolling.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QSizePolicy


def compact_form(form):
    """Make a ``QFormLayout`` wrap long rows and let fields fill the width.

    With ``WrapLongRows`` a row whose label + field can't fit side by side
    drops the field onto its own line, so the row's required width is the
    *wider* of the two — never their sum. ``AllNonFixedFieldsGrow`` lets the
    fields expand to the column width rather than dictate it.
    """
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft |
                          Qt.AlignmentFlag.AlignTop)


def no_horizontal_scroll(scroll):
    """Forbid the side scrollbar on a panel scroll area.

    Safe only once the hosted widgets can shrink to the viewport (see
    :func:`compact_form` / :func:`shrink_combo`); otherwise content would clip.
    """
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


def shrink_combo(combo):
    """Let a combo elide its text and grow/shrink with its column.

    A combo box defaults to the width of its widest entry, which for layer and
    field pickers (or the full font list) easily overruns the panel. Sizing it
    to a small minimum-content length with an expanding policy makes it fill the
    available width and elide overlong entries instead of forcing the panel
    wider.
    """
    combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(6)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
