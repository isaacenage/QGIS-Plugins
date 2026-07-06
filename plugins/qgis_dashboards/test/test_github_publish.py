# -*- coding: utf-8 -*-
"""Unit tests for github_publish (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_github_publish.py
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from github_publish import (
    slugify, asset_repo_path, asset_manifest_path, public_view_url,
    build_entry, manifest_upsert, parse_manifest, merge_manifest, tree_items,
    parse_repo, estimate_committed_bytes,
)


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Harbor Traffic"), "harbor-traffic")

    def test_accents_and_symbols(self):
        self.assertEqual(slugify("Población & Café 2024!"), "poblacion-cafe-2024")

    def test_collapses_and_trims(self):
        self.assertEqual(slugify("  --Hello   World--  "), "hello-world")

    def test_empty_falls_back(self):
        self.assertEqual(slugify(""), "dashboard")
        self.assertEqual(slugify("!!!"), "dashboard")
        self.assertEqual(slugify(None), "dashboard")

    def test_custom_fallback(self):
        self.assertEqual(slugify("###", fallback="untitled"), "untitled")

    def test_stable(self):
        self.assertEqual(slugify("My Map"), slugify("My Map"))


class TestPaths(unittest.TestCase):
    def test_repo_path(self):
        self.assertEqual(asset_repo_path("foo", "index.html"),
                         "public/dashboards/foo/index.html")

    def test_manifest_path(self):
        self.assertEqual(asset_manifest_path("foo", "thumb.png"),
                         "dashboards/foo/thumb.png")

    def test_view_url(self):
        self.assertEqual(
            public_view_url("harbor-traffic"),
            "https://qgis.byzenterra.org/qdashboards/view?d=harbor-traffic")

    def test_view_url_encodes(self):
        self.assertEqual(public_view_url("a b"),
                         "https://qgis.byzenterra.org/qdashboards/view?d=a%20b")


class TestBuildEntry(unittest.TestCase):
    def test_shape(self):
        e = build_entry("s", "Title", "Isaac", "2026-06-19")
        self.assertEqual(e, {
            "slug": "s", "title": "Title", "author": "Isaac",
            "date": "2026-06-19", "path": "dashboards/s/index.html",
            "thumb": "dashboards/s/thumb.png",
        })

    def test_description_optional(self):
        self.assertNotIn("description", build_entry("s", "T", "A", "d"))
        self.assertEqual(
            build_entry("s", "T", "A", "d", description="hi")["description"], "hi")

    def test_title_defaults_to_slug(self):
        self.assertEqual(build_entry("s", "", "A", "d")["title"], "s")


class TestManifestUpsert(unittest.TestCase):
    def test_append_new(self):
        out = manifest_upsert([], {"slug": "a"})
        self.assertEqual(out, [{"slug": "a"}])

    def test_replace_in_place(self):
        entries = [{"slug": "a", "title": "old"}, {"slug": "b"}]
        out = manifest_upsert(entries, {"slug": "a", "title": "new"})
        self.assertEqual(out, [{"slug": "a", "title": "new"}, {"slug": "b"}])

    def test_does_not_mutate_input(self):
        entries = [{"slug": "a", "title": "old"}]
        manifest_upsert(entries, {"slug": "a", "title": "new"})
        self.assertEqual(entries, [{"slug": "a", "title": "old"}])

    def test_no_duplicate_on_republish(self):
        out = manifest_upsert([{"slug": "a"}], {"slug": "a"})
        self.assertEqual(len(out), 1)


class TestParseManifest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(parse_manifest(""), [])
        self.assertEqual(parse_manifest("   "), [])
        self.assertEqual(parse_manifest(None), [])

    def test_malformed_is_empty(self):
        self.assertEqual(parse_manifest("{not json"), [])

    def test_non_list_is_empty(self):
        self.assertEqual(parse_manifest('{"slug": "a"}'), [])

    def test_valid_list(self):
        self.assertEqual(parse_manifest('[{"slug": "a"}]'), [{"slug": "a"}])


class TestMergeManifest(unittest.TestCase):
    def test_new_entry(self):
        text, is_update = merge_manifest("[]", build_entry("a", "A", "", "d"))
        self.assertFalse(is_update)
        self.assertEqual(json.loads(text)[0]["slug"], "a")
        self.assertTrue(text.endswith("\n"))

    def test_update_existing(self):
        first, _ = merge_manifest("[]", build_entry("a", "Old", "", "d1"))
        second, is_update = merge_manifest(first, build_entry("a", "New", "", "d2"))
        self.assertTrue(is_update)
        data = json.loads(second)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "New")

    def test_tolerates_missing_manifest(self):
        text, is_update = merge_manifest(None, build_entry("a", "A", "", "d"))
        self.assertFalse(is_update)
        self.assertEqual(len(json.loads(text)), 1)


class TestTreeItems(unittest.TestCase):
    def test_build(self):
        items = tree_items([("public/dashboards/a/index.html", "sha1"),
                            ("public/dashboards/manifest.json", "sha2")])
        self.assertEqual(items, [
            {"path": "public/dashboards/a/index.html", "mode": "100644",
             "type": "blob", "sha": "sha1"},
            {"path": "public/dashboards/manifest.json", "mode": "100644",
             "type": "blob", "sha": "sha2"},
        ])


class TestParseRepo(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_repo("isaacenage/QGIS-Dashboard"),
                         ("isaacenage", "QGIS-Dashboard"))

    def test_strips_slashes(self):
        self.assertEqual(parse_repo("/owner/name/"), ("owner", "name"))

    def test_invalid_raises(self):
        for bad in ("", "owner", "owner/name/extra", "/", "owner/"):
            with self.assertRaises(ValueError):
                parse_repo(bad)


class TestEstimate(unittest.TestCase):
    def test_base64_inflation(self):
        self.assertEqual(estimate_committed_bytes(300, 0), 400)


if __name__ == "__main__":
    unittest.main()
