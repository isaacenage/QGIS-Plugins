# -*- coding: utf-8 -*-
"""Unit tests for the per-element style schema (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_style_schema.py

``style_schema`` imports nothing, so it is loaded standalone from the
``elements`` dir; ``theme`` (plugin root) imports only ``copy``.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "elements"))
sys.path.insert(0, _ROOT)

import style_schema as ss  # noqa: E402
from theme import Theme  # noqa: E402

# every element type the dashboard ships (mirrors elements/__init__.py)
ELEMENT_TYPES = ["indicator", "chart", "list", "pivot", "map",
                 "category_selector", "text", "image", "header"]

# keys a per-role field must never reuse — they belong to Theme.OVERRIDE_KEYS
# and would be misread by Theme.merged_with. The few intentional theme-shaped
# fields are allowed.
_THEME_OVERRIDE = {"surface_bg", "text", "text_muted", "accent", "chart_bg",
                   "series", "font_family", "heading_font", "font_size",
                   "title_size", "value_size"}
_ALLOWED_THEME_KEYS = {"surface_bg", "border", "chart_bg", "series", "text"}


class SchemaIntegrityTest(unittest.TestCase):
    def test_every_type_has_a_schema(self):
        for t in ELEMENT_TYPES:
            self.assertIn(t, ss.STYLE_SCHEMAS, t)
            self.assertTrue(ss.sections_for(t), t)

    def test_every_type_has_a_tile_section_with_size(self):
        for t in ELEMENT_TYPES:
            kinds = [f.kind for f in ss.fields_for(t)]
            self.assertIn(ss.TILE_SIZE, kinds, "%s missing tile size" % t)
            # exactly one geometry field
            self.assertEqual(kinds.count(ss.TILE_SIZE), 1, t)

    def test_no_duplicate_keys_within_a_type(self):
        for t in ELEMENT_TYPES:
            keys = ss.style_keys(t)
            self.assertEqual(len(keys), len(set(keys)),
                             "%s has duplicate style keys" % t)

    def test_role_keys_avoid_theme_override_namespace(self):
        # any field key that collides with a theme override key must be one of
        # the intentional theme-shaped fields (with a matching theme_key).
        for t in ELEMENT_TYPES:
            for f in ss.fields_for(t):
                if f.kind == ss.TILE_SIZE:
                    continue
                if f.key in _THEME_OVERRIDE:
                    self.assertIn(f.key, _ALLOWED_THEME_KEYS,
                                  "%s.%s collides with a theme override key"
                                  % (t, f.key))

    def test_every_field_resolves_a_default(self):
        th = Theme.default()
        for t in ELEMENT_TYPES:
            for f in ss.fields_for(t):
                if f.kind == ss.TILE_SIZE:
                    continue
                val = ss.default_for(f, th)
                self.assertIsNotNone(val, "%s.%s default is None" % (t, f.key))

    def test_choice_fields_have_choices(self):
        for t in ELEMENT_TYPES:
            for f in ss.fields_for(t):
                if f.kind == ss.CHOICE:
                    self.assertTrue(f.opts.get("choices"),
                                    "%s.%s missing choices" % (t, f.key))

    def test_theme_key_defaults_track_theme(self):
        th = Theme.default().with_values(accent="#ff0000")
        # indicator value color tracks the theme accent
        value_color = next(f for f in ss.fields_for("indicator")
                           if f.key == "value_color")
        self.assertEqual(ss.default_for(value_color, th), "#ff0000")

    def test_heading_family_resolves_via_method(self):
        th = Theme.default().with_values(heading_font="Georgia")
        title_font = next(f for f in ss.fields_for("indicator")
                          if f.key == "title_font")
        self.assertEqual(ss.default_for(title_font, th), "Georgia")


if __name__ == "__main__":
    unittest.main()
