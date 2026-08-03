# -*- coding: utf-8 -*-
"""The AutoQAD scripting API — drive the plugin from code or from an LLM.

This is the supported programmatic entry point. AutoQAD registers no Processing
algorithm; automation clients (QGIS MCP calling ``execute_code``, or a plain
PyQGIS script) come through here::

    aq = qgis.utils.plugins['autoqad']
    aq.command("LINE 0,0 10,0 10,8 0,8 C")
    aq.draw({"layers": [...], "entities": [...]})
    aq.list_layers(); aq.api_reference()

Two surfaces, deliberately:

* :func:`run_macro` takes an **AutoCAD macro string** and feeds its tokens
  through the ordinary command runner, one prompt at a time. The command cannot
  tell the input came from a string rather than a mouse — which means anything
  a user can draw, an agent can drive, with no parallel code path to keep in
  sync.
* :func:`build_drawing` takes a **structured spec** and is the better fit for
  generating a whole drawing at once. It goes through the same document API the
  commands use.

:func:`spec_to_operations` is pure — no QGIS, no Qt — so the whole translation
layer is unit-testable, and it reports problems as *warnings* rather than
exceptions: an agent that names a missing layer gets a usable drawing plus a
note, not a traceback.
"""

import shlex

from .style import aci, hatches, linetypes, lineweights

#: Entity types :func:`build_drawing` understands.
ENTITY_TYPES = ("line", "polyline", "rectangle", "circle", "arc", "polygon",
                "ellipse", "point", "text", "hatch")


# --- pure translation --------------------------------------------------------

def _as_point(value):
    """Coerce ``[x, y]`` (or a tuple) into a float pair, or ``None``."""
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None


def _as_points(value):
    if not isinstance(value, (list, tuple)):
        return []
    points = [_as_point(item) for item in value]
    return [p for p in points if p is not None]


def spec_to_operations(spec):
    """Normalise a drawing *spec* into ``(operations, warnings)``.

    Pure: takes and returns plain data. Every operation is a dict the executor
    can apply directly; every problem is reported as a warning string rather
    than raised, so a partially valid spec still produces a drawing.
    """
    warnings = []
    operations = {"layers": [], "variables": {}, "entities": [],
                  "commands": []}

    if not isinstance(spec, dict):
        return (operations, ["Spec must be a dict."])

    # --- layers ---
    for entry in spec.get("layers", []) or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            warnings.append("Skipped a layer with no name.")
            continue

        colour = entry.get("color", 7)
        if isinstance(colour, str):
            lookup = {v.lower(): k for k, v in aci.NAMES.items()}
            resolved = lookup.get(colour.strip().lower())
            if resolved is None:
                warnings.append(
                    "Unknown colour '{0}' on layer '{1}' — using 7.".format(
                        colour, entry["name"]))
                resolved = 7
            colour = resolved

        linetype = str(entry.get("linetype", linetypes.CONTINUOUS)).upper()
        if linetype not in linetypes.STANDARD:
            warnings.append(
                "Unknown linetype '{0}' on layer '{1}' — using CONTINUOUS."
                .format(linetype, entry["name"]))
            linetype = linetypes.CONTINUOUS

        weight = entry.get("lineweight", lineweights.DEFAULT)
        try:
            weight = lineweights.snap_to_ladder(int(weight))
        except (TypeError, ValueError):
            warnings.append(
                "Bad lineweight on layer '{0}' — using default.".format(
                    entry["name"]))
            weight = lineweights.DEFAULT

        operations["layers"].append({
            "name": str(entry["name"]),
            "color": int(colour),
            "linetype": linetype,
            "lineweight": int(weight),
            "on": bool(entry.get("on", True)),
            "frozen": bool(entry.get("frozen", False)),
            "locked": bool(entry.get("locked", False)),
            "description": str(entry.get("description", "")),
        })

    # --- variables ---
    for name, value in (spec.get("variables") or {}).items():
        operations["variables"][str(name).upper()] = value

    # --- entities ---
    for index, entry in enumerate(spec.get("entities", []) or []):
        operation, problem = _entity_operation(entry, index)
        if problem:
            warnings.append(problem)
        if operation is not None:
            operations["entities"].append(operation)

    # --- raw command macros ---
    for entry in spec.get("commands", []) or []:
        if isinstance(entry, str) and entry.strip():
            operations["commands"].append(entry.strip())

    return (operations, warnings)


