# coding=utf-8
"""Tests for the HTML export's pure (Qt/QGIS-free) modules.

Mirrors the pivot_engine testing pattern: the serialization, theme-to-CSS, and
HTML-assembly logic is exercised on plain dicts with no QGIS runtime. The
QGIS-touching collectors and the JS runtime are verified manually inside QGIS /
a browser (see the design spec's testing section).
"""

__author__ = 'isaacenagework@gmail.com'
__date__ = '2026-06-16'
__copyright__ = 'Copyright 2026, Isaac Enage'

import json
import unittest

from export.serialize import (
    build_model, build_tile, build_page, clean_config, EXPORT_VERSION,
)


class CleanConfigStyleHoistTest(unittest.TestCase):
    """Relocated per-tile style values surface under the legacy names the
    browser runtime reads, so export keeps working after the appearance split."""

    def test_renamed_keys_hoisted(self):
        cfg = clean_config({"id": "x", "style": {
            "value_px": 48, "rows_shown": 25, "cols_shown": 6,
            "title_font": "Georgia", "text_align": "center"}})
        self.assertEqual(cfg["value_size"], 48)
        self.assertEqual(cfg["max_rows"], 25)
        self.assertEqual(cfg["max_cols"], 6)
        self.assertEqual(cfg["font_family"], "Georgia")
        self.assertEqual(cfg["align"], "center")

    def test_same_name_keys_hoisted(self):
        cfg = clean_config({"style": {"icon_size": 32,
                                      "animation": "fade",
                                      "max_categories": 5,
                                      "logo_slot": "right"}})
        self.assertEqual(cfg["icon_size"], 32)
        self.assertEqual(cfg["animation"], "fade")
        self.assertEqual(cfg["max_categories"], 5)
        self.assertEqual(cfg["logo_slot"], "right")

    def test_heading_reconstructed_from_weight(self):
        cfg = clean_config({"style": {"text_weight": 700}})
        self.assertTrue(cfg["heading"])
        cfg2 = clean_config({"style": {"text_weight": 400}})
        self.assertNotIn("heading", cfg2)

    def test_explicit_top_level_wins(self):
        cfg = clean_config({"max_rows": 99, "style": {"rows_shown": 25}})
        self.assertEqual(cfg["max_rows"], 99)


from export.theme_css import (  # noqa: E402
    theme_to_css_vars, referenced_families, font_face_css,
)
from export.html_builder import build_html, embed_json  # noqa: E402
from export.basemap import xyz_template_to_leaflet, OSM_BASEMAP  # noqa: E402
from export.size_estimate import estimate_layer_bytes  # noqa: E402


class CleanConfigTest(unittest.TestCase):
    def test_drops_id_keeps_rest(self):
        cfg = {
            "id": "abc",
            "title": "Pop",
            "layer_id": "L1",
            "chart_type": "bar"}
        out = clean_config(cfg)
        self.assertNotIn("id", out)
        self.assertEqual(out["title"], "Pop")
        self.assertEqual(out["chart_type"], "bar")

    def test_none_yields_empty(self):
        self.assertEqual(clean_config(None), {})


