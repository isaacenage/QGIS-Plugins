# -*- coding: utf-8 -*-
"""Tests for the command registry, prompt matching and the scripting spec.

Runs without QGIS — every module exercised here is Qt-free at import time.
From the plugin directory::

    python test/test_engine.py
"""

import os
import sys
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PLUGIN_DIR)                      # bare-name imports
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))     # package imports

from engine.prompt import (                          # noqa: E402
    CANCEL, ENTER, KeywordPrompt, PointPrompt, SelectionPrompt,
)
from engine.registry import CommandRegistry          # noqa: E402
from autoqad import scripting                        # noqa: E402


class _Fake(object):
    name = "FAKE"
    aliases = ()
    group = "draw"
    description = ""
    modifies = True


def _command(name, aliases=(), group="draw", description=""):
    return type("Cmd", (_Fake,), {
        "name": name, "aliases": tuple(aliases), "group": group,
        "description": description})


class TestRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = CommandRegistry().register_all([
            _command("LINE", ("L",)),
            _command("PLINE", ("PL",)),
            _command("RECTANG", ("REC",)),
            _command("CIRCLE", ("C",), description="Draw a circle."),
            _command("COPY", ("CO",), group="modify"),
        ])

    def test_exact_name(self):
        self.assertEqual(self.registry.resolve("LINE").name, "LINE")

    def test_case_insensitive(self):
        self.assertEqual(self.registry.resolve("line").name, "LINE")
        self.assertEqual(self.registry.resolve("  LiNe  ").name, "LINE")

    def test_alias(self):
        self.assertEqual(self.registry.resolve("L").name, "LINE")
        self.assertEqual(self.registry.resolve("PL").name, "PLINE")

    def test_unique_prefix_resolves(self):
        # "RECT" is a unique prefix of RECTANG, and is not a declared alias.
        self.assertEqual(self.registry.resolve("RECT").name, "RECTANG")

    def test_ambiguous_prefix_does_not_resolve(self):
        # "C" is an alias for CIRCLE, so it wins over the CIRCLE/COPY ambiguity.
        self.assertEqual(self.registry.resolve("C").name, "CIRCLE")
        # "CO" is an alias for COPY.
        self.assertEqual(self.registry.resolve("CO").name, "COPY")
        # But a genuinely ambiguous, undeclared prefix must not guess.
        registry = CommandRegistry().register_all(
            [_command("CIRCLE"), _command("CIRCUIT")])
        self.assertIsNone(registry.resolve("CIRC"))

    def test_unknown_returns_none(self):
        for value in ("NOTACOMMAND", "", None, "   "):
            self.assertIsNone(self.registry.resolve(value))

    def test_contains_and_len(self):
        self.assertIn("LINE", self.registry)
        self.assertIn("L", self.registry)
        self.assertNotIn("ZZZ", self.registry)
        self.assertEqual(len(self.registry), 5)

    def test_registration_order_preserved(self):
        self.assertEqual(self.registry.names()[0], "LINE")
        self.assertEqual(self.registry.names()[-1], "COPY")

    def test_re_registering_replaces_without_duplicating(self):
        self.registry.register(_command("LINE", ("L", "LI")))
        self.assertEqual(len(self.registry), 5)
        self.assertEqual(self.registry.resolve("LI").name, "LINE")

    def test_groups_and_by_group(self):
        self.assertEqual(self.registry.groups(), ["draw", "modify"])
        self.assertEqual([c.name for c in self.registry.by_group("modify")],
                         ["COPY"])

    def test_completions(self):
        self.assertIn("PLINE", self.registry.completions("P"))
        self.assertEqual(self.registry.completions(""), [])

    def test_aliases_for(self):
        self.assertEqual(self.registry.aliases_for("LINE"), ["L"])

    def test_reference_shape(self):
        entry = self.registry.reference()[3]
        self.assertEqual(entry["name"], "CIRCLE")
        self.assertEqual(entry["description"], "Draw a circle.")
        self.assertIn("aliases", entry)
        self.assertIn("group", entry)

    def test_registering_nameless_command_raises(self):
        with self.assertRaises(ValueError):
            CommandRegistry().register(_command(""))


