# -*- coding: utf-8 -*-
"""Tests for enumerating, clearing and discarding a drawing.

Two user-visible problems live here.

``ALL`` at a Select-objects prompt needs a way to name every entity, which is
what :meth:`DrawingDocument.all_entities` provides — without it the plugin
could add objects but never remove them in bulk.

And removing the tables from the layer tree used to be undoable by design:
``ensure_open`` reattaches to the GeoPackage, so everything reappeared on the
next toggle with no way to say "no, I meant it". :meth:`DrawingDocument.discard`
is that way, and these tests check it takes the storage *and* the project's
record of it with it.

Needs QGIS on the path. From the plugin directory::

    python test/test_document_storage.py
"""

import gc
import os
import shutil
import sys
import tempfile
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))

from qgis.core import (                                     # noqa: E402
    QgsApplication, QgsCoordinateReferenceSystem, QgsProject,
)

from autoqad.core.document import LINES, POINTS, TABLES    # noqa: E402
from autoqad.core.document import DrawingDocument           # noqa: E402
from autoqad.core.variables import VariableStore            # noqa: E402
from autoqad.geom import build                              # noqa: E402

_APP = QgsApplication([], False)
_APP.initQgis()

_CRS = QgsCoordinateReferenceSystem("EPSG:3857")


