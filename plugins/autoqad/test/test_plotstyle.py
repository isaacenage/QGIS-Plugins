# -*- coding: utf-8 -*-
"""Tests for the plot style table — AutoCAD's CTB as QGIS expressions.

Runs without QGIS. From the plugin directory::

    python test/test_plotstyle.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from style import plotstyle   # noqa: E402


class TestModes(unittest.TestCase):

    def test_known_modes(self):
        self.assertEqual(plotstyle.MODE_KEYS,
                         ("normal", "monochrome", "grayscale"))

    def test_normalise_accepts_case_and_padding(self):
        self.assertEqual(plotstyle.normalise("  MonoChrome "), "monochrome")

    def test_unknown_mode_falls_back_to_normal(self):
        self.assertEqual(plotstyle.normalise("ctb"), "normal")
        self.assertEqual(plotstyle.normalise(None), "normal")
        self.assertEqual(plotstyle.normalise(""), "normal")

    def test_labels_and_descriptions_exist_for_every_mode(self):
        for key in plotstyle.MODE_KEYS:
            self.assertTrue(plotstyle.label_for(key))
            self.assertTrue(plotstyle.describe(key))


class TestColorExpression(unittest.TestCase):
    """The heart of it: white must never survive to the sheet."""

    def test_normal_folds_white_to_black(self):
        expression = plotstyle.color_expression("normal")
        self.assertIn("'#ffffff'", expression)
        self.assertIn("'#000000'", expression)
        self.assertIn("CASE WHEN", expression)

    def test_normal_keeps_the_drawn_colour_otherwise(self):
        expression = plotstyle.color_expression("normal")
        # The ELSE branch hands back the field, so red stays red.
        self.assertIn('coalesce("aq_rgb"', expression)
        self.assertIn("ELSE", expression)

    def test_monochrome_is_a_black_literal(self):
        self.assertEqual(plotstyle.color_expression("monochrome"), "'#000000'")

    def test_monochrome_ignores_the_field(self):
        expression = plotstyle.color_expression("monochrome", field="aq_rgb")
        self.assertNotIn("aq_rgb", expression)

    def test_grayscale_uses_rec601_weights(self):
        expression = plotstyle.color_expression("grayscale")
        self.assertIn("color_rgb(", expression)
        self.assertIn("0.299", expression)
        self.assertIn("0.587", expression)
        self.assertIn("0.114", expression)

    def test_grayscale_folds_white_first(self):
        # Without this a grayscale plot of a CAD drawing is a blank sheet:
        # grey(white) is still white.
        expression = plotstyle.color_expression("grayscale")
        self.assertIn("'#000000'", expression)
        self.assertIn("CASE WHEN", expression)

    def test_custom_field_is_honoured(self):
        expression = plotstyle.color_expression("normal", field="plot_rgb")
        self.assertIn('"plot_rgb"', expression)
        self.assertNotIn('"aq_rgb"', expression)

    def test_field_names_are_quoted_as_identifiers(self):
        expression = plotstyle.color_expression("normal")
        self.assertIn('"aq_rgb"', expression)

    def test_fallback_colour_is_a_string_literal(self):
        expression = plotstyle.color_expression("normal", fallback="#123456")
        self.assertIn("'#123456'", expression)


class TestWidthExpression(unittest.TestCase):

    def test_default_reads_the_resolved_width(self):
        expression = plotstyle.width_expression()
        self.assertIn('coalesce("aq_w"', expression)

    def test_disabled_lineweights_plot_hairline(self):
        expression = plotstyle.width_expression(enabled=False)
        self.assertNotIn("aq_w", expression)
        self.assertAlmostEqual(float(expression), 0.05, places=6)

    def test_disabled_lineweights_respect_the_floor(self):
        expression = plotstyle.width_expression(enabled=False, minimum_mm=0.25)
        self.assertAlmostEqual(float(expression), 0.25, places=6)

    def test_minimum_floors_the_width(self):
        expression = plotstyle.width_expression(minimum_mm=0.13)
        self.assertTrue(expression.startswith("max("))
        self.assertIn("0.13", expression)

    def test_zero_minimum_adds_no_wrapper(self):
        expression = plotstyle.width_expression(minimum_mm=0.0)
        self.assertFalse(expression.startswith("max("))

    def test_negative_minimum_is_clamped_away(self):
        expression = plotstyle.width_expression(minimum_mm=-2.0)
        self.assertFalse(expression.startswith("max("))


class TestPlotStyle(unittest.TestCase):

    def test_defaults(self):
        style = plotstyle.PlotStyle()
        self.assertEqual(style.mode, "normal")
        self.assertTrue(style.lineweights_enabled)
        self.assertEqual(style.minimum_width_mm, 0.0)

    def test_mode_is_normalised_on_construction(self):
        self.assertEqual(plotstyle.PlotStyle("GRAYSCALE").mode, "grayscale")
        self.assertEqual(plotstyle.PlotStyle("nonsense").mode, "normal")

    def test_negative_minimum_is_clamped(self):
        self.assertEqual(plotstyle.PlotStyle(minimum_width_mm=-1.0)
                         .minimum_width_mm, 0.0)

    def test_expressions_match_the_module_functions(self):
        style = plotstyle.PlotStyle("grayscale", minimum_width_mm=0.13)
        self.assertEqual(style.color_expression(),
                         plotstyle.color_expression("grayscale"))
        self.assertEqual(style.width_expression(),
                         plotstyle.width_expression(minimum_mm=0.13))

    def test_replace_returns_a_new_object(self):
        original = plotstyle.PlotStyle("normal")
        changed = original.replace(mode="monochrome")
        self.assertEqual(original.mode, "normal")
        self.assertEqual(changed.mode, "monochrome")
        self.assertIsNot(original, changed)

    def test_round_trips_through_a_dict(self):
        style = plotstyle.PlotStyle("monochrome", False, 0.2)
        self.assertEqual(plotstyle.PlotStyle.from_dict(style.to_dict()), style)

    def test_from_dict_tolerates_junk(self):
        style = plotstyle.PlotStyle.from_dict(None)
        self.assertEqual(style, plotstyle.PlotStyle())

    def test_equality_against_other_types(self):
        self.assertNotEqual(plotstyle.PlotStyle(), "normal")

    def test_from_variables(self):
        class FakeVariables(object):
            _values = {"PLOTSTYLE": "grayscale", "PLOTLW": False,
                       "PLOTLWMIN": 0.13}

            def get(self, name):
                return self._values[name]

        style = plotstyle.PlotStyle.from_variables(FakeVariables())
        self.assertEqual(style.mode, "grayscale")
        self.assertFalse(style.lineweights_enabled)
        self.assertAlmostEqual(style.minimum_width_mm, 0.13)


if __name__ == "__main__":
    unittest.main()