class TestPromptKeywords(unittest.TestCase):

    def setUp(self):
        self.prompt = PointPrompt("Specify next point or",
                                  options=["Close", "Undo"])

    def test_capitalised_abbreviation(self):
        self.assertEqual(self.prompt.match_keyword("C"), "Close")
        self.assertEqual(self.prompt.match_keyword("U"), "Undo")

    def test_case_insensitive(self):
        self.assertEqual(self.prompt.match_keyword("c"), "Close")
        self.assertEqual(self.prompt.match_keyword("close"), "Close")

    def test_full_word(self):
        self.assertEqual(self.prompt.match_keyword("Close"), "Close")

    def test_multi_letter_abbreviation(self):
        prompt = PointPrompt("x", options=["CEnter", "COpy"])
        self.assertEqual(prompt.match_keyword("CE"), "CEnter")
        self.assertEqual(prompt.match_keyword("CO"), "COpy")

    def test_ambiguous_prefix_is_rejected(self):
        prompt = PointPrompt("x", options=["Close", "Chord"])
        # Both start with C; the capitalised prefix of each is "C", and the
        # first exact-abbreviation match wins deterministically.
        self.assertEqual(prompt.match_keyword("C"), "Close")
        # A genuinely ambiguous full-word prefix must not guess.
        self.assertIsNone(prompt.match_keyword("Cl0"))

    def test_no_match(self):
        for value in ("X", "", None, "12.5", "10,20"):
            self.assertIsNone(self.prompt.match_keyword(value))

    def test_coordinates_never_match_keywords(self):
        # Critical: the runner tries keywords before coordinates, so a
        # coordinate must never be swallowed as an option.
        for value in ("10,20", "@5<45", "-3.5", "0,0"):
            self.assertIsNone(self.prompt.match_keyword(value))

    def test_format_shows_options_and_default(self):
        self.assertEqual(self.prompt.format(),
                         "Specify next point or [Close/Undo]: ")
        plain = PointPrompt("Specify point")
        self.assertEqual(plain.format(), "Specify point: ")
        with_default = PointPrompt("Enter sides", default=4)
        self.assertEqual(with_default.format(), "Enter sides <4>: ")

    def test_prompt_kinds(self):
        self.assertEqual(PointPrompt("x").kind, "point")
        self.assertEqual(KeywordPrompt("x", ["A"]).kind, "keyword")
        self.assertEqual(SelectionPrompt("x").kind, "selection")

    def test_sentinels_are_falsey_and_distinct(self):
        self.assertFalse(CANCEL)
        self.assertFalse(ENTER)
        self.assertIsNot(CANCEL, ENTER)


