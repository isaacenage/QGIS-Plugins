# -*- coding: utf-8 -*-
"""Regression tests for the input flow that made most commands unusable.

Two defects are pinned here, because between them they disabled every command
that is not answered purely by canvas clicks:

* **A bare Enter at a "Select objects" prompt threw the selection away.** The
  runner turned it into the ENTER sentinel, every selection command read that
  as "stop", and so ERASE / MOVE / ROTATE / SCALE / … aborted the moment the
  user did what AutoCAD teaches them to do.
* **There was no way to select everything.** ``ALL`` is how a CAD user clears
  a drawing; without it the plugin could add entities but never remove them
  in bulk.

Run from the plugin directory with QGIS on the path::

    python test/test_command_flow.py
"""

import os
import sys
import unittest

# ``runner.py`` reaches sideways with ``from ..input import coords``, so every
# module here has to come in through the package rather than by bare name —
# otherwise ``engine.prompt`` and ``autoqad.engine.prompt`` are two different
# modules and the runner's ``isinstance`` check never matches.
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(_PLUGIN_DIR))

from autoqad.engine.prompt import (                  # noqa: E402
    ENTER, IntegerPrompt, PointPrompt, SelectionPrompt, StringPrompt,
)
from autoqad.engine.registry import CommandRegistry  # noqa: E402
from autoqad.engine.runner import CommandRunner      # noqa: E402
from autoqad.engine.command import Command           # noqa: E402

from qgis.PyQt.QtCore import QEvent, Qt              # noqa: E402
from qgis.PyQt.QtGui import QKeyEvent                # noqa: E402

from autoqad.input.maptool import AutoQadMapTool     # noqa: E402


class FakeVariables(object):
    """Just enough of :class:`~core.variables.VariableStore` for the runner."""

    clockwise_angles = False

    def __init__(self, values=None):
        self._values = {"CMDECHO": 0, "ANGBASE": 0.0}
        self._values.update(values or {})

    def get(self, name):
        return self._values.get(name, 0)


class FakeDocument(object):
    """A closed document that can still enumerate entities."""

    is_open = False

    def __init__(self, entities=()):
        self._entities = list(entities)

    def all_tables(self):
        return []

    def all_entities(self, table_names=None):
        return list(self._entities)


class FakeContext(object):

    def __init__(self, document=None, variables=None):
        self.document = document or FakeDocument()
        self.variables = variables or FakeVariables()
        self.pointer = None
        self.messages = []

    def write(self, text):
        self.messages.append(text)


class RecordingSelectionCommand(Command):
    """Records whatever answer the selection prompt receives."""

    name = "PICKER"
    group = "modify"
    needs_selection = True
    last_answer = "unset"

    def run(self):
        RecordingSelectionCommand.last_answer = yield SelectionPrompt(
            "Select objects")


class RecordingValueCommand(Command):
    """Records a typed integer then a typed string."""

    name = "TYPER"
    group = "draw"
    answers = ()

    def run(self):
        sides = yield IntegerPrompt("Enter number of sides", minimum=3,
                                    maximum=1024, default=4)
        content = yield StringPrompt("Enter text")
        RecordingValueCommand.answers = (sides, content)


def _runner(document=None, picks=()):
    registry = CommandRegistry().register_all(
        [RecordingSelectionCommand, RecordingValueCommand])
    context = FakeContext(document=document)
    runner = CommandRunner(context, registry)
    runner.selection_provider = lambda: list(picks)
    return runner


