# -*- coding: utf-8 -*-
"""Tests for HATCH boundary detection.

HATCH failed on every invocation with::

    HATCH failed: QgsGeometry.polygonize(): not enough arguments

``QgsGeometry.polygonize`` is a **static** method taking the linework as a
list, so calling it on the unioned geometry (``noded.polygonize()``) raises
``TypeError`` — and the ``except (AttributeError, RuntimeError)`` around it did
not catch that, so the exception aborted the command rather than degrading to
"no boundary found". These pin the working call.

The second failure was quieter and would have survived the first fix:
polygonising returns a *geometry collection*, while ``aq_polygons`` is a
single-part ``Polygon`` table whose provider rejects a collection outright
(``addFeatures`` returns False and stores nothing). Faces are therefore split
into single-part polygons and stored one hatch per face.

Needs QGIS on the path. From the plugin directory::

    python test/test_hatch_boundary.py
"""

import os
import sys
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))

from qgis.core import (                                     # noqa: E402
    QgsApplication, QgsCircle, QgsFeature, QgsGeometry, QgsPoint, QgsPointXY,
    QgsVectorLayer,
)

from autoqad.commands.hatch import (                        # noqa: E402
    HatchCommand, as_linework, polygon_parts, rings_as_polygons,
)
from autoqad.core.compat import GEOM_LINE, GEOM_POLYGON     # noqa: E402

_APP = QgsApplication([], False)
_APP.initQgis()


def _line(start, end):
    return QgsGeometry.fromPolylineXY([QgsPointXY(*start), QgsPointXY(*end)])


def _square(size=10.0):
    """A closed box drawn as four separate LINE entities, as LINE leaves it."""
    return [
        _line((0, 0), (size, 0)),
        _line((size, 0), (size, size)),
        _line((size, size), (0, size)),
        _line((0, size), (0, 0)),
    ]


def _polygonise(geometries, point):
    return HatchCommand._polygonise(geometries, point)


class TestPolygonise(unittest.TestCase):
    """The boundary finder, driven exactly as the two HATCH paths drive it."""

    def test_four_separate_lines_enclose_one_face(self):
        found = _polygonise(_square(), (5.0, 5.0))
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0].area(), 100.0, places=6)

    def test_the_face_is_a_single_part_polygon(self):
        # A collection or multipolygon is silently dropped by the polygon
        # table's provider, so this is the difference between a hatch and
        # nothing at all.
        found = _polygonise(_square(), (5.0, 5.0))
        self.assertFalse(found[0].isMultipart())
        self.assertEqual(found[0].type(), GEOM_POLYGON)

    def test_a_pick_outside_every_face_finds_nothing(self):
        self.assertEqual(_polygonise(_square(), (50.0, 50.0)), [])

    def test_crossing_lines_are_noded_before_faces_are_built(self):
        # A dividing wall overshooting both ends: without noding there is one
        # face, with it there are two.
        walls = _square() + [_line((4, -2), (4, 12))]
        self.assertEqual(len(_polygonise(walls, None)), 2)

    def test_the_pick_takes_the_smallest_containing_face(self):
        # The room, not the building.
        walls = _square() + [_line((4, -2), (4, 12))]
        found = _polygonise(walls, (7.0, 5.0))
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0].area(), 60.0, places=6)

    def test_no_point_returns_every_face(self):
        walls = _square() + [_line((4, -2), (4, 12))]
        areas = sorted(round(face.area(), 6) for face in _polygonise(walls, None))
        self.assertEqual(areas, [40.0, 60.0])

    def test_a_single_closed_ring_still_yields_its_face(self):
        # CIRCLE and RECTANGLE store one closed entity, not four lines.
        circle = QgsGeometry(QgsCircle(QgsPoint(0, 0), 5.0).toCircularString())
        segmentised = QgsGeometry(circle.constGet().segmentize())
        found = _polygonise([segmentised], (0.0, 0.0))
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0].area(), 78.5, places=1)

    def test_open_linework_encloses_nothing(self):
        gap = _square()[:-1]          # three sides of the box
        self.assertEqual(_polygonise(gap, (5.0, 5.0)), [])

    def test_no_candidates_is_not_an_error(self):
        self.assertEqual(_polygonise([], (0.0, 0.0)), [])
        self.assertEqual(_polygonise([], None), [])

    def test_empty_and_null_geometries_are_ignored(self):
        noise = [QgsGeometry(), None] + _square()
        self.assertEqual(len(_polygonise(noise, (5.0, 5.0))), 1)


