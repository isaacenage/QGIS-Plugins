# -*- coding: utf-8 -*-
"""The AutoQAD command catalogue.

One place that knows every command. The runner, the command line's
autocompletion, the icon rail and the scripting API all read from the registry
built here, so adding a command to :data:`ALL_COMMANDS` makes it available
everywhere at once — typed, clicked, or driven by an agent.
"""

from ..engine.registry import CommandRegistry
from .draw import DRAW_COMMANDS
from .hatch import HATCH_COMMANDS
from .io_cmd import IO_COMMANDS
from .modify import MODIFY_COMMANDS
from .plot_cmd import PLOT_COMMANDS
from .tools import TOOL_COMMANDS

#: Every command AutoQAD ships, in the order they appear in the UI.
ALL_COMMANDS = (DRAW_COMMANDS + HATCH_COMMANDS + MODIFY_COMMANDS
                + TOOL_COMMANDS + IO_COMMANDS + PLOT_COMMANDS)


def build_registry():
    """Return a :class:`CommandRegistry` populated with every command."""
    return CommandRegistry().register_all(ALL_COMMANDS)