class TestSelectionPromptAnswers(unittest.TestCase):
    """Enter at a selection prompt must commit the picks, not abort."""

    def setUp(self):
        # The recorder is a class attribute, so a leftover value from the
        # previous test would make "the command was never answered" pass.
        RecordingSelectionCommand.last_answer = "unset"

    def test_enter_commits_the_picks_made_so_far(self):
        picks = [("aq_lines", 1), ("aq_lines", 2)]
        runner = _runner(picks=picks)
        runner.start("PICKER")
        runner.supply_text("")
        self.assertEqual(RecordingSelectionCommand.last_answer, picks)

    def test_enter_with_no_picks_answers_with_an_empty_selection(self):
        runner = _runner(picks=[])
        runner.start("PICKER")
        runner.supply_text("")
        self.assertEqual(RecordingSelectionCommand.last_answer, [])

    def test_enter_is_never_the_enter_sentinel_at_a_selection_prompt(self):
        runner = _runner(picks=[("aq_points", 7)])
        runner.start("PICKER")
        runner.supply_text("")
        self.assertIsNot(RecordingSelectionCommand.last_answer, ENTER)

    def test_all_selects_every_entity_in_the_drawing(self):
        every = [("aq_lines", 1), ("aq_points", 4), ("aq_polygons", 9)]
        runner = _runner(document=FakeDocument(every), picks=[])
        runner.start("PICKER")
        runner.supply_text("ALL")
        self.assertEqual(RecordingSelectionCommand.last_answer, every)

    def test_all_is_case_insensitive(self):
        every = [("aq_lines", 1)]
        runner = _runner(document=FakeDocument(every), picks=[])
        runner.start("PICKER")
        runner.supply_text("all")
        self.assertEqual(RecordingSelectionCommand.last_answer, every)

    def test_an_abbreviation_of_all_still_selects_everything(self):
        # Otherwise "A" resolves as a keyword and the command is handed the
        # literal string "ALL" where it expects a list of picks.
        every = [("aq_lines", 1), ("aq_points", 2)]
        runner = _runner(document=FakeDocument(every), picks=[])
        runner.start("PICKER")
        runner.supply_text("a")
        self.assertEqual(RecordingSelectionCommand.last_answer, every)

    def test_a_star_selects_everything(self):
        every = [("aq_lines", 3)]
        runner = _runner(document=FakeDocument(every), picks=[])
        runner.start("PICKER")
        runner.supply_text("*")
        self.assertEqual(RecordingSelectionCommand.last_answer, every)

    def test_nonsense_is_rejected_rather_than_passed_on(self):
        runner = _runner(picks=[])
        runner.start("PICKER")
        self.assertFalse(runner.supply_text("qqq"))
        # The command is still waiting, not holding a string it cannot use.
        self.assertTrue(runner.is_running)
        self.assertEqual(RecordingSelectionCommand.last_answer, "unset")

    def test_the_picks_are_released_once_consumed(self):
        released = []
        runner = _runner(picks=[("aq_lines", 1)])
        runner.selectionConsumed.connect(lambda: released.append(True))
        runner.start("PICKER")
        runner.supply_text("")
        self.assertEqual(released, [True])


class TestSelectionPromptDisplay(unittest.TestCase):

    def test_a_multi_pick_prompt_advertises_all(self):
        self.assertIn("ALL", SelectionPrompt("Select objects").format())

    def test_a_single_pick_prompt_does_not(self):
        prompt = SelectionPrompt("Select object to offset", single=True)
        self.assertNotIn("ALL", prompt.format())

    def test_explicit_options_are_left_alone(self):
        prompt = SelectionPrompt("Select objects", options=["Window"])
        self.assertEqual(prompt.options, ["Window"])


class TestTypedInputStillWorks(unittest.TestCase):
    """The selection shortcut must not disturb ordinary typed prompts."""

    def test_an_integer_then_a_string_arrive_intact(self):
        runner = _runner()
        runner.start("TYPER")
        runner.supply_text("6")
        runner.supply_text("hello world")
        self.assertEqual(RecordingValueCommand.answers, (6, "hello world"))

    def test_enter_still_means_the_default_at_a_value_prompt(self):
        runner = _runner()
        runner.start("TYPER")
        runner.supply_text("")
        self.assertIs(runner.prompt.kind, "string")


