# -*- coding: utf-8 -*-
"""Tests for CAD text rendering.

The TEXT command stored ``aq_text`` on a point feature and nothing ever drew
it: the point table's renderer was a cross marker and the layer had no
labelling at all, so placing text produced a tiny cross and no string. These
pin the labelling that turns those anchors back into visible text, and the
end-to-end render actually putting ink on the canvas.

Note the care taken to keep ``settings`` alive: ``dataDefinedProperties()``
returns a reference *into* it, so reading it off a temporary is a use after
free rather than a test failure.

Needs QGIS on the path. From the plugin directory::

    python test/test_text_style.py
"""

import os
import sys
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))

from qgis.PyQt.QtCore import QSize                          # noqa: E402
from qgis.PyQt.QtGui import QColor                          # noqa: E402
from qgis.core import (                                     # noqa: E402
    QgsApplication, QgsCoordinateReferenceSystem, QgsExpression,
    QgsExpressionContext, QgsExpressionContextUtils, QgsFeature, QgsGeometry,
    QgsMapRendererSequentialJob, QgsMapSettings, QgsPointXY, QgsRectangle,
    QgsVectorLayer,
)

from autoqad.core.compat import RENDER_MAP_UNITS            # noqa: E402
from autoqad.core.document import POINTS, _table_fields     # noqa: E402
from autoqad.style import symbology                         # noqa: E402

_APP = QgsApplication([], False)
_APP.initQgis()


def _point_layer():
    layer = QgsVectorLayer("Point?crs=EPSG:3857", "aq_points", "memory")
    layer.dataProvider().addAttributes(_table_fields(POINTS))
    layer.updateFields()
    return layer


def _add(layer, x, y, entity_type, text=None, height=2.5, rotation=0.0):
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
    feature["aq_type"] = entity_type
    feature["aq_layer"] = "0"
    feature["aq_rgb"] = "#ffffff"
    feature["aq_text"] = text
    feature["aq_height"] = height
    feature["aq_rot"] = rotation
    layer.dataProvider().addFeatures([feature])
    return feature


class TestTextLabeling(unittest.TestCase):

    def setUp(self):
        self.labeling = symbology.build_text_labeling(2.5)
        self.settings = self.labeling.settings()

    def test_labelling_is_available(self):
        self.assertIsNotNone(self.labeling)

    def test_it_labels_the_text_field(self):
        self.assertEqual(self.settings.fieldName, symbology.FIELD_TEXT)
        self.assertFalse(self.settings.isExpression)

    def test_text_height_is_in_map_units(self):
        # CAD text is a height in drawing units, not a cartographic point
        # size: it stays the same size relative to the drawing at every zoom.
        text_format = self.settings.format()
        self.assertEqual(text_format.sizeUnit(), RENDER_MAP_UNITS)

    def test_height_rotation_and_colour_come_from_the_feature(self):
        properties = self.settings.dataDefinedProperties()
        bound = set()
        for key in properties.propertyKeys():
            field = properties.property(key).field()
            if field:
                bound.add(field)
        self.assertEqual(
            bound, {symbology.FIELD_HEIGHT, symbology.FIELD_ROTATION,
                    symbology.FIELD_RGB})

    def test_empty_text_is_not_labelled(self):
        properties = self.settings.dataDefinedProperties()
        expressions = [properties.property(key).expressionString()
                       for key in properties.propertyKeys()]
        self.assertTrue(any(symbology.FIELD_TEXT in (e or "")
                            for e in expressions))

    def test_overlapping_labels_are_never_dropped(self):
        # A CAD drawing is not a map: text is an entity, so it draws even when
        # two strings collide.
        self.assertTrue(self.settings.displayAll)


class TestPointRenderer(unittest.TestCase):
    """The node cross must not sit under every string."""

    def setUp(self):
        self.renderer = symbology.build_point_renderer()
        self.layer = _point_layer()

    def _matching_rules(self, entity_type):
        _add(self.layer, 0.0, 0.0, entity_type, text="HELLO")
        feature = next(self.layer.getFeatures())
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.layerScope(self.layer))
        context.setFeature(feature)

        matched = []
        for rule in self.renderer.rootRule().children():
            expression = QgsExpression(rule.filterExpression())
            if bool(expression.evaluate(context)):
                matched.append(rule.label())
        return matched

    def test_a_plain_point_gets_the_node_cross(self):
        self.assertEqual(self._matching_rules("POINT"), ["Nodes"])

    def test_a_text_anchor_gets_no_cross(self):
        self.assertEqual(self._matching_rules("TEXT"), ["Text anchors"])


class TestTextActuallyRenders(unittest.TestCase):
    """The end-to-end check: ink lands where the string was placed."""

    def _render(self, entity_type, text):
        layer = _point_layer()
        layer.setRenderer(symbology.build_point_renderer())
        labeling = symbology.build_text_labeling(2.5)
        layer.setLabeling(labeling)
        layer.setLabelsEnabled(True)
        _add(layer, 0.0, 0.0, entity_type, text=text, height=6.0)

        settings = QgsMapSettings()
        settings.setLayers([layer])
        settings.setDestinationCrs(QgsCoordinateReferenceSystem("EPSG:3857"))
        settings.setExtent(QgsRectangle(-20, -20, 20, 20))
        settings.setOutputSize(QSize(400, 400))
        settings.setBackgroundColor(QColor("#000000"))

        job = QgsMapRendererSequentialJob(settings)
        job.start()
        job.waitForFinished()
        image = job.renderedImage()

        black = QColor("#000000").rgb()
        return sum(1 for y in range(0, image.height(), 2)
                   for x in range(0, image.width(), 2)
                   if QColor(image.pixel(x, y)).rgb() != black)

    def test_a_text_entity_paints_something(self):
        self.assertGreater(self._render("TEXT", "HELLO"), 0,
                           "a TEXT entity rendered as nothing at all")

    def test_a_text_entity_with_no_string_paints_nothing(self):
        self.assertEqual(self._render("TEXT", None), 0)


if __name__ == "__main__":
    unittest.main()