def _entity_operation(entry, index):
    """Validate one entity spec. Returns ``(operation_or_None, warning)``."""
    label = "entity #{0}".format(index + 1)
    if not isinstance(entry, dict):
        return (None, "Skipped {0}: not an object.".format(label))

    kind = str(entry.get("type", "")).strip().lower()
    if kind not in ENTITY_TYPES:
        return (None, "Skipped {0}: unknown type '{1}'. Valid types: {2}."
                .format(label, kind, ", ".join(ENTITY_TYPES)))

    operation = {
        "type": kind,
        "layer": entry.get("layer"),
        "color": entry.get("color"),
        "linetype": entry.get("linetype"),
        "lineweight": entry.get("lineweight"),
    }

    if kind in ("line", "polyline"):
        points = _as_points(entry.get("points"))
        if len(points) < 2:
            return (None, "Skipped {0}: '{1}' needs at least 2 points."
                    .format(label, kind))
        operation["points"] = points
        operation["closed"] = bool(entry.get("closed", False))

    elif kind == "rectangle":
        corners = _as_points(entry.get("corners"))
        if len(corners) < 2:
            return (None,
                    "Skipped {0}: 'rectangle' needs 2 corner points."
                    .format(label))
        operation["corners"] = corners[:2]

    elif kind == "circle":
        centre = _as_point(entry.get("center") or entry.get("centre"))
        if centre is None:
            return (None, "Skipped {0}: 'circle' needs a center."
                    .format(label))
        try:
            radius = float(entry.get("radius", 0))
        except (TypeError, ValueError):
            radius = 0.0
        if radius <= 0:
            return (None, "Skipped {0}: 'circle' needs a positive radius."
                    .format(label))
        operation["center"] = centre
        operation["radius"] = radius

    elif kind == "arc":
        points = _as_points(entry.get("points"))
        if len(points) < 3:
            return (None,
                    "Skipped {0}: 'arc' needs 3 points (start, through, end)."
                    .format(label))
        operation["points"] = points[:3]

    elif kind == "polygon":
        centre = _as_point(entry.get("center") or entry.get("centre"))
        if centre is None:
            return (None, "Skipped {0}: 'polygon' needs a center."
                    .format(label))
        try:
            radius = float(entry.get("radius", 0))
            sides = int(entry.get("sides", 4))
        except (TypeError, ValueError):
            return (None, "Skipped {0}: bad radius or sides.".format(label))
        if radius <= 0 or sides < 3:
            return (None,
                    "Skipped {0}: needs radius > 0 and at least 3 sides."
                    .format(label))
        operation.update({"center": centre, "radius": radius, "sides": sides,
                          "inscribed": bool(entry.get("inscribed", True))})

    elif kind == "ellipse":
        centre = _as_point(entry.get("center") or entry.get("centre"))
        if centre is None:
            return (None, "Skipped {0}: 'ellipse' needs a center."
                    .format(label))
        try:
            major = float(entry.get("major_radius", 0))
            minor = float(entry.get("minor_radius", 0))
        except (TypeError, ValueError):
            return (None, "Skipped {0}: bad ellipse radii.".format(label))
        if major <= 0 or minor <= 0:
            return (None, "Skipped {0}: ellipse radii must be positive."
                    .format(label))
        operation.update({"center": centre, "major_radius": major,
                          "minor_radius": minor,
                          "rotation": float(entry.get("rotation", 0.0))})

    elif kind in ("point", "text"):
        position = _as_point(entry.get("at") or entry.get("position"))
        if position is None:
            return (None, "Skipped {0}: '{1}' needs an 'at' point."
                    .format(label, kind))
        operation["at"] = position
        if kind == "text":
            content = entry.get("text")
            if not content:
                return (None, "Skipped {0}: 'text' needs text content."
                        .format(label))
            operation["text"] = str(content)
            operation["height"] = entry.get("height")
            operation["rotation"] = float(entry.get("rotation", 0.0))

    elif kind == "hatch":
        boundary = _as_points(entry.get("boundary"))
        if len(boundary) < 3:
            return (None,
                    "Skipped {0}: 'hatch' needs a boundary of 3+ points."
                    .format(label))
        pattern = str(entry.get("pattern", "ANSI31")).upper()
        warning = None
        if pattern not in hatches.STANDARD:
            warning = ("Unknown hatch pattern '{0}' on {1} — using ANSI31."
                       .format(pattern, label))
            pattern = "ANSI31"
        operation.update({
            "boundary": boundary,
            "pattern": pattern,
            "scale": float(entry.get("scale", 1.0) or 1.0),
            "angle": float(entry.get("angle", 0.0) or 0.0),
        })
        return (operation, warning)

    return (operation, None)


