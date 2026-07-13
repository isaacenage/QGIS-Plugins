# -*- coding: utf-8 -*-
"""Unit tests for the theme transparency + border additions (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_theme_appearance.py

``theme`` (plugin root) imports only ``copy``, so it loads standalone.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from theme import Theme, OVERRIDE_KEYS  # noqa: E402


class TestDefaults(unittest.TestCase):
    def test_new_keys_present_with_defaults(self):
        t = Theme.default()
        self.assertEqual(t.tile_opacity, 100)
        self.assertEqual(t.border_width, 1)

    def test_new_keys_are_overridable(self):
        for key in ("tile_opacity", "border_width", "border"):
            self.assertIn(key, OVERRIDE_KEYS)


class TestAlpha(unittest.TestCase):
    def test_alpha_full(self):
        self.assertEqual(Theme.default().tile_alpha(), 1.0)

    def test_alpha_half(self):
        t = Theme.default().with_values(tile_opacity=50)
        self.assertAlmostEqual(t.tile_alpha(), 0.5)

    def test_alpha_zero(self):
        t = Theme.default().with_values(tile_opacity=0)
        self.assertEqual(t.tile_alpha(), 0.0)

    def test_alpha_clamped(self):
        self.assertEqual(
            Theme.default().with_values(
                tile_opacity=250).tile_alpha(), 1.0)
        self.assertEqual(
            Theme.default().with_values(
                tile_opacity=-
                5).tile_alpha(),
            0.0)


class TestRgba(unittest.TestCase):
    def test_surface_rgba_opaque(self):
        t = Theme.default().with_values(surface_bg="#ffffff", tile_opacity=100)
        self.assertEqual(t.surface_rgba(), "rgba(255, 255, 255, 1.000)")

    def test_surface_rgba_half(self):
        t = Theme.default().with_values(surface_bg="#000000", tile_opacity=50)
        self.assertEqual(t.surface_rgba(), "rgba(0, 0, 0, 0.500)")

    def test_chart_bg_rgba(self):
        t = Theme.default().with_values(chart_bg="#102030", tile_opacity=25)
        self.assertEqual(t.chart_bg_rgba(), "rgba(16, 32, 48, 0.250)")

    def test_short_hex_expands(self):
        t = Theme.default().with_values(surface_bg="#fff", tile_opacity=100)
        self.assertEqual(t.surface_rgba(), "rgba(255, 255, 255, 1.000)")

    def test_bad_hex_falls_back_white(self):
        t = Theme.default().with_values(surface_bg="not-a-color", tile_opacity=100)
        self.assertEqual(t.surface_rgba(), "rgba(255, 255, 255, 1.000)")


class TestMergedOverride(unittest.TestCase):
    def test_override_applies_opacity_and_border(self):
        base = Theme.default()
        merged = base.merged_with({"tile_opacity": 40, "border_width": 3,
                                   "border": "#ff0000"})
        self.assertEqual(merged.tile_opacity, 40)
        self.assertEqual(merged.border_width, 3)
        self.assertEqual(merged.border, "#ff0000")

    def test_zero_opacity_override_not_dropped(self):
        # 0 is a meaningful override (fully transparent), must not be treated
        # empty
        merged = Theme.default().merged_with({"tile_opacity": 0})
        self.assertEqual(merged.tile_opacity, 0)


if __name__ == "__main__":
    unittest.main()
