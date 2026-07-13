# coding=utf-8
"""Tests for multi-page, zoom/pan, and resize-handle features."""

__author__ = 'isaacenagework@gmail.com'
__date__ = '2026-06-15'
__copyright__ = 'Copyright 2026, Isaac Enage'

import os
import tempfile
import unittest

from utilities import get_qgis_app

from qgis.core import QgsProject

from dashboard_canvas import _proposed_resize, DashboardCanvas
from bus import DashboardBus
from elements.base import DashboardElement
from page_view import clamp_zoom, PageView
from window import (
    migrate_layout, DashboardWindow, DEFAULT_COLS, DEFAULT_ROWS,
    PROJECT_SCOPE, PROJECT_KEY,
)
import project_io
from theme import Theme

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


class ResizeMathTest(unittest.TestCase):
    START = (100, 100, 200, 150)   # x, y, w, h

    def test_south_east_grows_size_only(self):
        self.assertEqual(_proposed_resize("se", self.START, 30, 40),
                         (100, 100, 230, 190))

    def test_east_changes_width_only(self):
        self.assertEqual(_proposed_resize("e", self.START, 30, 999),
                         (100, 100, 230, 150))

    def test_north_moves_top_and_changes_height(self):
        self.assertEqual(_proposed_resize("n", self.START, 0, -40),
                         (100, 60, 200, 190))

    def test_west_moves_left_and_changes_width(self):
        self.assertEqual(_proposed_resize("w", self.START, -30, 0),
                         (70, 100, 230, 150))

    def test_north_west_moves_both_origins(self):
        self.assertEqual(_proposed_resize("nw", self.START, -30, -40),
                         (70, 60, 230, 190))

    def test_min_size_clamps_and_pins_origin(self):
        x, y, w, h = _proposed_resize("w", self.START, 500, 0, min_px=40)
        self.assertEqual(w, 40)
        self.assertEqual(x, 260)   # original right edge (100+200) - 40


