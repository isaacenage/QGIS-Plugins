# -*- coding: utf-8 -*-
"""The drawing document — three QGIS layers backed by one GeoPackage.

A CAD drawing needs mixed geometry on a single named layer; QGIS layers are
single geometry type. AutoQAD resolves that by making the CAD layer an
**attribute** rather than a QGIS layer, and splitting only by geometry:

``aq_curves``   compound curves — lines, polylines, arcs, circles, rectangles
``aq_points``   points — nodes, block and text insertion points
``aq_polygons`` polygons — hatches and solid fills

Three QGIS layers regardless of how many CAD layers a drawing carries. That is
what keeps the snapping locator and the spatial index small, and it maps
one-to-one onto DXF, where ``aq_layer`` simply becomes the DXF layer name.

Curves are stored as ``CompoundCurve`` so true arcs survive a round trip
instead of being segmentised on save.

Storage is a GeoPackage beside the project (durable, indexed, curve-capable).
When the project has no directory yet — an unsaved project — the document falls
back to memory layers so drawing can start immediately, and
:meth:`DrawingDocument.materialise` moves it to disk once the project is saved.
"""

import os
import uuid

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFields,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

from ..style import cad_layer, hatches, linetypes, symbology
from ..style.symbology import (
    FIELD_COLOR, FIELD_DASH, FIELD_LAYER, FIELD_LTSCALE, FIELD_LTYPE,
    FIELD_LWEIGHT, FIELD_PAT_ANGLE, FIELD_PAT_SCALE, FIELD_PATTERN,
    FIELD_RGB, FIELD_TYPE, FIELD_WIDTH,
)
from .compat import make_field

CURVES = "aq_curves"
POINTS = "aq_points"
POLYGONS = "aq_polygons"

TABLES = (CURVES, POINTS, POLYGONS)

_GEOMETRY = {
    CURVES: "CompoundCurve",
    POINTS: "Point",
    POLYGONS: "Polygon",
}

FIELD_HANDLE = "aq_handle"
FIELD_CLOSED = "aq_closed"
FIELD_TEXT = "aq_text"
FIELD_HEIGHT = "aq_height"
FIELD_ROTATION = "aq_rot"

_PROJECT_SCOPE = "AutoQAD"


def _common_fields():
    """Fields every entity carries, whatever its geometry."""
    return [
        make_field(FIELD_HANDLE, "String", 40),
        make_field(FIELD_TYPE, "String", 20),
        make_field(FIELD_LAYER, "String", 255),
        # CAD truth — what DXF export writes.
        make_field(FIELD_COLOR, "Int"),
        make_field(FIELD_LTYPE, "String", 64),
        make_field(FIELD_LWEIGHT, "Int"),
        make_field(FIELD_LTSCALE, "Double"),
        # Resolved render values — what the renderer reads.
        make_field(FIELD_RGB, "String", 12),
        make_field(FIELD_WIDTH, "Double"),
        make_field(FIELD_DASH, "String", 255),
    ]


def _table_fields(table):
    fields = _common_fields()
    if table == CURVES:
        fields.append(make_field(FIELD_CLOSED, "Int"))
    elif table == POLYGONS:
        fields.extend([
            make_field(FIELD_PATTERN, "String", 64),
            make_field(FIELD_PAT_SCALE, "Double"),
            make_field(FIELD_PAT_ANGLE, "Double"),
        ])
    elif table == POINTS:
        fields.extend([
            make_field(FIELD_TEXT, "String", 1024),
            make_field(FIELD_HEIGHT, "Double"),
            make_field(FIELD_ROTATION, "Double"),
        ])
    return fields


def _qgs_fields(table):
    fields = QgsFields()
    for field in _table_fields(table):
        fields.append(field)
    return fields


def new_handle():
    """Return a fresh entity handle (the CAD equivalent of a feature id)."""
    return uuid.uuid4().hex[:16].upper()


