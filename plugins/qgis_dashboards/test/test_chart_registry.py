# coding=utf-8
"""Tests for the chart-type registry and the generic ChartElement."""

__author__ = 'isaacenagework@gmail.com'
__date__ = '2026-06-15'
__copyright__ = 'Copyright 2026, Isaac Enage'

import unittest

from utilities import get_qgis_app

from bus import DashboardBus
from elements import create_element, ELEMENT_TYPES, ELEMENT_LABELS
from elements.chart import ChartElement
from elements.chart_specs import (
    CHART_SPECS, CHART_TYPE_ORDER, fold_categories, filter_literal,
)
from elements.charts.painters import PAINTERS

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


class ChartSpecsTest(unittest.TestCase):
    def test_expected_six_types(self):
        self.assertEqual(set(CHART_SPECS),
                         {"bar", "barh", "line", "area", "pie", "donut"})
        self.assertEqual(set(CHART_TYPE_ORDER), set(CHART_SPECS))

    def test_every_spec_painter_is_registered(self):
        for ctype, spec in CHART_SPECS.items():
            self.assertIn(spec["painter"], PAINTERS,
                          "missing painter for {}".format(ctype))

    def test_filter_literal_quotes_strings_not_numbers(self):
        self.assertEqual(filter_literal("region", "North"),
                         '"region" = \'North\'')
        self.assertEqual(filter_literal("year", "2020"), '"year" = 2020')

    def test_fold_categories_truncates_without_other(self):
        items = [("a", 5), ("b", 4), ("c", 3), ("d", 2)]
        self.assertEqual(fold_categories(items, 2, fold_other=False),
                         [("a", 5), ("b", 4)])

    def test_fold_categories_sums_tail_into_other(self):
        items = [("a", 5), ("b", 4), ("c", 3), ("d", 2)]
        folded = fold_categories(items, 2, fold_other=True)
        self.assertEqual(folded, [("a", 5), ("b", 4), ("Other", 5.0)])

    def test_fold_categories_noop_when_within_cap(self):
        items = [("a", 5), ("b", 4)]
        self.assertEqual(fold_categories(items, 5, fold_other=True), items)


class ChartElementTest(unittest.TestCase):
    def test_chart_is_registered_type(self):
        self.assertIn("chart", ELEMENT_TYPES)
        self.assertEqual(set(ELEMENT_TYPES), set(ELEMENT_LABELS))
        self.assertNotIn("serial_chart", ELEMENT_TYPES)
        self.assertNotIn("pie_chart", ELEMENT_TYPES)

    def test_create_each_chart_type_builds_right_painter(self):
        bus = DashboardBus(IFACE)
        for ctype in CHART_TYPE_ORDER:
            el = create_element("chart", bus, {"chart_type": ctype}, PARENT)
            self.assertIsInstance(el, ChartElement)
            self.assertEqual(el.type_name, "chart")
            expected = PAINTERS[CHART_SPECS[ctype]["painter"]]
            self.assertIsInstance(el.view, expected)

    def test_default_chart_type_is_bar(self):
        bus = DashboardBus(IFACE)
        el = create_element("chart", bus, {}, PARENT)
        self.assertEqual(el._chart_type(), "bar")

    def test_donut_inner_radius_applied(self):
        bus = DashboardBus(IFACE)
        el = create_element("chart", bus, {"chart_type": "donut"}, PARENT)
        self.assertGreater(el._spec()["inner"], 0.0)


class LegacyMigrationTest(unittest.TestCase):
    def test_serial_chart_migrates_to_bar(self):
        bus = DashboardBus(IFACE)
        el = create_element(
            "serial_chart", bus, {
                "category_field": "x", "statistic": "sum"}, PARENT)
        self.assertEqual(el.type_name, "chart")
        self.assertEqual(el._chart_type(), "bar")
        self.assertEqual(el.to_dict()["__type__"], "chart")

    def test_pie_chart_migrates_to_pie(self):
        bus = DashboardBus(IFACE)
        el = create_element("pie_chart", bus, {"category_field": "x"}, PARENT)
        self.assertEqual(el._chart_type(), "pie")

    def test_pie_with_inner_radius_migrates_to_donut(self):
        bus = DashboardBus(IFACE)
        el = create_element("pie_chart", bus,
                            {"inner_radius": 0.5, "max_slices": 5}, PARENT)
        self.assertEqual(el._chart_type(), "donut")
        self.assertEqual(el.config["max_categories"], 5)


if __name__ == "__main__":
    unittest.main()
