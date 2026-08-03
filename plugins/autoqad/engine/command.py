# -*- coding: utf-8 -*-
"""The Command base class.

Pure module: no Qt, no QGIS beyond what the document exposes.

A command is a **generator**. It yields prompts and receives answers::

    class LineCommand(Command):
        name = "LINE"
        aliases = ("L",)

        def run(self):
            previous = yield PointPrompt("Specify first point")
            while True:
                point = yield PointPrompt("Specify next point or",
                                          options=["Close", "Undo"],
                                          rubber=RubberPolyline([previous]),
                                          base_point=previous)
                if point in (CANCEL, ENTER):
                    return
                self.document.add_curve(line_geometry(previous, point))
                previous = point

That is the whole control-flow model. AutoCAD's prompt sequences are naturally
coroutines, and expressing them as one collapses the explicit step-integer state
machines that make hand-written CAD command code so bulky — the prompt order is
just the order the code reads in.

Commands receive a :class:`CommandContext` giving them the document, the
variables, the canvas and message output. They never touch widgets.
"""

from .prompt import CANCEL, ENTER


class CommandContext(object):
    """Everything a command is allowed to reach.

    Deliberately narrow: a command gets data and services, never widgets. That
    is what lets the identical command run from the mouse, the command line, or
    an LLM through the scripting facade.
    """

    def __init__(self, document, variables, canvas=None, iface=None,
                 message=None, history=None):
        self.document = document
        self.variables = variables
        self.canvas = canvas
        self.iface = iface
        self._message = message
        self.history = history

    def write(self, text):
        """Echo a line to the command history pane."""
        if self._message is not None:
            self._message(text)


class Command(object):
    """Base class for every AutoQAD command.

    Subclasses set :attr:`name` (and optionally :attr:`aliases`) and implement
    :meth:`run` as a generator.
    """

    #: The command name as typed (upper case).
    name = ""
    #: Alternative names, AutoCAD's command aliases (``L`` for ``LINE``).
    aliases = ()
    #: One-line description shown by HELP and the scripting API reference.
    description = ""
    #: Which UI group the command belongs to, for the icon rail.
    group = "draw"
    #: When True the command edits the drawing and needs an undo transaction.
    modifies = True
    #: When True the command needs a selection before it can prompt.
    needs_selection = False

    def __init__(self, context):
        self.context = context

    # ---- convenience accessors ----

    @property
    def document(self):
        return self.context.document

    @property
    def variables(self):
        return self.context.variables

    @property
    def canvas(self):
        return self.context.canvas

    def write(self, text):
        self.context.write(text)

    def var(self, name):
        return self.variables.get(name)

    def set_var(self, name, value):
        return self.variables.set(name, value)

    # ---- the coroutine ----

    def run(self):                            # pragma: no cover - overridden
        """Implement as a generator yielding prompts.

        Yielding a :class:`~.prompt.Prompt` suspends the command until the
        runner supplies an answer. Returning ends the command normally.
        """
        raise NotImplementedError(
            "{0} must implement run() as a generator".format(type(self).__name__))

    # ---- helpers shared by many commands ----

    @staticmethod
    def is_finished(answer):
        """True when *answer* means "stop here" — Escape or a bare Enter."""
        return answer is CANCEL or answer is ENTER

    @staticmethod
    def is_cancelled(answer):
        return answer is CANCEL

    def current_layer_name(self):
        return self.var("CLAYER")

    def angle_frame(self):
        """Return ``(angle_base_degrees, clockwise)`` for coordinate maths."""
        return (self.var("ANGBASE"), self.variables.clockwise_angles)