class TestSpecTranslation(unittest.TestCase):

    def test_minimal_spec(self):
        operations, warnings = scripting.spec_to_operations({
            "entities": [{"type": "line", "points": [[0, 0], [10, 0]]}]})
        self.assertEqual(warnings, [])
        self.assertEqual(len(operations["entities"]), 1)
        self.assertEqual(operations["entities"][0]["points"],
                         [(0.0, 0.0), (10.0, 0.0)])

    def test_layers_normalise(self):
        operations, warnings = scripting.spec_to_operations({
            "layers": [{"name": "A-WALL", "color": 7,
                        "linetype": "hidden", "lineweight": 36}]})
        self.assertEqual(warnings, [])
        layer = operations["layers"][0]
        self.assertEqual(layer["linetype"], "HIDDEN")
        # 36 is off-ladder and snaps to 35.
        self.assertEqual(layer["lineweight"], 35)

    def test_named_colour_resolves(self):
        operations, _warnings = scripting.spec_to_operations({
            "layers": [{"name": "L", "color": "Red"}]})
        self.assertEqual(operations["layers"][0]["color"], 1)

    def test_unknown_colour_warns_and_falls_back(self):
        operations, warnings = scripting.spec_to_operations({
            "layers": [{"name": "L", "color": "chartreuse"}]})
        self.assertEqual(operations["layers"][0]["color"], 7)
        self.assertTrue(any("chartreuse" in w for w in warnings))

    def test_unknown_linetype_warns(self):
        operations, warnings = scripting.spec_to_operations({
            "layers": [{"name": "L", "linetype": "SQUIGGLE"}]})
        self.assertEqual(operations["layers"][0]["linetype"], "CONTINUOUS")
        self.assertTrue(any("SQUIGGLE" in w for w in warnings))

    def test_unknown_entity_type_is_skipped_with_warning(self):
        operations, warnings = scripting.spec_to_operations({
            "entities": [{"type": "hypercube"}]})
        self.assertEqual(operations["entities"], [])
        self.assertTrue(any("hypercube" in w for w in warnings))

    def test_line_needs_two_points(self):
        operations, warnings = scripting.spec_to_operations({
            "entities": [{"type": "line", "points": [[0, 0]]}]})
        self.assertEqual(operations["entities"], [])
        self.assertTrue(warnings)

    def test_circle_requires_positive_radius(self):
        _ops, warnings = scripting.spec_to_operations({
            "entities": [{"type": "circle", "center": [0, 0], "radius": 0}]})
        self.assertTrue(warnings)

        operations, warnings = scripting.spec_to_operations({
            "entities": [{"type": "circle", "center": [1, 2], "radius": 3}]})
        self.assertEqual(warnings, [])
        self.assertEqual(operations["entities"][0]["center"], (1.0, 2.0))

    def test_centre_spelling_accepted(self):
        operations, _warnings = scripting.spec_to_operations({
            "entities": [{"type": "circle", "centre": [1, 2], "radius": 3}]})
        self.assertEqual(operations["entities"][0]["center"], (1.0, 2.0))

    def test_arc_needs_three_points(self):
        _ops, warnings = scripting.spec_to_operations({
            "entities": [{"type": "arc", "points": [[0, 0], [1, 1]]}]})
        self.assertTrue(warnings)

    def test_hatch_pattern_validated(self):
        operations, warnings = scripting.spec_to_operations({
            "entities": [{"type": "hatch",
                          "boundary": [[0, 0], [1, 0], [1, 1]],
                          "pattern": "ANSI31"}]})
        self.assertEqual(warnings, [])
        self.assertEqual(operations["entities"][0]["pattern"], "ANSI31")

        operations, warnings = scripting.spec_to_operations({
            "entities": [{"type": "hatch",
                          "boundary": [[0, 0], [1, 0], [1, 1]],
                          "pattern": "NOTAPATTERN"}]})
        self.assertEqual(operations["entities"][0]["pattern"], "ANSI31")
        self.assertTrue(warnings)

    def test_text_requires_content(self):
        _ops, warnings = scripting.spec_to_operations({
            "entities": [{"type": "text", "at": [0, 0]}]})
        self.assertTrue(warnings)

        operations, warnings = scripting.spec_to_operations({
            "entities": [{"type": "text", "at": [0, 0], "text": "LIVING"}]})
        self.assertEqual(warnings, [])
        self.assertEqual(operations["entities"][0]["text"], "LIVING")

    def test_entity_style_overrides_carried(self):
        operations, _warnings = scripting.spec_to_operations({
            "entities": [{"type": "line", "points": [[0, 0], [1, 1]],
                          "layer": "A-WALL", "color": 3,
                          "linetype": "HIDDEN", "lineweight": 35}]})
        entity = operations["entities"][0]
        self.assertEqual(entity["layer"], "A-WALL")
        self.assertEqual(entity["color"], 3)
        self.assertEqual(entity["lineweight"], 35)

    def test_commands_passed_through(self):
        operations, _warnings = scripting.spec_to_operations({
            "commands": ["LINE 0,0 10,0", "  ", ""]})
        self.assertEqual(operations["commands"], ["LINE 0,0 10,0"])

    def test_non_dict_spec_is_reported(self):
        operations, warnings = scripting.spec_to_operations("not a spec")
        self.assertEqual(operations["entities"], [])
        self.assertTrue(warnings)

    def test_empty_spec_is_valid(self):
        operations, warnings = scripting.spec_to_operations({})
        self.assertEqual(warnings, [])
        self.assertEqual(operations["entities"], [])

    def test_a_realistic_floor_plan_spec_validates_clean(self):
        spec = {
            "layers": [
                {"name": "A-WALL", "color": 7, "lineweight": 35},
                {"name": "A-DOOR", "color": 3, "lineweight": 18},
                {"name": "A-HATCH", "color": 8, "lineweight": 9},
            ],
            "entities": [
                {"type": "polyline", "layer": "A-WALL",
                 "points": [[0, 0], [8, 0], [8, 6], [0, 6]], "closed": True},
                {"type": "arc", "layer": "A-DOOR",
                 "points": [[2, 0], [2.6, 0.6], [2, 1.2]]},
                {"type": "hatch", "layer": "A-HATCH",
                 "boundary": [[0, 0], [8, 0], [8, 6], [0, 6]],
                 "pattern": "ANSI31", "scale": 0.5},
                {"type": "text", "layer": "A-WALL", "at": [4, 3],
                 "text": "LIVING", "height": 0.3},
            ],
        }
        operations, warnings = scripting.spec_to_operations(spec)
        self.assertEqual(warnings, [])
        self.assertEqual(len(operations["layers"]), 3)
        self.assertEqual(len(operations["entities"]), 4)

    def test_api_reference_is_text(self):
        reference = scripting.api_reference(None)
        self.assertIn("SPEC SCHEMA", reference)
        self.assertIn("MACRO STRINGS", reference)
        self.assertIn("LINEWEIGHTS", reference)


if __name__ == "__main__":
    unittest.main(verbosity=2)