def is_alive(layer):
    """True when *layer* is a live, valid vector layer.

    A PyQGIS wrapper outlives the C++ object it points at. When the user
    removes a layer from the project, QGIS destroys the C++ ``QgsVectorLayer``
    but any Python reference we still hold remains — and touching it raises
    ``RuntimeError: wrapped C/C++ object ... has been deleted``.

    Every access to a stored layer goes through this guard, because the
    alternative is that deleting a layer crashes whatever happens to touch it
    next — including the mouse-move pipeline, which touches it 60 times a
    second.
    """
    if layer is None:
        return False
    try:
        return layer.isValid()
    except RuntimeError:
        return False


class DrawingDocument(object):
    """Owns a drawing's three QGIS layers, its CAD layer table and its styling.

    The document is the only writer of the resolved style fields, which is what
    lets the renderer read them without a ByLayer lookup per feature.
    """

    def __init__(self, variables, project=None):
        self.variables = variables
        self.project = project or QgsProject.instance()
        self.layers = cad_layer.LayerTable()
        self.linetype_table = dict(linetypes.STANDARD)
        self.pattern_table = dict(hatches.STANDARD)
        self._tables = {}          # name -> QgsVectorLayer
        self._gpkg_path = None

    # ---- lifecycle ----------------------------------------------------------

    @property
    def is_open(self):
        """True when all three tables are present and still alive.

        Prunes dead references as a side effect, so a drawing whose layers the
        user deleted reports closed rather than raising.
        """
        self.prune_dead()
        return len(self._tables) == len(TABLES)

    def prune_dead(self):
        """Drop references to layers whose C++ object is gone.

        Returns True if anything was pruned. Safe to call from the hot path —
        it is a handful of cheap guarded calls.
        """
        dead = [name for name, layer in self._tables.items()
                if not is_alive(layer)]
        for name in dead:
            del self._tables[name]
        return bool(dead)

    def table(self, name):
        """Return the live :class:`QgsVectorLayer` for *name*, or ``None``."""
        layer = self._tables.get(name)
        if layer is not None and not is_alive(layer):
            del self._tables[name]
            return None
        return layer

    def all_tables(self):
        """Return every live table, in canonical order."""
        return [layer for layer in (self.table(n) for n in TABLES)
                if layer is not None]

    def crs(self):
        for layer in self.all_tables():
            return layer.crs()
        return self.project.crs()

    def on_layers_removed(self, layer_ids):
        """Drop our references when the project removes layers.

        Connected to ``QgsProject.layersWillBeRemoved``, which fires *before*
        the C++ objects are destroyed — so this is the one moment we can still
        identify them safely.
        """
        removed = set(layer_ids or [])
        if not removed:
            return
        for name in list(self._tables):
            layer = self._tables[name]
            try:
                if layer.id() in removed:
                    del self._tables[name]
            except RuntimeError:
                del self._tables[name]

    def ensure_open(self, crs=None):
        """Open the drawing, creating storage if needed. Returns True on success.

        Order matters. Adopting layers already in the project comes first, so
        reopening a ``.qgz`` does not duplicate the tables. Reloading from a
        known GeoPackage comes next, so deleting the layers from the layer tree
        and then drawing again *recovers the existing drawing* rather than
        overwriting it. Only then is anything created.
        """
        if self.is_open:
            return True
        if self._adopt_project_layers():
            self.load_state()
            return True
        if self._reload_from_geopackage():
            self.load_state()
            return True
        return self.create(crs)

    def _reload_from_geopackage(self):
        """Re-add the tables from an existing GeoPackage on disk.

        This is what makes deleting the layers from the layer tree
        non-destructive: the data is still in the ``.gpkg``, so we reattach to
        it instead of writing fresh empty tables over the top.
        """
        path = self._gpkg_path or self.default_gpkg_path()
        if not path or not os.path.exists(path):
            return False

        found = {}
        for table in TABLES:
            layer = QgsVectorLayer(
                "{0}|layername={1}".format(path, table), table, "ogr")
            if not layer.isValid():
                return False
            if layer.fields().indexOf(FIELD_HANDLE) < 0:
                return False
            found[table] = layer

        self._tables = found
        for name, layer in found.items():
            layer.setCustomProperty("autoqad/table", name)
            self.project.addMapLayer(layer)
        self._gpkg_path = path
        self.apply_renderers()
        return True

    def _adopt_project_layers(self):
        """Find existing AutoQAD tables already loaded in the project."""
        found = {}
        for layer in self.project.mapLayers().values():
            if not isinstance(layer, QgsVectorLayer):
                continue
            custom = layer.customProperty("autoqad/table")
            if custom in TABLES:
                found[custom] = layer
            elif layer.name() in TABLES and layer.fields().indexOf(
                    FIELD_HANDLE) >= 0:
                found[layer.name()] = layer
        if len(found) == len(TABLES):
            self._tables = found
            for name, layer in found.items():
                layer.setCustomProperty("autoqad/table", name)
                self._path_from_layer(layer)
            self.apply_renderers()
            return True
        return False

    def _path_from_layer(self, layer):
        source = layer.source()
        if "|" in source:
            candidate = source.split("|", 1)[0]
            if candidate.lower().endswith(".gpkg"):
                self._gpkg_path = candidate

    def default_gpkg_path(self):
        """Where the drawing's GeoPackage belongs for the current project."""
        project_path = self.project.fileName()
        if not project_path:
            return None
        directory = os.path.dirname(project_path)
        stem = os.path.splitext(os.path.basename(project_path))[0]
        if not directory or not os.path.isdir(directory):
            return None
        return os.path.join(directory, "{0}_autoqad.gpkg".format(stem))

    def create(self, crs=None, gpkg_path=None):
        """Create the three tables. Returns True on success.

        Falls back to memory layers when no writable GeoPackage path exists, so
        an unsaved project can still be drawn on.
        """
        crs = crs or self.project.crs()
        if not isinstance(crs, QgsCoordinateReferenceSystem) or not crs.isValid():
            crs = QgsCoordinateReferenceSystem("EPSG:3857")

        path = gpkg_path or self.default_gpkg_path()
        created = {}
        if path:
            created = self._create_geopackage(path, crs)
        if not created:
            created = self._create_memory(crs)
        if not created:
            return False

        self._tables = created
        for name, layer in created.items():
            layer.setCustomProperty("autoqad/table", name)
            layer.setReadOnly(False)
            self.project.addMapLayer(layer)
        self.apply_renderers()
        self.save_state()
        return True

    def _memory_layer(self, table, crs):
        uri = "{0}?crs={1}".format(_GEOMETRY[table], crs.authid() or "EPSG:3857")
        layer = QgsVectorLayer(uri, table, "memory")
        if not layer.isValid():
            return None
        provider = layer.dataProvider()
        provider.addAttributes(_table_fields(table))
        layer.updateFields()
        return layer

    def _create_memory(self, crs):
        created = {}
        for table in TABLES:
            layer = self._memory_layer(table, crs)
            if layer is None:
                return {}
            created[table] = layer
        self._gpkg_path = None
        return created

    def _create_geopackage(self, path, crs):
        """Write empty tables into a GeoPackage and load them back."""
        created = {}
        first = not os.path.exists(path)
        for table in TABLES:
            source = self._memory_layer(table, crs)
            if source is None:
                return {}

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = table
            options.fileEncoding = "UTF-8"
            if first:
                options.actionOnExistingFile = (
                    QgsVectorFileWriter.CreateOrOverwriteFile)
                first = False
            else:
                options.actionOnExistingFile = (
                    QgsVectorFileWriter.CreateOrOverwriteLayer)

            try:
                result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    source, path, self.project.transformContext(), options)
            except AttributeError:        # pragma: no cover - QGIS < 3.20
                result = QgsVectorFileWriter.writeAsVectorFormatV2(
                    source, path, self.project.transformContext(), options)
            code = result[0] if isinstance(result, (tuple, list)) else result
            if code != QgsVectorFileWriter.NoError:
                return {}

            loaded = QgsVectorLayer(
                "{0}|layername={1}".format(path, table), table, "ogr")
            if not loaded.isValid():
                return {}
            created[table] = loaded

        self._gpkg_path = path
        return created

    def materialise(self):
        """Move memory-backed tables onto disk once the project has a path.

        Called after the project is saved. Returns True when a move happened.
        """
        if self._gpkg_path or not self.is_open:
            return False
        path = self.default_gpkg_path()
        if not path:
            return False

        snapshot = {}
        for name in TABLES:
            layer = self.table(name)
            if layer is not None:
                snapshot[name] = list(layer.getFeatures())
        old = [layer for layer in self._tables.values() if is_alive(layer)]
        crs = self.crs()

        created = self._create_geopackage(path, crs)
        if not created:
            return False

        for name, layer in created.items():
            features = snapshot.get(name) or []
            if features:
                layer.dataProvider().addFeatures(features)
            layer.setCustomProperty("autoqad/table", name)
            self.project.addMapLayer(layer)

        self._tables = created
        for layer in old:
            self.project.removeMapLayer(layer.id())
        self.apply_renderers()
        return True

    def close(self):
        """Drop the document's layers from the project."""
        for layer in list(self._tables.values()):
            try:
                self.project.removeMapLayer(layer.id())
            except (RuntimeError, AttributeError):
                pass
        self._tables = {}

    # ---- rendering ----------------------------------------------------------

    def used_patterns(self):
        """Distinct hatch patterns present in the polygon table."""
        polygons = self.table(POLYGONS)
        if polygons is None:
            return [hatches.SOLID]
        index = polygons.fields().indexOf(FIELD_PATTERN)
        if index < 0:
            return [hatches.SOLID]
        names = {v for v in polygons.uniqueValues(index) if v}
        names.add(hatches.SOLID)
        return sorted(names)

    def apply_renderers(self):
        """(Re)build every table's renderer from the current drawing state."""
        curves = self.table(CURVES)
        if curves is not None:
            curves.setRenderer(symbology.build_line_renderer())
            curves.triggerRepaint()

        points = self.table(POINTS)
        if points is not None:
            points.setRenderer(symbology.build_point_renderer())
            points.triggerRepaint()

        polygons = self.table(POLYGONS)
        if polygons is not None:
            polygons.setRenderer(symbology.build_fill_renderer(
                self.used_patterns(), self.pattern_table))
            polygons.triggerRepaint()

    def refresh(self):
        for layer in self.all_tables():
            layer.triggerRepaint()

    # ---- style resolution ---------------------------------------------------

    def resolved_style(self, layer_name, color=None, linetype=None,
                       lineweight=None, ltscale=None):
        """Resolve an entity's render fields against its CAD layer."""
        target = self.layers.get_or_create(layer_name)
        return symbology.resolve_entity_style(
            target,
            color=color,
            linetype=linetype,
            lineweight=lineweight,
            ltscale=1.0 if ltscale is None else ltscale,
            global_ltscale=self.variables.get("LTSCALE"),
            lineweight_display=self.variables.get("LWDISPLAY"),
            background_is_dark=self.variables.background_is_dark,
            linetype_table=self.linetype_table)

    def restyle_layer(self, layer_name):
        """Recompute resolved style for every entity on *layer_name*.

        This is the bounded refresh that keeps the denormalised style fields
        honest after a layer's colour/linetype/lineweight changes.
        """
        target = self.layers.get(layer_name)
        if target is None:
            return 0

        touched = 0
        expression = '"{0}" = \'{1}\''.format(
            FIELD_LAYER, str(layer_name).replace("'", "''"))

        for table in self.all_tables():
            fields = table.fields()
            index_rgb = fields.indexOf(FIELD_RGB)
            index_w = fields.indexOf(FIELD_WIDTH)
            index_dash = fields.indexOf(FIELD_DASH)
            if min(index_rgb, index_w, index_dash) < 0:
                continue

            updates = {}
            for feature in table.getFeatures(expression):
                resolved = self.resolved_style(
                    layer_name,
                    color=feature[FIELD_COLOR],
                    linetype=feature[FIELD_LTYPE],
                    lineweight=feature[FIELD_LWEIGHT],
                    ltscale=feature[FIELD_LTSCALE])
                updates[feature.id()] = {
                    index_rgb: resolved[FIELD_RGB],
                    index_w: resolved[FIELD_WIDTH],
                    index_dash: resolved[FIELD_DASH],
                }
            if updates:
                self._change_attributes(table, updates)
                touched += len(updates)
                table.triggerRepaint()
        return touched

    def restyle_all(self):
        return sum(self.restyle_layer(name) for name in self.layers.names())

    # ---- writes -------------------------------------------------------------
    #
    # Writes go through the layer's **edit buffer** whenever the layer is in
    # edit mode, and fall back to the provider otherwise. This matters twice
    # over: the buffer batches a whole command into one disk write instead of
    # one per entity (a provider write per click is a visible UI stall on a
    # GeoPackage), and it is what makes Ctrl+Z undo a CAD operation rather
    # than nothing at all. The provider path remains for headless scripting,
    # where no edit session is open.

    @staticmethod
    def _add_features(layer, features):
        """Add features, returning their ids."""
        if layer.isEditable():
            if not layer.addFeatures(features):
                return []
            return [f.id() for f in features]
        ok, added = layer.dataProvider().addFeatures(features)
        return [f.id() for f in added] if ok else []

    @staticmethod
    def _delete_features(layer, feature_ids):
        if layer.isEditable():
            return layer.deleteFeatures(list(feature_ids))
        return layer.dataProvider().deleteFeatures(list(feature_ids))

    @staticmethod
    def _change_geometry(layer, feature_id, geometry):
        if layer.isEditable():
            return layer.changeGeometry(feature_id, geometry)
        return layer.dataProvider().changeGeometryValues(
            {feature_id: geometry})

    @staticmethod
    def _change_attributes(layer, updates):
        if layer.isEditable():
            ok = True
            for feature_id, values in updates.items():
                for index, value in values.items():
                    ok = layer.changeAttributeValue(
                        feature_id, index, value) and ok
            return ok
        return layer.dataProvider().changeAttributeValues(updates)

    def set_geometry(self, table_name, feature_id, geometry):
        """Replace one entity's geometry. Returns True on success."""
        layer = self.table(table_name)
        if layer is None or geometry is None or geometry.isEmpty():
            return False
        return self._change_geometry(layer, feature_id, geometry)

    # ---- entity creation ----------------------------------------------------

    def add_entity(self, table_name, geometry, entity_type,
                   layer_name=None, color=None, linetype=None,
                   lineweight=None, ltscale=None, extra=None):
        """Add one entity and return its feature id, or ``None`` on failure.

        Style defaults come from the current entity variables (CECOLOR,
        CELTYPE, CELWEIGHT), exactly as they do in AutoCAD.
        """
        table = self.table(table_name)
        if table is None or geometry is None or geometry.isEmpty():
            return None

        name = layer_name or self.variables.get("CLAYER")
        target = self.layers.get_or_create(name)
        if not target.is_editable:
            return None

        color = self.variables.get("CECOLOR") if color is None else color
        linetype = self.variables.get("CELTYPE") if linetype is None else linetype
        lineweight = (self.variables.get("CELWEIGHT")
                      if lineweight is None else lineweight)
        ltscale = (self.variables.get("CELTSCALE")
                   if ltscale is None else ltscale)

        resolved = self.resolved_style(target.name, color, linetype,
                                       lineweight, ltscale)

        feature = QgsFeature(table.fields())
        feature.setGeometry(geometry)
        feature[FIELD_HANDLE] = new_handle()
        feature[FIELD_TYPE] = str(entity_type).upper()
        feature[FIELD_LAYER] = target.name
        feature[FIELD_COLOR] = int(color)
        feature[FIELD_LTYPE] = str(linetype).upper()
        feature[FIELD_LWEIGHT] = int(lineweight)
        feature[FIELD_LTSCALE] = float(ltscale)
        feature[FIELD_RGB] = resolved[FIELD_RGB]
        feature[FIELD_WIDTH] = resolved[FIELD_WIDTH]
        feature[FIELD_DASH] = resolved[FIELD_DASH]

        for key, value in (extra or {}).items():
            if table.fields().indexOf(key) >= 0:
                feature[key] = value

        added = self._add_features(table, [feature])
        if not added:
            return None
        table.triggerRepaint()
        return added[0]

    def add_curve(self, geometry, entity_type="LINE", closed=False, **kwargs):
        extra = dict(kwargs.pop("extra", None) or {})
        extra[FIELD_CLOSED] = 1 if closed else 0
        return self.add_entity(CURVES, geometry, entity_type, extra=extra,
                               **kwargs)

    def add_point(self, geometry, entity_type="POINT", text=None,
                  height=None, rotation=0.0, **kwargs):
        extra = dict(kwargs.pop("extra", None) or {})
        if text is not None:
            extra[FIELD_TEXT] = text
        extra[FIELD_HEIGHT] = (self.variables.get("TEXTSIZE")
                               if height is None else height)
        extra[FIELD_ROTATION] = rotation
        return self.add_entity(POINTS, geometry, entity_type, extra=extra,
                               **kwargs)

    def add_hatch(self, geometry, pattern=None, pattern_scale=None,
                  pattern_angle=None, **kwargs):
        extra = dict(kwargs.pop("extra", None) or {})
        extra[FIELD_PATTERN] = str(
            pattern or self.variables.get("HPNAME")).upper()
        extra[FIELD_PAT_SCALE] = (self.variables.get("HPSCALE")
                                  if pattern_scale is None else pattern_scale)
        extra[FIELD_PAT_ANGLE] = (self.variables.get("HPANG")
                                  if pattern_angle is None else pattern_angle)
        feature_id = self.add_entity(POLYGONS, geometry, "HATCH", extra=extra,
                                     **kwargs)
        if feature_id is not None:
            self.apply_renderers()      # a new pattern may need a new rule
        return feature_id

    def delete(self, table_name, feature_ids):
        """Delete entities by feature id. Returns the number removed."""
        table = self.table(table_name)
        if table is None or not feature_ids:
            return 0
        if self._delete_features(table, feature_ids):
            table.triggerRepaint()
            return len(feature_ids)
        return 0

    def count(self):
        """Total entity count across every table."""
        return sum(layer.featureCount() for layer in self.all_tables())

    # ---- persistence --------------------------------------------------------

    def save_state(self):
        """Write the CAD layer table into the project."""
        import json
        self.project.writeEntry(_PROJECT_SCOPE, "layers",
                                json.dumps(self.layers.to_dict()))
        if self._gpkg_path:
            self.project.writeEntry(_PROJECT_SCOPE, "gpkg", self._gpkg_path)

    def load_state(self):
        """Read the CAD layer table back out of the project."""
        import json
        raw, ok = self.project.readEntry(_PROJECT_SCOPE, "layers", "")
        if ok and raw:
            try:
                self.layers = cad_layer.LayerTable.from_dict(json.loads(raw))
            except (ValueError, TypeError):
                pass
        stored, ok = self.project.readEntry(_PROJECT_SCOPE, "gpkg", "")
        if ok and stored:
            self._gpkg_path = stored
        return True
