// Legacy gallery-submission shim.
//
// Older plugin versions POST dashboards here (gzipped, ≤4 MB — the Vercel
// body cap). Current plugin versions upload straight to Supabase Storage with
// the publishable key and never touch this route. It now writes to the same
// Supabase bucket + dashboards table (service key, server-side only) instead
// of opening a GitHub Pull Request — submissions go live instantly.

import { gunzipSync } from "node:zlib";
import { slugify } from "@/lib/submit-core.mjs";

export const runtime = "nodejs";

const SUPABASE_URL = "https://dywixbogcfphybzmimqw.supabase.co";
const BUCKET = "dashboards";
const PUBLIC_VIEW_BASE = "https://qgis.byzenterra.org/qdashboards/view";

// Mirror the bucket / table constraints.
const MAX_HTML_BYTES = 50 * 1024 * 1024; // decompressed
const MAX_THUMB_BYTES = 4 * 1024 * 1024;
const MAX_TITLE = 200;
const MAX_AUTHOR = 120;
const MAX_DESC = 400;
const MAX_SLUG_ATTEMPTS = 25;
// Sanity marker that the upload is a real exported dashboard, not arbitrary
// HTML: every export embeds its data in <script ... id="dashboard-data">.
const DASHBOARD_MARKER = 'id="dashboard-data"';

class SubmitError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface SubmitBody {
  title?: unknown;
  author?: unknown;
  description?: unknown;
  html_gz_b64?: unknown;
  thumb_b64?: unknown;
}

function asString(value: unknown, field: string, max: number, required = true): string {
  if (value === undefined || value === null || value === "") {
    if (required) throw new SubmitError(400, `Missing "${field}".`);
    return "";
  }
  if (typeof value !== "string") throw new SubmitError(400, `"${field}" must be text.`);
  const trimmed = value.trim();
  if (required && !trimmed) throw new SubmitError(400, `"${field}" can't be empty.`);
  if (trimmed.length > max) throw new SubmitError(400, `"${field}" is too long.`);
  return trimmed;
}

function decodeBase64(value: unknown, field: string): Buffer {
  if (typeof value !== "string" || !value) {
    throw new SubmitError(400, `Missing "${field}".`);
  }
  try {
    return Buffer.from(value, "base64");
  } catch {
    throw new SubmitError(400, `"${field}" is not valid base64.`);
  }
}

function candidateSlug(base: string, attempt: number): string {
  return attempt === 0 ? base : `${base}-${attempt + 1}`;
}

// ---- Supabase REST (service key, server-side only) ---------------------------

function serviceKey(): string {
  const key = process.env.SUPABASE_SECRET_KEY;
  if (!key) {
    console.error("SUPABASE_SECRET_KEY is not configured.");
    throw new SubmitError(500, "The gallery service is not configured yet. Please contact the maintainer.");
  }
  return key;
}

function isDuplicate(status: number, body: unknown): boolean {
  if (status === 409) return true;
  return (
    typeof body === "object" &&
    body !== null &&
    ((body as Record<string, unknown>).statusCode === "409" ||
      (body as Record<string, unknown>).error === "Duplicate")
  );
}

async function storageUpload(
  key: string,
  objectKey: string,
  data: Buffer,
  contentType: string,
): Promise<"ok" | "conflict"> {
  const res = await fetch(`${SUPABASE_URL}/storage/v1/object/${BUCKET}/${objectKey}`, {
    method: "POST",
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": contentType,
    },
    body: new Uint8Array(data),
    cache: "no-store",
  });
  if (res.ok) return "ok";
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error body */
  }
  if (isDuplicate(res.status, body)) return "conflict";
  console.error(`Storage upload ${objectKey} -> ${res.status}`, body);
  throw new SubmitError(502, "The gallery storage rejected the upload. Try again shortly.");
}

async function insertRow(key: string, row: Record<string, unknown>): Promise<"ok" | "conflict"> {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/dashboards`, {
    method: "POST",
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify(row),
    cache: "no-store",
  });
  if (res.ok) return "ok";
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error body */
  }
  if (isDuplicate(res.status, body)) return "conflict";
  console.error(`dashboards insert -> ${res.status}`, body);
  throw new SubmitError(502, "The gallery couldn't register the dashboard. Try again shortly.");
}

// ---- handler ----------------------------------------------------------------

async function handle(req: Request): Promise<Response> {
  const key = serviceKey();

  let parsed: SubmitBody;
  try {
    parsed = (await req.json()) as SubmitBody;
  } catch {
    throw new SubmitError(400, "Expected a JSON body.");
  }

  const title = asString(parsed.title, "title", MAX_TITLE);
  const author = asString(parsed.author, "author", MAX_AUTHOR, false);
  const description = asString(parsed.description, "description", MAX_DESC, false);
  const thumbBytes = decodeBase64(parsed.thumb_b64, "thumb_b64");
  if (thumbBytes.length > MAX_THUMB_BYTES) {
    throw new SubmitError(413, "The thumbnail is too large.");
  }

  const htmlGz = decodeBase64(parsed.html_gz_b64, "html_gz_b64");
  let htmlBuf: Buffer;
  try {
    htmlBuf = gunzipSync(htmlGz);
  } catch {
    throw new SubmitError(400, "The dashboard data could not be read (bad gzip).");
  }
  if (htmlBuf.length > MAX_HTML_BYTES) {
    throw new SubmitError(413, "This dashboard is too large to publish to the gallery.");
  }
  if (!htmlBuf.toString("utf-8").includes(DASHBOARD_MARKER)) {
    throw new SubmitError(400, "That file doesn't look like an exported dashboard.");
  }

  // The index.html upload claims the slug (storage inserts are
  // first-write-wins); on collision retry with -2, -3, …
  const base = slugify(title);
  let slug: string | null = null;
  for (let attempt = 0; attempt < MAX_SLUG_ATTEMPTS; attempt += 1) {
    const candidate = candidateSlug(base, attempt);
    const outcome = await storageUpload(key, `${candidate}/index.html`, htmlBuf, "text/html");
    if (outcome === "ok") {
      slug = candidate;
      break;
    }
  }
  if (!slug) {
    throw new SubmitError(409, "Too many dashboards share this title. Rename your QGIS project and try again.");
  }

  // A missing thumbnail degrades the card, not the dashboard.
  let hasThumb = false;
  try {
    hasThumb = (await storageUpload(key, `${slug}/thumb.png`, thumbBytes, "image/png")) === "ok";
  } catch {
    hasThumb = false;
  }

  const row: Record<string, unknown> = {
    slug,
    title: title || slug,
    author: author || null,
    html_path: `${BUCKET}/${slug}/index.html`,
    thumb_path: hasThumb ? `${BUCKET}/${slug}/thumb.png` : null,
    html_bytes: htmlBuf.length,
  };
  if (description) row.description = description;
  if ((await insertRow(key, row)) !== "ok") {
    throw new SubmitError(409, "This gallery name is reserved. Rename your QGIS project and try again.");
  }

  const viewUrl = `${PUBLIC_VIEW_BASE}?d=${encodeURIComponent(slug)}`;
  return Response.json({ ok: true, slug, view_url: viewUrl });
}

export async function POST(req: Request): Promise<Response> {
  try {
    return await handle(req);
  } catch (err) {
    if (err instanceof SubmitError) {
      return Response.json({ ok: false, message: err.message }, { status: err.status });
    }
    console.error("Unexpected submit error:", err);
    return Response.json(
      { ok: false, message: "Something went wrong while submitting. Please try again." },
      { status: 500 },
    );
  }
}