# --- execution ---------------------------------------------------------------

def build_drawing(controller, spec):
    """Apply a *spec* to the drawing. Returns a result dict.

    The result carries ``{layers, entities, warnings, errors}`` so an agent can
    tell what actually landed without having to re-read the drawing.
    """
    operations, warnings = spec_to_operations(spec)
    document = controller.document

    if not document.is_open:
        crs = controller.canvas.mapSettings().destinationCrs()
        if not document.ensure_open(crs):
            return {"layers": 0, "entities": 0, "warnings": warnings,
                    "errors": ["Could not open the drawing tables."]}

    errors = []

    # Layers first — entities reference them.
    for entry in operations["layers"]:
        layer = document.layers.get_or_create(entry["name"])
        layer.color = entry["color"]
        layer.linetype = entry["linetype"]
        layer.lineweight = entry["lineweight"]
        layer.on = entry["on"]
        layer.frozen = entry["frozen"]
        layer.locked = entry["locked"]
        layer.description = entry["description"]

    for name, value in operations["variables"].items():
        try:
            controller.variables.set(name, value)
        except KeyError:
            warnings.append("Unknown system variable '{0}'.".format(name))

    created = 0
    for operation in operations["entities"]:
        try:
            if _create_entity(document, operation):
                created += 1
            else:
                warnings.append("Could not create a '{0}' entity.".format(
                    operation["type"]))
        except Exception as error:            # noqa: BLE001 - reported, not raised
            errors.append("{0}: {1}".format(operation["type"], error))

    for macro in operations["commands"]:
        result = run_macro(controller, macro)
        warnings.extend(result.get("warnings", []))
        errors.extend(result.get("errors", []))

    document.apply_renderers()
    document.save_state()
    document.refresh()

    return {
        "layers": len(operations["layers"]),
        "entities": created,
        "warnings": warnings,
        "errors": errors,
    }


def _create_entity(document, operation):
    """Create one entity through the ordinary document API."""
    from .geom import build

    kind = operation["type"]
    style = {
        "layer_name": operation.get("layer"),
        "color": operation.get("color"),
        "linetype": operation.get("linetype"),
        "lineweight": operation.get("lineweight"),
    }
    style = {k: v for k, v in style.items() if v is not None}

    if kind == "line":
        geometry = build.polyline(operation["points"])
        return document.add_curve(geometry, "LINE", **style) is not None

    if kind == "polyline":
        geometry = build.polyline(operation["points"],
                                  closed=operation["closed"])
        return document.add_curve(geometry, "PLINE",
                                  closed=operation["closed"],
                                  **style) is not None

    if kind == "rectangle":
        geometry = build.rectangle(operation["corners"][0],
                                   operation["corners"][1])
        return document.add_curve(geometry, "RECTANGLE", closed=True,
                                  **style) is not None

    if kind == "circle":
        geometry = build.circle(operation["center"], operation["radius"])
        return document.add_curve(geometry, "CIRCLE", closed=True,
                                  **style) is not None

    if kind == "arc":
        start, through, end = operation["points"]
        geometry = build.arc_three_points(start, through, end)
        return document.add_curve(geometry, "ARC", **style) is not None

    if kind == "polygon":
        geometry = build.regular_polygon(
            operation["center"], operation["radius"], operation["sides"],
            inscribed=operation["inscribed"])
        return document.add_curve(geometry, "POLYGON", closed=True,
                                  **style) is not None

    if kind == "ellipse":
        geometry = build.ellipse(
            operation["center"], operation["major_radius"],
            operation["minor_radius"], operation["rotation"])
        return document.add_curve(geometry, "ELLIPSE", closed=True,
                                  **style) is not None

    if kind == "point":
        return document.add_point(build.point(operation["at"]), "POINT",
                                  **style) is not None

    if kind == "text":
        return document.add_point(
            build.point(operation["at"]), "TEXT",
            text=operation["text"], height=operation.get("height"),
            rotation=operation.get("rotation", 0.0), **style) is not None

    if kind == "hatch":
        geometry = build.polygon(operation["boundary"])
        return document.add_hatch(
            geometry, pattern=operation["pattern"],
            pattern_scale=operation["scale"],
            pattern_angle=operation["angle"], **style) is not None

    return False


