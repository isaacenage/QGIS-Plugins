# -*- coding: utf-8 -*-
"""Unit tests for elements/aggregate_filter (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_aggregate_filter.py

aggregate_filter.py has no third-party imports, so it is imported standalone
(via the ``elements`` dir on the path) to avoid loading elements/__init__,
which pulls in qgis.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "elements"))

import aggregate_filter as af  # noqa: E402

F = '"region" = \'A\''


class TestInjectFilter(unittest.TestCase):
    def test_noop_without_filter(self):
        self.assertEqual(af.inject_filter('sum("pop")', None), 'sum("pop")')
        self.assertEqual(af.inject_filter('sum("pop")', ""), 'sum("pop")')

    def test_noop_without_expression(self):
        self.assertEqual(af.inject_filter("", F), "")
        self.assertEqual(af.inject_filter(None, F), None)

    def test_simple_count(self):
        self.assertEqual(
            af.inject_filter("count(1)", F),
            'count(1, filter:=({}))'.format(F))

    def test_sum_of_field(self):
        self.assertEqual(
            af.inject_filter('sum("pop")', F),
            'sum("pop", filter:=({}))'.format(F))

    def test_ratio_of_two_aggregates(self):
        # both aggregates get the filter independently
        self.assertEqual(
            af.inject_filter('sum("a") / sum("b")', F),
            'sum("a", filter:=({0})) / sum("b", filter:=({0}))'.format(F))

    def test_non_aggregate_function_untouched(self):
        # round() is not an aggregate; only the inner sum() gets the filter
        self.assertEqual(
            af.inject_filter('round(sum("a"), 2)', F),
            'round(sum("a", filter:=({})), 2)'.format(F))

    def test_existing_filter_not_doubled(self):
        expr = 'count(1, filter:="x" > 0)'
        self.assertEqual(af.inject_filter(expr, F), expr)

    def test_scalar_min_max_not_aggregated(self):
        # QGIS min()/max() are element-wise over arguments, not aggregates
        expr = 'min("a", "b")'
        self.assertEqual(af.inject_filter(expr, F), expr)

    def test_field_name_with_paren_like_text_in_quotes(self):
        # a parenthesis inside a quoted field/string must not confuse the
        # scanner
        expr = '''sum("pop") || ' (total)' '''
        self.assertEqual(
            af.inject_filter(expr, F),
            '''sum("pop", filter:=({})) || ' (total)' '''.format(F))

    def test_nested_aggregates_both_filtered(self):
        self.assertEqual(
            af.inject_filter('sum(maximum("a"))', F),
            'sum(maximum("a", filter:=({0})), filter:=({0}))'.format(F))

    def test_whitespace_between_name_and_paren(self):
        self.assertEqual(
            af.inject_filter('count (1)', F),
            'count (1, filter:=({}))'.format(F))

    def test_minimum_maximum_mean(self):
        for fn in ("minimum", "maximum", "mean", "median", "count_distinct"):
            self.assertEqual(
                af.inject_filter('{}("v")'.format(fn), F),
                '{}("v", filter:=({}))'.format(fn, F))

    def test_quoted_filter_keyword_not_mistaken(self):
        # a field literally named "filter" must not be read as the filter param
        expr = 'sum("filter")'
        self.assertEqual(
            af.inject_filter(expr, F),
            'sum("filter", filter:=({}))'.format(F))


if __name__ == "__main__":
    unittest.main()
