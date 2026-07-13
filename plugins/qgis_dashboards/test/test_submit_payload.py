# -*- coding: utf-8 -*-
"""Unit tests for submit_payload (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_submit_payload.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from submit_payload import (  # noqa: E402
    MAX_AUTHOR, MAX_DESC, MAX_HTML_BYTES, MAX_TITLE,
    build_row, candidate_slug, exceeds_size_limit, object_key, slugify,
    storage_path, view_url,
)


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("My Dashboard"), "my-dashboard")

    def test_accents_stripped(self):
        self.assertEqual(slugify("Café São Paulo"), "cafe-sao-paulo")

    def test_symbol_runs_collapse(self):
        self.assertEqual(slugify("A -- B__C!!"), "a-b-c")

    def test_empty_falls_back(self):
        self.assertEqual(slugify(""), "dashboard")
        self.assertEqual(slugify("!!!"), "dashboard")
        self.assertEqual(slugify(None), "dashboard")

    def test_matches_site_slugify_examples(self):
        # Mirrors lib/submit-core.mjs test expectations
        self.assertEqual(slugify("Flood Risk 2026"), "flood-risk-2026")


class TestCandidateSlug(unittest.TestCase):
    def test_first_attempt_is_base(self):
        self.assertEqual(candidate_slug("map", 0), "map")

    def test_suffixes_start_at_2(self):
        self.assertEqual(candidate_slug("map", 1), "map-2")
        self.assertEqual(candidate_slug("map", 2), "map-3")


class TestPaths(unittest.TestCase):
    def test_object_key(self):
        self.assertEqual(
            object_key(
                "my-map",
                "index.html"),
            "my-map/index.html")

    def test_storage_path_includes_bucket(self):
        self.assertEqual(
            storage_path("my-map", "thumb.png"), "dashboards/my-map/thumb.png")

    def test_view_url_encodes_slug(self):
        self.assertEqual(
            view_url("flood risk"),
            "https://qgis.byzenterra.org/qdashboards/view?d=flood%20risk")


class TestBuildRow(unittest.TestCase):
    def test_full_row(self):
        row = build_row("my-map", "My Map", "Isaac", " A summary ", 1234)
        self.assertEqual(row["slug"], "my-map")
        self.assertEqual(row["title"], "My Map")
        self.assertEqual(row["author"], "Isaac")
        self.assertEqual(row["description"], "A summary")
        self.assertEqual(row["html_path"], "dashboards/my-map/index.html")
        self.assertEqual(row["thumb_path"], "dashboards/my-map/thumb.png")
        self.assertEqual(row["html_bytes"], 1234)

    def test_no_thumb(self):
        row = build_row("m", "T", "A", None, 1, has_thumb=False)
        self.assertIsNone(row["thumb_path"])

    def test_empty_title_falls_back_to_slug(self):
        row = build_row("my-map", "", "A", None, 1)
        self.assertEqual(row["title"], "my-map")

    def test_blank_author_is_null(self):
        row = build_row("m", "T", "   ", None, 1)
        self.assertIsNone(row["author"])

    def test_empty_description_omitted(self):
        for desc in (None, "", "   "):
            row = build_row("m", "T", "A", desc, 1)
            self.assertNotIn("description", row)

    def test_lengths_clamped_to_table_constraints(self):
        row = build_row("m", "t" * 500, "a" * 500, "d" * 500, 1)
        self.assertEqual(len(row["title"]), MAX_TITLE)
        self.assertEqual(len(row["author"]), MAX_AUTHOR)
        self.assertEqual(len(row["description"]), MAX_DESC)


class TestSizeGuard(unittest.TestCase):
    def test_small_is_within_limit(self):
        self.assertFalse(exceeds_size_limit(b"<html></html>"))

    def test_boundary_exactly_at_limit_is_ok(self):
        class FakeBytes:
            def __len__(self):
                return MAX_HTML_BYTES
        self.assertFalse(exceeds_size_limit(FakeBytes()))

    def test_over_limit_flagged(self):
        class FakeBytes:
            def __len__(self):
                return MAX_HTML_BYTES + 1
        self.assertTrue(exceeds_size_limit(FakeBytes()))

    def test_limit_matches_bucket_cap(self):
        self.assertEqual(MAX_HTML_BYTES, 50 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
