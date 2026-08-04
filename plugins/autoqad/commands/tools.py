# -*- coding: utf-8 -*-
"""Utility commands — LAYER, SETVAR, UNITS, ID, DIST, AREA, UNDO, HELP …

Commands that open a dialog do so through ``context.open_dialog(name)`` rather
than importing a widget, keeping the "commands never touch the UI" rule intact
and leaving them runnable headless from the scripting facade.
"""

from ..engine.command import Command
from ..engine.prompt import (
    CANCEL, ENTER, KeywordPrompt, PointPrompt, SelectionPrompt, StringPrompt,
)
from ..geom import build, construct
from ..style import aci, cad_layer, linetypes


class _DialogCommand(Command):
    """A command whose whole job is to open a dialog."""

    dialog = ""
    modifies = False

    def run(self):
        opener = getattr(self.context, "open_dialog", None)
        if opener is None:
            self.write("{0} needs the AutoQAD user interface.".format(
                self.name))
        else:
            opener(self.dialog)
        return
        yield        # noqa: unreachable - keeps run() a generator


class LayerCommand(_DialogCommand):
    name = "LAYER"
    aliases = ("LA", "DDLMODES")
    description = "Open the Layer Manager."
    group = "tools"
    dialog = "layers"


class DraftingSettingsCommand(_DialogCommand):
    name = "DSETTINGS"
    aliases = ("DS", "SE", "OSNAP")
    description = "Open Drafting Settings (snap, grid, polar)."
    group = "tools"
    dialog = "dsettings"


class OptionsCommand(_DialogCommand):
    name = "OPTIONS"
    aliases = ("OP", "PREFERENCES")
    description = "Open AutoQAD Options."
    group = "tools"
    dialog = "options"


class HatchEditCommand(_DialogCommand):
    name = "HATCHEDIT"
    aliases = ("HE",)
    description = "Open the hatch pattern gallery."
    group = "tools"
    dialog = "patterns"


class MakeLayerCommand(Command):
    """Create a layer and make it current, without opening a dialog."""

    name = "MKLAYER"
    aliases = ("-LAYER",)
    description = "Create a CAD layer and make it current."
    group = "tools"
    modifies = False

    def run(self):
        name = yield StringPrompt("Enter new layer name")
        if self.is_finished(name) or not str(name).strip():
            return

        clean = cad_layer.sanitize_name(name)
        existed = clean in self.document.layers
        layer = self.document.layers.get_or_create(clean)

        if not existed:
            colour = yield StringPrompt(
                "Enter colour (ACI number or name)", default="7")
            if colour not in (CANCEL, ENTER) and str(colour).strip():
                layer.color = self._parse_colour(colour)

            linetype = yield StringPrompt("Enter linetype",
                                          default=linetypes.CONTINUOUS)
            if linetype not in (CANCEL, ENTER) and str(linetype).strip():
                candidate = str(linetype).upper()
                if candidate in self.document.linetype_table:
                    layer.linetype = candidate

        self.document.layers.set_current(clean)
        self.set_var("CLAYER", clean)
        self.document.restyle_layer(clean)
        self.document.save_state()
        self.write("Current layer is now '{0}'.".format(clean))

    @staticmethod
    def _parse_colour(text):
        value = str(text).strip()
        try:
            return max(0, min(255, int(value)))
        except ValueError:
            pass
        lookup = {name.lower(): index for index, name in aci.NAMES.items()}
        return lookup.get(value.lower(), 7)


class SetVarCommand(Command):
    """Read or write a system variable."""

    name = "SETVAR"
    aliases = ("SET",)
    description = "Read or set a system variable."
    group = "tools"
    modifies = False

    def run(self):
        name = yield StringPrompt("Enter variable name or", options=["?"])
        if self.is_finished(name):
            return

        if name == "?":
            self.write("Variables: " + ", ".join(self.variables.names()))
            return

        key = str(name).strip().upper()
        try:
            current = self.variables.get(key)
        except KeyError:
            self.write("Unknown variable: {0}".format(key))
            return

        self.write("{0} = {1}  ({2})".format(
            key, current, self.variables.describe(key)))

        value = yield StringPrompt(
            "Enter new value for {0}".format(key), default=current)
        if value in (CANCEL, ENTER):
            return

        try:
            self.variables.set(key, value)
        except KeyError:
            return
        self.write("{0} set to {1}".format(key, self.variables.get(key)))


