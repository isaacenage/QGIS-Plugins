# -*- coding: utf-8 -*-
"""Unit tests for legacy-config → style migration (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_style_migrate.py
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "elements"))

from style_migrate import migrate_element_style  # noqa: E402


class _Theme(object):
    title_size = 13


class MigrateTest(unittest.TestCase):
    def test_text_align_and_heading(self):
        cfg = {"text": "Hi", "align": "center", "heading": True}
        migrate_element_style(cfg, "text", _Theme())
        self.assertNotIn("align", cfg)
        self.assertNotIn("heading", cfg)
        self.assertEqual(cfg["style"]["text_align"], "center")
        self.assertEqual(cfg["style"]["text_weight"], 700)
        self.assertEqual(cfg["style"]["text_px"], round(13 * 1.7))
        self.assertEqual(cfg["text"], "Hi")   # content untouched

    def test_text_non_heading_drops_flag_without_size(self):
        cfg = {"heading": False}
        migrate_element_style(cfg, "text", _Theme())
        self.assertNotIn("heading", cfg)
        self.assertNotIn("style", cfg)        # nothing to migrate

    def test_header_fonts_renamed(self):
        cfg = {"title": "Brand", "font_family": "Georgia", "font_size": 40,
               "align": "right", "logo_size": 60, "logo_slot": "right"}
        migrate_element_style(cfg, "header")
        self.assertEqual(cfg["title"], "Brand")
        self.assertEqual(cfg["style"]["title_font"], "Georgia")
        self.assertEqual(cfg["style"]["title_px"], 40)
        self.assertEqual(cfg["style"]["title_align"], "right")
        self.assertEqual(cfg["style"]["logo_size"], 60)
        self.assertEqual(cfg["style"]["logo_slot"], "right")
        for legacy in ("font_family", "font_size", "align"):
            self.assertNotIn(legacy, cfg)

    def test_indicator_value_size_renamed(self):
        cfg = {"value_expression": "count(1)", "value_size": 48,
               "icon_size": 32, "animation": "fade"}
        migrate_element_style(cfg, "indicator")
        self.assertEqual(cfg["style"]["value_px"], 48)
        self.assertEqual(cfg["style"]["icon_size"], 32)
        self.assertEqual(cfg["style"]["animation"], "fade")
        self.assertNotIn("value_size", cfg)
        self.assertEqual(cfg["value_expression"], "count(1)")

    def test_pivot_caps(self):
        cfg = {"max_rows": 100, "max_cols": 8}
        migrate_element_style(cfg, "pivot")
        self.assertEqual(cfg["style"]["rows_shown"], 100)
        self.assertEqual(cfg["style"]["cols_shown"], 8)

    def test_does_not_clobber_existing_style(self):
        cfg = {"value_size": 48, "style": {"value_px": 99}}
        migrate_element_style(cfg, "indicator")
        self.assertEqual(cfg["style"]["value_px"], 99)   # kept

    def test_idempotent(self):
        cfg = {"align": "center"}
        migrate_element_style(cfg, "text")
        snapshot = {k: dict(v) if isinstance(v, dict) else v
                    for k, v in cfg.items()}
        migrate_element_style(cfg, "text")   # second pass
        self.assertEqual(cfg, snapshot)

    def test_unknown_type_noop(self):
        cfg = {"foo": "bar"}
        migrate_element_style(cfg, "nope")
        self.assertEqual(cfg, {"foo": "bar"})


if __name__ == "__main__":
    unittest.main()
