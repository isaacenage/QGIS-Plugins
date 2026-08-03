# -*- coding: utf-8 -*-
"""Tests for the tool palette's wrapping arithmetic.

The placement maths is extracted from the Qt layout precisely so it can be
checked here — wrapping is easy to get subtly wrong, and the failure modes
(items off-canvas, an infinite loop when the palette is narrower than one
button) are unpleasant to debug through a GUI.

Runs without QGIS or Qt. From the plugin directory::

    python test/test_flow_layout.py
"""

import os
import re
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_flow_positions():
    """Import ``flow_positions`` without dragging in Qt.

    ``flow_layout.py`` imports from ``qgis.PyQt`` at module level, so the pure
    function is extracted and exec'd on its own rather than stubbing the whole
    Qt namespace for one pure routine.
    """
    source = open(os.path.join(_PLUGIN_DIR, "ui", "flow_layout.py"),
                  encoding="utf-8").read()
    match = re.search(r"^def flow_positions\(.*?(?=\n\ndef |\Z)", source,
                      re.S | re.M)
    if match is None:
        raise AssertionError("flow_positions not found in flow_layout.py")
    namespace = {}
    exec(compile(match.group(0), "flow_layout.py", "exec"), namespace)
    return namespace["flow_positions"]


flow_positions = _load_flow_positions()

BUTTON = (34, 34)
SPACING = 4


class TestFlowPositions(unittest.TestCase):

    def place(self, count, width, size=BUTTON):
        """Place *count* buttons into a content band *width* px wide."""
        return flow_positions([size] * count, left=0, top=0,
                              right=width - 1, spacing=SPACING)

    # ---- single row ----

    def test_empty_input(self):
        positions, bottom = flow_positions([], 0, 0, 100, SPACING)
        self.assertEqual(positions, [])
        self.assertEqual(bottom, 0)

    def test_single_item_starts_at_origin(self):
        positions, _bottom = self.place(1, 200)
        self.assertEqual(positions[0], (0, 0))

    def test_items_advance_by_width_plus_spacing(self):
        positions, _bottom = self.place(3, 400)
        self.assertEqual(positions[0], (0, 0))
        self.assertEqual(positions[1], (38, 0))
        self.assertEqual(positions[2], (76, 0))

    def test_single_row_height(self):
        _positions, bottom = self.place(3, 400)
        self.assertEqual(bottom, 34)

    # ---- wrapping ----

    def test_wraps_when_out_of_width(self):
        # 100px band fits two 34px buttons (0-33, 38-71); the third wraps.
        positions, _bottom = self.place(3, 100)
        self.assertEqual(positions[0], (0, 0))
        self.assertEqual(positions[1], (38, 0))
        self.assertEqual(positions[2], (0, 38))

    def test_wrapped_rows_stack_by_height_plus_spacing(self):
        positions, bottom = self.place(5, 100)
        rows = sorted({y for _x, y in positions})
        self.assertEqual(rows, [0, 38, 76])
        self.assertEqual(bottom, 110)

    def test_every_item_stays_within_the_band(self):
        width = 120
        positions, _bottom = self.place(10, width)
        for x, _y in positions:
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x + BUTTON[0], width)

    def test_wider_band_uses_fewer_rows(self):
        narrow = {y for _x, y in self.place(12, 100)[0]}
        wide = {y for _x, y in self.place(12, 400)[0]}
        self.assertGreater(len(narrow), len(wide))

    # ---- the one-column floor ----

    def test_exactly_one_column_when_band_fits_one_button(self):
        positions, _bottom = self.place(4, 34)
        self.assertEqual([x for x, _y in positions], [0, 0, 0, 0])
        self.assertEqual([y for _x, y in positions], [0, 38, 76, 114])

    def test_band_narrower_than_a_button_still_terminates(self):
        # The first-item-never-wraps guard: without it this loops forever.
        positions, bottom = self.place(3, 10)
        self.assertEqual(len(positions), 3)
        self.assertEqual([y for _x, y in positions], [0, 38, 76])
        self.assertEqual(bottom, 110)

    def test_zero_width_band_terminates(self):
        positions, _bottom = self.place(2, 0)
        self.assertEqual(len(positions), 2)

    # ---- mixed sizes (buttons plus separators) ----

    def test_mixed_widths_pack_correctly(self):
        # A 1px separator between two buttons, in a generous band.
        sizes = [(34, 34), (1, 34), (34, 34)]
        positions, bottom = flow_positions(sizes, 0, 0, 399, SPACING)
        self.assertEqual(positions[0], (0, 0))
        self.assertEqual(positions[1], (38, 0))
        self.assertEqual(positions[2], (43, 0))
        self.assertEqual(bottom, 34)

    def test_row_height_follows_the_tallest_item(self):
        sizes = [(34, 34), (34, 50), (34, 34)]
        positions, bottom = flow_positions(sizes, 0, 0, 99, SPACING)
        # First two share row 0; the third wraps below the 50px-tall row.
        self.assertEqual(positions[2], (0, 54))
        self.assertEqual(bottom, 88)

    # ---- offsets ----

    def test_respects_left_and_top_offsets(self):
        positions, bottom = flow_positions(
            [BUTTON] * 2, left=6, top=6, right=105, spacing=SPACING)
        self.assertEqual(positions[0], (6, 6))
        self.assertEqual(positions[1], (44, 6))
        self.assertEqual(bottom, 40)

    def test_wrap_returns_to_the_left_offset(self):
        positions, _bottom = flow_positions(
            [BUTTON] * 3, left=6, top=6, right=79, spacing=SPACING)
        self.assertEqual(positions[2][0], 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
