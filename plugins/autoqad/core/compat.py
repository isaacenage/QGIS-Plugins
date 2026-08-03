# -*- coding: utf-8 -*-
"""Qt5/Qt6 and QGIS 3.22 - 4.x compatibility shims.

AutoQAD targets QGIS 3.22 through 4.99, which spans the PyQt5 -> PyQt6 and
Qt5 -> Qt6 transitions. Two classes of breakage matter:

1. **Enum scoping.** Qt6 removed the unscoped aliases (``Qt.AlignLeft``); only
   the scoped form (``Qt.AlignmentFlag.AlignLeft``) exists. The scoped form is
   valid on Qt5 too, so AutoQAD *always* writes the scoped form directly and
   needs no helper for Qt itself. QGIS's own enums moved the other way over
   time (``QgsWkbTypes.LineGeometry`` -> ``Qgis.GeometryType.Line``), so those
   go through :func:`enum_member` / the resolved constants below.

2. **Field types.** ``QgsField`` took a ``QVariant.Type`` historically; QGIS
   3.38 deprecated that in favour of ``QMetaType.Type``, and QGIS 4 may drop
   the old overload. :func:`make_field` picks whichever the running build
   accepts.

Nothing here does any work at import time beyond resolving a handful of enum
members, so importing this module is cheap and safe on every supported build.
"""

from qgis.PyQt.QtCore import QVariant

try:                                     # Qt6 / PyQt6
    from qgis.PyQt.QtGui import QAction  # noqa: F401
except ImportError:                      # pragma: no cover - Qt5 / PyQt5
    from qgis.PyQt.QtWidgets import QAction  # noqa: F401

from qgis.core import QgsField, QgsWkbTypes

try:
    from qgis.core import Qgis
except ImportError:                      # pragma: no cover - very old builds
    Qgis = None


def enum_member(owner, scope_name, member_name):
    """Return ``owner.member_name``, falling back to ``owner.scope_name.member``.

    Handles the QGIS/Qt migration from unscoped enum aliases to nested scoped
    enums without the caller caring which build is running.
    """
    try:
        return getattr(owner, member_name)
    except AttributeError:
        return getattr(getattr(owner, scope_name), member_name)


def _geometry_type(name):
    """Resolve a geometry-type enum across QGIS 3.22 - 4.x."""
    if Qgis is not None:
        try:
            return getattr(Qgis.GeometryType, name)
        except AttributeError:
            pass
    return getattr(QgsWkbTypes, name + "Geometry")


# Geometry types, resolved once.
GEOM_POINT = _geometry_type("Point")
GEOM_LINE = _geometry_type("Line")
GEOM_POLYGON = _geometry_type("Polygon")


def _render_unit(name):
    """Resolve a render unit across QGIS 3.22 - 4.x.

    ``QgsUnitTypes.RenderMillimeters`` became ``Qgis.RenderUnit.Millimeters``.
    """
    if Qgis is not None:
        try:
            return getattr(Qgis.RenderUnit, name)
        except AttributeError:
            pass
    from qgis.core import QgsUnitTypes
    legacy = {"Millimeters": "RenderMillimeters",
              "MapUnits": "RenderMapUnits",
              "Pixels": "RenderPixels",
              "Points": "RenderPoints"}
    return getattr(QgsUnitTypes, legacy[name])


RENDER_MM = _render_unit("Millimeters")
RENDER_MAP_UNITS = _render_unit("MapUnits")
RENDER_PIXELS = _render_unit("Pixels")


# --- field construction ------------------------------------------------------

def _metatype(kind):
    """Return the QMetaType member for *kind*, or None if unavailable."""
    try:
        from qgis.PyQt.QtCore import QMetaType
    except ImportError:                  # pragma: no cover
        return None
    return getattr(QMetaType.Type, kind, None)


_VARIANT_TYPES = {
    "String": QVariant.String,
    "Int": QVariant.Int,
    "Double": QVariant.Double,
    "Bool": QVariant.Bool,
}

_METATYPE_NAMES = {
    "String": "QString",
    "Int": "Int",
    "Double": "Double",
    "Bool": "Bool",
}


def make_field(name, kind, length=0, precision=0):
    """Build a :class:`QgsField` named *name* of *kind*.

    *kind* is one of ``"String"``, ``"Int"``, ``"Double"``, ``"Bool"``. Prefers
    the modern ``QMetaType``-based constructor and falls back to the
    ``QVariant``-based one on builds that predate it.
    """
    meta = _metatype(_METATYPE_NAMES[kind])
    if meta is not None:
        try:
            return QgsField(name, meta, len=length, prec=precision)
        except (TypeError, ValueError):
            pass
    return QgsField(name, _VARIANT_TYPES[kind], len=length, prec=precision)


def exec_dialog(dialog):
    """Run *dialog* modally across PyQt5 (``exec_``) and PyQt6 (``exec``)."""
    runner = getattr(dialog, "exec", None) or getattr(dialog, "exec_")
    return runner()