class TestPointPromptUnaffected(unittest.TestCase):

    def test_a_point_prompt_still_wants_points(self):
        prompt = PointPrompt("Specify point")
        self.assertEqual(prompt.kind, "point")
        self.assertEqual(prompt.options, [])


class _KeySink(object):
    """Stands in for the map tool when testing its key-forwarding rule."""

    _RESERVED_KEYS = AutoQadMapTool._RESERVED_KEYS

    def __init__(self, capture=True):
        self.sent = []
        self.keyTyped = self
        self.variables = FakeVariables({"CMDKEYCAPTURE": capture})

    def emit(self, text):
        self.sent.append(text)


def _key(key, text="", modifiers=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)


class TestCanvasTypingReachesTheCommandLine(unittest.TestCase):
    """Clicking the canvas took focus, and the map tool ate every keystroke.

    That is what made POLYGON, TEXT, HATCH, a scale factor and every keyword
    option look frozen: the prompt was showing, the user typed, nothing
    happened.
    """

    def setUp(self):
        self.sink = _KeySink()

    def _forward(self, event):
        return AutoQadMapTool._forward_to_command_line(self.sink, event)

    def test_a_digit_is_forwarded(self):
        self.assertTrue(self._forward(_key(Qt.Key.Key_6, "6")))
        self.assertEqual(self.sink.sent, ["6"])

    def test_a_letter_is_forwarded(self):
        self.assertTrue(self._forward(_key(Qt.Key.Key_D, "D")))
        self.assertEqual(self.sink.sent, ["D"])

    def test_punctuation_used_by_coordinates_is_forwarded(self):
        for key, text in ((Qt.Key.Key_Comma, ","), (Qt.Key.Key_At, "@"),
                          (Qt.Key.Key_Less, "<"), (Qt.Key.Key_Period, ".")):
            self.assertTrue(self._forward(_key(key, text)), text)
        self.assertEqual(self.sink.sent, [",", "@", "<", "."])

    def test_backspace_is_forwarded_so_typos_can_be_fixed(self):
        self.assertTrue(self._forward(_key(Qt.Key.Key_Backspace, "\b")))
        self.assertEqual(self.sink.sent, ["\b"])

    def test_control_chords_are_left_to_qgis(self):
        event = _key(Qt.Key.Key_Z, "\x1a",
                     Qt.KeyboardModifier.ControlModifier)
        self.assertFalse(self._forward(event))
        self.assertEqual(self.sink.sent, [])

    def test_alt_chords_are_left_to_qgis(self):
        event = _key(Qt.Key.Key_F, "f", Qt.KeyboardModifier.AltModifier)
        self.assertFalse(self._forward(event))

    def test_shifted_letters_are_still_forwarded(self):
        event = _key(Qt.Key.Key_A, "A", Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(self._forward(event))
        self.assertEqual(self.sink.sent, ["A"])

    def test_delete_still_belongs_to_qgis(self):
        self.assertFalse(self._forward(_key(Qt.Key.Key_Delete, "\x7f")))

    def test_function_and_arrow_keys_are_not_taken(self):
        for key in (Qt.Key.Key_F8, Qt.Key.Key_F3, Qt.Key.Key_Left,
                    Qt.Key.Key_Up, Qt.Key.Key_PageDown):
            self.assertFalse(self._forward(_key(key)), key)
        self.assertEqual(self.sink.sent, [])

    def test_capture_can_be_switched_off_to_free_qgis_shortcuts(self):
        # Capturing letters is what disables QGIS's own single-key shortcuts
        # for the session; CMDKEYCAPTURE is the way to hand them back.
        sink = _KeySink(capture=False)
        taken = AutoQadMapTool._forward_to_command_line(
            sink, _key(Qt.Key.Key_L, "L"))
        self.assertFalse(taken)
        self.assertEqual(sink.sent, [])


if __name__ == "__main__":
    unittest.main()