class BuildTileTest(unittest.TestCase):
    def test_minimal_tile(self):
        tile = {"id": "t1", "type": "chart",
                "grid": {"x": 0, "y": 0, "w": 4, "h": 3},
                "config": {"id": "t1", "category_field": "region"}}
        out = build_tile(tile)
        self.assertEqual(out["id"], "t1")
        self.assertEqual(out["type"], "chart")
        self.assertEqual(out["grid"], {"x": 0, "y": 0, "w": 4, "h": 3})
        self.assertEqual(out["config"], {"category_field": "region"})
        # absent optional keys are omitted entirely
        self.assertNotIn("layer_id", out)
        self.assertNotIn("base_pass", out)

    def test_optional_keys_passthrough(self):
        tile = {"id": "m", "type": "map", "grid": {},
                "map": {"extent": [0, 1, 2, 3]},
                "layer_id": "L1", "base_pass": [0, 2]}
        out = build_tile(tile)
        self.assertEqual(out["map"], {"extent": [0, 1, 2, 3]})
        self.assertEqual(out["layer_id"], "L1")
        self.assertEqual(out["base_pass"], [0, 2])

    def test_none_optional_is_omitted(self):
        tile = {"id": "i", "type": "indicator", "grid": {},
                "indicator_value": None}
        out = build_tile(tile)
        self.assertNotIn("indicator_value", out)

    def test_indicator_icon_uri_passthrough(self):
        tile = {"id": "i", "type": "indicator", "grid": {},
                "icon_uri": "data:image/png;base64,ZZ",
                "config": {"animation": "odometer", "value_size": 48}}
        out = build_tile(tile)
        self.assertEqual(out["icon_uri"], "data:image/png;base64,ZZ")
        self.assertEqual(out["config"]["animation"], "odometer")
        self.assertEqual(out["config"]["value_size"], 48)


class HeaderTileTest(unittest.TestCase):
    def test_header_is_a_normal_tile_with_logo_uri(self):
        # the header is a positioned tile now — no separate docked-banner key
        page = {"id": "p1", "title": "P", "connections": {},
                "tiles": [{"id": "h", "type": "header",
                           "grid": {"x": 0, "y": 0, "w": 1000, "h": 80},
                           "logo_uri": "data:image/png;base64,AA",
                           "config": {"title": "Brand", "logo_slot": "left"}}]}
        out = build_page(page)
        self.assertNotIn("header", out)
        hdr = out["tiles"][0]
        self.assertEqual(hdr["type"], "header")
        self.assertEqual(hdr["logo_uri"], "data:image/png;base64,AA")
        self.assertEqual(hdr["config"]["title"], "Brand")

    def test_no_header_key_on_a_plain_page(self):
        out = build_page({"id": "p1", "title": "P", "connections": {},
                          "tiles": []})
        self.assertNotIn("header", out)


class BuildModelTest(unittest.TestCase):
    def _page(self):
        return {"id": "p1", "title": "Page 1",
                "connections": {"s": ["t"]},
                "tiles": [{"id": "s", "type": "chart", "grid": {},
                           "config": {}}]}

    def test_top_level_shape(self):
        model = build_model(
            (12, 8), {
                "accent": "#123456"}, "p1", [
                self._page()], {
                "L1": {
                    "fields": [], "features": []}})
        self.assertEqual(model["version"], EXPORT_VERSION)
        self.assertEqual(model["grid"], {"cols": 12, "rows": 8})
        self.assertEqual(model["theme"], {"accent": "#123456"})
        self.assertEqual(model["active_page"], "p1")
        self.assertEqual(len(model["pages"]), 1)
        self.assertEqual(model["pages"][0]["connections"], {"s": ["t"]})
        self.assertIn("L1", model["layers"])

    def test_gap_defaults_to_zero(self):
        model = build_model((12, 8), {}, "p1", [self._page()], {})
        self.assertEqual(model["gap"], 0)

    def test_gap_is_carried_through(self):
        model = build_model((12, 8), {}, "p1", [self._page()], {}, gap=16)
        self.assertEqual(model["gap"], 16)

    def test_round_trips_through_json(self):
        model = build_model((10, 6), {}, "p1", [self._page()], {})
        again = json.loads(json.dumps(model))
        self.assertEqual(again["grid"]["cols"], 10)


