# -*- coding: utf-8 -*-
"""AutoQAD system variables — the SETVAR store.

Mirrors AutoCAD's system variables: a flat, typed, named store that both the UI
and the command line read and write (``OSMODE``, ``ORTHOMODE``, ``LTSCALE`` …).
Keeping every tunable here means a command never reaches into a dialog for
state, and the whole drafting configuration serialises as one dict.

Scope follows AutoCAD's own split:

* **Drawing** variables live in the project and travel with the ``.qgz``
  (LTSCALE, CELTYPE, CLAYER, ANGBASE …).
* **Application** variables live in ``QSettings`` and follow the user across
  projects (APERTURE, PICKBOX, AUTOSNAP colours, cursor size …).

Pure Python plus ``QSettings``/``QgsProject`` for persistence; the value logic
itself is Qt-free and unit-testable.
"""

from qgis.PyQt.QtCore import QObject, QSettings, pyqtSignal

_SETTINGS_GROUP = "AutoQAD"
_PROJECT_SCOPE = "AutoQAD"

# Object snap bit flags — the OSMODE bitmask, matching AutoCAD's values.
OSNAP_END = 1           # endpoint
OSNAP_MID = 2           # midpoint
OSNAP_CEN = 4           # center
OSNAP_NODE = 8          # node / point
OSNAP_QUA = 16          # quadrant
OSNAP_INT = 32          # intersection
OSNAP_INS = 64          # insertion
OSNAP_PER = 128         # perpendicular
OSNAP_TAN = 256         # tangent
OSNAP_NEA = 512         # nearest
OSNAP_NONE = 1024       # clear all
OSNAP_APP = 2048        # apparent intersection
OSNAP_EXT = 4096        # extension
OSNAP_PAR = 8192        # parallel

#: Ordered ``(flag, short, label)`` triples for the drafting-settings UI.
OSNAP_MODES = (
    (OSNAP_END, "END", "Endpoint"),
    (OSNAP_MID, "MID", "Midpoint"),
    (OSNAP_CEN, "CEN", "Center"),
    (OSNAP_NODE, "NOD", "Node"),
    (OSNAP_QUA, "QUA", "Quadrant"),
    (OSNAP_INT, "INT", "Intersection"),
    (OSNAP_INS, "INS", "Insertion"),
    (OSNAP_PER, "PER", "Perpendicular"),
    (OSNAP_TAN, "TAN", "Tangent"),
    (OSNAP_NEA, "NEA", "Nearest"),
    (OSNAP_APP, "APP", "Apparent intersection"),
    (OSNAP_EXT, "EXT", "Extension"),
    (OSNAP_PAR, "PAR", "Parallel"),
)

DEFAULT_OSMODE = (OSNAP_END | OSNAP_MID | OSNAP_CEN
                  | OSNAP_INT | OSNAP_PER | OSNAP_NEA)


class _Var(object):
    """One variable definition: type, default, scope and help text."""

    __slots__ = ("name", "kind", "default", "scope", "help")

    def __init__(self, name, kind, default, scope, help_text):
        self.name = name
        self.kind = kind              # "int" | "float" | "str" | "bool"
        self.default = default
        self.scope = scope            # "drawing" | "app"
        self.help = help_text


def _d(name, kind, default, help_text):
    return _Var(name, kind, default, "drawing", help_text)


def _a(name, kind, default, help_text):
    return _Var(name, kind, default, "app", help_text)