class _DocumentCase(unittest.TestCase):
    """A real document on a real GeoPackage in a throwaway directory."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="autoqad-test-")
        self.project = QgsProject()
        self.project.setFileName(os.path.join(self.directory, "drawing.qgz"))
        self.variables = VariableStore()
        self.document = DrawingDocument(self.variables, self.project)
        self.assertTrue(self.document.create(_CRS), "could not create tables")

    def tearDown(self):
        try:
            self.document.close()
        except RuntimeError:
            pass
        self.project.clear()
        # Let QGIS drop its file handles before the directory goes: on
        # Windows an open GeoPackage cannot be deleted, and a half-removed
        # one poisons the next test's provider.
        self.document = None
        self.project = None
        gc.collect()
        shutil.rmtree(self.directory, ignore_errors=True)

    def _draw(self, count=3):
        for index in range(count):
            self.document.add_curve(
                build.line((0.0, float(index)), (10.0, float(index))), "LINE")


class TestAllEntities(_DocumentCase):

    def test_an_empty_drawing_names_nothing(self):
        self.assertEqual(self.document.all_entities(), [])

    def test_every_curve_is_named_with_its_table(self):
        self._draw(3)
        selection = self.document.all_entities()
        self.assertEqual(len(selection), 3)
        self.assertEqual({name for name, _fid in selection}, {LINES})

    def test_entities_span_every_table(self):
        self._draw(1)
        self.document.add_point(build.point((1.0, 1.0)), "POINT")
        tables = {name for name, _fid in self.document.all_entities()}
        self.assertEqual(tables, {LINES, POINTS})

    def test_the_ids_are_the_ones_the_tables_hand_out(self):
        self._draw(2)
        real = {feature.id()
                for feature in self.document.table(LINES).getFeatures()}
        named = {fid for _name, fid in self.document.all_entities()}
        self.assertEqual(named, real)


class TestClear(_DocumentCase):
    """ERASE ALL has to actually empty the drawing."""

    def test_it_removes_every_entity(self):
        self._draw(4)
        self.document.add_point(build.point((1.0, 1.0)), "POINT")
        self.assertEqual(self.document.clear(), 5)
        self.assertEqual(self.document.count(), 0)

    def test_the_tables_survive(self):
        self._draw(2)
        self.document.clear()
        self.assertTrue(self.document.is_open)
        self.assertEqual(len(self.document.all_tables()), len(TABLES))

    def test_clearing_an_empty_drawing_is_a_noop(self):
        self.assertEqual(self.document.clear(), 0)


class TestDiscard(_DocumentCase):
    """Removing the layers must be able to actually mean it."""

    def test_keeping_the_storage_leaves_the_file_behind(self):
        self._draw(1)
        self.document.commit()
        path = self.document.storage_path()
        ok, _message = self.document.discard(delete_storage=False)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(path))

    def test_deleting_the_storage_removes_the_file(self):
        self._draw(1)
        self.document.commit()
        path = self.document.storage_path()
        self.assertTrue(os.path.exists(path))

        ok, _message = self.document.discard(delete_storage=True)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(path))

    def test_a_discarded_drawing_does_not_reopen_itself(self):
        # The bug: delete the layers, toggle the plugin, and every object is
        # back because ensure_open reattached to the GeoPackage.
        self._draw(2)
        self.document.commit()
        self.document.discard(delete_storage=True)

        self.assertTrue(self.document.ensure_open(_CRS))
        self.assertEqual(self.document.count(), 0)

    def test_a_kept_drawing_does_reopen_itself(self):
        # The safety net stays: this is the mis-click case.
        self._draw(2)
        self.document.commit()
        self.document.discard(delete_storage=False)

        self.assertTrue(self.document.ensure_open(_CRS))
        self.assertEqual(self.document.count(), 2)

    def test_the_project_forgets_the_drawing(self):
        self._draw(1)
        self.document.commit()
        self.document.discard(delete_storage=True)

        stored, ok = self.project.readEntry("AutoQAD", "gpkg", "")
        self.assertFalse(ok and stored)

    def test_discarding_twice_is_harmless(self):
        self._draw(1)
        self.document.commit()
        self.document.discard(delete_storage=True)
        ok, _message = self.document.discard(delete_storage=True)
        self.assertTrue(ok)


class TestLegacyTableNames(_DocumentCase):
    """A drawing written before ``aq_curves`` became ``aq_lines`` must open.

    Renaming the table without this would not lose the data, but it would look
    exactly as though it had: reload finds no ``aq_lines``, falls through to
    create, and writes empty tables alongside the drawing the user still has.
    """

    def _make_legacy(self, entities=3):
        """Return the path to a drawing whose line table uses the old name."""
        self._draw(entities)
        self.document.commit()
        path = self.document.storage_path()
        self.document.close()
        self.project.clear()
        gc.collect()          # Windows will not rename a table GDAL still holds

        from osgeo import ogr
        ogr.UseExceptions()               # GDAL 4's default; silences the warning
        source = ogr.Open(path, 1)
        self.assertIsNotNone(source, "could not reopen the GeoPackage")
        source.ExecuteSQL('ALTER TABLE "{0}" RENAME TO "aq_curves"'.format(LINES))
        source = None
        gc.collect()
        return path

    def _fresh_document(self, path):
        project = QgsProject()
        project.setFileName(os.path.join(self.directory, "drawing.qgz"))
        document = DrawingDocument(self.variables, project)
        document._gpkg_path = path
        return document, project

    def test_the_legacy_table_is_actually_there(self):
        # Guards the test itself: if the rename silently failed, everything
        # below would pass for the wrong reason.
        path = self._make_legacy()
        from osgeo import ogr
        ogr.UseExceptions()
        source = ogr.Open(path, 0)
        names = {source.GetLayerByIndex(i).GetName()
                 for i in range(source.GetLayerCount())}
        source = None
        self.assertIn("aq_curves", names)
        self.assertNotIn(LINES, names)

    def test_reloading_finds_the_legacy_table(self):
        path = self._make_legacy(3)
        document, _project = self._fresh_document(path)
        try:
            self.assertTrue(document._reload_from_geopackage())
            self.assertTrue(document.is_open)
        finally:
            document.close()

    def test_the_entities_come_back(self):
        path = self._make_legacy(3)
        document, _project = self._fresh_document(path)
        try:
            document._reload_from_geopackage()
            self.assertEqual(document.count(), 3)
            named = {name for name, _fid in document.all_entities()}
            self.assertEqual(named, {LINES})
        finally:
            document.close()

    def test_the_layer_takes_the_current_name(self):
        path = self._make_legacy(1)
        document, _project = self._fresh_document(path)
        try:
            document._reload_from_geopackage()
            self.assertEqual(document.table(LINES).name(), LINES)
        finally:
            document.close()

    def test_drawing_into_a_migrated_table_still_works(self):
        path = self._make_legacy(1)
        document, _project = self._fresh_document(path)
        try:
            document._reload_from_geopackage()
            self.assertIsNotNone(document.add_curve(
                build.line((0.0, 0.0), (1.0, 1.0)), "LINE"))
            self.assertEqual(document.count(), 2)
        finally:
            document.close()

    def test_a_legacy_layer_already_in_the_project_is_adopted(self):
        # The .qgz path: the layers are loaded under their old names and must
        # be recognised rather than duplicated.
        path = self._make_legacy(2)
        document, project = self._fresh_document(path)
        try:
            document._reload_from_geopackage()
            for layer in document.all_tables():
                layer.setCustomProperty("autoqad/table", "aq_curves"
                                        if layer.name() == LINES else layer.name())
            adopting = DrawingDocument(self.variables, project)
            self.assertTrue(adopting._adopt_project_layers())
            self.assertEqual(adopting.count(), 2)
            self.assertEqual(adopting.table(LINES).name(), LINES)
        finally:
            document.close()


class TestCommit(_DocumentCase):
    """Edits live in the buffer so undo works; commit is the flush."""

    def test_edits_made_in_an_edit_session_survive_a_commit(self):
        for table in self.document.all_tables():
            table.startEditing()
        self._draw(2)
        self.assertTrue(self.document.commit())

        # Re-read straight from disk, bypassing every wrapper we hold.
        reread = DrawingDocument(self.variables, QgsProject())
        reread._gpkg_path = self.document.storage_path()
        self.assertTrue(reread._reload_from_geopackage())
        self.assertEqual(reread.count(), 2)
        reread.close()

    def test_committing_leaves_the_session_open_for_the_next_command(self):
        for table in self.document.all_tables():
            table.startEditing()
        self._draw(1)
        self.document.commit()
        self.assertTrue(
            all(table.isEditable() for table in self.document.all_tables()))

    def test_committing_a_closed_document_is_harmless(self):
        self.document.close()
        self.assertTrue(self.document.commit())


if __name__ == "__main__":
    unittest.main()
