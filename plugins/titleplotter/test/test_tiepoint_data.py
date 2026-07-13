# -*- coding: utf-8 -*-
"""Tests for the pure tie point helpers (no QGIS required).

Run directly so the test package __init__ (which may import qgis) is not
loaded:  python test/test_tiepoint_data.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tiepoint_data import (  # noqa: E402
    build_search_params,
    build_search_url,
    correction_payload,
    filter_rows,
    merge_rows,
    normalize_name,
    parse_coordinate,
    provinces_from_rows,
    row_matches,
)

ROWS = [
    {"id": 1, "name": "BLLM 1", "description": "Cad 614-D Botolan",
     "province": "ZAMBALES", "municipality": "BOTOLAN",
     "northing": 1691760.514, "easting": 394854.244},
    {"id": 2, "name": "BLBM 10", "description": "Pls 467-D",
     "province": "RIZAL", "municipality": "TANAY",
     "northing": 1614000.0, "easting": 528659.872},
    {"id": 3, "name": "BLLM 13", "description": None,
     "province": "ZAMBALES", "municipality": "IBA",
     "northing": None, "easting": 400300.0},
]


class TestNormalizeName(unittest.TestCase):
    def test_strips_spaces_and_case(self):
        self.assertEqual(normalize_name("BLLM 1"), "bllm1")
        self.assertEqual(normalize_name("  B L L M 1 "), "bllm1")
        self.assertEqual(normalize_name(None), "")


class TestBuildSearchParams(unittest.TestCase):
    def test_no_filters_has_select_order_limit_only(self):
        params = dict(build_search_params())
        self.assertIn("select", params)
        self.assertIn("order", params)
        self.assertEqual(params["limit"], "1000")
        self.assertNotIn("name_key", params)
        self.assertNotIn("province", params)

    def test_all_filters(self):
        params = dict(build_search_params(
            name="BLLM 1", description="Cad", municipality="Botolan",
            province="ZAMBALES", limit=50))
        self.assertEqual(params["name_key"], "ilike.*bllm1*")
        self.assertEqual(params["description"], "ilike.*Cad*")
        self.assertEqual(params["municipality"], "ilike.*Botolan*")
        self.assertEqual(params["province"], "eq.ZAMBALES")
        self.assertEqual(params["limit"], "50")

    def test_blank_filters_are_dropped(self):
        params = dict(
            build_search_params(
                name="  ",
                description="",
                province=" "))
        self.assertNotIn("name_key", params)
        self.assertNotIn("description", params)
        self.assertNotIn("province", params)

    def test_url_encodes_values(self):
        url = build_search_url("https://x.supabase.co", name="BLLM 1")
        self.assertIn("/rest/v1/tiepoints?", url)
        self.assertIn("name_key=ilike.%2Abllm1%2A", url)


class TestRowFiltering(unittest.TestCase):
    def test_name_is_space_and_case_insensitive(self):
        self.assertTrue(row_matches(ROWS[0], name="bllm1"))
        self.assertTrue(row_matches(ROWS[0], name="LLM 1"))
        self.assertFalse(row_matches(ROWS[0], name="BLBM"))

    def test_province_is_exact(self):
        self.assertTrue(row_matches(ROWS[0], province="ZAMBALES"))
        self.assertFalse(row_matches(ROWS[0], province="ZAMBA"))

    def test_description_handles_none(self):
        self.assertFalse(row_matches(ROWS[2], description="Cad"))

    def test_filter_rows_sorts_by_province_municipality_name(self):
        result = filter_rows(ROWS)
        self.assertEqual([r["id"] for r in result], [2, 1, 3])

    def test_filter_rows_combined(self):
        result = filter_rows(ROWS, name="bllm", province="ZAMBALES")
        self.assertEqual([r["id"] for r in result], [1, 3])


class TestMergeRows(unittest.TestCase):
    def test_merge_adds_and_overwrites_without_mutating(self):
        existing = {"1": {"id": 1, "name": "OLD"}}
        merged = merge_rows(existing, ROWS[:2])
        self.assertEqual(merged["1"]["name"], "BLLM 1")
        self.assertIn("2", merged)
        # original untouched (immutability)
        self.assertEqual(existing["1"]["name"], "OLD")
        self.assertNotIn("2", existing)

    def test_rows_without_id_are_skipped(self):
        merged = merge_rows({}, [{"name": "no id"}])
        self.assertEqual(merged, {})


class TestProvincesFromRows(unittest.TestCase):
    def test_unique_sorted(self):
        self.assertEqual(provinces_from_rows(ROWS), ["RIZAL", "ZAMBALES"])


class TestParseCoordinate(unittest.TestCase):
    def test_empty_is_valid_none(self):
        self.assertEqual(parse_coordinate(""), (None, True))
        self.assertEqual(parse_coordinate("   "), (None, True))

    def test_numeric_with_thousands_separator(self):
        self.assertEqual(parse_coordinate(
            "1,691,760.514"), (1691760.514, True))

    def test_garbage_is_invalid(self):
        self.assertEqual(parse_coordinate("abc"), (None, False))


class TestCorrectionPayload(unittest.TestCase):
    def test_full_payload(self):
        payload = correction_payload(
            ROWS[0], proposed_northing=1691000.0, proposed_easting=None,
            remarks="  field survey  ", reporter_name="  Juan Dela Cruz ",
            contact="", plugin_version="2.1.0")
        self.assertEqual(payload["tiepoint_id"], 1)
        self.assertEqual(payload["tiepoint_name"], "BLLM 1")
        self.assertEqual(payload["current_northing"], 1691760.514)
        self.assertEqual(payload["proposed_northing"], 1691000.0)
        self.assertIsNone(payload["proposed_easting"])
        self.assertEqual(payload["remarks"], "field survey")
        self.assertEqual(payload["reporter_name"], "Juan Dela Cruz")
        self.assertIsNone(payload["reporter_contact"])
        self.assertEqual(payload["plugin_version"], "2.1.0")

    def test_blank_reporter_name_is_null(self):
        payload = correction_payload(ROWS[0], remarks="x", reporter_name="  ")
        self.assertIsNone(payload["reporter_name"])


if __name__ == "__main__":
    unittest.main()
