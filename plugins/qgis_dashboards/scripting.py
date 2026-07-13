# -*- coding: utf-8 -*-
"""Headless scripting facade — build dashboards from a single dict.

This module is the **stable public API** an automation client (QGIS MCP /
Claude Code via ``execute_code``, a PyQGIS script, a custom plugin) uses to
create a whole dashboard without touching the GUI. It turns one friendly,
JSON-serializable *spec* into the window's internal **v3 layout dict** and
applies it through the same code path the ``.qdash`` loader uses, so a scripted
dashboard is byte-for-byte the same as one built by hand.

Two layers:

* :func:`spec_to_layout` is **pure** (stdlib only): friendly spec -> v3 layout
  dict + a list of warnings. It takes pluggable ``resolve_layer`` /
  ``resolve_theme`` callables so it is unit-testable without QGIS.
* :func:`build_dashboard`, :func:`add_element`, :func:`list_layers` are the
  QGIS-touching entry points; they wire the real ``QgsProject`` layer lookup and
  the preset gallery into :func:`spec_to_layout` and drive a live
  ``DashboardWindow``. They import QGIS lazily so importing this module (for the
  pure helpers / tests) never needs a QGIS environment.

The plugin object (``qgis.utils.plugins['qgis_dashboards']``) re-exposes these
as ``build_dashboard`` / ``add_element`` / ``list_layers`` / ``api_reference``
so an agent can do, inside ``execute_code``::

    from qgis.utils import plugins
    plugins['qgis_dashboards'].build_dashboard({...})
"""

import uuid

# --- defaults (kept in sync with dashboard_canvas / window, but hardcoded here
#     so the pure layer needs no QGIS import) ---------------------------------
DEFAULT_REGION = (1280, 720)   # export/print region (page) in logical px
DEFAULT_GRID = (12, 8)         # cols x rows for cell-based `at` placement

# The element types the registry knows (elements/__init__.ELEMENT_TYPES). Kept
# here as a constant so spec validation needs no QGIS import; keep in sync when
# a new element type is added.
ELEMENT_TYPE_NAMES = (
    "indicator", "chart", "pivot", "list", "map", "category_selector",
    "filter", "legend", "text", "image", "header",
)

# The 23 chart types (elements/chart_specs.CHART_SPECS). For reference / help.
CHART_TYPE_NAMES = (
    "bar", "barh", "lollipop", "lollipop_h", "dot", "radial_bar", "radar",
    "line", "step", "spline", "area", "waterfall", "pie", "donut", "rose",
    "funnel", "treemap", "grouped_bar", "stacked_bar", "scatter", "bubble",
    "histogram", "candlestick",
)

# Element types that bind to no vector layer (a "layer" key is ignored for
# them).
_LAYERLESS = frozenset(("text", "image", "header", "legend"))

# Keys handled specially per element (everything else is copied into config).
_META_KEYS = frozenset(("type", "ref", "at", "grid", "layer"))


# ----------------------------------------------------------------------------
# Pure spec -> layout translation (no QGIS)
# ----------------------------------------------------------------------------

def _gen_id():
    return uuid.uuid4().hex[:8]


def _rect_from_at(at, region, grid):
    """Convert a ``[col, row, colspan, rowspan]`` cell rect to a pixel rect.

    Cells are evenly divided across the export/print *region* using the *grid*
    (cols, rows). Returns a ``{"x","y","w","h"}`` dict in logical pixels.
    """
    col, row, cspan, rspan = (list(at) + [1, 1, 1, 1])[:4]
    cols, rows = grid
    rw, rh = region
    cw = rw / float(max(cols, 1))
    ch = rh / float(max(rows, 1))
    return {
        "x": int(round(col * cw)),
        "y": int(round(row * ch)),
        "w": int(round(max(cspan, 1) * cw)),
        "h": int(round(max(rspan, 1) * ch)),
    }


def _normalize_pages(spec):
    """Return the spec's pages as a list of ``{title, elements, connections}``.

    Accepts either a multi-page ``{"pages": [...]}`` spec or the single-page
    shorthand ``{"elements": [...], "connections": [...]}``.
    """
    if isinstance(spec.get("pages"), list) and spec["pages"]:
        pages = []
        for i, p in enumerate(spec["pages"]):
            pages.append({
                "title": p.get("title") or "Page {}".format(i + 1),
                "elements": list(p.get("elements") or []),
                "connections": list(p.get("connections") or []),
            })
        return pages
    return [{
        "title": spec.get("title") or "Page 1",
        "elements": list(spec.get("elements") or []),
        "connections": list(spec.get("connections") or []),
    }]


