# -*- coding: utf-8 -*-
"""Tests for system variables and the dark-background rule.

CAD mode paints model space black, which changes what ACI 7 means: it is the
one index whose appearance is defined *relative to the background*, and it is
the default colour of layer "0" and therefore of most entities in a drawing.
Get this wrong and the whole drawing renders in the one colour that is
invisible against the canvas.

Runs without QGIS. From the plugin directory::

    python test/test_variables.py
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock


class _FakeModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = MagicMock(name=name)
        setattr(self, name, value)
        return value


for _name in ("qgis", "qgis.core", "qgis.gui", "qgis.PyQt",
              "qgis.PyQt.QtCore", "qgis.PyQt.QtGui", "qgis.PyQt.QtWidgets"):
    sys.modules.setdefault(_name, _FakeModule(_name))

sys.modules["qgis.PyQt.QtCore"].pyqtSignal = lambda *a, **k: MagicMock()
sys.modules["qgis.PyQt.QtCore"].QObject = type(
    "QObject", (), {"__init__": lambda self, *a, **k: None})

# symbology.py uses package-relative imports (``from ..core.compat import``),
# so everything here is reached through the ``autoqad`` package rather than by
# bare module name.
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))

from autoqad.core.variables import (                          # noqa: E402
    DEFINITIONS, is_dark_colour,
)
from autoqad.style import (                                   # noqa: E402
    aci, cad_layer, lineweights, symbology,
)


class TestIsDarkColour(unittest.TestCase):

    def test_black_is_dark(self):
        self.assertTrue(is_dark_colour("#000000"))

    def test_white_is_light(self):
        self.assertFalse(is_dark_colour("#ffffff"))

    def test_autocad_model_space_grey_is_dark(self):
        # AutoCAD's classic near-black model space.
        self.assertTrue(is_dark_colour("#33393f"))

    def test_shorthand_hex(self):
        self.assertTrue(is_dark_colour("#000"))
        self.assertFalse(is_dark_colour("#fff"))

    def test_leading_hash_optional(self):
        self.assertTrue(is_dark_colour("000000"))

    def test_uses_perceptual_luminance_not_average(self):
        # Pure blue averages to 85 (looks "mid") but is perceptually dark;
        # pure yellow averages to 170 and is perceptually light. A plain mean
        # would get blue right by luck and yellow wrong.
        self.assertTrue(is_dark_colour("#0000ff"))
        self.assertFalse(is_dark_colour("#ffff00"))
        self.assertFalse(is_dark_colour("#00ff00"))

    def test_garbage_defaults_to_dark(self):
        # CAD mode's default is black, so dark is the safer guess.
        for value in ("", None, "not-a-colour", "#12"):
            self.assertTrue(is_dark_colour(value))


class TestCadModeDefaults(unittest.TestCase):

    def test_canvas_defaults_to_black(self):
        self.assertEqual(DEFINITIONS["CANVASCOLOR"].default, "#000000")

    def test_crosshair_and_pickbox_are_white(self):
        self.assertEqual(DEFINITIONS["CURSORCOLOR"].default, "#ffffff")
        self.assertEqual(DEFINITIONS["PICKBOXCOLOR"].default, "#ffffff")

    def test_every_colour_default_is_visible_on_black(self):
        # Any colour drawn over model space must not itself be black.
        for name in ("CURSORCOLOR", "PICKBOXCOLOR", "AUTOSNAPCOLOR",
                     "TRACKCOLOR", "RUBBERCOLOR", "HIGHLIGHTCOLOR",
                     "GRIPCOLOR", "GRIPHOT"):
            self.assertFalse(
                is_dark_colour(DEFINITIONS[name].default),
                "{0} default is too dark to see on a black canvas".format(name))


class TestByLayerResolvesAgainstBackground(unittest.TestCase):
    """The chain that decides whether a drawing is visible at all."""

    def setUp(self):
        # Layer "0" as a fresh drawing has it: ACI 7.
        self.layer = cad_layer.CadLayer("0", color=7)

    def test_layer_zero_is_aci_seven(self):
        self.assertEqual(self.layer.color, 7)

    def test_bylayer_entity_is_white_on_a_dark_canvas(self):
        self.assertEqual(
            self.layer.resolve_color(aci.BYLAYER, background_is_dark=True),
            (255, 255, 255))

    def test_bylayer_entity_is_black_on_a_light_canvas(self):
        self.assertEqual(
            self.layer.resolve_color(aci.BYLAYER, background_is_dark=False),
            (0, 0, 0))

    def test_resolved_style_emits_white_on_dark(self):
        style = symbology.resolve_entity_style(
            self.layer, background_is_dark=True)
        self.assertEqual(style[symbology.FIELD_RGB], "#ffffff")

    def test_resolved_style_emits_black_on_light(self):
        style = symbology.resolve_entity_style(
            self.layer, background_is_dark=False)
        self.assertEqual(style[symbology.FIELD_RGB], "#000000")

    def test_explicit_colours_ignore_the_background(self):
        # Only ACI 7 is background-relative; red is red either way.
        for dark in (True, False):
            self.assertEqual(
                self.layer.resolve_color(1, background_is_dark=dark),
                (255, 0, 0))

    def test_a_layer_coloured_seven_also_follows_the_background(self):
        style = symbology.resolve_entity_style(
            cad_layer.CadLayer("A-WALL", color=7), background_is_dark=True)
        self.assertEqual(style[symbology.FIELD_RGB], "#ffffff")

    def test_resolved_style_carries_width_and_dash(self):
        layer = cad_layer.CadLayer("A-WALL", color=7, linetype="HIDDEN",
                                   lineweight=35)
        style = symbology.resolve_entity_style(layer, background_is_dark=True)
        self.assertEqual(style[symbology.FIELD_RGB], "#ffffff")
        self.assertAlmostEqual(style[symbology.FIELD_WIDTH], 0.35)
        self.assertTrue(style[symbology.FIELD_DASH])

    def test_lineweight_display_off_forces_hairline(self):
        layer = cad_layer.CadLayer("A-WALL", color=7, lineweight=200)
        style = symbology.resolve_entity_style(
            layer, background_is_dark=True, lineweight_display=False)
        self.assertAlmostEqual(style[symbology.FIELD_WIDTH],
                               lineweights.HAIRLINE_MM)


if __name__ == "__main__":
    unittest.main(verbosity=2)