class IdCommand(Command):
    """Report the coordinates of a point."""

    name = "ID"
    description = "Report the coordinates of a point."
    group = "tools"
    modifies = False

    def run(self):
        point = yield PointPrompt("Specify point")
        if self.is_finished(point):
            return
        precision = int(self.var("LUPREC"))
        self.write("X = {0:.{p}f}   Y = {1:.{p}f}".format(
            point[0], point[1], p=precision))


class DistanceCommand(Command):
    """Measure between two points."""

    name = "DIST"
    aliases = ("DI", "MEASUREGEOM")
    description = "Measure the distance and angle between two points."
    group = "tools"
    modifies = False

    def run(self):
        first = yield PointPrompt("Specify first point")
        if self.is_finished(first):
            return
        from ..engine.prompt import RubberLine
        second = yield PointPrompt("Specify second point",
                                   rubber=RubberLine(first), base_point=first)
        if self.is_finished(second):
            return

        length = construct.distance(first, second)
        angle = construct.angle_of(first, second)
        precision = int(self.var("LUPREC"))
        angle_precision = int(self.var("AUPREC"))

        from ..input.coords import from_math_angle
        display_angle = from_math_angle(
            angle, self.var("ANGBASE"), self.variables.clockwise_angles)

        self.write(
            "Distance = {0:.{p}f},  Angle = {1:.{a}f},  "
            "Delta X = {2:.{p}f},  Delta Y = {3:.{p}f}".format(
                length, display_angle,
                second[0] - first[0], second[1] - first[1],
                p=precision, a=angle_precision))


class AreaCommand(Command):
    """Report the area and perimeter of a selection or a picked polygon."""

    name = "AREA"
    aliases = ("AA",)
    description = "Report area and perimeter."
    group = "tools"
    modifies = False

    def run(self):
        selection = yield SelectionPrompt("Select objects to measure")
        if self.is_finished(selection) or not selection:
            return

        total_area = 0.0
        total_length = 0.0
        for table_name, feature_id in selection:
            layer = self.document.table(table_name)
            if layer is None:
                continue
            try:
                feature = layer.getFeature(feature_id)
            except (RuntimeError, KeyError):
                continue
            geometry = feature.geometry() if feature is not None else None
            if geometry is None or geometry.isEmpty():
                continue

            total_length += geometry.length()
            if geometry.type() == 2:          # polygon
                total_area += geometry.area()
            else:
                points = build.vertices_of(geometry)
                if len(points) > 3 and construct.are_coincident(points[0],
                                                                points[-1]):
                    closed = build.polygon(points)
                    if closed is not None:
                        total_area += closed.area()

        precision = int(self.var("LUPREC"))
        self.write("Area = {0:.{p}f},  Perimeter = {1:.{p}f}".format(
            total_area, total_length, p=precision))


class UnitsCommand(Command):
    """Set linear/angular precision and the drawing's angle frame."""

    name = "UNITS"
    aliases = ("UN", "DDUNITS")
    description = "Set drawing units, precision and angle direction."
    group = "tools"
    modifies = False

    def run(self):
        precision = yield StringPrompt("Linear precision (decimal places)",
                                       default=self.var("LUPREC"))
        if precision not in (CANCEL, ENTER):
            try:
                self.set_var("LUPREC", max(0, min(8, int(precision))))
            except (TypeError, ValueError):
                pass

        angular = yield StringPrompt("Angular precision (decimal places)",
                                     default=self.var("AUPREC"))
        if angular not in (CANCEL, ENTER):
            try:
                self.set_var("AUPREC", max(0, min(8, int(angular))))
            except (TypeError, ValueError):
                pass

        base = yield StringPrompt(
            "Angle zero direction in degrees (0 = east, 90 = north)",
            default=self.var("ANGBASE"))
        if base not in (CANCEL, ENTER):
            try:
                self.set_var("ANGBASE", float(base))
            except (TypeError, ValueError):
                pass

        direction = yield KeywordPrompt(
            "Angle direction", ["Counterclockwise", "Clockwise"],
            default="Counterclockwise")
        if direction == "Clockwise":
            self.set_var("ANGDIR", 1)
        elif direction == "Counterclockwise":
            self.set_var("ANGDIR", 0)

        self.write("Units updated.")


