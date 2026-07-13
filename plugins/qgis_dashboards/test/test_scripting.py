# -*- coding: utf-8 -*-
"""Unit tests for scripting.spec_to_layout (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_scripting.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripting import (  # noqa: E402
    spec_to_layout, _rect_from_at, DEFAULT_REGION, DEFAULT_GRID,
)


def _fake_layer_resolver(known):
    return lambda ref: known.get(ref)


class TestRectFromAt(unittest.TestCase):
    def test_cells_map_to_region_pixels(self):
        # 12x8 grid over 1200x800 -> 100px cells
        r = _rect_from_at([0, 0, 3, 2], (1200, 800), (12, 8))
        self.assertEqual(r, {"x": 0, "y": 0, "w": 300, "h": 200})

    def test_offset_cell(self):
        r = _rect_from_at([6, 4, 6, 4], (1200, 800), (12, 8))
        self.assertEqual(r, {"x": 600, "y": 400, "w": 600, "h": 400})

    def test_span_floors_at_one(self):
        r = _rect_from_at([0, 0, 0, 0], (1200, 800), (12, 8))
        self.assertEqual(r["w"], 100)
        self.assertEqual(r["h"], 100)


class TestSpecToLayout(unittest.TestCase):
    def test_single_page_shorthand(self):
        layout, warns = spec_to_layout({
            "title": "KPIs",
            "elements": [{"type": "indicator", "title": "Total",
                          "value_expression": "count(1)"}],
        })
        self.assertEqual(layout["version"], 3)
        self.assertEqual(len(layout["pages"]), 1)
        self.assertEqual(layout["pages"][0]["title"], "KPIs")
        self.assertEqual(layout["canvas"], {"w": DEFAULT_REGION[0],
                                            "h": DEFAULT_REGION[1]})
        el = layout["pages"][0]["elements"][0]
        self.assertEqual(el["__type__"], "indicator")
        self.assertEqual(el["value_expression"], "count(1)")
        self.assertIn("id", el)
        self.assertEqual(warns, [])

    def test_layer_resolved_by_name(self):
        resolve = _fake_layer_resolver({"Parcels": "Parcels_xyz"})
        layout, warns = spec_to_layout({
            "elements": [{"type": "chart", "layer": "Parcels",
                          "chart_type": "bar", "category_field": "zone"}],
        }, resolve_layer=resolve)
        el = layout["pages"][0]["elements"][0]
        self.assertEqual(el["layer_id"], "Parcels_xyz")
        self.assertNotIn("layer", el)
        self.assertEqual(warns, [])

    def test_unknown_layer_warns_and_leaves_unbound(self):
        layout, warns = spec_to_layout({
            "elements": [{"type": "list", "layer": "Missing"}],
        }, resolve_layer=_fake_layer_resolver({}))
        el = layout["pages"][0]["elements"][0]
        self.assertNotIn("layer_id", el)
        self.assertEqual(len(warns), 1)
        self.assertIn("Missing", warns[0])

    def test_layerless_type_ignores_layer(self):
        layout, _ = spec_to_layout({
            "elements": [{"type": "text", "layer": "Parcels", "text": "Hi"}],
        }, resolve_layer=_fake_layer_resolver({"Parcels": "p"}))
        el = layout["pages"][0]["elements"][0]
        self.assertNotIn("layer_id", el)
        self.assertEqual(el["text"], "Hi")

    def test_at_becomes_pixel_grid(self):
        layout, _ = spec_to_layout({
            "grid": {"cols": 12, "rows": 8},
            "canvas": {"w": 1200, "h": 800},
            "elements": [{"type": "indicator", "at": [0, 0, 3, 2]}],
        })
        el = layout["pages"][0]["elements"][0]
        self.assertEqual(el["grid"], {"x": 0, "y": 0, "w": 300, "h": 200})

    def test_no_at_means_no_grid_key(self):
        layout, _ = spec_to_layout({
            "elements": [{"type": "indicator"}],
        })
        self.assertNotIn("grid", layout["pages"][0]["elements"][0])

    def test_connections_resolve_refs_to_ids(self):
        layout, warns = spec_to_layout({
            "elements": [
                {"type": "chart", "ref": "src", "chart_type": "bar"},
                {"type": "indicator", "ref": "kpi"},
                {"type": "map", "ref": "m"},
            ],
            "connections": [{"from": "src", "to": ["kpi", "m"]}],
        })
        els = layout["pages"][0]["elements"]
        src_id = els[0]["id"]
        kpi_id = els[1]["id"]
        m_id = els[2]["id"]
        self.assertEqual(layout["pages"][0]["connections"],
                         {src_id: [kpi_id, m_id]})
        self.assertEqual(warns, [])

    def test_connection_dangling_ref_warns(self):
        layout, warns = spec_to_layout({
            "elements": [{"type": "chart", "ref": "src"}],
            "connections": [{"from": "src", "to": ["nope"]}],
        })
        self.assertEqual(layout["pages"][0]["connections"], {})
        self.assertTrue(any("nope" in w for w in warns))

    def test_self_connection_dropped(self):
        layout, _ = spec_to_layout({
            "elements": [{"type": "chart", "ref": "src"}],
            "connections": [{"from": "src", "to": ["src"]}],
        })
        self.assertEqual(layout["pages"][0]["connections"], {})

    def test_explicit_id_is_kept_and_wirable(self):
        layout, _ = spec_to_layout({
            "elements": [
                {"type": "chart", "id": "fixed1", "ref": "src"},
                {"type": "indicator", "id": "fixed2"},
            ],
            "connections": [{"from": "src", "to": ["fixed2"]}],
        })
        self.assertEqual(layout["pages"][0]["elements"][0]["id"], "fixed1")
        self.assertEqual(
            layout["pages"][0]["connections"], {
                "fixed1": ["fixed2"]})

    def test_theme_dict_passthrough(self):
        layout, _ = spec_to_layout({
            "theme": {"accent": "#ff0000"},
            "elements": [{"type": "text", "text": "x"}],
        })
        self.assertEqual(layout["theme"], {"accent": "#ff0000"})

    def test_theme_preset_name_resolved(self):
        def resolve(name):
            return {"accent": "#38bdf8"} if name == "Midnight Slate" else {}
        layout, _ = spec_to_layout({
            "theme": "Midnight Slate",
            "elements": [{"type": "text", "text": "x"}],
        }, resolve_theme=resolve)
        self.assertEqual(layout["theme"], {"accent": "#38bdf8"})

    def test_theme_preset_with_overrides(self):
        def resolve(name):
            return {"accent": "#000000", "window_bg": "#111111"}
        layout, _ = spec_to_layout({
            "theme": {"preset": "X", "accent": "#ffffff"},
            "elements": [{"type": "text", "text": "x"}],
        }, resolve_theme=resolve)
        self.assertEqual(
            layout["theme"]["accent"],
            "#ffffff")     # override wins
        self.assertEqual(
            layout["theme"]["window_bg"],
            "#111111")  # preset kept

    def test_locked_only_when_specified(self):
        a, _ = spec_to_layout({"elements": [{"type": "text", "text": "x"}]})
        self.assertNotIn("locked", a)
        b, _ = spec_to_layout({"locked": True,
                               "elements": [{"type": "text", "text": "x"}]})
        self.assertTrue(b["locked"])

    def test_multi_page(self):
        layout, _ = spec_to_layout({
            "pages": [
                {"title": "One", "elements": [{"type": "text", "text": "a"}]},
                {"title": "Two", "elements": [{"type": "text", "text": "b"}]},
            ],
        })
        self.assertEqual([p["title"] for p in layout["pages"]], ["One", "Two"])
        self.assertEqual(layout["active_page"], layout["pages"][0]["id"])

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            spec_to_layout({"elements": [{"type": "bogus"}]})

    def test_missing_type_raises(self):
        with self.assertRaises(ValueError):
            spec_to_layout({"elements": [{"title": "no type"}]})

    def test_defaults_grid_and_region(self):
        layout, _ = spec_to_layout({"elements": []})
        self.assertEqual(layout["grid"],
                         {"cols": DEFAULT_GRID[0], "rows": DEFAULT_GRID[1]})


if __name__ == "__main__":
    unittest.main()
