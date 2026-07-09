// Pure, dependency-free helpers for the legacy submission API route
// (app/api/submit/route.ts). No Next/React/Node-fs imports here, so this runs
// under `node --test` (see submit-core.test.mjs). Mirrors the plugin's
// submit_payload.py slug logic so plugin and site agree.

const SLUG_STRIP = /[^a-z0-9]+/g;
const COMBINING = /[̀-ͯ]/g; // accents, after NFKD decomposition

/**
 * URL-safe slug for a title: lowercase, accents stripped, non-alphanumeric runs
 * collapsed to single hyphens, trimmed. Empty/symbol-only → fallback.
 * Mirrors github_publish.slugify so plugin and site agree.
 * @param {string|null|undefined} title
 * @param {string} [fallback]
 * @returns {string}
 */
export function slugify(title, fallback = "dashboard") {
  const text = (title || "")
    .normalize("NFKD")
    .replace(COMBINING, "")
    .toLowerCase()
    .replace(SLUG_STRIP, "-")
    .replace(/^-+|-+$/g, "");
  return text || fallback;
}

/**
 * Return a slug not already used. If `base` is taken, append -2, -3, … until
 * free. `taken` is any iterable of existing slugs.
 * @param {string} base
 * @param {Iterable<string>} taken
 * @returns {string}
 */
export function uniqueSlug(base, taken) {
  const used = new Set(taken);
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

/**
 * A single manifest entry (also the per-dashboard meta.json contents). Paths are
 * relative to public/. Mirrors lib/manifest.ts:DashboardEntry and the former
 * github_publish.build_entry.
 * @param {{slug:string,title?:string,author?:string,date:string,description?:string}} fields
 */
export function buildEntry({ slug, title, author, date, description }) {
  /** @type {Record<string, string>} */
  const entry = {
    slug,
    title: title || slug,
    author: author || "",
    date,
    path: `dashboards/${slug}/index.html`,
    thumb: `dashboards/${slug}/thumb.png`,
  };
  if (description) entry.description = description;
  return entry;
}

/**
 * Sort manifest entries newest-first (date desc), ties broken by title asc.
 * Returns a NEW array (input not mutated).
 * @param {Array<{date?:string,title?:string}>} entries
 */
export function sortEntries(entries) {
  return [...entries].sort((a, b) => {
    const da = a.date || "";
    const db = b.date || "";
    if (da !== db) return da < db ? 1 : -1; // newer date first
    return (a.title || "").localeCompare(b.title || "");
  });
}
