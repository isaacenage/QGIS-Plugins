# ArcGIS Dashboards (2026) & ArcGIS for Power BI — widgets and map-connection reference

**Date:** 2026-07-04 · **Method:** deep-research workflow (5 search angles → 21 sources fetched → 100 claims extracted → top 25 adversarially verified by 3-vote panels; 25/25 confirmed, 0 refuted).
**Audience:** the `qgis_dashboards` plugin team, for feature-parity study against Esri's two dashboard/mapping products.

**Confidence legend used throughout:**

- ✅ **Verified** — claim survived a 3-vote adversarial verification panel (all 3-0 except one 2-1 noted inline).
- ◐ **Primary-source extracted** — verbatim-quoted from official Esri/Microsoft documentation but not run through the verification panel (the panel budget was consumed by the Dashboards claims). Treat as reliable but re-check before load-bearing decisions.

---

## Part 1 — ArcGIS Dashboards (current through the June 2026 release)

### 1.1 The element model ✅

- Most dashboard elements are **data-driven**, and binding a data source is the mandatory **first** configuration step. The **map element binds to a web map or web scene**; other elements (indicator, gauge, list, details, …) bind to a **layer or an Arcade data expression**. ([Configure an element](https://doc.arcgis.com/en/dashboards/latest/get-started/configure-an-element.htm), [Understand data sources](https://doc.arcgis.com/en/dashboards/latest/get-started/understand-data-sources.htm))
- Every element is configured through a **multi-tab configuration window**: *General* (header/captions), *Data* plus element-specific tabs (the visualization), and a per-element *Accessibility* tab.
- ◐ All elements share a **four-part anatomy**: header (title + "more information"), top caption, visualization area, bottom caption.
- ◐ General-tab options common to elements: **Enable focus mode** (viewer can expand the element), **Data download** (for data-driven elements), and a configurable **"No data"** label shown when the (possibly cross-filtered) query returns nothing.
- ✅ **Cross-filter-aware rendering is built in**: an element can be set to render only after receiving a filter/selection from another element via the **"Render only when filtered"** option, with a configurable **"No selection"** placeholder state (defaulting to the source element's title) shown before any selection.

### 1.2 Element catalog

The element roster, confirmed ✅ through the docs' data-binding text and the filter-target list ("filter actions can target lists, details, charts, tables, embedded content, rich text, and selectors… also indicator values and references, gauge values, minimums and maximums, and number selector minimum and maximum values" — [Configuring actions on dashboard elements](https://doc.arcgis.com/en/dashboards/latest/create-and-share/configuring-actions-on-dashboard-elements.htm)):

| Element | Purpose | Action role (map connection) |
|---|---|---|
| **Map** | Live web map / web scene (2D or 3D ◐; a dashboard may contain several maps or none) | Source **and** target — see §1.3 |
| **Map legend** | Legend bound to one map element | Dependent on a map — see §1.4 |
| **Serial chart** | One or more series along x/y axes; categories from grouped field values ◐ | Source (selection → filter/location actions) and filter target |
| **Pie chart** | Proportional category chart | Source and filter target |
| **Indicator** | Big-number card (value + reference) | Filter target (its value/reference can be driven by a filter); since June 2026, feature-based indicators can also be a **source** ◐ |
| **Gauge** | Progress/meter (value, min, max) | Filter target (value/min/max drivable); feature-based gauges can be a source since June 2026 ◐ |
| **List** | Rows/features from a layer, field-template + sort ◐ | Source — selecting a row can Flash / Pan / Zoom / Show pop-up / filter targets; also filter target |
| **Details** | Feature attribute pop-up-style panel | Filter target; feature-based details can be a source since June 2026 ◐ |
| **Table** | Tabular data | Filter target |
| **Rich text** | Formatted text; since June 2026 supports an **optional data source** (data-driven) ◐ | Filter target; feature-based rich text can be **source and target** since June 2026 ◐ |
| **Embedded content** | External content by URL | Filter target; feature-based embedded content can be a source since June 2026 ◐ |
| **Header** | Banner along the dashboard top: title, branding, links ◐ | Presentational (hosts selectors) |
| **Category selector** | Dropdown/list/button bar of category values | Source only — the canonical filter source; one selection can drive several simultaneous actions ✅ |
| **Number selector** | Numeric input/range | Source; its own min/max can also be a filter *target* ✅ |
| **Date selector** | Date picker; a **slider** option was added Oct 2025 ◐ | Source |

### 1.3 The map element — tools, and how everything connects to it

**Built-in configurable map tools** ✅ ([Map element and tools](https://doc.arcgis.com/en/dashboards/latest/get-started/map-element-and-tools.htm)):

- Scalebar (line or ruler style ◐)
- **Default extent and bookmarks** — return to initial extent; jump to web-map bookmarks
- **Legend**
- **Layer visibility** — toggle operational layers on/off
- **Basemap switcher** — run-time only; *"If you change the basemap using the basemap switcher in the map element, your changes are not saved. To permanently change the basemap, you must change it in the web map."*
- **Search** — find locations or features
- Compass, find-my-location, pan/rotate (scenes), zoom in/out
- **Point zoom scale** — the scale used when a zoom *action* targets this map
- **Measurement** — linear distances, areas and perimeters

Pop-ups configured in the web map display when features are clicked ◐. Zoom controls render lower-right; bookmarks/legend upper-right ◐.

**Map as action TARGET** ✅ — selections on other elements can prompt the map to:

- **Zoom**, **Pan**, **Flash**, **Show pop-up**, **Follow feature** (five location actions), plus **Filter** applied to its operational layers.

**Map as action SOURCE** ✅ — two distinct wiring tabs:

- **Map actions tab** — triggers on a **change in the map's extent**: filter other elements to the visible extent, set another map element's extent (extent sync), or apply a spatial filter to a target.
- **Layer actions tab** — triggers on a **change in selection in an operational layer**: features are selected by clicking or with **Rectangle, Lasso, Circle, and Line** drawing tools.
- Documented limitation: **layer actions are unsupported on layers with clustering or binning enabled**.
- Operational layers participate independently of the map: a list/selector selection can filter one operational layer while the map itself stays put ◐.

### 1.4 Map legend element ✅

- **Dependent, not standalone**: *"The map legend element requires a map element to be added to your dashboard first."* It doesn't appear in the Add menu until a map exists.
- With multiple maps, the author must **explicitly bind the legend to one map** — the link is a per-element setting, not automatic.
- ◐ Layer order in the legend mirrors the web map's order; layers hidden in the web map, or outside their visible scale range, are hidden from the legend too.

### 1.5 The action framework (source → action → target) ✅

The complete interactivity model ([Actions](https://doc.arcgis.com/en/dashboards/latest/create-and-share/actions.htm)):

- *"An action's source can be the dashboard or one of its elements. An action's target is always one of the dashboard's elements."*
- **Exactly four trigger events**: **URL parameter change**, **map extent change**, **selection change**, **feature change** (feature change added post-11.4).
- **Exactly seven actions**: **Filter**, **Set extent**, **Flash**, **Show pop-up**, **Pan**, **Follow feature**, **Zoom**.
  - **Filter** = cross-filtering: *"Reduces the number of features available to the target element or operational layer when it's rendering."*
  - All six non-filter actions are defined against a **target map element**.
  - **Follow feature** (map stays centered on a moving feature) is desktop-view-only, web-maps-only, and requires point geometry, a refresh interval, and an operational-layer data source.
- **One source selection can drive several simultaneous actions on one target** — e.g. a category selector enabling Flash + Show pop-up + Pan + Zoom on the same map at once.
- Filter targets: lists, details, charts, tables, embedded content, rich text, selectors — plus indicator values/references, gauge value/min/max, and number-selector min/max.
- Non-map targets receive **attribute filter** actions and, where the source has polygon geometry, **spatial filter** actions. A source map's extent can set another map's extent or spatially filter a target.
- ◐ When source and target use **different data sources**, wiring requires an explicit relationship: an **attribute relationship** (source field/value matched against target field values) or a **spatial relationship** (source geometry intersected with target geometry).
- ◐ Authoring UX: wiring is configured per source element on its **Actions** tab — choose Single/Multiple selection mode, then **toggle on each target element**.

### 1.6 URL-parameter framework ✅

URL parameters are a first-class action *source* — the same action vocabulary invoked from outside the dashboard ([URL parameters](https://doc.arcgis.com/en/dashboards/latest/create-and-share/url-parameters.htm), [Configuring actions on URL parameters](https://doc.arcgis.com/en/dashboards/latest/create-and-share/configuring-actions-on-url-parameters.htm)):

- **Five author-configurable types**: **category**, **numeric**, **date**, **feature**, **geometry**. Configured at design time (name the parameter, choose an action, explicitly add target elements; feature parameters also pick a data source + **Unique ID field**).
- **Runtime syntax is a hash fragment, not a query string**: `<scheme>://<yourURL>/apps/dashboards/<id>#param=value&param2=value2`.
- Per-type action matrix:

| Parameter type | Available actions | Typical targets |
|---|---|---|
| Category | Filter (attribute) | Map's operational layer, list, details, charts, indicator, gauge, embedded content, selectors (latest docs add tables, rich text) |
| Numeric | Filter (attribute) — single values or ranges | same |
| Date | Filter (attribute) — ISO 8601 or UNIX epoch | same |
| Feature (matched via unique-ID field) | Zoom, Pan, Flash, Show pop-up, Filter (attribute or spatial — spatial only for polygon sources); latest docs add Follow feature | Map + filterable elements |
| Geometry: **point** | Zoom, Pan, Flash | Map |
| Geometry: **extent** | Set extent, Filter (spatial) | Map + filterable elements |

  → 6 of the 7 actions are exposed through URLs (all but Set extent for non-geometry types).
- ◐ Values must be percent-encoded (but commas separating multi-values must not be); all types accept `((null))`/`((notnull))`, category additionally `((empty))`/`((notempty))`.
- ◐ Changing parameters at runtime does **not** reload the dashboard (except the built-in `locale`); URL parameters and selectors targeting the same elements *"can contradict one another and cause unexpected results."* Built-in reserved parameters (`locale`, `mode`/edit, view) exist apart from the five author-created types.
- One panel vote was 2-1 on the configuration *workflow* only — UI drift between 10.9.1 (Add action/Add target buttons in dashboard settings) and the current release (per-view Settings with toggle-based targets). The source→action→target model itself is unchanged.
- ◐ Esri best practice: add URL parameters **last**, after all elements are configured.

### 1.7 Themes and views ◐

Dashboards support built-in and fully custom themes, and an optional separately-configured **mobile view** (may add new elements or reuse desktop ones; desktop view is the mobile default). (Esri tutorial, updated 2025-08-22.)

---

## Part 2 — ArcGIS for Power BI (all ◐ — primary-source extracted, not panel-verified)

Sources: [Esri: Get started with ArcGIS for Power BI](https://doc.arcgis.com/en/microsoft-365/latest/power-bi/get-started-with-arcgis-for-power-bi.htm), [Accounts](https://doc.arcgis.com/en/power-bi/latest/get-started/accounts.htm), [Apply a style](https://doc.arcgis.com/en/power-bi/latest/workflows/apply-a-style.htm), [Microsoft: ArcGIS visualizations](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-arcgis), [Microsoft: end-user ArcGIS](https://learn.microsoft.com/en-us/power-bi/consumer/end-user-arcgis), [What's new](https://doc.arcgis.com/en/power-bi/latest/get-started/what-s-new-in-arcgis-for-power-bi.htm).

### 2.1 What it is

A custom map visual **included with Power BI by default** (no install step) that adds ArcGIS mapping to reports and dashboards. Core documented capabilities: present data geographically, style via **smart mapping** templates, make area-based selections, show feature information for active layers, view demographics of areas of interest. Requires network connectivity — **ArcGIS maps cannot be viewed offline**.

### 2.2 Layers and symbology (smart mapping)

- Default symbology is **predictive smart mapping**: the symbol style updates automatically as data attributes are added to the visual.
- Point-coordinates-only layers offer only **Location** or **Heat map** styles; adding categorical/numeric attributes unlocks styles such as **Types and size** or **Color**. **Size** requires numeric attributes; **Color** handles categorical or numeric. The Symbol-type dropdown is context-sensitive (only styles that logically apply are listed). Styling lives in the Layers pane's **Symbology** and **Style options** tabs.
- A **Clustering** theme exists, but clustered locations cannot be used as buffer/drive-time input points.
- Recent additions (see §3.2): **pie/donut chart per location**, **dot density**, **predominant category**, **relationship (bivariate)** styles.

### 2.3 Map tools for report consumers

An expandable **Map tools** button exposes:

- **Layers pane** — show/hide layers, drag to reorder, zoom to a layer's data extent.
- **Search pane** — pin an address/place/POI; pins persist only for the session and cannot be saved with the map.
- **Basemap gallery** — for standard-tier users exactly four basemaps: Dark Gray Canvas, Light Gray Canvas, OpenStreetMap, Streets.

### 2.4 Selection tools and cross-filtering with other Power BI visuals

- **Seven location-selection tools**: single select, rectangle, circle, polygon, freehand polygon, **select by reference layer** (only when a reference layer is active), **drive-time select** (only when a buffer/drive-time search-area layer is active) — plus an eraser to clear.
- Selecting features on the map **triggers interactions (cross-filter/highlight) with the report's other visuals** — the standard Power BI interaction model. Hard cap: **250 selected data points at a time**.

### 2.5 Analysis tools

Four capabilities: **Infographics** (interactive demographic cards for map areas), **Reference layer** (demographic or ArcGIS layers), **Buffer/Drive time** (ring buffer up to **100 miles**, drive time up to **30 minutes**, **one search area per map**), **Find similar** (locations with attributes comparable to the current selection; only offered to consumers if the designer included data for it).

### 2.6 Data limits

Up to **30,000 data points** plotted from lat/long; address-type geocoding (ZIPs, street addresses) processes only the **first 15,000** points (place names and countries exempt).

### 2.7 Licensing tiers

| Capability | Standard (included with Power BI, no sign-in) | ArcGIS account (ArcGIS Online / Enterprise 10.8.1+) |
|---|---|---|
| Basemaps | 4 (Dark Gray, Light Gray, OSM, Streets) | All Esri + organization + custom basemaps |
| Geocoding | 3,500 locations/map; 10,000/month | 10,000/map; **no monthly limit** |
| Reference layers | 10 curated US-demographic layers + publicly shared ArcGIS feature layers | All global web maps/layers incl. Living Atlas & org content |
| Infographics | Curated US gallery, ≤ 2 variables, Drive Time/Radius only | Global demographics, ≤ 5 variables, GeoEnrichment data browser, all distance/travel settings |
| Buffer/drive-time analyses | 5 per map | 10 per map |
| Join layers | one | multiple (creation gated to Creator-or-higher) |
| Edit & save map | — | Creator-or-higher user type/role; publishing needs Power BI Pro/Premium; Enterprise 10.8.1 needs an ArcGIS for Power BI add-on license |

---

## Part 3 — What shipped in 2025–2026 (all ◐ unless noted)

### 3.1 ArcGIS Dashboards

- **October 2025** ([blog](https://www.esri.com/arcgis-blog/products/ops-dashboard/announcements/discover-whats-new-in-arcgis-dashboards-october-2025), ArcGIS Online cadence):
  - **Data sources panel** in the action bar — lists every map, layer and data expression in the dashboard; identify/replace/**repair broken data sources** in one place.
  - **Date-selector slider** option for temporal filtering.
  - Time-series charts: date-axis label spacing options (Compact / Default / Spacious).
  - Around this release, feature-based rich text, gauge and indicator became eligible **action sources** (surfaced in verifier cross-checks ✅-adjacent; see June 2026 consolidation below).
- **February 2026** ([blog](https://www.esri.com/arcgis-blog/products/ops-dashboard/announcements/discover-whats-new-in-arcgis-dashboards-february-2026)): **no new user-facing features** — bug fixes and performance only, plus an updated Accessibility Conformance Report (VPAT).
- **June 2026** ([What's new](https://doc.arcgis.com/en/dashboards/latest/reference/whats-new.htm)) — enhancements, no brand-new element types:
  - Action framework expanded: **feature-based Rich Text, Gauge, Indicator, Details, and Embedded Content can be action sources**; feature-based Rich Text can also be an action **target**.
  - **Rich Text supports an optional data source** — now a data-driven element.
  - **Indicator** gained resizable top/middle/bottom text sections (drag panel gutters).
  - Viewer-facing controls: author-enabled **focus mode** (expand an element) and a **Show feature menu** toggle for feature-based elements.
  - Verifier cross-checks of the release notes confirm **no new action types** were added ✅ — the seven-action vocabulary is stable.

### 3.2 ArcGIS for Power BI

- **v2025.1.800 (2025-06-20)** ([change log](https://community.esri.com/t5/arcgis-for-power-bi-blog/arcgis-for-power-bi-v-2025-1-change-log-and/ba-p/1626997)):
  - **Power BI report themes** support (built-in themes, custom theme JSON, downloadable ArcGIS theme snippets, high-contrast mode). Themes apply only to the Power BI data layer and map-tools UI — ArcGIS layers and joined layers are not themed; downloading the visual's theme requires ArcGIS sign-in.
  - **Spatial reference support** for non-WGS84 Power BI XY data (picked in the Location type widget); configurable **Home extent**.
  - **Save to ArcGIS** (layer styling/properties written back; owner/Admin/shared-update group; edit mode only); **Hide selected layer** button; **18 new demographic feature layers**.
  - Fixes: buffer/drive-time single-select on certain line layers; Join Layer creation restricted to Creator-or-higher.
- **Current what's-new page** (undated "most recent update"): four new smart-mapping styles — **pie/donut chart per location, dot density, predominant category, relationship (bivariate)**; Measure tool gained **geometry guides** and **snap to layer**; **multiple label classes** + expanded label formatting; redesigned **Analysis pane**; **Microsoft Entra ID consent flow** for guest access.

---

## Part 4 — Parity notes for `qgis_dashboards`

How the plugin's architecture maps onto the ArcGIS Dashboards model (for roadmap discussion, not verified claims):

| ArcGIS Dashboards concept | `qgis_dashboards` equivalent | Gap / note |
|---|---|---|
| Source→action→target wiring, explicit per-element | `DashboardBus` connection graph; per-tile **Connections…** inspector | ✔ Same explicit-wiring philosophy. ArcGIS separates *which action* per edge; our edges are filter-only + implicit fly-to on the map |
| **Filter** action (cross-filter) | `set_filter` / `combined_filter_for` (AND of wired sources) | ✔ equivalent |
| **Flash / Pan / Zoom** on a map from a list selection | `featureAction` → map zoom+flash | Partial — we fuse the three into one behavior; ArcGIS lets authors enable each independently |
| **Show pop-up** action | — (map identify exists in Use mode, but not action-triggered) | Gap |
| **Follow feature** (live tracking) | — | Gap (ArcGIS limits it to desktop + point layers + refresh interval) |
| **Set extent** (map→map extent sync) | — (single map mirrors QGIS canvas) | Gap; relevant if multi-map pages ever land |
| Map extent change → filter targets (**Map actions** tab) | `map_element` debounced extent filter (`extent_filter_expression`) | ✔ equivalent, ours is CRS-safe expression-based |
| Layer selection tools (Rectangle/Lasso/Circle/Line) | — (click-identify only) | Gap: no on-map multi-feature selection as a filter source |
| "Render only when filtered" + "No selection" placeholder | — | Gap; interesting low-cost UX parity item |
| URL parameters (#param=value external entry) | — (`scripting.py` facade is the programmatic entry) | Different audience: ours targets automation (MCP), theirs targets link-sharing |
| Selectors: category / number / date | `category_selector` only | Gap: number + date (slider) selectors |
| Map legend element (bound to one map) | filter-legend work (see `docs/superpowers/specs/2026-06-21-filter-legend-map-filtering-design.md`) | Similar dependent-element pattern: legend must bind to an existing map |
| Attribute/spatial relationships across data sources | — (filters assume shared layer semantics per target) | Gap: cross-layer field mapping for filters |
| Element anatomy: header/captions/no-data/focus mode | title/description in `base.py`; no no-data label, no focus mode | Partial |

**Where our model differs by design:** QGIS Dashboards' Build/Use lock, free-canvas geometry, and per-tile theme overrides have no ArcGIS Dashboards counterpart; ArcGIS's grid-of-stacked-panels layout and mobile view have none in ours.

---

## Appendix — verification detail

- **Verified findings**: 25 claims → 25 confirmed (24 × 3-0, 1 × 2-1 where the dissent concerned UI drift between doc versions, not substance), merged to 11 findings. All concern ArcGIS Dashboards; checked live against the `/latest/` doc branch on 2026-07-04 (post-June-2026 release).
- **Extraction-only sections** (Parts 2 and 3): verbatim quotes from official Esri (`doc.arcgis.com`, `esri.com/arcgis-blog`, `community.esri.com` official product blog) and Microsoft (`learn.microsoft.com`) pages, captured by the same workflow but outside the 25-claim verification budget. The Power BI what's-new page carries no version numbers/dates — its items cannot be pinned to 2025 vs 2026 from that page alone.
- **Version-drift caution**: two URL-parameter claims cite version-pinned 10.9.1 pages; the current release configures the same wiring per **view** (Settings tab, toggle-based targets) instead of the old Add action/Add target buttons.
- **Open questions for a follow-up pass**:
  1. Per-element deep dives (gauge, table, details, rich text, embedded content, header, number/date selectors) — each one's full option set was only confirmed indirectly.
  2. Adversarial verification of the Power BI section (Part 2) and the release-notes section (Part 3).
  3. Whether map tools (search, bookmarks, measurement) interact with or conflict with dashboard actions.
  4. Full documented limitations of layer actions beyond the clustering/binning restriction.

### Primary sources

| Source | Coverage |
|---|---|
| [Configure an element](https://doc.arcgis.com/en/dashboards/latest/get-started/configure-an-element.htm) | element model, anatomy, render-only-when-filtered |
| [Actions](https://doc.arcgis.com/en/dashboards/latest/create-and-share/actions.htm) | trigger events, seven actions, relationships |
| [Configuring actions on dashboard elements](https://doc.arcgis.com/en/dashboards/latest/create-and-share/configuring-actions-on-dashboard-elements.htm) | filter targets, map source/target tabs, Actions tab UX |
| [Map element and tools](https://doc.arcgis.com/en/dashboards/latest/get-started/map-element-and-tools.htm) | map tool set, selection tools, clustering limitation |
| [Map legend](https://doc.arcgis.com/en/dashboards/latest/get-started/map-legend.htm) | dependent legend element |
| [URL parameters](https://doc.arcgis.com/en/dashboards/latest/create-and-share/url-parameters.htm) + [Configuring actions on URL parameters](https://doc.arcgis.com/en/dashboards/latest/create-and-share/configuring-actions-on-url-parameters.htm) (+ 10.9.1 tables) | five types, hash syntax, per-type action matrix |
| [Dashboards What's new](https://doc.arcgis.com/en/dashboards/latest/reference/whats-new.htm) + Oct 2025 / Feb 2026 blogs | 2025–2026 Dashboards releases |
| [Get started with ArcGIS for Power BI](https://doc.arcgis.com/en/microsoft-365/latest/power-bi/get-started-with-arcgis-for-power-bi.htm), [Accounts](https://doc.arcgis.com/en/power-bi/latest/get-started/accounts.htm), [Apply a style](https://doc.arcgis.com/en/power-bi/latest/workflows/apply-a-style.htm) | Power BI visual capabilities, smart mapping, tiers |
| [Microsoft: ArcGIS visualizations](https://learn.microsoft.com/en-us/power-bi/visuals/power-bi-visualizations-arcgis), [end-user ArcGIS](https://learn.microsoft.com/en-us/power-bi/consumer/end-user-arcgis) | selection tools, limits, consumer map tools |
| [Power BI What's new](https://doc.arcgis.com/en/power-bi/latest/get-started/what-s-new-in-arcgis-for-power-bi.htm), [v2025.1 change log](https://community.esri.com/t5/arcgis-for-power-bi-blog/arcgis-for-power-bi-v-2025-1-change-log-and/ba-p/1626997) | 2025–2026 Power BI releases |
| [Esri tutorial: Create your first dashboard](https://www.esri.com/arcgis-blog/products/ops-dashboard/mapping/create-first-arcgis-dashboards), [URL-parameter tutorial](https://developers.arcgis.com/documentation/app-builders/no-code/tutorials/tools/customize-dashboard-url-parameter/) | authoring walkthroughs, list→map actions, themes/mobile view |
