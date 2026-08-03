# AutoQAD

**CAD-style drawing in QGIS** — an AutoCAD-like command line, full object
snaps, precision input, and *real* AutoCAD symbology: the 256-colour ACI
palette, `acad.lin` linetypes, millimetre lineweights and `acad.pat` hatch
patterns.

By **Isaac Enage** ([byZenterra](https://qgis.byzenterra.org)). GPL-3.0.

Built for drawing floor plans and site drawings inside QGIS without falling
back on the native vector digitising tools — and scriptable by LLM agents
through QGIS MCP.

---

## What it does

Type `L`, click two points, and you have a line on a CAD layer with an ACI
colour, a linetype and a plot lineweight in millimetres. Type `O` and offset a
wall. Type `H`, pick inside a room, and get an ANSI31 hatch. The command line,
the object snaps, the ortho/polar constraints and the keyword options all
behave the way they do in AutoCAD.

### Commands

| Group | Commands |
|---|---|
| **Draw** | `LINE` `PLINE` `RECTANG` `CIRCLE` `ARC` `POLYGON` `ELLIPSE` `POINT` `TEXT` `HATCH` `SOLID` |
| **Modify** | `MOVE` `COPY` `ROTATE` `SCALE` `MIRROR` `OFFSET` `TRIM` `EXTEND` `FILLET` `ARRAY` `EXPLODE` `JOIN` `ERASE` |
| **Tools** | `LAYER` `MKLAYER` `DSETTINGS` `OPTIONS` `SETVAR` `UNITS` `ID` `DIST` `AREA` `UNDO` `REDO` `PURGE` `HELP` `DXFOUT` |

Standard aliases work (`L`, `PL`, `REC`, `C`, `A`, `M`, `CO`, `O`, `TR`, `EX`,
`F`, `E`, `H`, `LA`), and any unique prefix resolves — `RECT` reaches
`RECTANG` without being declared.

### Object snaps

Endpoint · Midpoint · Center · Node · Quadrant · Intersection · Perpendicular ·
Tangent · Extension · Nearest — each with its own AutoCAD marker glyph.

### Precision input

```
10,20      absolute cartesian      @10,20     relative
10<45      absolute polar          @10<45     relative polar
10         direct distance entry along the cursor direction
```

Plus ortho (F8), polar tracking (F10), grid snap (F9) and a status bar of
toggles. Angle base and direction are configurable, so survey bearings
("north = 0, clockwise") parse correctly.

---

## Why it is fast

CAD plugins in QGIS have a reputation for making the application stutter. The
cause is almost always the same: reimplementing in interpreted Python what QGIS
already does in C++, then calling it from the mouse-move loop.

AutoQAD's rules, each the inverse of a specific failure mode:

- **Never hand-roll GEOS.** Intersections, offsets and buffers go through
  `QgsGeometry`.
- **Snap through `QgsPointLocator`**, obtained from the canvas's own
  `QgsSnappingUtils` — an R-tree QGIS builds, keeps warm and invalidates.
- **Coalesce mouse moves** onto one ~16 ms timer. Raw move events only record a
  position; the pipeline runs at most once per frame.
- **Analytic snaps run on one already-picked entity**, never a layer scan.
  Perpendicular and tangent are closed-form maths on a single known entity.
- **Preview with canvas items**, never `canvas.refresh()`.
- **No shadow layers.**

The pointer pipeline records its own timing in `PointerTracker.last_duration_ms`,
so a slow drawing can be measured rather than guessed at.

---

## The data model

Three QGIS layers in one GeoPackage, regardless of how many CAD layers a
drawing has:

```
drawing.gpkg
 ├ aq_curves    (CompoundCurve)  lines, polylines, arcs, circles
 ├ aq_points    (Point)          nodes, text and block anchors
 └ aq_polygons  (Polygon)        hatches and solid fills
```

The **CAD layer is an attribute** (`aq_layer`), not a QGIS layer. That keeps the
snapping index small, maps one-to-one onto DXF, and means CAD layer state
(freeze, lock, plot, ACI colour, linetype, lineweight) lives where it can
actually be expressed — the Layer Manager — rather than in the QGIS layer tree,
which has no vocabulary for it.

Curves are stored as `CompoundCurve`, so a circle stays a true circle through
save, reload and DXF export instead of degrading into a polygon.

### How the AutoCAD look is produced

| ACAD concept | QGIS mechanism | Fidelity |
|---|---|---|
| ACI colour (256-index) | Generated ACI table → `QColor` | Exact |
| Lineweight (0.00–2.11 mm) | Symbol width in `RenderMillimeters` | Exact |
| Simple linetypes | `setCustomDashVector()`, scaled by LTSCALE | Exact |
| Complex linetypes (embedded text) | Marker line | Approximate — flagged |
| Hatch patterns | One `QgsLinePatternFillSymbolLayer` per `.pat` line family | Exact for ANSI31/37, NET, EARTH … |
| ByLayer / entity override | Resolved style denormalised onto each feature | Exact |

Real parsers for `acad.lin` and `acad.pat` ship in `style/linetypes.py` and
`style/hatches.py`, so you can load your own pattern files.

---

## Scripting / LLM control

```python
aq = qgis.utils.plugins['autoqad']

aq.command("LINE 0,0 10,0 10,8 0,8 C")     # macro string
aq.draw({                                   # structured spec
    "layers": [{"name": "A-WALL", "color": 7, "lineweight": 35}],
    "entities": [
        {"type": "polyline", "layer": "A-WALL",
         "points": [[0,0],[8,0],[8,6],[0,6]], "closed": True},
        {"type": "hatch", "boundary": [[0,0],[8,0],[8,6],[0,6]],
         "pattern": "ANSI31", "scale": 0.5},
    ],
})
aq.list_layers(); aq.list_commands(); aq.api_reference()
aq.export_dxf("plan.dxf")
```

Macro strings go through the **same command runner** the mouse and keyboard
use — a command cannot tell where its input came from, so there is no parallel
agent code path to drift out of sync.

Unknown layers, patterns and linetypes produce *warnings and a fallback*, never
an exception, so a partially-valid spec still yields a drawing.

Full schema: `aq.api_reference()`.

---

## Install

```bash
python install.py            # or: make deploy
```

Then restart QGIS and enable **AutoQAD** in *Plugins → Manage and Install
Plugins*. No build step is required. `install.py --uninstall` removes it,
`--profile <name>` targets a non-default profile.

> **Do not install with `cp -r`.** When the destination already exists,
> `cp -r plugins/autoqad "$PROFILE/python/plugins/"` copies the source *into*
> the existing folder rather than over it, producing a plugin tree nested
> inside one of its own subpackages. The symptom is an `ImportError` naming
> something that is plainly defined in the source — because the file being
> imported is not the file you are looking at. `install.py` removes the
> destination first and verifies the result, so it is safe to re-run.

Installing from the packaged zip (*Plugins → Install from ZIP*) is also safe;
QGIS replaces the folder rather than merging into it.

Profile locations, if you need them:

```
Windows  %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\
Linux    ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
macOS    ~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/
```

**Optional:** install [`ezdxf`](https://ezdxf.mozman.at/) for full-fidelity DXF
export (layer table, true arcs, hatch patterns). Without it, AutoQAD falls back
to QGIS's own DXF writer, which exports geometry but flattens symbology.

Requires QGIS 3.22 or newer, including QGIS 4.x — the codebase uses scoped Qt
enums and `qgis.PyQt` throughout, so it runs on both Qt5 and Qt6.

---

## Development

```bash
# Syntax-check everything (no QGIS needed)
make check

# Run the pure-module tests (no QGIS needed) — 177 tests
make test-pure

# Full suite (needs a sourced QGIS environment)
make test
```

The Qt-free modules — `style/aci.py`, `style/linetypes.py`, `style/hatches.py`,
`style/lineweights.py`, `style/cad_layer.py`, `geom/construct.py`,
`input/coords.py`, `input/ortho_polar.py`, `engine/prompt.py`,
`engine/registry.py` and the spec translator in `scripting.py` — are unit-tested
without a QGIS runtime.

When adding a module or asset directory, register it in **both** `pb_tool.cfg`
and the `Makefile`, or it will not ship in the packaged zip.

---

## Credit

AutoQAD is an original implementation by Isaac Enage. It is not derived from,
and shares no source with, any other CAD plugin.