class TestPolygonParts(unittest.TestCase):
    """Flattening whatever GEOS hands back into storable polygons."""

    def test_a_collection_is_split_into_its_polygons(self):
        collection = QgsGeometry.fromWkt(
            "GEOMETRYCOLLECTION(POLYGON((0 0,1 0,1 1,0 1,0 0)),"
            "POLYGON((2 2,4 2,4 4,2 4,2 2)))")
        parts = polygon_parts(collection)
        self.assertEqual(len(parts), 2)
        self.assertFalse(any(part.isMultipart() for part in parts))
        self.assertEqual(sorted(round(p.area(), 6) for p in parts), [1.0, 4.0])

    def test_a_multipolygon_is_split_too(self):
        multi = QgsGeometry.fromWkt(
            "MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)),((2 2,3 2,3 3,2 3,2 2)))")
        self.assertEqual(len(polygon_parts(multi)), 2)

    def test_a_lone_polygon_passes_through(self):
        single = QgsGeometry.fromWkt("POLYGON((0 0,1 0,1 1,0 1,0 0))")
        self.assertEqual(len(polygon_parts(single)), 1)

    def test_non_polygons_are_discarded(self):
        mixed = QgsGeometry.fromWkt(
            "GEOMETRYCOLLECTION(POINT(0 0),LINESTRING(0 0,1 1),"
            "POLYGON((0 0,1 0,1 1,0 1,0 0)))")
        self.assertEqual(len(polygon_parts(mixed)), 1)

    def test_nothing_in_nothing_out(self):
        self.assertEqual(polygon_parts(None), [])
        self.assertEqual(polygon_parts(QgsGeometry()), [])


class TestStorability(unittest.TestCase):
    """What the polygon table will actually accept."""

    @staticmethod
    def _layer():
        return QgsVectorLayer("Polygon?crs=EPSG:3857", "aq_polygons", "memory")

    def _store(self, geometry):
        layer = self._layer()
        feature = QgsFeature(layer.fields())
        feature.setGeometry(geometry)
        ok, _added = layer.dataProvider().addFeatures([feature])
        return ok, layer.featureCount()

    def test_a_collection_is_rejected_by_the_polygon_table(self):
        # The reason polygonised faces cannot be stored as they come back.
        collection = QgsGeometry.fromWkt(
            "GEOMETRYCOLLECTION(POLYGON((0 0,1 0,1 1,0 1,0 0)),"
            "POLYGON((2 2,3 2,3 3,2 3,2 2)))")
        ok, count = self._store(collection)
        self.assertFalse(ok)
        self.assertEqual(count, 0)

    def test_every_face_the_finder_returns_is_storable(self):
        walls = _square() + [_line((4, -2), (4, 12))]
        faces = _polygonise(walls, None)
        self.assertEqual(len(faces), 2)
        for face in faces:
            ok, count = self._store(face)
            self.assertTrue(ok)
            self.assertEqual(count, 1)


class TestRingsAsPolygons(unittest.TestCase):
    """The fallback for linework GEOS declines to polygonise."""

    def test_a_closed_ring_becomes_a_polygon(self):
        ring = QgsGeometry.fromPolylineXY([
            QgsPointXY(0, 0), QgsPointXY(4, 0), QgsPointXY(4, 4),
            QgsPointXY(0, 4), QgsPointXY(0, 0)])
        polygons = rings_as_polygons([ring])
        self.assertEqual(len(polygons), 1)
        self.assertAlmostEqual(polygons[0].area(), 16.0, places=6)

    def test_an_open_run_is_not_a_ring(self):
        run = QgsGeometry.fromPolylineXY([
            QgsPointXY(0, 0), QgsPointXY(4, 0), QgsPointXY(4, 4)])
        self.assertEqual(rings_as_polygons([run]), [])


class TestAsLinework(unittest.TestCase):
    """Selecting an existing fill as a boundary object has to contribute lines."""

    def test_a_polygon_contributes_its_boundary(self):
        polygon = QgsGeometry.fromWkt("POLYGON((0 0,4 0,4 4,0 4,0 0))")
        converted = as_linework(polygon)
        self.assertEqual(converted.type(), GEOM_LINE)
        self.assertAlmostEqual(converted.length(), 16.0, places=6)

    def test_a_selected_fill_can_be_rehatched(self):
        polygon = QgsGeometry.fromWkt("POLYGON((0 0,4 0,4 4,0 4,0 0))")
        found = _polygonise([as_linework(polygon)], (2.0, 2.0))
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0].area(), 16.0, places=6)

    def test_lines_are_left_alone(self):
        line = _line((0, 0), (1, 1))
        self.assertEqual(as_linework(line).asWkt(), line.asWkt())

    def test_nothing_in_nothing_out(self):
        self.assertIsNone(as_linework(None))
        self.assertTrue(as_linework(QgsGeometry()).isEmpty())


if __name__ == "__main__":
    unittest.main()
