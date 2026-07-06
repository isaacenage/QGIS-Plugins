# -*- coding: utf-8 -*-
"""Unit tests for elements/legend_model (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_legend_model.py

legend_model.py has no third-party imports, so it is imported standalone (via
the ``elements`` dir on the path) to avoid loading elements/__init__, which
pulls in qgis.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "elements"))

import legend_model as lm


class TestCategoriesToExpression(unittest.TestCase):
    def test_all_selected_returns_none(self):
        self.assertIsNone(
            lm.categories_to_expression("type", ["a", "b", "c"], 3))

    def test_subset_strings(self):
        self.assertEqual(
            lm.categories_to_expression("type", ["a", "b"], 3),
            '"type" IN (\'a\', \'b\')')

    def test_single_value(self):
        self.assertEqual(
            lm.categories_to_expression("type", ["a"], 3),
            '"type" IN (\'a\')')

    def test_numeric_values_unquoted(self):
        self.assertEqual(
            lm.categories_to_expression("zone", [1, 2], 3),
            '"zone" IN (1, 2)')

    def test_string_with_apostrophe_escaped(self):
        self.assertEqual(
            lm.categories_to_expression("name", ["O'Brien"], 2),
            '"name" IN (\'O\'\'Brien\')')

    def test_null_value_uses_is_null(self):
        self.assertEqual(
            lm.categories_to_expression("type", [None], 3),
            '"type" IS NULL')

    def test_null_and_values_combined_with_or(self):
        self.assertEqual(
            lm.categories_to_expression("type", ["a", None], 3),
            '("type" IN (\'a\') OR "type" IS NULL)')

    def test_empty_selection_matches_nothing(self):
        self.assertEqual(
            lm.categories_to_expression("type", [], 3),
            '"type" IN (NULL)')


class TestRangesToExpression(unittest.TestCase):
    def test_all_selected_returns_none(self):
        ranges = [(0, 10), (10, 20)]
        self.assertIsNone(lm.ranges_to_expression("v", ranges, 2))

    def test_single_range(self):
        self.assertEqual(
            lm.ranges_to_expression("v", [(0, 10)], 2),
            '("v" >= 0 AND "v" <= 10)')

    def test_multiple_ranges_or(self):
        self.assertEqual(
            lm.ranges_to_expression("v", [(0, 10), (20, 30)], 3),
            '(("v" >= 0 AND "v" <= 10) OR ("v" >= 20 AND "v" <= 30))')

    def test_empty_matches_nothing(self):
        self.assertEqual(
            lm.ranges_to_expression("v", [], 2),
            '"v" IN (NULL)')


if __name__ == "__main__":
    unittest.main()