def run_macro(controller, text):
    """Run an AutoCAD-style macro string through the ordinary command runner.

    ``"LINE 0,0 10,0 10,8 C"`` starts LINE and feeds each token to the next
    prompt, exactly as if it had been typed. A bare token that the prompt
    cannot interpret ends the sequence with a warning rather than hanging.
    """
    warnings = []
    errors = []

    try:
        tokens = shlex.split(str(text))
    except ValueError as error:
        return {"ok": False, "warnings": [], "errors": [str(error)]}

    if not tokens:
        return {"ok": False, "warnings": ["Empty macro."], "errors": []}

    runner = controller.runner
    document = controller.document
    if not document.is_open:
        crs = controller.canvas.mapSettings().destinationCrs()
        if not document.ensure_open(crs):
            return {"ok": False, "warnings": [],
                    "errors": ["Could not open the drawing tables."]}

    command_name = tokens[0]
    if runner.registry.resolve(command_name) is None:
        return {"ok": False, "warnings": [],
                "errors": ["Unknown command: {0}".format(command_name)]}

    if not runner.start(command_name):
        return {"ok": False, "warnings": [],
                "errors": ["Could not start {0}.".format(command_name)]}

    for token in tokens[1:]:
        if not runner.is_running:
            warnings.append(
                "{0} finished before consuming '{1}'.".format(
                    command_name, token))
            break
        # A literal backslash or semicolon means "press Enter", as in an
        # AutoCAD script.
        value = "" if token in (";", "\\") else token
        if not runner.supply_text(value):
            warnings.append("'{0}' was not accepted at that prompt.".format(
                token))
            break

    if runner.is_running:
        # An unterminated macro (e.g. LINE with no closing Enter) is ended
        # cleanly rather than left waiting for a mouse that will never come.
        runner.supply_text("")
        if runner.is_running:
            runner.cancel()

    document.refresh()
    return {"ok": not errors, "warnings": warnings, "errors": errors}


# --- introspection -----------------------------------------------------------

def list_layers(controller):
    """Return every CAD layer with its properties."""
    return [{
        "name": layer.name,
        "color": layer.color,
        "color_name": aci.name(layer.color),
        "hex": layer.hex_color(),
        "linetype": layer.linetype,
        "lineweight": layer.lineweight,
        "lineweight_mm": lineweights.to_mm(layer.lineweight),
        "on": layer.on,
        "frozen": layer.frozen,
        "locked": layer.locked,
        "current": layer.name == controller.document.layers.current_name,
    } for layer in controller.document.layers.all()]


def list_commands(controller):
    """Return every command with its aliases, group and description."""
    return controller.registry.reference()


def list_patterns(controller):
    """Return the available hatch patterns and linetypes."""
    document = controller.document
    return {
        "hatch_patterns": [{
            "name": name,
            "description": hatches.get(name, document.pattern_table).description,
            "families": len(hatches.get(name, document.pattern_table).families),
        } for name in hatches.names(document.pattern_table)],
        "linetypes": [{
            "name": name,
            "description": linetypes.get(name,
                                         document.linetype_table).description,
            "continuous": linetypes.get(
                name, document.linetype_table).is_continuous,
        } for name in linetypes.names(document.linetype_table)],
        "lineweights_mm": [lineweights.to_mm(v) for v in lineweights.LADDER],
    }