def _resolve_theme_value(theme, resolve_theme):
    """Turn the spec's ``theme`` (preset name / dict / dict-with-preset) into a
    partial theme dict (``{}`` for the default theme)."""
    if isinstance(theme, dict):
        if "preset" in theme:
            data = dict(resolve_theme(theme["preset"]) or {})
            for k, v in theme.items():
                if k != "preset":
                    data[k] = v
            return data
        return dict(theme)
    if isinstance(theme, str) and theme:
        return dict(resolve_theme(theme) or {})
    return {}


def spec_to_layout(spec, resolve_layer=None, resolve_theme=None):
    """Translate a friendly *spec* dict into the window's v3 layout dict.

    Pure (stdlib only). *resolve_layer* maps a layer name/id reference to a
    concrete layer id (returns ``None`` if unknown); *resolve_theme* maps a
    preset name to a partial theme dict. Both default to no-ops so the function
    is testable in isolation.

    Returns ``(layout_dict, warnings)`` where *warnings* is a list of
    human-readable strings (unknown layer, dangling connection, ...).

    Raises :class:`ValueError` for a structurally invalid spec (unknown element
    type, element missing a type).
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")
    resolve_layer = resolve_layer or (lambda ref: ref)
    resolve_theme = resolve_theme or (lambda name: {})

    warnings = []
    region = tuple(_region_of(spec))
    grid = tuple(_grid_of(spec))

    out_pages = []
    for p in _normalize_pages(spec):
        refmap = {}        # ref/id -> element id, for wiring connections
        out_elements = []
        for elem in p["elements"]:
            out_elements.append(
                _build_element(elem, region, grid, resolve_layer,
                               refmap, warnings))
        out_pages.append({
            "id": _gen_id(),
            "title": p["title"],
            "elements": out_elements,
            "connections": _build_connections(p["connections"], refmap,
                                              warnings),
        })

    layout = {
        "version": 3,
        "grid": {"cols": grid[0], "rows": grid[1]},
        "gap": int(spec.get("gap", 0)),
        "canvas": {"w": region[0], "h": region[1]},
        "theme": _resolve_theme_value(spec.get("theme"), resolve_theme),
        "window": {},
        "active_page": out_pages[0]["id"] if out_pages else None,
        "pages": out_pages,
    }
    # Only pin the Build/Use lock when the spec is explicit; otherwise let
    # migrate_layout default it from content (a dashboard with tiles opens in
    # Use mode = interactive).
    if "locked" in spec:
        layout["locked"] = bool(spec["locked"])
    return layout, warnings


def _region_of(spec):
    cv = spec.get("canvas")
    if isinstance(cv, dict) and cv.get("w") and cv.get("h"):
        return (int(cv["w"]), int(cv["h"]))
    return DEFAULT_REGION


def _grid_of(spec):
    g = spec.get("grid")
    if isinstance(g, dict) and g.get("cols") and g.get("rows"):
        return (int(g["cols"]), int(g["rows"]))
    return DEFAULT_GRID


def _build_element(elem, region, grid, resolve_layer, refmap, warnings):
    if not isinstance(elem, dict):
        raise ValueError("each element must be a dict, got {!r}".format(elem))
    t = elem.get("type")
    if t not in ELEMENT_TYPE_NAMES:
        raise ValueError(
            "unknown element type {!r}; valid types: {}".format(
                t, ", ".join(ELEMENT_TYPE_NAMES)))

    config = {k: v for k, v in elem.items() if k not in _META_KEYS}

    # bind a layer by name or id (skip for layerless presentational types)
    ref = elem.get("layer")
    if ref is not None and t not in _LAYERLESS:
        layer_id = resolve_layer(ref)
        if layer_id:
            config["layer_id"] = layer_id
        else:
            warnings.append(
                "element {!r}: layer {!r} not found — left unbound".format(
                    elem.get("title") or t, ref))

    eid = elem.get("id") or _gen_id()
    config["id"] = eid
    if elem.get("ref"):
        refmap[elem["ref"]] = eid
    refmap.setdefault(eid, eid)

    out = dict(config)
    out["__type__"] = t

    at = elem.get("at")
    if at is not None:
        out["grid"] = _rect_from_at(at, region, grid)
    elif isinstance(elem.get("grid"), dict):
        out["grid"] = dict(elem["grid"])   # explicit pixel rect passthrough
    return out


def _build_connections(rules, refmap, warnings):
    """Turn ``[{"from": ref, "to": [refs]}]`` into ``{src_id: [target_ids]}``."""
    conns = {}
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        src = refmap.get(rule.get("from"))
        if not src:
            warnings.append(
                "connection from {!r}: no element with that ref/id".format(
                    rule.get("from")))
            continue
        targets = []
        for tref in (rule.get("to") or []):
            tid = refmap.get(tref)
            if not tid:
                warnings.append(
                    "connection {!r} -> {!r}: target not found".format(
                        rule.get("from"), tref))
            elif tid != src and tid not in targets:
                targets.append(tid)
        if targets:
            conns.setdefault(src, []).extend(
                t for t in targets if t not in conns.get(src, []))
    return conns


# ----------------------------------------------------------------------------
# QGIS-touching entry points (drive a live DashboardWindow)
# ----------------------------------------------------------------------------

def _project_layer_resolver():
    """Return a ``resolve_layer(ref) -> layer_id|None`` over the current project.

    Matches a project layer by exact id, then exact name, then case-insensitive
    name.
    """
    from qgis.core import QgsProject
    proj = QgsProject.instance()
    by_id = proj.mapLayers()
    layers = list(by_id.values())

    def resolve(ref):
        if ref in by_id:
            return ref
        for lyr in layers:
            if lyr.name() == ref:
                return lyr.id()
        low = ref.lower() if isinstance(ref, str) else ref
        for lyr in layers:
            if lyr.name().lower() == low:
                return lyr.id()
        return None

    return resolve


def _preset_theme_resolver():
    """Return a ``resolve_theme(name) -> partial theme dict`` over the gallery."""
    from . import presets

    def resolve(name):
        if name in presets.names():
            return presets.theme_for(name).to_dict()
        return {}

    return resolve


def build_dashboard(window, spec, show=True, save=True):
    """Build a whole dashboard on *window* from *spec*, replacing any current one.

    *spec* is the friendly dict documented in :data:`API_REFERENCE`. Layers are
    resolved against the current ``QgsProject`` and themes against the preset
    gallery. Returns a summary dict ``{pages, elements, warnings}``.

    With *save* the dashboard is also written into the ``.qgz`` project; with
    *show* the window is brought to the front.
    """
    from .window import migrate_layout

    layout, warnings = spec_to_layout(
        spec,
        resolve_layer=_project_layer_resolver(),
        resolve_theme=_preset_theme_resolver())
    data = migrate_layout(layout)
    window._apply_layout_dict(data)
    window.show_dashboard()
    if save:
        window.save_to_project()
    if show:
        window.restore_from_bubble()
    return {
        "pages": len(data["pages"]),
        "elements": sum(len(p["elements"]) for p in data["pages"]),
        "warnings": warnings,
    }


def add_element(window, type_name, config=None, at=None, layer=None,
                connect_to=None):
    """Add ONE element to the current page of a live *window* and return its id.

    A convenience for incremental scripting (vs. :func:`build_dashboard`, which
    rebuilds the whole dashboard). *at* is a ``[col, row, colspan, rowspan]``
    cell rect on the current grid (auto-placed if omitted); *layer* binds a
    layer by name/id; *connect_to* is an element id (or list) this element
    should cross-filter as a source.
    """
    if type_name not in ELEMENT_TYPE_NAMES:
        raise ValueError(
            "unknown element type {!r}; valid types: {}".format(
                type_name, ", ".join(ELEMENT_TYPE_NAMES)))
    config = dict(config or {})

    if layer is not None and type_name not in _LAYERLESS:
        layer_id = _project_layer_resolver()(layer)
        if layer_id:
            config["layer_id"] = layer_id

    rect = None
    if at is not None:
        page = window.current_page()
        region = page.canvas.region_size() if page else DEFAULT_REGION
        grid = (window.canvas_cols(), window.canvas_rows())
        r = _rect_from_at(at, region, grid)
        rect = (r["x"], r["y"], r["w"], r["h"])

    tile = window.add_element(type_name, config, rect)
    element_id = tile.element.id

    if connect_to:
        targets = [connect_to] if isinstance(
            connect_to, str) else list(connect_to)
        window.bus.set_targets(element_id, targets)
    return element_id


def list_layers():
    """Return a list of the current project's layers with field metadata.

    Each entry: ``{name, id, kind, geometry, feature_count, fields}`` (the
    geometry/feature_count/fields keys are present for vector layers only).
    This is how an automation client discovers which layers and fields to bind
    tiles to before calling :func:`build_dashboard`.
    """
    from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
    out = []
    for lyr in QgsProject.instance().mapLayers().values():
        info = {"name": lyr.name(), "id": lyr.id()}
        if isinstance(lyr, QgsVectorLayer):
            info["kind"] = "vector"
            try:
                info["geometry"] = QgsWkbTypes.geometryDisplayString(
                    lyr.geometryType())
            except Exception:
                info["geometry"] = ""
            info["feature_count"] = lyr.featureCount()
            info["fields"] = [f.name() for f in lyr.fields()]
        else:
            info["kind"] = "raster/other"
        out.append(info)
    return out


# ----------------------------------------------------------------------------
# Self-documenting reference (an agent can print this over MCP)
# ----------------------------------------------------------------------------

API_REFERENCE = r"""
QGIS Dashboard — scripting API (drive the plugin headlessly, no mouse)
======================================================================

