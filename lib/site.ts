// Centralized site copy + links, so pages and the plugin's published URLs stay
// in sync. The plugin builds the same view URL in submit_payload.view_url.

// The umbrella identity — the root "/" hub that lists every QGIS plugin.
export const HUB = {
  name: "QGIS Plugins",
  tagline: "Free, open-source tools that make QGIS do more.",
  domain: "qgis.byzenterra.org",
  author: "Isaac Enage",
  authorEmail: "isaacenagework@gmail.com",
  github: "https://github.com/isaacenage",
  repo: "https://github.com/isaacenage/QGIS-Plugins",
} as const;

// The QGIS Dashboard plugin identity — its section lives under /qdashboards.
export const SITE = {
  name: "QGIS Dashboard",
  tagline: "Interactive, cross-filtering dashboards — built right inside QGIS.",
  domain: "qgis.byzenterra.org",
  // The dashboard site is a route segment of the hub, not a Next basePath.
  basePath: "/qdashboards",
  author: "Isaac Enage",
  authorEmail: "isaacenagework@gmail.com",
  repo: "https://github.com/isaacenage/QGIS-Plugins",
  issues: "https://github.com/isaacenage/QGIS-Plugins/issues",
} as const;

/** Prefix an absolute-from-root page path with the dashboard route segment. */
export function withBase(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${SITE.basePath}${p}`;
}

/** The public viewer URL for a published dashboard slug. */
export function viewUrl(slug: string): string {
  return withBase(`/view?d=${encodeURIComponent(slug)}`);
}