class ThemeCssTest(unittest.TestCase):
    def test_emits_core_variables(self):
        css = theme_to_css_vars({"accent": "#2b7de9", "surface_bg": "#ffffff"})
        self.assertIn(":root", css)
        self.assertIn("--accent: #2b7de9;", css)
        self.assertIn("--surface-bg: #ffffff;", css)

    def test_derives_accent_hover_darker(self):
        css = theme_to_css_vars({"accent": "#ffffff"})
        # 255 * 0.86 = 219 -> 0xdb
        self.assertIn("--accent-hover: #dbdbdb;", css)

    def test_series_become_indexed_vars(self):
        css = theme_to_css_vars({"series": ["#111111", "#222222"]})
        self.assertIn("--series-0: #111111;", css)
        self.assertIn("--series-1: #222222;", css)

    def test_missing_keys_fall_back(self):
        css = theme_to_css_vars({})
        self.assertIn("--accent: #2b7de9;", css)
        self.assertIn("Inter", css)

    def test_heading_family_defaults_to_body(self):
        css = theme_to_css_vars({"font_family": "Poppins"})
        # No separate heading font -> heading stack collapses to the body
        # stack.
        self.assertIn('--heading-family: "Poppins",', css)

    def test_heading_family_pairing_leads_with_heading(self):
        css = theme_to_css_vars(
            {"font_family": "Open Sans", "heading_font": "Playfair Display"})
        self.assertIn(
            '--heading-family: "Playfair Display", "Open Sans",', css)


class HtmlBuilderTest(unittest.TestCase):
    def test_embed_json_neutralizes_script_close(self):
        embedded = embed_json({"x": "</script><b>hi"})
        self.assertNotIn("</script>", embedded)
        self.assertIn("<\\/script>", embedded)

    def test_build_html_contains_data_css_and_js(self):
        model = build_model((12, 8), {"accent": "#abcdef"}, "p1",
                            [{"id": "p1", "title": "P", "connections": {},
                              "tiles": []}], {})
        html = build_html(model, ":root{--accent:#abcdef;}",
                          "/*css*/", "/*js*/", title="My Dash")
        self.assertIn("<!doctype html>", html)
        self.assertIn('id="dashboard-data"', html)
        self.assertIn("--accent:#abcdef;", html)
        self.assertIn("/*js*/", html)
        self.assertIn("<title>My Dash</title>", html)
        # the embedded JSON is real, parseable JSON
        marker = 'id="dashboard-data">'
        start = html.index(marker) + len(marker)
        end = html.index("</script>", start)
        parsed = json.loads(html[start:end])
        self.assertEqual(parsed["theme"]["accent"], "#abcdef")

    def test_build_html_escapes_title(self):
        model = build_model((1, 1), {}, None, [], {})
        html = build_html(model, "", "", "", title="<evil>")
        self.assertIn("&lt;evil&gt;", html)
        self.assertNotIn("<title><evil>", html)

    def test_build_html_inlines_leaflet_before_runtime(self):
        model = build_model((1, 1), {}, None, [], {})
        html = build_html(model, "", "/*RT_CSS*/", "/*RT_JS*/",
                          leaflet_css="/*LEAFLET_CSS*/",
                          leaflet_js="/*LEAFLET_JS*/", title="D")
        self.assertIn("/*LEAFLET_CSS*/", html)
        self.assertIn("/*LEAFLET_JS*/", html)
        # leaflet CSS before runtime CSS; leaflet JS before runtime JS
        self.assertLess(
            html.index("/*LEAFLET_CSS*/"),
            html.index("/*RT_CSS*/"))
        self.assertLess(html.index("/*LEAFLET_JS*/"), html.index("/*RT_JS*/"))