From QGIS Python (e.g. an MCP `execute_code` call):

    from qgis.utils import plugins
    dash = plugins['qgis_dashboards']

    # 1) discover layers + fields to bind to
    dash.list_layers()
    # -> [{'name': 'Parcels', 'id': 'Parcels_abc', 'kind': 'vector',
    #      'geometry': 'Polygon', 'feature_count': 1240,
    #      'fields': ['zone', 'area_sqm', 'owner']}, ...]

    # 2) build a whole dashboard from one spec
    dash.build_dashboard(SPEC)            # returns {pages, elements, warnings}

    # or add one tile at a time to the current page
    cid = dash.add_element('chart',
              {'title': 'By zone', 'chart_type': 'bar',
               'category_field': 'zone', 'statistic': 'count'},
              at=[0, 2, 6, 4], layer='Parcels')

SPEC schema (all keys optional unless noted)
--------------------------------------------
{
  "title":  "Sales Overview",          # default page title
  "theme":  "Midnight Slate",          # preset name, OR a dict of theme keys,
                                        # OR {"preset": "...", "accent": "#f00"}
  "canvas": {"w": 1280, "h": 720},     # export/print region (page) in px
  "grid":   {"cols": 12, "rows": 8},   # cells for `at` placement
  "gap":    8,                          # px gap drawn inside every tile
  "locked": true,                       # true=Use mode (interactive),
                                        # false=Build mode (editable). Default:
                                        # Use mode when the dashboard has tiles.
  "pages": [                            # OR use top-level "elements" for 1 page
    {
      "title": "Overview",
      "elements": [ ELEMENT, ... ],
      "connections": [ {"from": REF, "to": [REF, ...]}, ... ]
    }
  ]
}

