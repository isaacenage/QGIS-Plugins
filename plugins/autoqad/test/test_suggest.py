# -*- coding: utf-8 -*-
"""Tests for the as-you-type command suggestions.

This is the ranking behind the box that opens at the cursor: what ``PL``
offers, what ``POL`` offers, and what a typo still recovers. Pure — the widget
needs a canvas, the ranking does not, which is the whole reason it lives in the
registry.

Runs without QGIS. From the plugin directory::

    python test/test_suggest.py
"""

import os
import sys
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PLUGIN_DIR)                      # bare-name imports
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))     # package imports

from engine.registry import (                        # noqa: E402
    RANK_ALIAS_EXACT, RANK_CONTAINS, RANK_FUZZY, RANK_NAME_PREFIX,
    CommandRegistry,
)


class _Fake(object):
    aliases = ()
    group = "draw"
    description = ""
    modifies = True


def _command(name, aliases=(), description=""):
    return type("Cmd", (_Fake,), {
        "name": name, "aliases": tuple(aliases), "description": description})


def _registry(*entries):
    return CommandRegistry().register_all(
        [_command(*entry) if isinstance(entry, tuple) else _command(entry)
         for entry in entries])


#: A stand-in catalogue shaped like the real one — the cases that matter are
#: shared prefixes (POLYGON/POLYLINE) and aliases that collide with them (PL).
CATALOGUE = _registry(
    ("LINE", ("L",), "Draw straight line segments."),
    ("PLINE", ("PL",), "Draw a polyline."),
    ("POLYGON", ("POL",), "Draw a regular polygon."),
    ("MPOLYGON", (), "Draw a filled polygon."),
    ("POINT", ("PO",), "Place a point."),
    ("RECTANG", ("REC", "RECTANGLE"), "Draw a rectangle."),
    ("CIRCLE", ("C",), "Draw a circle."),
    ("ERASE", ("E", "DELETE"), "Delete selected objects."),
)


def _names(rows):
    return [row.name for row in rows]


class TestSuggest(unittest.TestCase):

    def test_nothing_typed_suggests_nothing(self):
        self.assertEqual(CATALOGUE.suggest(""), [])
        self.assertEqual(CATALOGUE.suggest("   "), [])

    def test_a_single_letter_lists_every_command_starting_with_it(self):
        names = _names(CATALOGUE.suggest("P"))
        for expected in ("PLINE", "POLYGON", "POINT"):
            self.assertIn(expected, names)

    def test_an_exact_alias_wins_outright(self):
        # Typing PL and meaning anything but PLINE is not a thing.
        rows = CATALOGUE.suggest("PL")
        self.assertEqual(rows[0].name, "PLINE")
        self.assertEqual(rows[0].rank, RANK_ALIAS_EXACT)

    def test_the_matching_alias_is_reported_so_it_can_be_shown(self):
        rows = CATALOGUE.suggest("PL")
        self.assertEqual(rows[0].hint, "PL")

    def test_pol_offers_every_polygon(self):
        # The user's case: a prefix that names one command and is contained in
        # another has to surface both.
        names = _names(CATALOGUE.suggest("POL"))
        self.assertIn("POLYGON", names)
        self.assertIn("MPOLYGON", names)

    def test_a_name_prefix_outranks_a_mere_containment(self):
        rows = {row.name: row.rank for row in CATALOGUE.suggest("POL")}
        self.assertEqual(rows["POLYGON"], RANK_ALIAS_EXACT)
        self.assertEqual(rows["MPOLYGON"], RANK_CONTAINS)

    def test_a_prefix_of_a_name_ranks_above_a_prefix_of_an_alias(self):
        rows = {row.name: row.rank for row in CATALOGUE.suggest("REC")}
        self.assertEqual(rows["RECTANG"], RANK_ALIAS_EXACT)

    def test_a_typo_still_finds_the_command(self):
        names = _names(CATALOGUE.suggest("CIRCEL"))
        self.assertIn("CIRCLE", names)
        rows = {row.name: row.rank for row in CATALOGUE.suggest("CIRCEL")}
        self.assertEqual(rows["CIRCLE"], RANK_FUZZY)

    def test_nonsense_matches_nothing(self):
        self.assertEqual(CATALOGUE.suggest("ZZZQQQ"), [])

    def test_results_are_capped(self):
        self.assertLessEqual(len(CATALOGUE.suggest("P", limit=2)), 2)

    def test_a_zero_limit_returns_everything_matching(self):
        self.assertGreater(len(CATALOGUE.suggest("P", limit=0)), 2)

    def test_matching_is_case_insensitive(self):
        self.assertEqual(_names(CATALOGUE.suggest("pl")),
                         _names(CATALOGUE.suggest("PL")))

    def test_descriptions_ride_along_for_the_tooltip(self):
        rows = CATALOGUE.suggest("LINE")
        self.assertEqual(rows[0].description, "Draw straight line segments.")

    def test_ranks_come_back_in_order(self):
        ranks = [row.rank for row in CATALOGUE.suggest("PO", limit=0)]
        self.assertEqual(ranks, sorted(ranks))

    def test_an_exact_name_prefix_is_ranked_as_such(self):
        rows = {row.name: row.rank for row in CATALOGUE.suggest("MPOL")}
        self.assertEqual(rows["MPOLYGON"], RANK_NAME_PREFIX)


class TestBestCompletion(unittest.TestCase):
    """Inline completion may only ever extend what was typed."""

    def test_it_completes_a_unique_prefix(self):
        self.assertEqual(CATALOGUE.best_completion("REC"), "RECTANG")

    def test_it_completes_through_an_alias_to_the_real_name(self):
        self.assertEqual(CATALOGUE.best_completion("PL"), "PLINE")

    def test_it_never_rewrites_the_typed_characters(self):
        # ERASE's alias DELETE must not turn a typed "DEL" into "ERASE".
        completion = CATALOGUE.best_completion("DEL")
        self.assertTrue(completion == "" or completion.startswith("DEL"),
                        completion)

    def test_a_typo_completes_to_nothing_rather_than_something_wrong(self):
        self.assertEqual(CATALOGUE.best_completion("CIRCEL"), "")

    def test_an_empty_prefix_completes_to_nothing(self):
        self.assertEqual(CATALOGUE.best_completion(""), "")

    def test_a_complete_name_needs_no_completion(self):
        self.assertEqual(CATALOGUE.best_completion("LINE"), "LINE")

    def test_it_is_case_insensitive(self):
        self.assertEqual(CATALOGUE.best_completion("rec"), "RECTANG")


class TestExistingLookupUnaffected(unittest.TestCase):
    """Suggestions are an addition; resolution must behave as before."""

    def test_exact_names_still_resolve(self):
        self.assertIsNotNone(CATALOGUE.resolve("POLYGON"))

    def test_aliases_still_resolve(self):
        self.assertEqual(CATALOGUE.resolve_name("PL"), "PLINE")

    def test_an_ambiguous_prefix_still_resolves_to_nothing(self):
        # POLYGON and POINT both start with PO, so PO alone is ambiguous —
        # even though the suggestion list happily offers both.
        self.assertEqual(CATALOGUE.resolve_name("POL"), "POLYGON")
        self.assertGreater(len(CATALOGUE.suggest("PO")), 1)


if __name__ == "__main__":
    unittest.main()