class UndoCommand(Command):
    name = "UNDO"
    aliases = ("U",)
    description = "Undo the last operation."
    group = "tools"
    modifies = False

    def run(self):
        undone = 0
        for table in self.document.all_tables():
            if table.isEditable() and table.undoStack().canUndo():
                table.undoStack().undo()
                undone += 1
        self.document.refresh()
        self.write("Undo." if undone else "Nothing to undo.")
        return
        yield        # noqa: unreachable - keeps run() a generator


class RedoCommand(Command):
    name = "REDO"
    description = "Redo the last undone operation."
    group = "tools"
    modifies = False

    def run(self):
        redone = 0
        for table in self.document.all_tables():
            if table.isEditable() and table.undoStack().canRedo():
                table.undoStack().redo()
                redone += 1
        self.document.refresh()
        self.write("Redo." if redone else "Nothing to redo.")
        return
        yield        # noqa: unreachable - keeps run() a generator


class SaveDrawingCommand(Command):
    """Write pending edits to the drawing's storage.

    Commands leave their edits in each table's buffer so the undo stacks
    survive — committing clears them. That flush normally happens when the
    session ends or the project is saved; this is the explicit "write it now".
    """

    name = "QSAVE"
    aliases = ("SAVEDWG",)
    description = "Write pending drawing edits to storage."
    group = "tools"
    modifies = False

    def run(self):
        if not self.document.is_open:
            self.write("No drawing is open.")
        elif self.document.commit():
            self.write("Drawing saved.")
        else:
            self.write("Some edits could not be written. Check the log.")
        return
        yield        # noqa: unreachable - keeps run() a generator


class EraseAllCommand(Command):
    """Delete every entity in the drawing, leaving the CAD layers behind.

    ``ERASE`` with the ``ALL`` keyword does the same thing; this is the
    version you can put on a button, and it confirms first because there is no
    selection step to make the scope obvious.
    """

    name = "ERASEALL"
    aliases = ("DELALL",)
    description = "Delete every object in the drawing."
    group = "modify"

    def run(self):
        total = self.document.count()
        if not total:
            self.write("The drawing is already empty.")
            return

        answer = yield KeywordPrompt(
            "Delete all {0} object(s)?".format(total), ["Yes", "No"],
            default="No")
        if answer != "Yes":
            self.write("Nothing erased.")
            return

        self.write("{0} object(s) erased.".format(self.document.clear()))


class HelpCommand(Command):
    name = "HELP"
    aliases = ("?",)
    description = "List the available commands."
    group = "tools"
    modifies = False

    def run(self):
        registry = getattr(self.context, "registry", None)
        if registry is None:
            self.write("No command registry available.")
            return

        for group in registry.groups():
            names = []
            for command in registry.by_group(group):
                alias = ", ".join(command.aliases)
                names.append("{0}{1}".format(
                    command.name, " ({0})".format(alias) if alias else ""))
            self.write("{0}: {1}".format(group.title(), ", ".join(names)))
        return
        yield        # noqa: unreachable - keeps run() a generator


class PurgeCommand(Command):
    """Remove CAD layers that hold no entities."""

    name = "PURGE"
    aliases = ("PU",)
    description = "Delete empty CAD layers."
    group = "tools"
    modifies = False

    def run(self):
        used = set()
        for table in self.document.all_tables():
            index = table.fields().indexOf("aq_layer")
            if index >= 0:
                used.update(v for v in table.uniqueValues(index) if v)

        removed = []
        for name in list(self.document.layers.names()):
            if name == cad_layer.DEFAULT_LAYER or name in used:
                continue
            if self.document.layers.remove(name):
                removed.append(name)

        self.document.save_state()
        self.write("Purged {0} empty layer(s).".format(len(removed))
                   if removed else "No empty layers to purge.")
        return
        yield        # noqa: unreachable - keeps run() a generator


TOOL_COMMANDS = (
    LayerCommand, MakeLayerCommand, DraftingSettingsCommand, OptionsCommand,
    HatchEditCommand, SetVarCommand, IdCommand, DistanceCommand, AreaCommand,
    UnitsCommand, UndoCommand, RedoCommand, SaveDrawingCommand,
    EraseAllCommand, HelpCommand, PurgeCommand,
)
