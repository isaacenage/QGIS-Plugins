# -*- coding: utf-8 -*-
"""DXF export — AutoQAD's drawings back out to CAD.

Two paths, and the plugin picks whichever is available:

* **ezdxf** (preferred, optional dependency) writes a real DXF with the CAD
  semantics intact — layer table with ACI colours, linetypes and lineweights,
  true ``ARC``/``CIRCLE`` entities from stored curves, ``LWPOLYLINE`` with
  bulges, and ``HATCH`` entities carrying their pattern name, scale and angle.
* **QgsDxfExport** (always present) is the fallback. It writes geometry and
  layer names correctly but flattens AutoQAD's symbology into QGIS symbology,
  so linetype and hatch-pattern fidelity is lost.

The three-table data model pays off here: ``aq_layer`` maps straight onto the
DXF layer name, and the CAD-truth fields (``aq_color``, ``aq_ltype``,
``aq_lw``) are already exactly what the DXF layer table wants.
"""

import os

from ..geom import build, construct
from ..style import linetypes

try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False


def is_available():
    """True when full-fidelity export is possible."""
    return HAS_EZDXF


def describe_backend():
    if HAS_EZDXF:
        return "ezdxf (full symbology fidelity)"
    return "QGIS DXF export (geometry only — install 'ezdxf' for linetypes, " \
           "lineweights and hatch patterns)"


def export(document, path, version="R2010"):
    """Write *document* to *path*. Returns ``(ok, message)``."""
    if not document or not document.is_open:
        return (False, "No drawing is open.")

    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        return (False, "Folder does not exist: {0}".format(directory))

    if HAS_EZDXF:
        return _export_ezdxf(document, path, version)
    return _export_qgis(document, path)


# --- ezdxf path --------------------------------------------------------------

def _export_ezdxf(document, path, version):
    drawing = ezdxf.new(version, setup=True)
    modelspace = drawing.modelspace()

    _write_layer_table(drawing, document)

    written = 0
    written += _write_curves(modelspace, document)
    written += _write_points(modelspace, document)
    written += _write_hatches(modelspace, document)

    try:
        drawing.saveas(path)
    except (IOError, OSError) as error:
        return (False, "Could not write {0}: {1}".format(path, error))

    return (True, "Exported {0} entities to {1}".format(
        written, os.path.basename(path)))


def _write_layer_table(drawing, document):
    """Recreate the CAD layer table, with colours, linetypes and lineweights."""
    for cad in document.layers.all():
        linetype_name = cad.linetype
        if linetype_name != linetypes.CONTINUOUS:
            _ensure_linetype(drawing, document, linetype_name)

        attributes = {
            "color": cad.color,
            "linetype": (linetype_name
                         if linetype_name in drawing.linetypes
                         else "CONTINUOUS"),
        }
        if cad.name in drawing.layers:
            layer = drawing.layers.get(cad.name)
            layer.dxf.color = cad.color
            layer.dxf.linetype = attributes["linetype"]
        else:
            layer = drawing.layers.add(cad.name, dxfattribs=attributes)

        # DXF stores lineweight in hundredths of a millimetre, which is
        # precisely how AutoQAD carries it — no conversion needed.
        try:
            layer.dxf.lineweight = int(cad.lineweight)
        except (AttributeError, ValueError):
            pass

        layer.off = not cad.on
        if cad.frozen:
            layer.freeze()
        layer.lock() if cad.locked else layer.unlock()
        try:
            layer.dxf.plot = 1 if cad.plottable else 0
            layer.transparency = cad.transparency / 100.0
        except (AttributeError, ValueError):
            pass


def _ensure_linetype(drawing, document, name):
    """Add a linetype definition to the DXF if it is not already there."""
    if name in drawing.linetypes:
        return
    pattern = document.linetype_table.get(name)
    if pattern is None or not pattern.elements:
        return
    total = sum(abs(e) or 0.0 for e in pattern.elements)
    try:
        drawing.linetypes.add(
            name,
            pattern=[total] + list(pattern.elements),
            description=pattern.description or name)
    except (ValueError, TypeError):
        pass


def _common_attribs(feature):
    """Translate an entity's CAD-truth fields into DXF attributes."""
    attribs = {"layer": feature.attribute("aq_layer") or "0"}

    colour = feature.attribute("aq_color")
    if colour is not None and int(colour) != 256:
        attribs["color"] = int(colour)

    linetype = feature.attribute("aq_ltype")
    if linetype and str(linetype).upper() not in ("BYLAYER", "BYBLOCK"):
        attribs["linetype"] = str(linetype).upper()

    weight = feature.attribute("aq_lw")
    if weight is not None and int(weight) >= 0:
        attribs["lineweight"] = int(weight)

    scale = feature.attribute("aq_ltscale")
    if scale is not None and float(scale) != 1.0:
        attribs["ltscale"] = float(scale)

    return attribs