ELEMENT
  "type"  (required): one of
      indicator | chart | pivot | list | map | category_selector |
      filter | legend | text | image | header
  "ref"   : a handle (string) used in "connections" wiring
  "title" : tile heading
  "layer" : layer NAME or id to bind (ignored for text/image/header/legend)
  "at"    : [col, row, colspan, rowspan] on the grid (auto-placed if omitted)
  "style" : per-tile appearance override dict (see Theme keys below)
  "base_filter" : a QgsExpression string applied to this tile only
  ...plus the per-type config keys:

  indicator : value_expression (e.g. "count(1)", 'sum("pop")'),
              reference_expression, top_text, prefix, suffix,
              decimals (int), no_value_text,
              icon_path (a file path or pasted raw <svg> markup),
              icon_gap (px between the icon and the value)
  chart     : chart_type (see list below), and by shape:
              category  -> category_field, statistic(count|sum|mean), value_field
              series    -> category_field, series_field, statistic, value_field
              xy        -> x_field, y_field
              xyz       -> x_field, y_field, size_field
              bins      -> value_field, bin_count (int)
              ohlc      -> category_field, open_field, high_field,
                           low_field, close_field
  pivot     : row_field, col_field, statistic(count|sum|mean|min|max),
              value_field, show_totals (bool)
  list      : display_fields (list of field names)
  map       : source_filter_mode (off|extent|selection|relay)
  category_selector : category_field
  filter    : fields (list of field names)
  legend    : (none — mirrors every map layer)
  text      : text, style:{align:left|center|right, heading:bool}
  image     : path, style:{fit:contain|stretch}
  header    : title,
              logo_path (a file path or pasted raw <svg> markup),
              logo_gap (px between the logo and the title)

chart_type values:
  bar barh lollipop lollipop_h dot radial_bar radar line step spline area
  waterfall pie donut rose funnel treemap grouped_bar stacked_bar scatter
  bubble histogram candlestick

Theme keys (use in "theme" dict or a tile "style"):
  window_bg surface_bg text text_muted accent border chart_bg zebra selection
  series(list of #hex) font_family heading_font font_size title_size value_size
  radius border_width tile_opacity(0-100)

Theme presets (names for "theme"):
  Summarizer Blue, Slate Professional, Indigo SaaS, Fintech Amber, Teal Health,
  Emerald Corporate, Rose Editorial, Graphite Gold, Sunset Coral, Omagie Glass,
  Smartech Mauve, Cardio Lime, Midnight Slate, Carbon Dark, Indigo Night,
  Amber Noir, Violet Dusk, Mint Glass, Lime Noir

Cross-filtering: a "connection" wires a SOURCE tile's selection to one or more
TARGET tiles. Sources: chart, pivot, map, category_selector, filter. Targets:
indicator, chart, pivot, list, map. Example — clicking the "byZone" chart filters
the KPI and the map:
  "connections": [{"from": "byZone", "to": ["totalKpi", "mainMap"]}]
"""


def api_reference():
    """Return the human-readable scripting reference (see :data:`API_REFERENCE`)."""
    return API_REFERENCE
