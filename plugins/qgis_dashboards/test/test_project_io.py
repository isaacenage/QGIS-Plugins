# coding=utf-8
"""Tests for the pure ``.qdash`` file module (no QGIS runtime needed).

Run directly so the test package ``__init__`` (which imports qgis) is not
loaded::

    cd qgis_dashboards && PYTHONPATH=$(pwd) python test/test_project_io.py
"""

__author__ = 'isaacenagework@gmail.com'
__date__ = '2026-06-16'
__copyright__ = 'Copyright 2026, Isaac Enage'

import json
import os
import tempfile
import unittest

from project_io import (
    ensure_suffix, write_layout_file, read_layout_file, display_name,
    QDASH_SUFFIX, FORMAT_TAG,
)


class EnsureSuffixTest(unittest.TestCase):
    def test_adds_when_missing(self):
        self.assertEqual(ensure_suffix("out/foo"), "out/foo" + QDASH_SUFFIX)

    def test_keeps_when_present(self):
        self.assertEqual(ensure_suffix("foo.qdash"), "foo.qdash")

    def test_case_insensitive(self):
        self.assertEqual(ensure_suffix("foo.QDASH"), "foo.QDASH")


class RoundTripTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()

    def test_write_then_read(self):
        data = {"version": 3, "pages": [{"id": "p1", "title": "P"}]}
        path = write_layout_file(os.path.join(self._dir, "dash"), data)
        self.assertTrue(path.endswith(QDASH_SUFFIX))
        back = read_layout_file(path)
        self.assertEqual(back["version"], 3)
        self.assertEqual(back["pages"][0]["id"], "p1")

    def test_format_marker_added(self):
        path = write_layout_file(os.path.join(self._dir, "d"), {"version": 3})
        back = read_layout_file(path)
        self.assertEqual(back["_format"], FORMAT_TAG)

    def test_input_not_mutated(self):
        data = {"version": 3}
        write_layout_file(os.path.join(self._dir, "d"), data)
        self.assertNotIn("_format", data)

    def test_read_rejects_non_object(self):
        path = os.path.join(self._dir, "list.qdash")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump([1, 2, 3], fh)
        with self.assertRaises(ValueError):
            read_layout_file(path)


class DisplayNameTest(unittest.TestCase):
    def test_strips_dir_and_extension(self):
        self.assertEqual(display_name("/a/b/Sales.qdash"), "Sales")

    def test_empty_falls_back(self):
        self.assertEqual(display_name(""), "Dashboard")


if __name__ == "__main__":
    unittest.main()