def _write_curves(modelspace, document):
    """Write curves, preserving true arcs and circles where they exist."""
    table = document.table("aq_curves")
    if table is None:
        return 0

    written = 0
    for feature in table.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue

        attribs = _common_attribs(feature)
        entity_type = (feature.attribute("aq_type") or "").upper()
        points = build.vertices_of(geometry)
        if len(points) < 2:
            continue

        if entity_type == "CIRCLE":
            circle = _fit_circle(points)
            if circle is not None:
                centre, radius = circle
                modelspace.add_circle(centre, radius, dxfattribs=attribs)
                written += 1
                continue

        if entity_type == "ARC":
            arc = _fit_arc(points)
            if arc is not None:
                centre, radius, start_deg, end_deg = arc
                modelspace.add_arc(centre, radius, start_deg, end_deg,
                                   dxfattribs=attribs)
                written += 1
                continue

        closed = bool(feature.attribute("aq_closed"))
        modelspace.add_lwpolyline(
            [(p[0], p[1]) for p in points],
            format="xy",
            dxfattribs=dict(attribs, closed=closed))
        written += 1

    return written


def _fit_circle(points):
    """Recover a circle from a stored curve's vertices, if it is one."""
    if len(points) < 5:
        return None
    circle = construct.circle_from_three_points(
        points[0], points[len(points) // 3], points[2 * len(points) // 3])
    if circle is None:
        return None
    centre, radius = circle
    if radius <= 0:
        return None
    for sample in points:
        if abs(construct.distance(centre, sample) - radius) > radius * 0.01:
            return None
    if not construct.are_coincident(points[0], points[-1], radius * 0.01):
        return None
    return (centre, radius)


def _fit_arc(points):
    """Recover an arc's centre, radius and angle range from its vertices."""
    if len(points) < 3:
        return None
    import math
    result = construct.arc_three_points(
        points[0], points[len(points) // 2], points[-1])
    if result is None:
        return None
    centre, radius, start, end, ccw = result
    for sample in points:
        if abs(construct.distance(centre, sample) - radius) > radius * 0.01:
            return None
    start_deg = math.degrees(start) % 360.0
    end_deg = math.degrees(end) % 360.0
    if not ccw:
        start_deg, end_deg = end_deg, start_deg
    return (centre, radius, start_deg, end_deg)


def _write_points(modelspace, document):
    table = document.table("aq_points")
    if table is None:
        return 0

    written = 0
    for feature in table.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue
        vertex = geometry.asPoint()
        attribs = _common_attribs(feature)
        text = feature.attribute("aq_text")

        if text:
            height = feature.attribute("aq_height") or 1.0
            rotation = feature.attribute("aq_rot") or 0.0
            entity = modelspace.add_text(
                str(text),
                dxfattribs=dict(attribs, height=float(height),
                                rotation=float(rotation)))
            try:
                entity.set_placement((vertex.x(), vertex.y()))
            except AttributeError:        # pragma: no cover - older ezdxf
                entity.dxf.insert = (vertex.x(), vertex.y())
        else:
            modelspace.add_point((vertex.x(), vertex.y()),
                                 dxfattribs=attribs)
        written += 1

    return written


def _write_hatches(modelspace, document):
    """Write hatches as real DXF HATCH entities with their pattern intact."""
    table = document.table("aq_polygons")
    if table is None:
        return 0

    written = 0
    for feature in table.getFeatures():
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            continue

        attribs = _common_attribs(feature)
        pattern = (feature.attribute("aq_pattern") or "SOLID").upper()
        scale = float(feature.attribute("aq_pat_scale") or 1.0)
        angle = float(feature.attribute("aq_pat_angle") or 0.0)

        try:
            hatch = modelspace.add_hatch(dxfattribs=attribs)
        except (AttributeError, TypeError):
            continue

        if pattern != "SOLID":
            try:
                hatch.set_pattern_fill(pattern, scale=scale, angle=angle)
            except (ValueError, TypeError, AttributeError):
                hatch.set_solid_fill()
        else:
            hatch.set_solid_fill()

        for ring in _rings_of(geometry):
            if len(ring) >= 3:
                hatch.paths.add_polyline_path(ring, is_closed=True)
        written += 1

    return written


def _rings_of(geometry):
    """Return every ring of a (multi)polygon as lists of ``(x, y)``."""
    rings = []
    try:
        if geometry.isMultipart():
            polygons = geometry.asMultiPolygon()
        else:
            polygons = [geometry.asPolygon()]
    except (AttributeError, RuntimeError):
        return rings

    for polygon in polygons or []:
        for ring in polygon or []:
            rings.append([(p.x(), p.y()) for p in ring])
    return rings


# --- QGIS fallback path ------------------------------------------------------

def _export_qgis(document, path):
    """Fallback export via QGIS's own DXF writer."""
    from qgis.core import QgsDxfExport

    export_writer = QgsDxfExport()
    layers = []
    for table in document.all_tables():
        try:
            layers.append(QgsDxfExport.DxfLayer(table))
        except (AttributeError, TypeError):
            layers.append(table)

    try:
        export_writer.addLayers(layers)
    except (AttributeError, TypeError):
        return (False, "This QGIS build cannot export DXF without ezdxf.")

    export_writer.setSymbologyScale(1000.0)
    try:
        export_writer.setDestinationCrs(document.crs())
    except AttributeError:
        pass

    try:
        with open(path, "w", encoding="utf-8") as handle:
            code = export_writer.writeToFile(handle, "UTF-8")
    except (IOError, OSError) as error:
        return (False, "Could not write {0}: {1}".format(path, error))

    if code != 0:
        return (False, "QGIS DXF export failed (code {0}).".format(code))
    return (True, "Exported to {0} (geometry only — install 'ezdxf' for full "
                  "symbology).".format(os.path.basename(path)))
