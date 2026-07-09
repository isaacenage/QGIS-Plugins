// The single contract between the plugin and this site. The plugin's
// "Publish to public" uploads a dashboard's files to the Supabase
// "dashboards" storage bucket and registers one row in the dashboards table;
// the gallery reads that table here. No repo commits, no rebuilds — a
// published dashboard appears as soon as the row lands.
//
// The publishable key below is safe in client code by design: Row Level
// Security limits it to reading published rows and inserting new ones.

export interface DashboardEntry {
  slug: string;
  title: string;
  author: string;
  date: string; // ISO YYYY-MM-DD
  path: string; // storage path, e.g. "dashboards/<slug>/index.html"
  thumb?: string; // storage path, e.g. "dashboards/<slug>/thumb.png"
  description?: string;
}

const SUPABASE_URL = "https://dywixbogcfphybzmimqw.supabase.co";
const SUPABASE_PUBLISHABLE_KEY =
  "sb_publishable_boQFoicY4U3d2naPjM8Ogg_vurpLiro";

interface DashboardRow {
  slug: string;
  title: string;
  author: string | null;
  description: string | null;
  html_path: string;
  thumb_path: string | null;
  created_at: string;
}

/** Public CDN URL for a storage path recorded in the table. */
function storageUrl(path: string): string {
  return `${SUPABASE_URL}/storage/v1/object/public/${path
    .split("/")
    .map(encodeURIComponent)
    .join("/")}`;
}

/**
 * URL the viewer FETCHES the dashboard HTML from. Supabase serves HTML as
 * text/plain on the shared domain (anti-phishing), so this is not iframe-able
 * directly — the viewer fetches it and loads a sandboxed Blob URL instead
 * (see components/dashboard-frame.tsx).
 */
export function dashboardSrc(entry: DashboardEntry): string {
  return storageUrl(entry.path);
}

/** Direct download link for the self-contained dashboard file. */
export function downloadSrc(entry: DashboardEntry): string {
  return `${dashboardSrc(entry)}?download=${encodeURIComponent(entry.slug)}.html`;
}

/** URL of a dashboard's thumbnail, or null if it has none. */
export function thumbSrc(entry: DashboardEntry): string | null {
  if (!entry.thumb) return null;
  return storageUrl(entry.thumb);
}

/**
 * Load the published dashboards from Supabase (client-side fetch), newest
 * first. Returns [] on any failure — an empty gallery is a valid state.
 */
export async function loadManifest(): Promise<DashboardEntry[]> {
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/dashboards` +
        `?status=eq.published` +
        `&select=slug,title,author,description,html_path,thumb_path,created_at` +
        `&order=created_at.desc`,
      {
        headers: {
          apikey: SUPABASE_PUBLISHABLE_KEY,
          Authorization: `Bearer ${SUPABASE_PUBLISHABLE_KEY}`,
        },
        cache: "no-store",
      },
    );
    if (!res.ok) return [];
    const rows = (await res.json()) as DashboardRow[];
    if (!Array.isArray(rows)) return [];
    return rows
      .filter((r) => r && typeof r.slug === "string" && typeof r.html_path === "string")
      .map((r) => ({
        slug: r.slug,
        title: r.title || r.slug,
        author: r.author ?? "",
        date: (r.created_at || "").slice(0, 10),
        path: r.html_path,
        thumb: r.thumb_path ?? undefined,
        ...(r.description ? { description: r.description } : {}),
      }));
  } catch {
    return [];
  }
}
