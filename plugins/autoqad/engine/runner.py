# -*- coding: utf-8 -*-
"""The command runner — drives a command coroutine and routes input to it.

This is the single place that decides what a piece of input *means*. A command
yields a prompt declaring what it wants; the runner takes whatever arrives —
a canvas click, typed text, a selection, an Escape — interprets it against that
prompt, and sends the result back into the generator.

The consequence worth stating plainly: **a command cannot tell where its input
came from.** The mouse, the command line, a macro string and the scripting
facade all funnel through :meth:`supply_point` / :meth:`supply_text`, so an
LLM-driven drawing exercises exactly the same code path as a hand-drawn one.

Undo is handled per command, not per edit: the runner opens an edit command on
every table when a modifying command starts and closes it when the command
ends, so one Ctrl+Z undoes one CAD operation rather than one feature insert.
"""

from qgis.PyQt.QtCore import QObject, pyqtSignal

from ..input import coords
from .prompt import CANCEL, ENTER, Prompt, SelectionPrompt

# Runner states.
IDLE = "idle"
RUNNING = "running"


class CommandRunner(QObject):
    """Runs one command at a time and exposes its prompt to the UI."""

    #: The active prompt changed; carries the formatted prompt text.
    promptChanged = pyqtSignal(str)
    #: A command started; carries its name.
    commandStarted = pyqtSignal(str)
    #: A command ended; carries its name and whether it completed normally.
    commandEnded = pyqtSignal(str, bool)
    #: The preview descriptor changed; carries a Rubber or None.
    rubberChanged = pyqtSignal(object)
    #: A line of output for the history pane.
    messaged = pyqtSignal(str)
    #: A pending selection was handed to a command; whoever gathered it should
    #: now let it go, or the next command would inherit stale picks.
    selectionConsumed = pyqtSignal()

    def __init__(self, context, registry, parent=None):
        super().__init__(parent)
        self.context = context
        self.registry = registry
        #: Callable returning the picks gathered so far, as
        #: ``[(table_name, feature_id), ...]``. Set by whatever is doing the
        #: picking — the map tool in the GUI, nothing at all when headless.
        self.selection_provider = None
        self._command = None
        self._generator = None
        self._prompt = None
        self._state = IDLE
        self._last_point = None
        self._last_command = None
        self._pending_selection = []
        self._edit_open = False

    # ---- state ----

    @property
    def state(self):
        return self._state

    @property
    def is_running(self):
        return self._state == RUNNING

    @property
    def prompt(self):
        """The prompt currently awaiting an answer, or ``None``."""
        return self._prompt

    @property
    def command_name(self):
        return self._command.name if self._command else ""

    @property
    def last_point(self):
        """The most recent point supplied — the anchor for relative input."""
        return self._last_point

    def set_last_point(self, point):
        self._last_point = point

    @property
    def wants_point(self):
        return self._prompt is not None and self._prompt.kind in (
            "point", "distance", "angle")

    @property
    def wants_selection(self):
        return self._prompt is not None and self._prompt.kind == "selection"

    @property
    def base_point(self):
        """Anchor for ortho/polar constraint at the current prompt."""
        if self._prompt is None:
            return None
        return self._prompt.base_point or self._last_point

    # ---- lifecycle ----

    def start(self, name, initial_selection=None):
        """Start the command called *name*. Returns True if it started."""
        if self.is_running:
            self.cancel()

        command_class = self.registry.resolve(name)
        if command_class is None:
            self.messaged.emit("Unknown command: {0}".format(name))
            return False

        command = command_class(self.context)
        if command.needs_selection:
            self._pending_selection = list(initial_selection or [])

        self._command = command
        self._generator = command.run()
        self._state = RUNNING
        self._last_command = command.name

        if self.context.variables.get("CMDECHO"):
            self.messaged.emit("Command: {0}".format(command.name))

        self._begin_edit()
        self.commandStarted.emit(command.name)
        return self._advance(None)

    def repeat_last(self):
        """Re-run the previous command — what a bare Enter does in AutoCAD."""
        if self._last_command:
            return self.start(self._last_command)
        return False

    def cancel(self):
        """Abort the running command, rolling nothing back but stopping cleanly."""
        if not self.is_running:
            self._clear_prompt()
            return
        name = self.command_name
        self._close_generator()
        self._end_edit(commit=True)
        self._finish(name, completed=False)

    def _close_generator(self):
        if self._generator is not None:
            try:
                self._generator.close()
            except (RuntimeError, StopIteration):
                pass

    def _finish(self, name, completed):
        self._command = None
        self._generator = None
        self._state = IDLE
        self._pending_selection = []
        self._clear_prompt()
        self.rubberChanged.emit(None)
        self.commandEnded.emit(name, completed)

    def _clear_prompt(self):
        self._prompt = None
        self.promptChanged.emit("")

    # ---- undo transactions ----

    def _begin_edit(self):
        """Open one edit command per table so undo is per CAD operation."""
        if not self._command or not self._command.modifies:
            return
        document = self.context.document
        if document is None or not document.is_open:
            return
        for table in document.all_tables():
            if not table.isEditable():
                table.startEditing()
            table.beginEditCommand(self._command.name)
        self._edit_open = True

    def _end_edit(self, commit=True):
        """Close the command's undo macro, leaving the edit session open.

        Writing the buffer to storage here is what used to happen, and it is
        what made UNDO permanently report "Nothing to undo":
        ``commitChanges`` clears the layer's undo stack, so every macro this
        method had just closed was destroyed a line later. The buffer is
        flushed at the points that actually mean "done" — the session ending,
        the project being saved — through ``DrawingDocument.commit``.
        """
        if not self._edit_open:
            return
        document = self.context.document
        if document is not None and document.is_open:
            for table in document.all_tables():
                try:
                    if commit:
                        table.endEditCommand()
                    else:
                        table.destroyEditCommand()
                except (RuntimeError, AttributeError):
                    pass
        self._edit_open = False

    # ---- driving the coroutine ----

    def _advance(self, value):
        """Send *value* into the command and pick up the next prompt."""
        if self._generator is None:
            return False
        name = self.command_name
        try:
            result = (self._generator.send(value) if value is not None
                      else next(self._generator))
        except StopIteration:
            self._end_edit(commit=True)
            self._finish(name, completed=True)
            return True
        except Exception as error:            # noqa: BLE001 - surfaced to user
            self._end_edit(commit=True)
            self.messaged.emit("{0} failed: {1}".format(name, error))
            self._finish(name, completed=False)
            return False

        if isinstance(result, Prompt):
            self._prompt = result
            self.promptChanged.emit(result.format())
            self.rubberChanged.emit(result.rubber)
            if result.kind == "selection" and self._pending_selection:
                pending, self._pending_selection = self._pending_selection, []
                return self._advance(pending)
        else:
            # A command yielded something that is not a prompt — treat it as a
            # message and keep going.
            if result is not None:
                self.messaged.emit(str(result))
            return self._advance(ENTER)
        return True

    # ---- input entry points ----

    def supply_point(self, point):
        """Answer the current prompt with a map point from the canvas."""
        if not self.is_running or self._prompt is None:
            return False

        kind = self._prompt.kind
        if kind == "point":
            self._last_point = point
            return self._advance(point)

        if kind == "distance":
            anchor = self.base_point
            if anchor is None:
                return False
            import math
            distance = math.hypot(point[0] - anchor[0], point[1] - anchor[1])
            return self._advance(distance)

        if kind == "angle":
            anchor = self.base_point
            if anchor is None:
                return False
            import math
            return self._advance(
                math.atan2(point[1] - anchor[1], point[0] - anchor[0]))

        return False

    def supply_selection(self, selection):
        """Answer a selection prompt with ``[(table, feature_id), ...]``."""
        if not self.is_running or not self.wants_selection:
            return False
        advanced = self._advance(list(selection))
        self.selectionConsumed.emit()
        return advanced

    # ---- selection sources ----

    def pending_selection(self):
        """The picks gathered so far by whoever is doing the picking."""
        if self.selection_provider is None:
            return []
        try:
            return list(self.selection_provider() or [])
        except (RuntimeError, TypeError):
            return []

    def _every_entity(self):
        """Every entity in the drawing — what the ``ALL`` keyword means."""
        document = self.context.document
        if document is None:
            return []
        try:
            return list(document.all_entities())
        except (AttributeError, RuntimeError):
            return []

    def _selection_from_text(self, raw):
        """Interpret typed input at a Select-objects prompt.

        Returns a selection list, or ``None`` when the text is not selection
        input and should fall through to ordinary parsing.

        A bare Enter commits whatever has been picked so far. That is the
        AutoCAD flow — pick, pick, Enter — and reading it as the ENTER
        sentinel instead is what silently aborted every selection command.

        ``ALL`` goes through the prompt's own keyword matching, so its
        abbreviations resolve here rather than falling through and reaching
        the command as the literal string ``"ALL"``.
        """
        if not raw:
            return self.pending_selection()
        if raw.strip() == "*":
            return self._every_entity()

        prompt = self._prompt
        keyword = prompt.match_keyword(raw) if prompt is not None else None
        if keyword == SelectionPrompt.ALL:
            return self._every_entity()
        return None

    def supply_text(self, text):
        """Answer the current prompt with typed text.

        With no command running, the text is treated as a command name (or a
        bare Enter repeats the last command) — which is exactly what the
        command line does.
        """
        raw = "" if text is None else str(text).strip()

        if not self.is_running:
            if not raw:
                return self.repeat_last()
            return self.start(raw)

        prompt = self._prompt
        if prompt is None:
            return False

        if self.wants_selection:
            answer = self._selection_from_text(raw)
            if answer is not None:
                return self.supply_selection(answer)

        if not raw:
            if prompt.allow_enter:
                return self._advance(ENTER)
            self.messaged.emit("A value is required.")
            return False

        keyword = prompt.match_keyword(raw)
        if keyword is not None:
            return self._advance(keyword)

        value = self._interpret(prompt, raw)
        if value is None:
            self.messaged.emit("Invalid input: {0}".format(raw))
            self.promptChanged.emit(prompt.format())
            return False
        if prompt.kind == "point":
            self._last_point = value
        return self._advance(value)

    def _interpret(self, prompt, raw):
        """Parse *raw* according to *prompt*'s declared kind."""
        kind = prompt.kind

        if kind == "point":
            angle_base = self.context.variables.get("ANGBASE")
            clockwise = self.context.variables.clockwise_angles
            return coords.parse_and_resolve(
                raw, last_point=self._last_point,
                cursor_point=self._cursor_point(),
                angle_base=angle_base, clockwise=clockwise)

        if kind == "distance":
            return coords.parse_distance(raw)

        if kind == "angle":
            return coords.parse_angle(
                raw, self.context.variables.get("ANGBASE"),
                self.context.variables.clockwise_angles)

        if kind == "integer":
            try:
                value = int(float(raw))
            except (TypeError, ValueError):
                return None
            return prompt.clamp(value) if hasattr(prompt, "clamp") else value

        if kind in ("string", "text"):
            return raw

        if kind in ("keyword", "selection"):
            # Keywords were matched above; a selection is answered by picking
            # or by ALL, both handled before parsing ever gets here. Anything
            # else is a typo, and saying so beats handing a command a string
            # where it expects a list of picks.
            return None

        return raw

    def _cursor_point(self):
        """Current constrained cursor position, for direct distance entry."""
        pointer = getattr(self.context, "pointer", None)
        if pointer is not None:
            return pointer.current_point
        return None

    def escape(self):
        """Handle the Escape key."""
        if self.is_running:
            name = self.command_name
            try:
                self._generator.throw(GeneratorExit)
            except (StopIteration, GeneratorExit, RuntimeError):
                pass
            except Exception:                 # noqa: BLE001
                pass
            self._end_edit(commit=True)
            self.messaged.emit("*Cancel*")
            self._finish(name, completed=False)
        else:
            self._clear_prompt()

    def send_cancel(self):
        """Answer the current prompt with CANCEL without killing the command."""
        if self.is_running:
            return self._advance(CANCEL)
        return False