class BusPageLocalTest(unittest.TestCase):
    def test_filter_is_isolated_per_page(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_targets("src", ["tgt"])
        bus.set_filter("src", '"a" = 1')
        self.assertEqual(bus.combined_filter_for("tgt"), '("a" = 1)')

        bus.set_active_page("B")
        self.assertIsNone(bus.combined_filter_for("tgt"))

        bus.set_active_page("A")
        self.assertEqual(bus.combined_filter_for("tgt"), '("a" = 1)')

    def test_connections_round_trip_per_page(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_targets("s1", ["t1", "t2"])
        data = bus.connections_to_dict("A")

        other = DashboardBus()
        other.set_active_page("A")
        other.load_connections(data, "A")
        self.assertEqual(other.targets_of("s1"), {"t1", "t2"})

    def test_forget_page_drops_state(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_targets("src", ["tgt"])
        bus.set_filter("src", '"a" = 1')
        bus.forget_page("A")
        bus.set_active_page("A")   # recreated empty
        self.assertIsNone(bus.combined_filter_for("tgt"))

    def test_clear_all_filters_uses_in_place_clear(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_targets("src", ["tgt"])
        bus.set_filter("src", '"a" = 1')
        bus.clear_all_filters()
        self.assertIsNone(bus.combined_filter_for("tgt"))
        self.assertEqual(bus.active_filter_count(), 0)

    def test_sources_of_is_reverse_lookup(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_targets("s1", ["t", "x"])
        bus.set_targets("s2", ["t"])
        self.assertEqual(bus.sources_of("t"), {"s1", "s2"})
        self.assertEqual(bus.sources_of("x"), {"s1"})
        self.assertEqual(bus.sources_of("none"), set())

    def test_set_connected_toggles_single_edge(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_targets("s", ["a", "b"])
        bus.set_connected("s", "c", True)
        self.assertEqual(bus.targets_of("s"), {"a", "b", "c"})
        bus.set_connected("s", "a", False)
        self.assertEqual(bus.targets_of("s"), {"b", "c"})
        bus.set_connected("s", "s", True)        # self-edge is ignored
        self.assertNotIn("s", bus.targets_of("s"))

    def test_rewiring_filterless_source_skips_filter_fanout(self):
        # Toggling a connection for a source with no active filter cannot change
        # any target's combined filter, so it must NOT emit filtersChanged (which
        # would re-query every accepting tile). It must still emit
        # connectionsChanged (the graph changed). This is the perf fix for the
        # "ticking Connections checkboxes is heavy with many tiles" report.
        bus = DashboardBus()
        bus.set_active_page("A")
        fc = []
        cc = []
        bus.filtersChanged.connect(lambda: fc.append(1))
        bus.connectionsChanged.connect(lambda: cc.append(1))

        bus.set_connected("src", "tgt", True)       # src has no active filter
        self.assertEqual(fc, [])                    # no expensive fan-out
        self.assertEqual(len(cc), 1)                # graph still changed

    def test_rewiring_active_source_emits_filter_fanout(self):
        # A source that DOES contribute a filter changes its targets' combined
        # filter when rewired, so filtersChanged must fire.
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_filter("src", '"a" = 1')
        fc = []
        bus.filtersChanged.connect(lambda: fc.append(1))

        bus.set_connected("src", "tgt", True)
        self.assertEqual(len(fc), 1)


class _CountingElement(DashboardElement):
    """A real element whose refresh() just counts calls (no layer needed)."""

    type_name = "counter"
    accepts_filter = True

    def __init__(self, bus, config=None):
        self.refreshes = 0
        super().__init__(bus, config)

    def refresh(self):
        self.refreshes += 1


class FilterChangeDetectionTest(unittest.TestCase):
    """An accepting tile re-queries only when its OWN combined filter changes."""

    def _element(self, bus, eid):
        return _CountingElement(bus, {"id": eid})

    def test_unchanged_combined_filter_skips_refresh(self):
        bus = DashboardBus()
        el = self._element(bus, "tgt")
        bus.set_targets("src", ["tgt"])
        self.assertEqual(el.refreshes, 0)            # filterless source: no-op

        bus.set_filter("src", '"a" = 1')             # now it actually changes
        self.assertEqual(el.refreshes, 1)

        bus.filtersChanged.emit()                    # spurious broadcast
        # combined unchanged → skip
        self.assertEqual(el.refreshes, 1)

        bus.set_filter("src", None)                  # cleared → changes again
        self.assertEqual(el.refreshes, 2)

    def test_unconnected_source_does_not_refresh_tile(self):
        bus = DashboardBus()
        el = self._element(bus, "tgt")               # not wired to "src"
        bus.filtersChanged.emit()                    # settle the change-detector
        base = el.refreshes
        # an unrelated source filters
        bus.set_filter("src", '"a" = 1')
        # combined still None → skip
        self.assertEqual(el.refreshes, base)


class _FakeElement(object):
    """Minimal stand-in for a DashboardElement (the dialog only reads these)."""

    def __init__(self, eid, is_source, accepts):
        self.id = eid
        self.is_filter_source = is_source
        self.accepts_filter = accepts

    def display_name(self):
        return self.id


class ElementConnectionsDialogTest(unittest.TestCase):
    """The per-element connections dialog edits both directions in place."""

    def _setup(self, focus):
        from connections_dialog import ElementConnectionsDialog
        bus = DashboardBus()
        bus.set_active_page("A")
        # chart: both roles; selector: source only; indicator: target only
        chart = _FakeElement("chart", True, True)
        selector = _FakeElement("sel", True, False)
        indicator = _FakeElement("ind", False, True)
        elements = [chart, selector, indicator]
        focus_el = {"chart": chart, "sel": selector, "ind": indicator}[focus]
        dlg = ElementConnectionsDialog(bus, focus_el, elements)
        return bus, dlg

    def test_both_sections_present_for_dual_role_tile(self):
        bus, dlg = self._setup("chart")
        # outgoing target candidate: indicator; incoming source candidate: sel
        self.assertIn(("ind", "out"), dlg._checks)
        self.assertIn(("sel", "in"), dlg._checks)
        # chart never wires to itself
        self.assertNotIn(("chart", "out"), dlg._checks)

    def test_apply_writes_outgoing_and_incoming_edges(self):
        bus, dlg = self._setup("chart")
        dlg._checks[("ind", "out")].setChecked(
            True)   # chart filters indicator
        dlg._checks[("sel", "in")].setChecked(True)    # selector filters chart
        dlg.apply()
        self.assertTrue(bus.is_connected("chart", "ind"))
        self.assertTrue(bus.is_connected("sel", "chart"))

    def test_source_only_tile_shows_no_incoming_section(self):
        bus, dlg = self._setup("sel")
        self.assertTrue(any(d == "out" for _, d in dlg._checks))
        self.assertFalse(any(d == "in" for _, d in dlg._checks))

    def test_apply_can_clear_an_existing_edge(self):
        bus, dlg = self._setup("ind")
        bus.set_targets("sel", ["ind"])               # pre-existing sel → ind
        # rebuild so the checkbox reflects the existing edge
        from connections_dialog import ElementConnectionsDialog
        dlg = ElementConnectionsDialog(
            bus, _FakeElement(
                "ind", False, True), [
                _FakeElement(
                    "sel", True, False), _FakeElement(
                    "ind", False, True)])
        self.assertTrue(dlg._checks[("sel", "in")].isChecked())
        dlg._checks[("sel", "in")].setChecked(False)
        dlg.apply()
        self.assertFalse(bus.is_connected("sel", "ind"))


class TextElementTest(unittest.TestCase):
    """The presentational text/heading container."""

    def _bus(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        return bus

    def test_factory_creates_text_element(self):
        from elements import create_element
        from elements.text_element import TextElement
        el = create_element("text", self._bus(), {"text": "Hi"})
        self.assertIsInstance(el, TextElement)

    def test_takes_no_part_in_cross_filtering(self):
        from elements import create_element
        el = create_element("text", self._bus(), {})
        self.assertFalse(el.is_filter_source)
        self.assertFalse(el.accepts_filter)

    def test_renders_text_and_alignment(self):
        from elements import create_element
        from qgis.PyQt.QtCore import Qt
        el = create_element("text", self._bus(),
                            {"text": "Heading", "align": "center"})
        self.assertEqual(el._label.text(), "Heading")
        self.assertTrue(el._label.alignment() & Qt.AlignmentFlag.AlignHCenter)

    def test_empty_text_shows_placeholder(self):
        from elements import create_element
        from elements.text_element import _PLACEHOLDER
        el = create_element("text", self._bus(), {"text": ""})
        self.assertEqual(el._label.text(), _PLACEHOLDER)


class ImageElementTest(unittest.TestCase):
    def _bus(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        return bus

    def test_is_full_bleed_presentational(self):
        from elements import create_element
        from elements.image_element import ImageElement
        el = create_element("image", self._bus(), {})
        self.assertIsInstance(el, ImageElement)
        self.assertTrue(el.full_bleed)
        self.assertFalse(el.is_filter_source)
        self.assertFalse(el.accepts_filter)

    def test_no_path_shows_placeholder(self):
        from elements import create_element
        el = create_element("image", self._bus(), {})
        self.assertIn("No image", el._label.text())

    def test_missing_file_is_reported(self):
        from elements import create_element
        el = create_element("image", self._bus(),
                            {"path": "/no/such/file.png"})
        self.assertIn("not found", el._label.text())


class AddElementDialogTest(unittest.TestCase):
    """Dynamic config rows for the new layerless tiles."""

    def _select(self, dlg, type_name):
        i = dlg.type_combo.findData(type_name)
        dlg.type_combo.setCurrentIndex(i)

    def test_text_hides_layer_row_and_returns_config(self):
        from add_element_dialog import AddElementDialog
        dlg = AddElementDialog()
        self._select(dlg, "indicator")
        self.assertFalse(dlg.layer_combo.isHidden())   # data tile shows layer
        self._select(dlg, "text")
        # layerless tile hides it
        self.assertTrue(dlg.layer_combo.isHidden())
        dlg._dyn["text"].setPlainText("Title here")
        t, cfg = dlg.result_config()
        self.assertEqual(t, "text")
        self.assertEqual(cfg["text"], "Title here")
        self.assertIn("align", cfg)
        self.assertNotIn("layer_id", cfg)

    def test_image_returns_path_and_fit(self):
        from add_element_dialog import AddElementDialog
        dlg = AddElementDialog()
        self._select(dlg, "image")
        dlg._dyn["path"]._edit.setText("C:/pics/logo.svg")
        t, cfg = dlg.result_config()
        self.assertEqual(t, "image")
        self.assertEqual(cfg["path"], "C:/pics/logo.svg")
        self.assertEqual(cfg["fit"], "contain")


class ZoomTest(unittest.TestCase):
    def test_clamp_zoom_bounds(self):
        # the range widened (0.1–4.0) so Reset Zoom can fit any page size
        self.assertEqual(clamp_zoom(0.01), 0.1)
        self.assertEqual(clamp_zoom(9.0), 4.0)
        self.assertAlmostEqual(clamp_zoom(1.25), 1.25)

    def test_pageview_default_zoom_is_one(self):
        view = PageView(DashboardCanvas(None, 12, 8))
        self.assertAlmostEqual(view.zoom(), 1.0)

    def test_pageview_set_zoom_clamps(self):
        view = PageView(DashboardCanvas(None, 12, 8))
        view.set_zoom(10.0)
        self.assertEqual(view.zoom(), 4.0)


class MigrateLayoutTest(unittest.TestCase):
    def test_v1_bare_list_becomes_one_page(self):
        data = migrate_layout([{"__type__": "indicator", "id": "a"}])
        self.assertEqual(data["version"], 3)
        self.assertEqual(len(data["pages"]), 1)
        self.assertEqual(data["pages"][0]["title"], "Page 1")
        self.assertEqual(data["pages"][0]["elements"][0]["id"], "a")
        self.assertEqual(data["grid"], {"cols": DEFAULT_COLS,
                                        "rows": DEFAULT_ROWS})

    def test_v2_wraps_elements_and_connections(self):
        v2 = {
            "version": 2,
            "grid": {"cols": 10, "rows": 6},
            "theme": {"accent": "#123456"},
            "connections": {"s": ["t"]},
            "elements": [{"__type__": "serial_chart", "id": "s"}],
        }
        data = migrate_layout(v2)
        self.assertEqual(data["version"], 3)
        self.assertEqual(data["grid"], {"cols": 10, "rows": 6})
        self.assertEqual(data["theme"], {"accent": "#123456"})
        self.assertEqual(len(data["pages"]), 1)
        self.assertEqual(data["pages"][0]["connections"], {"s": ["t"]})
        self.assertEqual(data["pages"][0]["elements"][0]["id"], "s")

    def test_v3_passes_through(self):
        v3 = {
            "version": 3,
            "grid": {"cols": 12, "rows": 8},
            "theme": {},
            "active_page": "p2",
            "pages": [
                {"id": "p1", "title": "One", "connections": {},
                 "elements": []},
                {"id": "p2", "title": "Two", "connections": {"a": ["b"]},
                 "elements": [{"__type__": "list", "id": "a"}]},
            ],
        }
        data = migrate_layout(v3)
        self.assertEqual(data["active_page"], "p2")
        self.assertEqual(len(data["pages"]), 2)
        self.assertEqual(data["pages"][1]["connections"], {"a": ["b"]})

    def test_empty_input_yields_one_empty_page(self):
        data = migrate_layout(None)
        self.assertEqual(len(data["pages"]), 1)
        self.assertEqual(data["pages"][0]["elements"], [])

    def test_gap_defaults_to_zero_when_absent(self):
        data = migrate_layout([{"__type__": "indicator", "id": "a"}])
        self.assertEqual(data["gap"], 0)

    def test_gap_passes_through(self):
        data = migrate_layout({"version": 3, "gap": 16, "pages": []})
        self.assertEqual(data["gap"], 16)

    def test_canvas_region_absent_in_older_blobs(self):
        data = migrate_layout([{"__type__": "indicator", "id": "a"}])
        self.assertIsNone(data["canvas"])

    def test_canvas_region_passes_through(self):
        data = migrate_layout(
            {"version": 3, "canvas": {"w": 1600, "h": 900}, "pages": []})
        self.assertEqual(data["canvas"], {"w": 1600, "h": 900})

    def test_resolve_canvas_size_uses_stored_region(self):
        size = DashboardWindow._resolve_canvas_size(
            {"canvas": {"w": 1600, "h": 900}, "pages": []})
        self.assertEqual(size, (1600, 900))

    def test_resolve_canvas_size_derives_from_content_when_absent(self):
        # legacy blob with no region: derive from the content bounding box
        # (rounded up) so the export keeps its previous extent
        data = {"pages": [{"elements": [
            {"grid": {"x": 0, "y": 0, "w": 300, "h": 200}},
            {"grid": {"x": 320, "y": 0, "w": 300, "h": 200}},
        ]}]}
        w, h = DashboardWindow._resolve_canvas_size(data)
        self.assertGreaterEqual(w, 620)   # past the right-most tile edge
        self.assertGreaterEqual(h, 200)

    def test_resolve_canvas_size_defaults_when_no_tiles(self):
        from window import DEFAULT_CANVAS_W, DEFAULT_CANVAS_H
        size = DashboardWindow._resolve_canvas_size({"pages": []})
        self.assertEqual(size, (DEFAULT_CANVAS_W, DEFAULT_CANVAS_H))


class MultiPageWindowTest(unittest.TestCase):
    def _win(self):
        return DashboardWindow(IFACE)

    def test_starts_with_one_page(self):
        win = self._win()
        self.assertEqual(len(win.pages()), 1)
        self.assertIs(win.current_canvas(), win.pages()[0].canvas)

    def test_add_page_creates_and_activates(self):
        win = self._win()
        page = win.add_page("Second")
        self.assertEqual(len(win.pages()), 2)
        self.assertEqual(page.title, "Second")
        self.assertIs(win.current_canvas(), page.canvas)
        self.assertEqual(win.bus._active_page, page.id)

    def test_add_element_lands_on_current_page(self):
        win = self._win()
        win.add_page("Second")
        win.add_element("indicator", {"title": "X"})
        self.assertEqual(len(win.current_canvas().tiles()), 1)
        self.assertEqual(len(win.pages()[0].canvas.tiles()), 0)

    def test_delete_page_keeps_at_least_one(self):
        win = self._win()
        first = win.pages()[0]
        win.add_page("Second")
        win.delete_page(first.id)
        self.assertEqual(len(win.pages()), 1)
        last = win.pages()[0]
        win.delete_page(last.id)
        self.assertEqual(len(win.pages()), 1)


class StartScreenAndFileTest(unittest.TestCase):
    """Start screen view-switching + .qdash save/open round-trip."""

    def _win(self):
        return DashboardWindow(IFACE)

    def test_constructed_window_shows_dashboard(self):
        win = self._win()
        self.assertIs(win._content_stack.currentWidget(), win._pages_col)

    def test_new_dashboard_resets_to_one_page(self):
        win = self._win()
        win.add_page("Second")
        self.assertEqual(len(win.pages()), 2)
        win.new_dashboard()
        self.assertEqual(len(win.pages()), 1)
        self.assertIs(win._content_stack.currentWidget(), win._pages_col)

    def test_layout_dict_round_trip_restores_element(self):
        win = self._win()
        win.add_element("indicator", {"title": "Pop"})
        data = win._build_layout_dict()
        win._apply_layout_dict(migrate_layout(data))
        self.assertEqual(len(win.current_canvas().tiles()), 1)

    def test_canvas_size_round_trips(self):
        win = self._win()
        win._set_canvas_size(1600, 900)
        self.assertEqual(win.canvas_size(), (1600, 900))
        data = win._build_layout_dict()
        self.assertEqual(data["canvas"], {"w": 1600, "h": 900})
        other = self._win()
        other._apply_layout_dict(migrate_layout(data))
        self.assertEqual(other.canvas_size(), (1600, 900))

    def test_save_and_open_qdash_file(self):
        win = self._win()
        win.add_element("indicator", {"title": "Pop"})
        tmp = tempfile.mkdtemp()
        path = project_io.write_layout_file(
            os.path.join(tmp, "dash"), win._build_layout_dict())
        self.assertTrue(path.endswith(project_io.QDASH_SUFFIX))
        # a fresh window (empty Page 1, no tiles) opens it without a prompt
        other = self._win()
        other.open_file_path(path)
        self.assertEqual(len(other.current_canvas().tiles()), 1)
        self.assertIs(other._content_stack.currentWidget(), other._pages_col)

    def test_load_from_project_without_dashboard_shows_start(self):
        QgsProject.instance().removeEntry(PROJECT_SCOPE, PROJECT_KEY)
        win = self._win()
        win.load_from_project()
        self.assertEqual(len(win.pages()), 0)
        self.assertIs(win._content_stack.currentWidget(), win.start_view)


class HeaderLayoutTest(unittest.TestCase):
    """Pure layout helpers for the header banner."""

    def test_inner_box_direction_per_slot(self):
        from elements.header_layout import inner_box_direction
        self.assertEqual(inner_box_direction("left"), ("h", True))
        self.assertEqual(inner_box_direction("right"), ("h", False))
        self.assertEqual(inner_box_direction("above"), ("v", True))
        self.assertEqual(inner_box_direction("below"), ("v", False))

    def test_resolve_header_page_overrides_global(self):
        from elements.header_layout import resolve_header
        page = {"title": "Page banner"}
        glob = {"title": "Global banner"}
        self.assertIs(resolve_header(page, glob), page)
        self.assertIs(resolve_header(None, glob), glob)
        self.assertIsNone(resolve_header(None, None))


class HeaderElementTest(unittest.TestCase):
    def _bus(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        return bus

    def test_factory_and_roles(self):
        from elements import create_element
        from elements.header import HeaderElement
        el = create_element("header", self._bus(), {"title": "Acme"})
        self.assertIsInstance(el, HeaderElement)
        self.assertFalse(el.is_filter_source)
        self.assertFalse(el.accepts_filter)

    def test_renders_title(self):
        from elements import create_element
        el = create_element("header", self._bus(), {"title": "Acme Corp"})
        self.assertEqual(el._title.text(), "Acme Corp")


class AddElementHeaderDialogTest(unittest.TestCase):
    def _select(self, dlg, type_name):
        i = dlg.type_combo.findData(type_name)
        dlg.type_combo.setCurrentIndex(i)

    def test_header_hides_layer_row_and_returns_config(self):
        from add_element_dialog import AddElementDialog
        dlg = AddElementDialog()
        self._select(dlg, "header")
        self.assertTrue(dlg.layer_combo.isHidden())
        dlg.title_edit.setText("Brand")
        t, cfg = dlg.result_config()
        self.assertEqual(t, "header")
        self.assertEqual(cfg["title"], "Brand")
        self.assertIn("font_family", cfg)
        # the header is a free-placed tile now — no dock/scope keys
        self.assertNotIn("anchor", cfg)
        self.assertNotIn("thickness", cfg)
        self.assertNotIn("scope_all_pages", cfg)
        self.assertNotIn("layer_id", cfg)


class WindowHeaderTest(unittest.TestCase):
    def _win(self):
        return DashboardWindow(IFACE)

    def test_header_added_as_tile_on_current_page(self):
        win = self._win()
        win.add_page("Second")
        # current page is the second one
        win.add_element("header", {"title": "Local"})
        cur = win.current_page()
        cur_types = [t.element.type_name for t in cur.canvas.tiles()]
        self.assertIn("header", cur_types)
        # the header is per-page now (no global scope): the other page is clean
        other = win.pages()[0]
        other_types = [t.element.type_name for t in other.canvas.tiles()]
        self.assertNotIn("header", other_types)

    def test_header_size_control_in_appearance(self):
        """The header's banner height is now the generic Tile-size control in
        the Tile Appearance panel (geometry, never the element config)."""
        from tile_style_form import TileStyleForm
        win = self._win()
        win.add_element("header", {"title": "Brand"})
        tile = next(t for t in win.current_page().canvas.tiles()
                    if t.element.type_name == "header")
        start_w, start_h = tile.grid_rect()[2:4]

        # the Tile-size control is seeded from the tile geometry
        form = TileStyleForm(tile.element, win.bus.theme)
        self.assertEqual(form.tile_size(), (start_w, start_h))
        # size is geometry, not style — it never leaks into the override dict
        self.assertNotIn("__size__", form.result_override() or {})

        # applying a height resizes the tile exactly (taller, then a thin band —
        # no MIN_TILE floor, so banners shorter than a normal tile are allowed)
        self.assertTrue(tile.set_height_px(start_h + 120))
        self.assertEqual(tile.grid_rect()[3], start_h + 120)
        self.assertTrue(tile.set_height_px(64))
        self.assertEqual(tile.grid_rect()[3], 64)

    def test_header_height_pushes_tiles_below(self):
        """Growing the banner pushes every tile below it down by the delta
        (accordion), and shrinking pulls them back up — never reverting."""
        win = self._win()
        win.add_element("header", {"title": "Brand"}
                        )       # lands at (0,0,w,80)
        # lands below the band
        win.add_element("text", {"title": "Body"})
        canvas = win.current_page().canvas
        header = next(t for t in canvas.tiles()
                      if t.element.type_name == "header")
        below = next(t for t in canvas.tiles()
                     if t.element.type_name == "text")
        hx, hy, hw, hh = header.grid_rect()
        by = below.grid_rect()[1]
        # it really is below
        self.assertGreaterEqual(by, hy + hh)

        # grow the banner by 100 → the tile below slides down by exactly 100
        header.set_height_px(hh + 100)
        self.assertEqual(below.grid_rect()[1], by + 100)
        # shrink back → the tile returns to its original row (push reversed)
        header.set_height_px(hh)
        self.assertEqual(below.grid_rect()[1], by)


class ThemeChromeTest(unittest.TestCase):
    def test_default_chrome_is_white(self):
        self.assertEqual(Theme.default().chrome_bg, "#ffffff")

    def test_window_qss_styles_chrome_not_just_canvas(self):
        qss = Theme.default().window_qss()
        self.assertIn("QMainWindow", qss)
        self.assertIn("QTabBar::tab", qss)
        # the horizontal toolbar was replaced by the left icon rail + status
        # bar
        self.assertIn("#dashSidebar", qss)
        self.assertIn("QStatusBar", qss)

    def test_chrome_bg_round_trips(self):
        t = Theme.default().with_values(chrome_bg="#101010")
        self.assertEqual(Theme.from_dict(t.to_dict()).chrome_bg, "#101010")


class EdgeActionTest(unittest.TestCase):
    """Per-edge actions: a flash-only edge drives location, not the filter."""

    def test_flash_only_edge_does_not_filter_but_drives_location(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_edge_actions("s", "m", {"flash"})
        bus.set_filter("s", '"a" = 1')
        self.assertIsNone(bus.combined_filter_for("m"))          # no filter
        self.assertEqual(bus.location_actions_for("m"), {"flash"})
        self.assertEqual(bus.location_filter_for("m"), '("a" = 1)')

    def test_filter_edge_filters(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_edge_actions("s", "t", {"filter"})
        bus.set_filter("s", '"a" = 1')
        self.assertEqual(bus.combined_filter_for("t"), '("a" = 1)')
        self.assertEqual(bus.location_actions_for("t"), set())

    def test_bundle_edge_both_filters_and_zooms(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_edge_actions("s", "m", {"filter", "zoom", "flash"})
        bus.set_filter("s", '"a" = 1')
        self.assertEqual(bus.combined_filter_for("m"), '("a" = 1)')
        self.assertEqual(bus.location_actions_for("m"), {"zoom", "flash"})

    def test_action_edge_round_trips(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.set_edge_actions("s", "m", {"filter", "zoom"})
        data = bus.connections_to_dict("A")

        other = DashboardBus()
        other.set_active_page("A")
        other.load_connections(data, "A")
        self.assertEqual(other.targets_of("s"), {"m"})
        self.assertEqual(other.edge_actions("s", "m"), {"filter", "zoom"})

    def test_upgrade_legacy_map_edges_bundles_implicit_map_edge(self):
        bus = DashboardBus()
        bus.set_active_page("A")
        bus.load_connections({"s": ["m", "t"]}, "A")   # legacy list shape
        bus.upgrade_legacy_map_edges("A", ["m"])
        self.assertEqual(
            bus.edge_actions(
                "s", "m"), {
                "filter", "zoom", "flash"})
        self.assertEqual(bus.edge_actions("s", "t"), {"filter"})   # non-map


if __name__ == "__main__":
    unittest.main()
