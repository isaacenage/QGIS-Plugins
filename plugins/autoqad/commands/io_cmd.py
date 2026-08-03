# -*- coding: utf-8 -*-
"""Import/export commands — DXFOUT, DXFIN."""

from ..engine.command import Command


class DxfOutCommand(Command):
    """Write the drawing to a DXF file."""

    name = "DXFOUT"
    aliases = ("EXPORTDXF", "SAVEDXF")
    description = "Export the drawing to a DXF file."
    group = "tools"
    modifies = False

    def run(self):
        opener = getattr(self.context, "open_dialog", None)
        if opener is None:
            self.write("DXFOUT needs the AutoQAD user interface.")
        else:
            opener("dxfout")
        return
        yield        # noqa: unreachable - keeps run() a generator


IO_COMMANDS = (DxfOutCommand,)
