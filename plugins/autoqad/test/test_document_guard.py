# -*- coding: utf-8 -*-
"""Regression tests for deleted-layer handling.

Deleting AutoQAD's tables from the QGIS layer tree destroys the underlying C++
objects while our Python wrappers survive. Touching one then raises
``RuntimeError: wrapped C/C++ object of type QgsVectorLayer has been deleted``
— and because the pointer pipeline touches them 60 times a second, that
surfaced as a crash dialog on every mouse move.

These tests stub QGIS so the guard can be exercised without a runtime.
From the plugin directory::

    python test/test_document_guard.py
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock


class _FakeModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = MagicMock(name=name)
        setattr(self, name, value)
        return value


for _name in ("qgis", "qgis.core", "qgis.gui", "qgis.PyQt",
              "qgis.PyQt.QtCore", "qgis.PyQt.QtGui", "qgis.PyQt.QtWidgets",
              "qgis.PyQt.QtSvg"):
    sys.modules.setdefault(_name, _FakeModule(_name))

sys.modules["qgis.PyQt.QtCore"].pyqtSignal = lambda *a, **k: MagicMock()
sys.modules["qgis.PyQt.QtCore"].QObject = type(
    "QObject", (), {"__init__": lambda self, *a, **k: None})
sys.modules["qgis.core"].QgsFeature = type("QgsFeature", (), {})

# document.py uses package-relative imports (``from ..style import ...``), so
# it must be reached as ``autoqad.core.document`` — the plugins directory on
# the path, not the plugin directory.
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))

from autoqad.core.document import (                            # noqa: E402
    TABLES, DrawingDocument, is_alive,
)


class DeadLayer(object):
    """A wrapper whose C++ object has been destroyed."""

    def isValid(self):
        raise RuntimeError(
            "wrapped C/C++ object of type QgsVectorLayer has been deleted")

    def id(self):
        raise RuntimeError(
            "wrapped C/C++ object of type QgsVectorLayer has been deleted")


class LiveLayer(object):
    def __init__(self, layer_id="live"):
        self._id = layer_id

    def isValid(self):
        return True

    def id(self):
        return self._id


class InvalidLayer(object):
    """Alive, but not a valid layer — e.g. a broken data source."""

    def isValid(self):
        return False

    def id(self):
        return "invalid"


class TestIsAlive(unittest.TestCase):

    def test_live_layer(self):
        self.assertTrue(is_alive(LiveLayer()))

    def test_none(self):
        self.assertFalse(is_alive(None))

    def test_invalid_layer(self):
        self.assertFalse(is_alive(InvalidLayer()))

    def test_deleted_layer_does_not_raise(self):
        # The whole point: this must return False, not propagate RuntimeError.
        self.assertFalse(is_alive(DeadLayer()))


class TestDocumentPruning(unittest.TestCase):

    def _document(self, tables):
        document = DrawingDocument(MagicMock(), project=MagicMock())
        document._tables = dict(tables)
        return document

    def test_is_open_with_all_live(self):
        document = self._document({n: LiveLayer(n) for n in TABLES})
        self.assertTrue(document.is_open)

    def test_is_open_survives_a_deleted_layer(self):
        tables = {n: LiveLayer(n) for n in TABLES}
        tables[TABLES[0]] = DeadLayer()
        document = self._document(tables)
        # Must report closed rather than raise — this is the crash.
        self.assertFalse(document.is_open)

    def test_is_open_prunes_the_dead_reference(self):
        tables = {n: LiveLayer(n) for n in TABLES}
        tables[TABLES[1]] = DeadLayer()
        document = self._document(tables)
        document.is_open
        self.assertNotIn(TABLES[1], document._tables)
        self.assertIn(TABLES[0], document._tables)

    def test_table_returns_none_for_dead_layer(self):
        document = self._document({TABLES[0]: DeadLayer()})
        self.assertIsNone(document.table(TABLES[0]))

    def test_table_returns_live_layer(self):
        live = LiveLayer()
        document = self._document({TABLES[0]: live})
        self.assertIs(document.table(TABLES[0]), live)

    def test_all_tables_skips_dead(self):
        tables = {n: LiveLayer(n) for n in TABLES}
        tables[TABLES[2]] = DeadLayer()
        document = self._document(tables)
        alive = document.all_tables()
        self.assertEqual(len(alive), len(TABLES) - 1)

    def test_all_tables_never_raises_when_everything_is_dead(self):
        document = self._document({n: DeadLayer() for n in TABLES})
        self.assertEqual(document.all_tables(), [])
        self.assertFalse(document.is_open)

    def test_prune_dead_reports_whether_it_pruned(self):
        document = self._document({n: LiveLayer(n) for n in TABLES})
        self.assertFalse(document.prune_dead())
        document._tables[TABLES[0]] = DeadLayer()
        self.assertTrue(document.prune_dead())
        self.assertFalse(document.prune_dead())

    def test_on_layers_removed_drops_matching_ids(self):
        document = self._document({n: LiveLayer(n) for n in TABLES})
        document.on_layers_removed([TABLES[0]])
        self.assertNotIn(TABLES[0], document._tables)
        self.assertIn(TABLES[1], document._tables)

    def test_on_layers_removed_ignores_unrelated_ids(self):
        document = self._document({n: LiveLayer(n) for n in TABLES})
        document.on_layers_removed(["some-other-layer"])
        self.assertEqual(len(document._tables), len(TABLES))

    def test_on_layers_removed_handles_already_dead_wrappers(self):
        # The signal can arrive after the object is gone; id() then raises.
        document = self._document({TABLES[0]: DeadLayer()})
        document.on_layers_removed(["anything"])
        self.assertEqual(document._tables, {})

    def test_on_layers_removed_with_empty_list_is_a_noop(self):
        document = self._document({n: LiveLayer(n) for n in TABLES})
        document.on_layers_removed([])
        document.on_layers_removed(None)
        self.assertEqual(len(document._tables), len(TABLES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
