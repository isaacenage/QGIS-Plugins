# -*- coding: utf-8 -*-
"""Unit tests for history (pure, no QGIS).

Run directly so the test package __init__ (which imports qgis) is not loaded:
    PYTHONPATH=$(pwd) python test/test_history.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from history import History  # noqa: E402


def _snap(n):
    """A small distinct layout-like snapshot keyed by *n*."""
    return {"version": 3, "pages": [{"id": "p", "elements": [{"v": n}]}]}


class TestHistory(unittest.TestCase):
    def test_empty_has_no_undo_or_redo(self):
        h = History()
        self.assertFalse(h.can_undo())
        self.assertFalse(h.can_redo())
        self.assertIsNone(h.undo())
        self.assertIsNone(h.redo())

    def test_seeded_current_is_not_undoable(self):
        # the seed is the live state; there is nothing earlier to undo to
        h = History(_snap(0))
        self.assertFalse(h.can_undo())
        self.assertEqual(h.current, _snap(0))

    def test_record_enables_undo(self):
        h = History(_snap(0))
        self.assertTrue(h.record(_snap(1)))
        self.assertTrue(h.can_undo())
        self.assertFalse(h.can_redo())

    def test_identical_record_is_noop(self):
        h = History(_snap(0))
        self.assertFalse(h.record(_snap(0)))
        self.assertFalse(h.can_undo())

    def test_record_dedups_after_normalization(self):
        # key order must not matter — JSON-normalized equality
        h = History({"a": 1, "b": 2})
        self.assertFalse(h.record({"b": 2, "a": 1}))

    def test_undo_redo_roundtrip(self):
        h = History(_snap(0))
        h.record(_snap(1))
        h.record(_snap(2))
        self.assertEqual(h.undo(), _snap(1))
        self.assertEqual(h.undo(), _snap(0))
        self.assertIsNone(h.undo())
        self.assertEqual(h.redo(), _snap(1))
        self.assertEqual(h.redo(), _snap(2))
        self.assertIsNone(h.redo())

    def test_record_after_undo_clears_redo(self):
        h = History(_snap(0))
        h.record(_snap(1))
        h.undo()                       # back to snap(0), redo holds snap(1)
        self.assertTrue(h.can_redo())
        h.record(_snap(9))             # a new branch wipes the redo future
        self.assertFalse(h.can_redo())
        self.assertEqual(h.current, _snap(9))
        self.assertEqual(h.undo(), _snap(0))

    def test_depth_cap_drops_oldest(self):
        h = History(_snap(0), max_depth=3)
        for n in range(1, 6):          # record snaps 1..5
            h.record(_snap(n))
        self.assertEqual(len(h), 3)    # only 3 undo steps retained
        self.assertEqual(h.undo(), _snap(4))
        self.assertEqual(h.undo(), _snap(3))
        self.assertEqual(h.undo(), _snap(2))
        self.assertIsNone(h.undo())    # snaps 0 and 1 fell off the bottom

    def test_snapshots_are_isolated_copies(self):
        src = _snap(0)
        h = History(src)
        src["pages"][0]["elements"][0]["v"] = 999   # mutate the caller's dict
        self.assertEqual(h.current, _snap(0))        # history is unaffected
        out = h.current
        out["pages"] = []                            # mutate the returned copy
        self.assertEqual(h.current, _snap(0))        # internal state intact


if __name__ == "__main__":
    unittest.main()
