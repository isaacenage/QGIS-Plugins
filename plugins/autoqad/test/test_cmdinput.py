# -*- coding: utf-8 -*-
"""Tests for the command box that opens at the cursor.

Exercises the real widget against a stand-in canvas — the box only ever asks
its parent for a width, a height and the focus, so a plain ``QWidget`` is
enough and no map canvas is needed.

Needs QGIS (for PyQt) on the path, and a GUI-capable QApplication; run with
``QT_QPA_PLATFORM=offscreen``. From the plugin directory::

    QT_QPA_PLATFORM=offscreen python test/test_cmdinput.py
"""

import os
import sys
import unittest

_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.PyQt.QtCore import QEvent, Qt                     # noqa: E402
from qgis.PyQt.QtGui import QKeyEvent                       # noqa: E402
from qgis.PyQt.QtWidgets import QApplication, QWidget       # noqa: E402

from autoqad.core.variables import VariableStore            # noqa: E402
from autoqad.engine.prompt import (                         # noqa: E402
    PointPrompt, StringPrompt,
)
from autoqad.engine.registry import CommandRegistry         # noqa: E402
from autoqad.input.cmdinput import DynamicCommandInput      # noqa: E402

_APP = QApplication.instance() or QApplication([])


class _Fake(object):
    aliases = ()
    group = "draw"
    description = ""
    modifies = True


def _command(name, aliases=(), description=""):
    return type("Cmd", (_Fake,), {
        "name": name, "aliases": tuple(aliases), "description": description})


def _registry():
    return CommandRegistry().register_all([
        _command("LINE", ("L",), "Draw straight line segments."),
        _command("PLINE", ("PL",), "Draw a polyline."),
        _command("POLYGON", ("POL",), "Draw a regular polygon."),
        _command("POINT", ("PO",), "Place a point."),
        _command("CIRCLE", ("C",), "Draw a circle."),
    ])


def _key(key, text="", modifiers=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)


class _CommandInputCase(unittest.TestCase):

    def setUp(self):
        self.canvas = QWidget()
        self.canvas.resize(800, 600)
        self.variables = VariableStore()
        self.box = DynamicCommandInput(self.canvas, self.variables,
                                       _registry())
        self.box.set_enabled(True)
        self.submitted = []
        self.cancelled = []
        self.box.submitted.connect(self.submitted.append)
        self.box.cancelled.connect(lambda: self.cancelled.append(True))

    def tearDown(self):
        self.box.dispose()
        self.canvas.deleteLater()

    # -- helpers --

    def _type(self, text, at=(100, 100)):
        for char in text:
            self.box.type_text(char, at)

    def _press(self, key, text=""):
        self.box._entry.keyPressEvent(_key(key, text))

    @property
    def _text(self):
        return self.box._entry.text()

    @property
    def _rows(self):
        return [self.box._list.item(i).text()
                for i in range(self.box._list.count())]

    @property
    def _list_shown(self):
        # The stand-in canvas is never shown, so Qt reports every child as
        # invisible; the box keeps its own state for exactly that reason.
        return self.box._list_shown


class TestOpening(_CommandInputCase):

    def test_it_starts_closed(self):
        self.assertFalse(self.box.is_open)

    def test_typing_a_letter_opens_it(self):
        self.box.type_text("L", (100, 100))
        self.assertTrue(self.box.is_open)

    def test_the_typed_letter_is_kept(self):
        self.box.type_text("L", (100, 100))
        self.assertTrue(self._text.startswith("L"))

    def test_it_opens_below_right_of_the_cursor(self):
        self.box.type_text("L", (100, 100))
        position = self.box._entry.pos()
        self.assertGreater(position.x(), 100)
        self.assertGreater(position.y(), 100)

    def test_it_stays_where_it_opened_as_the_mouse_moves_on(self):
        # Chasing the pointer would slide the suggestion list out from under
        # the user while they are reading it.
        self.box.type_text("L", (100, 100))
        opened_at = self.box._entry.pos()
        self.box.type_text("I", (500, 400))
        self.assertEqual(self.box._entry.pos().y(), opened_at.y())

    def test_backspace_on_a_closed_box_does_not_open_it(self):
        self.assertFalse(self.box.type_text("\b", (100, 100)))
        self.assertFalse(self.box.is_open)

    def test_it_declines_input_when_disabled(self):
        self.box.set_enabled(False)
        self.assertFalse(self.box.type_text("L", (100, 100)))
        self.assertFalse(self.box.is_open)

    def test_the_dyncmdinput_variable_switches_it_off(self):
        self.variables.set("DYNCMDINPUT", False)
        self.assertFalse(self.box.type_text("L", (100, 100)))

    def test_it_keeps_clear_of_the_right_edge(self):
        self.box.type_text("L", (795, 100))
        right = self.box._entry.pos().x() + self.box._entry.width()
        self.assertLessEqual(right, self.canvas.width())

    def test_it_keeps_clear_of_the_bottom_edge(self):
        self.box.type_text("L", (100, 595))
        bottom = self.box._entry.pos().y() + self.box._entry.height()
        self.assertLessEqual(bottom, self.canvas.height())