#: Every system variable AutoQAD understands.
DEFINITIONS = {v.name: v for v in (
    # --- drawing scope -----------------------------------------------------
    _d("CLAYER", "str", "0", "Current drawing layer."),
    _d("CECOLOR", "int", 256, "Current entity colour (ACI, 256 = ByLayer)."),
    _d("CELTYPE", "str", "BYLAYER", "Current entity linetype."),
    _d("CELWEIGHT", "int", -1, "Current entity lineweight (-1 = ByLayer)."),
    _d("CELTSCALE", "float", 1.0, "Current entity linetype scale."),
    _d("LTSCALE", "float", 1.0, "Global linetype scale."),
    _d("LWDISPLAY", "bool", True, "Display lineweights on screen."),
    _d("ORTHOMODE", "bool", False, "Constrain the cursor to the axes."),
    # On by default, as in AutoCAD: polar tracking is what makes the angle
    # readout and the alignment ray appear while dragging.
    _d("POLARMODE", "bool", True, "Polar tracking on."),
    _d("POLARANG", "float", 45.0, "Polar tracking increment, in degrees."),
    _d("OSMODE", "int", DEFAULT_OSMODE, "Running object-snap bitmask."),
    _d("OSNAPON", "bool", True, "Running object snaps enabled."),
    _d("OTRACK", "bool", False, "Object-snap tracking enabled."),
    _d("SNAPMODE", "bool", False, "Grid snap on."),
    _d("SNAPUNIT", "float", 0.5, "Grid snap spacing, in drawing units."),
    _d("GRIDMODE", "bool", False, "Grid display on."),
    _d("GRIDUNIT", "float", 1.0, "Grid spacing, in drawing units."),
    _d("ANGBASE", "float", 0.0, "Angle zero direction, degrees CCW from east."),
    _d("ANGDIR", "int", 0, "0 = counter-clockwise, 1 = clockwise."),
    _d("LUPREC", "int", 4, "Linear display precision, decimal places."),
    _d("AUPREC", "int", 2, "Angular display precision, decimal places."),
    _d("INSUNITS", "int", 6, "Drawing units (6 = metres, 4 = millimetres)."),
    _d("DIMSCALE", "float", 100.0, "Plot scale denominator (1:DIMSCALE)."),
    _d("HPNAME", "str", "ANSI31", "Current hatch pattern."),
    _d("HPSCALE", "float", 1.0, "Hatch pattern scale."),
    _d("HPANG", "float", 0.0, "Hatch pattern angle, in degrees."),
    _d("TEXTSIZE", "float", 0.2, "Default text height, in drawing units."),
    _d("DYNMODE", "bool", True, "Dynamic input near the cursor."),
    _d("BLIPMODE", "bool", False, "Mark picked points."),

    # --- application scope -------------------------------------------------
    _a("APERTURE", "int", 10, "Object-snap target height, in pixels."),
    _a("PICKBOX", "int", 5, "Entity-selection pick box, in pixels."),
    _a("CURSORSIZE", "int", 5, "Crosshair size, as a percent of the screen."),
    _a("CURSORCOLOR", "str", "#3c4650", "Crosshair colour."),
    _a("PICKBOXCOLOR", "str", "#3c4650", "Pick box and aperture colour."),
    _a("CROSSHAIR", "bool", True,
       "Draw the AutoCAD crosshair instead of the system pointer."),
    _a("AUTOSNAPSIZE", "int", 10, "Snap marker size, in pixels."),
    _a("AUTOSNAPCOLOR", "str", "#f2c200", "Snap marker colour."),
    _a("TRACKCOLOR", "str", "#7d8b99", "Tracking/alignment line colour."),
    _a("RUBBERCOLOR", "str", "#2b7de9", "Rubber-band preview colour."),
    _a("HIGHLIGHTCOLOR", "str", "#2b7de9", "Selection highlight colour."),
    _a("GRIPCOLOR", "str", "#2b7de9", "Unselected grip colour."),
    _a("GRIPHOT", "str", "#d13438", "Selected (hot) grip colour."),
    _a("GRIPSIZE", "int", 7, "Grip box size, in pixels."),
    _a("MOVETHROTTLE", "int", 16, "Pointer pipeline interval, in ms."),
    _a("SNAPMARKERS", "bool", True, "Draw snap markers."),
    _a("CMDECHO", "bool", True, "Echo commands to the history pane."),
)}


def _coerce(kind, value):
    """Coerce a stored value (often a string, via QSettings) to *kind*."""
    if kind == "bool":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on")
    if kind == "int":
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
    if kind == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return "" if value is None else str(value)


