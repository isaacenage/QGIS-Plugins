# coding=utf-8
"""Tests for the pure header-layout helpers (no QGIS runtime needed).

Run directly so the test package ``__init__`` (which imports qgis) is not
loaded::

    cd qgis_dashboards && PYTHONPATH=$(pwd) python test/test_header_layout.py
"""

__author__ = 'isaacenagework@gmail.com'
__date__ = '2026-06-16'
__copyright__ = 'Copyright 2026, Isaac Enage'

import os
import sys
import unittest

# Import the pure helper directly from the ``elements`` dir so the package
# ``__init__`` (which imports qgis) is not loaded.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "elements"))

from header_layout import header_tile_placement, materialize_header_tiles  # noqa: E402


class HeaderTilePlacementTest(unittest.TestCase):
    """Geometry for converting a docked legacy header into a canvas tile."""

    def test_top_places_band_and_shifts_tiles_down(self):
        rect, shift, region = header_tile_placement("top", 80, 1000, 600)
        # full-width band at the top
        self.assertEqual(rect, (0, 0, 1000, 80))
        # existing tiles move down
        self.assertEqual(shift, (0, 80))
        self.assertEqual(region, (1000, 680))         # region grows in height

    def test_bottom_places_band_and_leaves_tiles(self):
        rect, shift, region = header_tile_placement("bottom", 80, 1000, 600)
        # band below the old region
        self.assertEqual(rect, (0, 600, 1000, 80))
        self.assertEqual(shift, (0, 0))               # tiles unchanged
        self.assertEqual(region, (1000, 680))

    def test_left_places_band_and_shifts_tiles_right(self):
        rect, shift, region = header_tile_placement("left", 120, 1000, 600)
        # full-height band at the left
        self.assertEqual(rect, (0, 0, 120, 600))
        self.assertEqual(shift, (120, 0))             # tiles move right
        self.assertEqual(region, (1120, 600))         # region grows in width

    def test_right_places_band_and_leaves_tiles(self):
        rect, shift, region = header_tile_placement("right", 120, 1000, 600)
        # band right of the old region
        self.assertEqual(rect, (1000, 0, 120, 600))
        self.assertEqual(shift, (0, 0))
        self.assertEqual(region, (1120, 600))

    def test_unknown_anchor_falls_back_to_top(self):
        self.assertEqual(header_tile_placement("sideways", 50, 200, 100),
                         header_tile_placement("top", 50, 200, 100))


class MaterializeHeaderTilesTest(unittest.TestCase):
    """Legacy global/per-page headers become header tiles in each page."""

    def _page(self, header=None, elements=None):
        p = {"id": "p1", "title": "Page 1", "connections": {},
             "elements": elements if elements is not None else []}
        if header is not None:
            p["header"] = header
        return p

    def test_global_header_added_to_each_page_as_top_tile(self):
        pages = [self._page(elements=[{"__type__": "indicator", "grid": {
                            "x": 0, "y": 0, "w": 200, "h": 150}}])]
        glob = {"title": "Brand", "anchor": "top", "thickness": 80,
                "font_size": 22, "logo_slot": "left"}
        new_pages, w, h = materialize_header_tiles(pages, glob, 1000, 600)
        els = new_pages[0]["elements"]
        # existing tile shifted down by the band thickness
        self.assertEqual(els[0]["grid"], {"x": 0, "y": 80, "w": 200, "h": 150})
        # header appended as a header tile spanning the band
        hdr = els[1]
        self.assertEqual(hdr["__type__"], "header")
        self.assertEqual(hdr["grid"], {"x": 0, "y": 0, "w": 1000, "h": 80})
        self.assertEqual(hdr["title"], "Brand")
        # dock-only keys are stripped from the tile config
        self.assertNotIn("anchor", hdr)
        self.assertNotIn("thickness", hdr)
        self.assertNotIn("scope_all_pages", hdr)
        # region grew in height; the original 'header' key is gone
        self.assertEqual((w, h), (1000, 680))
        self.assertNotIn("header", new_pages[0])

    def test_per_page_header_overrides_global(self):
        pages = [self._page(header={"title": "Local", "anchor": "top",
                                    "thickness": 50})]
        glob = {"title": "Global", "anchor": "top", "thickness": 80}
        new_pages, w, h = materialize_header_tiles(pages, glob, 1000, 600)
        hdr = new_pages[0]["elements"][-1]
        self.assertEqual(hdr["title"], "Local")
        self.assertEqual(hdr["grid"]["h"], 50)
        self.assertEqual((w, h), (1000, 650))

    def test_no_header_leaves_page_unchanged(self):
        pages = [self._page(elements=[{"__type__": "chart", "grid": {
                            "x": 0, "y": 0, "w": 100, "h": 100}}])]
        new_pages, w, h = materialize_header_tiles(pages, None, 1000, 600)
        self.assertEqual(new_pages[0]["elements"],
                         [{"__type__": "chart",
                           "grid": {"x": 0, "y": 0, "w": 100, "h": 100}}])
        self.assertEqual((w, h), (1000, 600))

    def test_region_is_uniform_max_across_pages(self):
        # page A has a top header (grows height), page B has none
        page_a = {"id": "a", "title": "A", "connections": {}, "elements": [],
                  "header": {"title": "H", "anchor": "top", "thickness": 80}}
        page_b = {"id": "b", "title": "B", "connections": {}, "elements": []}
        new_pages, w, h = materialize_header_tiles(
            [page_a, page_b], None, 1000, 600)
        # both pages share the grown region
        self.assertEqual((w, h), (1000, 680))


if __name__ == "__main__":
    unittest.main()