def api_reference(controller=None):
    """Return the full scripting API reference as text.

    Built with a token substitution rather than ``str.format`` — the reference
    embeds a JSON schema, and its braces would be read as format fields.
    """
    command_lines = ""
    if controller is not None:
        for group in controller.registry.groups():
            names = ", ".join(c.name for c in controller.registry.by_group(group))
            command_lines += "\n  {0}: {1}".format(group, names)

    return _REFERENCE.replace(
        "@@COMMANDS@@", command_lines or " - (start a session to list)")


_REFERENCE = """AutoQAD scripting API
=====================
Access:  aq = qgis.utils.plugins['autoqad']

METHODS
  aq.command(text)          Run one macro string through the command runner.
  aq.draw(spec)             Build a whole drawing from a spec dict.
  aq.list_layers()          CAD layers and their properties.
  aq.list_commands()        Every command, alias and description.
  aq.list_patterns()        Hatch patterns, linetypes, lineweight ladder.
  aq.get_variable(name)     Read a system variable.
  aq.set_variable(n, v)     Write a system variable.
  aq.export_dxf(path)       Write the drawing to DXF. -> (ok, message)
  aq.api_reference()        This text.

MACRO STRINGS
  Tokens are fed to successive prompts, exactly as if typed:
    aq.command("LINE 0,0 10,0 10,8 0,8 C")
    aq.command("CIRCLE 5,4 2")
    aq.command("RECTANG 0,0 10,8")
  Coordinate forms: "10,20" absolute · "@10,20" relative
                    "10<45" polar    · "@10<45" relative polar
  ";" or "\\" in a macro means "press Enter".

SPEC SCHEMA  (aq.draw(spec))
  {
    "layers": [
      {"name": "A-WALL", "color": 7, "linetype": "CONTINUOUS",
       "lineweight": 35, "on": true, "frozen": false, "locked": false}
    ],
    "variables": {"LTSCALE": 1.0, "OSMODE": 39},
    "entities": [
      {"type": "line",      "layer": "A-WALL", "points": [[0,0],[10,0]]},
      {"type": "polyline",  "points": [[0,0],[10,0],[10,8]], "closed": true},
      {"type": "rectangle", "corners": [[0,0],[10,8]]},
      {"type": "circle",    "center": [5,4], "radius": 2},
      {"type": "arc",       "points": [[0,0],[1,1],[2,0]]},
      {"type": "polygon",   "center": [5,5], "radius": 3, "sides": 6,
                            "inscribed": true},
      {"type": "ellipse",   "center": [5,5], "major_radius": 4,
                            "minor_radius": 2, "rotation": 0.0},
      {"type": "point",     "at": [1,1]},
      {"type": "text",      "at": [1,1], "text": "LIVING", "height": 0.3},
      {"type": "hatch",     "boundary": [[0,0],[10,0],[10,8],[0,8]],
                            "pattern": "ANSI31", "scale": 1.0, "angle": 0}
    ],
    "commands": ["LINE 0,0 5,5"]
  }

  Every entity also accepts "layer", "color" (ACI 0-256, 256 = ByLayer),
  "linetype" and "lineweight" (hundredths of a mm, -1 = ByLayer).

  Returns {layers, entities, warnings, errors}. Unknown layers, patterns and
  linetypes produce warnings and a sensible fallback — never an exception.

LINEWEIGHTS   hundredths of a millimetre, snapped to the AutoCAD ladder:
  0 5 9 13 15 18 20 25 30 35 40 50 53 60 70 80 90 100 106 120 140 158 200 211

COLOURS       ACI index 1-255 (1 red, 2 yellow, 3 green, 4 cyan, 5 blue,
              6 magenta, 7 white/black), 256 = ByLayer.
COMMANDS@@COMMANDS@@
"""