class TestSuggestions(_CommandInputCase):

    def test_typing_shows_matching_commands(self):
        self._type("P")
        self.assertTrue(self._list_shown)
        self.assertTrue(any(row.startswith("PLINE") for row in self._rows))

    def test_pl_puts_pline_first_and_shows_the_alias(self):
        self._type("PL")
        self.assertEqual(self._rows[0], "PLINE  (PL)")

    def test_pol_suggests_polygon(self):
        self._type("POL")
        self.assertTrue(any(row.startswith("POLYGON") for row in self._rows))

    def test_no_matches_hides_the_list(self):
        self._type("ZZ")
        self.assertFalse(self._list_shown)

    def test_the_list_sits_under_the_box(self):
        self._type("P")
        entry = self.box._entry
        self.assertGreaterEqual(self.box._list.pos().y(),
                                entry.pos().y() + entry.height())

    def test_arrow_keys_walk_the_list(self):
        self._type("P")
        self.assertEqual(self.box._list.currentRow(), 0)
        self._press(Qt.Key.Key_Down)
        self.assertEqual(self.box._list.currentRow(), 1)
        self._press(Qt.Key.Key_Up)
        self.assertEqual(self.box._list.currentRow(), 0)

    def test_navigation_stops_at_the_ends(self):
        self._type("P")
        for _ in range(20):
            self._press(Qt.Key.Key_Down)
        self.assertEqual(self.box._list.currentRow(),
                         self.box._list.count() - 1)

    def test_tab_takes_the_highlighted_suggestion_without_running_it(self):
        self._type("P")
        self._press(Qt.Key.Key_Down)
        highlighted = self.box._list.currentItem().text().split("  (")[0]
        self._press(Qt.Key.Key_Tab)
        self.assertEqual(self._text, highlighted)
        self.assertEqual(self.submitted, [])


class TestInlineCompletion(_CommandInputCase):

    def test_it_appends_the_rest_of_the_best_match(self):
        self._type("PL")
        self.assertEqual(self._text, "PLINE")

    def test_the_appended_part_is_selected_so_typing_replaces_it(self):
        self._type("PL")
        self.assertEqual(self.box._entry.selectedText(), "INE")

    def test_typing_on_replaces_the_completion(self):
        # "PO" completes to POINT; typing L must give POL…, not POINTL.
        self._type("POL")
        self.assertTrue(self._text.startswith("POL"), self._text)

    def test_backspace_deletes_instead_of_re_completing(self):
        self._type("PL")
        self.box.type_text("\b", (100, 100))
        self.box.type_text("\b", (100, 100))
        self.assertLess(len(self._text), len("PLINE"))

    def test_it_is_off_while_a_command_is_running(self):
        # Mid-command the answer is a coordinate or a keyword, and completing
        # it against the command catalogue would fight every keystroke.
        self.box.set_prompt(PointPrompt("Specify next point"))
        self._type("PL")
        self.assertEqual(self._text, "PL")

    def test_the_autocomplete_variable_switches_it_off(self):
        self.variables.set("AUTOCOMPLETE", False)
        self._type("PL")
        self.assertEqual(self._text, "PL")


class TestCommitting(_CommandInputCase):

    def test_enter_submits_what_is_in_the_box(self):
        self._type("PL")
        self._press(Qt.Key.Key_Return)
        self.assertEqual(self.submitted, ["PLINE"])

    def test_submitting_closes_the_box(self):
        self._type("PL")
        self._press(Qt.Key.Key_Return)
        self.assertFalse(self.box.is_open)

    def test_space_submits_at_the_command_prompt(self):
        self._type("L")
        self._press(Qt.Key.Key_Space, " ")
        self.assertEqual(self.submitted, ["LINE"])

    def test_space_is_literal_when_the_prompt_wants_prose(self):
        # TEXT's contents obviously cannot be terminated by a space.
        self.box.set_prompt(StringPrompt("Enter text"))
        self._type("A")
        self._press(Qt.Key.Key_Space, " ")
        self.assertEqual(self.submitted, [])
        self.assertIn(" ", self._text)

    def test_clicking_a_suggestion_runs_it(self):
        self._type("P")
        self.box._list.setCurrentRow(1)
        self.box._accept_clicked()
        self.assertEqual(len(self.submitted), 1)
        self.assertNotIn("(", self.submitted[0])


