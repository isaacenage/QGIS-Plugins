# coding=utf-8
"""Pure tests for the indicator Statistic+Field expression helper."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicator_expr import build_aggregate, parse_aggregate, STATISTICS  # noqa: E402


class BuildAggregateTest(unittest.TestCase):
    def test_count_ignores_field(self):
        self.assertEqual(build_aggregate("count", None), "count(1)")
        self.assertEqual(build_aggregate("count", "pop"), "count(1)")

    def test_empty_statistic_is_count(self):
        self.assertEqual(build_aggregate("", None), "count(1)")

    def test_sum_mean_min_max_quote_the_field(self):
        self.assertEqual(build_aggregate("sum", "pop"), 'sum("pop")')
        self.assertEqual(build_aggregate("mean", "area"), 'mean("area")')
        self.assertEqual(build_aggregate("min", "h"), 'min("h")')
        self.assertEqual(build_aggregate("max", "h"), 'max("h")')

    def test_average_is_alias_for_mean(self):
        self.assertEqual(build_aggregate("average", "area"), 'mean("area")')

    def test_missing_field_for_field_statistic_returns_none(self):
        self.assertIsNone(build_aggregate("sum", ""))
        self.assertIsNone(build_aggregate("mean", None))

    def test_unknown_statistic_returns_none(self):
        self.assertIsNone(build_aggregate("median", "x"))


class ParseAggregateTest(unittest.TestCase):
    def test_count(self):
        self.assertEqual(parse_aggregate("count(1)"), ("count", None))
        self.assertEqual(parse_aggregate("COUNT( 1 )"), ("count", None))

    def test_field_aggregates(self):
        self.assertEqual(parse_aggregate('sum("pop")'), ("sum", "pop"))
        self.assertEqual(parse_aggregate(
            '  mean("area ha")  '), ("mean", "area ha"))

    def test_non_aggregate_is_none(self):
        self.assertIsNone(parse_aggregate('sum("a") + 1'))
        self.assertIsNone(parse_aggregate("$area"))
        self.assertIsNone(parse_aggregate(""))
        self.assertIsNone(parse_aggregate(None))

    def test_round_trip(self):
        for stat, fld in [("sum", "pop"), ("mean", "area"),
                          ("min", "h"), ("max", "h")]:
            self.assertEqual(
                parse_aggregate(
                    build_aggregate(
                        stat, fld)), (stat, fld))
        self.assertEqual(
            parse_aggregate(
                build_aggregate(
                    "count", None)), ("count", None))

    def test_statistics_constant(self):
        self.assertEqual(STATISTICS[0], "count")
        self.assertIn("sum", STATISTICS)


if __name__ == "__main__":
    unittest.main()