class XyzTemplateTest(unittest.TestCase):
    def test_osm_style_passthrough(self):
        out = xyz_template_to_leaflet(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertEqual(out["url_template"],
                         "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertFalse(out["tms"])

    def test_url_encoded_tokens_are_decoded(self):
        out = xyz_template_to_leaflet(
            "https://a.tile/%7Bz%7D/%7Bx%7D/%7By%7D.png")
        self.assertEqual(out["url_template"], "https://a.tile/{z}/{x}/{y}.png")

    def test_tms_minus_y_flagged_and_normalized(self):
        out = xyz_template_to_leaflet("https://a.tile/{z}/{x}/{-y}.png")
        self.assertTrue(out["tms"])
        self.assertIn("{y}", out["url_template"])
        self.assertNotIn("{-y}", out["url_template"])

    def test_garbage_returns_none(self):
        self.assertIsNone(xyz_template_to_leaflet("not a url"))
        self.assertIsNone(xyz_template_to_leaflet(""))
        self.assertIsNone(xyz_template_to_leaflet(None))

    def test_osm_fallback_constant_is_valid(self):
        self.assertIn("{z}", OSM_BASEMAP["url_template"])
        self.assertEqual(OSM_BASEMAP["tms"], False)


class MapBlockTest(unittest.TestCase):
    def test_map_block_passthrough(self):
        tile = {"id": "m", "type": "map", "grid": {},
                "map": {"basemap": {"url_template": "u"},
                        "extent": [0, 1, 2, 3], "layer_ids": ["L1"]}}
        out = build_tile(tile)
        self.assertEqual(out["map"]["extent"], [0, 1, 2, 3])
        self.assertEqual(out["map"]["layer_ids"], ["L1"])

    def test_map_image_no_longer_passed_through(self):
        tile = {"id": "m", "type": "map", "grid": {},
                "map_image": "data:image/png;base64,AAAA"}
        out = build_tile(tile)
        self.assertNotIn("map_image", out)

    def test_version_is_two(self):
        self.assertEqual(EXPORT_VERSION, 2)

    def test_layers_geometry_carried_through(self):
        model = build_model((12, 8), {}, "p1",
                            [{"id": "p1", "title": "P", "connections": {},
                              "tiles": []}],
                            {"L1": {"fields": [], "features": [], "geometry": []}})
        self.assertIn("geometry", model["layers"]["L1"])


class SizeEstimateTest(unittest.TestCase):
    def test_geometry_adds_to_estimate(self):
        base = estimate_layer_bytes(100, 5, include_geometry=False)
        with_geom = estimate_layer_bytes(100, 5, include_geometry=True)
        self.assertGreater(with_geom, base)

    def test_zero_features_is_zero(self):
        self.assertEqual(estimate_layer_bytes(0, 5, include_geometry=True), 0)

    def test_field_count_floored_at_one(self):
        # 0 fields must not zero out the attribute estimate
        self.assertGreater(
            estimate_layer_bytes(
                10, 0, include_geometry=False), 0)


class ReferencedFamiliesTest(unittest.TestCase):
    def test_collects_theme_and_tile_fonts(self):
        theme = {"font_family": "Brand Sans", "heading_font": "Brand Serif"}
        styles = [{"font_family": "Tile One"}, {"heading_font": "Tile Two"}]
        self.assertEqual(
            referenced_families(theme, styles),
            {"Brand Sans", "Brand Serif", "Tile One", "Tile Two"})

    def test_drops_empty_and_dedupes(self):
        theme = {"font_family": "Shared", "heading_font": ""}
        styles = [{"font_family": "Shared", "heading_font": None}, {}]
        self.assertEqual(referenced_families(theme, styles), {"Shared"})

    def test_handles_none_inputs(self):
        self.assertEqual(referenced_families(None, None), set())


class FontFaceCssTest(unittest.TestCase):
    def test_empty_is_blank(self):
        self.assertEqual(font_face_css([]), "")
        self.assertEqual(font_face_css(None), "")

    def test_truetype_entry(self):
        css = font_face_css([
            {"family": "Brand Sans", "format": "truetype", "b64": "QUJD"}])
        self.assertIn("font-family:'Brand Sans'", css)
        self.assertIn("data:font/ttf;base64,QUJD", css)
        self.assertIn("format('truetype')", css)

    def test_opentype_mime(self):
        css = font_face_css([
            {"family": "X", "format": "opentype", "b64": "QQ=="}])
        self.assertIn("data:font/otf;base64,QQ==", css)
        self.assertIn("format('opentype')", css)

    def test_skips_incomplete_entries(self):
        css = font_face_css([
            {"family": "", "format": "truetype", "b64": "QQ=="},
            {"family": "Y", "b64": ""}])
        self.assertEqual(css, "")


if __name__ == "__main__":
    unittest.main()
