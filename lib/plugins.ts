// The catalog of plugins the hub lists. This site is the home for every QGIS
// plugin byZenterra.org ships; each entry that is `status: "live"` links to
// its own section under the site (e.g. /qdashboards). Add a new plugin by
// adding a row here and creating its app/<slug>/ route segment — every
// "N plugins" figure on the site derives from this array's length.

export interface Plugin {
  slug: string; // route segment, e.g. "qdashboards"
  name: string;
  blurb: string; // one-line summary for the grid card
  pitch: string; // a fuller paragraph for the spotlight
  href: string; // where its card/CTA links (internal route or external)
  features: string[]; // short chips shown in the spotlight
  status: "live" | "soon";
}

export const PLUGINS: Plugin[] = [
  {
    slug: "qdashboards",
    name: "QGIS Dashboard",
    blurb:
      "Interactive, cross-filtering dashboards built from your vector layers.",
    pitch:
      "ArcGIS-Dashboards-style interactive dashboards built right inside your QGIS project. Charts, indicators, lists, a live map and selectors that cross-filter each other in real time — no export, no separate web app, no cost.",
    href: "/qdashboards",
    features: ["23 chart types", "Live cross-filter", "12 themes", "HTML export"],
    status: "live",
  },
  {
    slug: "titleplotterph",
    name: "Title Plotter PH",
    blurb:
      "Plot Philippine land titles from technical descriptions — no GIS background needed.",
    pitch:
      "Turn the bearing-and-distance technical descriptions on Philippine TCTs and OCTs into accurate parcel geometry, right inside QGIS. Snap to a built-in database of official tie points, preview the lot live, check the closing error, and even let AI OCR read the metes-and-bounds straight off a title image.",
    href: "/titleplotterph",
    features: ["85,000+ tie points", "AI OCR", "PRS92 / WGS84", "Offline cache"],
    status: "live",
  },
];

/** How many plugins the hub currently ships (live entries only). */
export function pluginCount(): number {
  return PLUGINS.filter((p) => p.status === "live").length;
}

/** The one plugin to spotlight on the hub (first live entry). */
export function featuredPlugin(): Plugin | undefined {
  return PLUGINS.find((p) => p.status === "live");
}