class TestDismissing(_CommandInputCase):

    def test_escape_with_text_just_clears_the_box(self):
        self._type("PL")
        self._press(Qt.Key.Key_Escape)
        self.assertFalse(self.box.is_open)
        self.assertEqual(self.cancelled, [])

    def test_escape_on_an_empty_box_aborts_the_command(self):
        self.box.type_text("L", (100, 100))
        self.box._entry.clear()
        self._press(Qt.Key.Key_Escape)
        self.assertEqual(self.cancelled, [True])

    def test_backspacing_past_the_start_closes_the_box(self):
        self.box.type_text("L", (100, 100))
        self.box._entry.clear()
        self._press(Qt.Key.Key_Backspace)
        self.assertFalse(self.box.is_open)

    def test_closing_reports_it_so_other_overlays_can_reclaim_the_space(self):
        seen = []
        self.box.visibilityChanged.connect(seen.append)
        self.box.type_text("L", (100, 100))
        self.box.close()
        self.assertEqual(seen, [True, False])

    def test_an_open_box_reserves_room_below_the_cursor(self):
        self.assertEqual(self.box.reserved_height(), 0)
        self.box.type_text("L", (100, 100))
        self.assertGreater(self.box.reserved_height(), 0)


class TestPromptKeywords(_CommandInputCase):
    """Inside a command the suggestions become the prompt's own options."""

    def setUp(self):
        super().setUp()
        self.box.set_prompt(PointPrompt(
            "Specify next point or", options=["Arc", "Close", "Undo"]))

    def test_it_offers_the_matching_keyword(self):
        self._type("C")
        self.assertEqual(self._rows, ["Close"])

    def test_it_does_not_offer_commands_mid_prompt(self):
        self._type("C")
        self.assertNotIn("CIRCLE", self._rows)

    def test_a_non_matching_letter_offers_nothing(self):
        self._type("Z")
        self.assertFalse(self._list_shown)

    def test_the_prompt_message_is_the_placeholder(self):
        self._type("C")
        self.assertIn("Specify next point",
                      self.box._entry.placeholderText())


class TestAgainstTheRealCatalogue(unittest.TestCase):
    """The stub registry proves the mechanism; this proves the shipping set.

    Ranking that reads well on five invented commands can still put the wrong
    thing first among forty real ones, and the examples below are the ones a
    user actually types.
    """

    def setUp(self):
        from autoqad.commands import build_registry

        self.canvas = QWidget()
        self.canvas.resize(800, 600)
        self.variables = VariableStore()
        self.box = DynamicCommandInput(self.canvas, self.variables,
                                       build_registry())
        self.box.set_enabled(True)
        self.submitted = []
        self.box.submitted.connect(self.submitted.append)

    def tearDown(self):
        self.box.dispose()
        self.canvas.deleteLater()

    def _type(self, text):
        for char in text:
            self.box.type_text(char, (100, 100))

    @property
    def _rows(self):
        return [self.box._list.item(i).text()
                for i in range(self.box._list.count())]

    def test_pl_reaches_pline(self):
        self._type("PL")
        self.assertEqual(self.box._entry.text(), "PLINE")
        self.assertEqual(self._rows[0], "PLINE  (PL)")

    def test_pol_reaches_polygon(self):
        self._type("POL")
        self.assertEqual(self.box._entry.text(), "POLYGON")

    def test_rec_reaches_rectang(self):
        self._type("REC")
        self.assertEqual(self.box._entry.text(), "RECTANG")

    def test_a_single_l_reaches_line(self):
        self._type("L")
        self.assertEqual(self.box._entry.text(), "LINE")

    def test_typing_a_whole_name_submits_it(self):
        self._type("CIRCLE")
        self.box._entry.keyPressEvent(_key(Qt.Key.Key_Return))
        self.assertEqual(self.submitted, ["CIRCLE"])

    def test_e_reaches_erase(self):
        self._type("E")
        self.assertEqual(self.box._entry.text(), "ERASE")

    def test_h_reaches_hatch(self):
        self._type("H")
        self.assertEqual(self.box._entry.text(), "HATCH")

    def test_every_suggestion_resolves_to_a_real_command(self):
        from autoqad.commands import build_registry

        registry = build_registry()
        for prefix in ("L", "P", "PO", "C", "E", "A", "M", "T", "S"):
            self._type(prefix)
            for label in self._rows:
                name = label.split("  (")[0]
                self.assertIsNotNone(registry.resolve(name),
                                     "{0} -> {1}".format(prefix, name))
            self.box.close()


if __name__ == "__main__":
    unittest.main()