class VariableStore(QObject):
    """Live system-variable store for one AutoQAD session.

    Emits :attr:`changed` with the variable name whenever a value actually
    changes, so the status toggles and the pointer pipeline can react without
    polling.
    """

    changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = {}
        self.reset_all()
        self._load_app_scope()

    # ---- access ----

    def get(self, name):
        """Return the current value of *name* (its default if never set)."""
        key = str(name).upper()
        if key not in DEFINITIONS:
            raise KeyError("Unknown system variable: {0}".format(name))
        return self._values[key]

    def set(self, name, value):
        """Set *name*, coercing to its declared type. Returns the stored value."""
        key = str(name).upper()
        definition = DEFINITIONS.get(key)
        if definition is None:
            raise KeyError("Unknown system variable: {0}".format(name))
        coerced = _coerce(definition.kind, value)
        if self._values.get(key) != coerced:
            self._values[key] = coerced
            if definition.scope == "app":
                self._save_app_var(key, coerced)
            self.changed.emit(key)
        return coerced

    def toggle(self, name):
        """Flip a boolean variable and return the new value."""
        return self.set(name, not bool(self.get(name)))

    def reset_all(self):
        self._values = {k: v.default for k, v in DEFINITIONS.items()}

    def names(self, scope=None):
        return sorted(k for k, v in DEFINITIONS.items()
                      if scope is None or v.scope == scope)

    def describe(self, name):
        definition = DEFINITIONS.get(str(name).upper())
        return definition.help if definition else ""

    # ---- convenience accessors used on the hot path ----

    @property
    def osnap_enabled(self):
        return bool(self.get("OSNAPON")) and self.get("OSMODE") != 0

    def osnap_active(self, flag):
        """True when object-snap *flag* is in the running snap mask."""
        return bool(self.get("OSMODE") & flag)

    def set_osnap(self, flag, enabled):
        mask = self.get("OSMODE")
        mask = (mask | flag) if enabled else (mask & ~flag)
        return self.set("OSMODE", mask)

    @property
    def clockwise_angles(self):
        return int(self.get("ANGDIR")) == 1

    # ---- persistence ----

    def _load_app_scope(self):
        settings = QSettings()
        settings.beginGroup(_SETTINGS_GROUP)
        for name, definition in DEFINITIONS.items():
            if definition.scope != "app":
                continue
            if settings.contains(name):
                self._values[name] = _coerce(definition.kind,
                                             settings.value(name))
        settings.endGroup()

    def _save_app_var(self, name, value):
        settings = QSettings()
        settings.beginGroup(_SETTINGS_GROUP)
        settings.setValue(name, value)
        settings.endGroup()

    def to_dict(self, scope="drawing"):
        """Serialise one scope for storage in the project file."""
        return {k: self._values[k] for k, v in DEFINITIONS.items()
                if v.scope == scope}

    def load_dict(self, data, scope="drawing"):
        """Restore values previously produced by :meth:`to_dict`."""
        for name, value in (data or {}).items():
            key = str(name).upper()
            definition = DEFINITIONS.get(key)
            if definition is None or definition.scope != scope:
                continue
            self._values[key] = _coerce(definition.kind, value)
        self.changed.emit("*")

    def save_to_project(self, project):
        """Write the drawing scope into *project* under the AutoQAD scope."""
        import json
        project.writeEntry(_PROJECT_SCOPE, "variables",
                           json.dumps(self.to_dict("drawing")))

    def load_from_project(self, project):
        """Read the drawing scope back out of *project*."""
        import json
        raw, ok = project.readEntry(_PROJECT_SCOPE, "variables", "")
        if not ok or not raw:
            self.load_dict({k: v.default for k, v in DEFINITIONS.items()
                            if v.scope == "drawing"})
            return False
        try:
            self.load_dict(json.loads(raw))
        except (ValueError, TypeError):
            return False
        return True
