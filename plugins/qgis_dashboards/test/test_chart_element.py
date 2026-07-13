# coding=utf-8
"""Tests for ChartElement click interaction (selection feedback)."""

__author__ = 'isaacenagework@gmail.com'
__date__ = '2026-06-22'
__copyright__ = 'Copyright 2026, Isaac Enage'

import unittest

from utilities import get_qgis_app

from bus import DashboardBus
from elements import create_element
from elements.chart import ChartElement

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


class ChartSelectionFeedbackTest(unittest.TestCase):
    """Clicking a bar highlights it immediately, independent of the cross-filter
    fan-out — a source-only chart is not its own filter target, so its
    ``filtersChanged`` is a no-op for it; the selection must still repaint."""

    def _layer(self):
        from qgis.core import QgsVectorLayer, QgsFeature, QgsProject
        lyr = QgsVectorLayer(
            "None?field=category:string&field=value:double", "chart", "memory")
        feats = []
        for cat, val in [("East", 10), ("East", 20), ("West", 7), ("West", 3)]:
            ft = QgsFeature(lyr.fields())
            ft.setAttributes([cat, float(val)])
            feats.append(ft)
        lyr.dataProvider().addFeatures(feats)
        lyr.updateExtents()
        QgsProject.instance().addMapLayer(lyr)
        return lyr

    def _chart(self, bus):
        lyr = self._layer()
        return create_element("chart", bus, {
            "chart_type": "bar", "category_field": "category",
            "statistic": "count", "layer_id": lyr.id()}, PARENT)

    def test_click_highlights_bar_immediately(self):
        bus = DashboardBus(IFACE)
        el = self._chart(bus)
        self.assertIsInstance(el, ChartElement)

        el._on_category("East")
        # the selection is reflected on the painter at once, with no dependence
        # on a filtersChanged-driven refresh round-trip
        self.assertEqual(el._selected, "East")
        self.assertEqual(el.view._selected, "East")
        # and the chart pushed its filter onto the bus as a source
        self.assertIsNotNone(bus._source_filters.get(el.id))

    def test_clicking_same_bar_toggles_selection_off(self):
        bus = DashboardBus(IFACE)
        el = self._chart(bus)
        el._on_category("East")
        el._on_category("East")                 # second click clears
        self.assertIsNone(el._selected)
        self.assertIsNone(el.view._selected)
        self.assertIsNone(bus._source_filters.get(el.id))

    def test_selection_survives_without_being_a_filter_target(self):
        # No source is wired into the chart, so the filtersChanged it emits does
        # not refresh it (change-detection skips it). The highlight must
        # persist.
        bus = DashboardBus(IFACE)
        el = self._chart(bus)
        el._on_category("West")
        bus.filtersChanged.emit()               # unrelated broadcast
        self.assertEqual(el.view._selected, "West")


if __name__ == "__main__":
    unittest.main()
