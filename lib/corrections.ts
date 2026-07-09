// Supabase access for the tie point corrections review desk (/approvals).
//
// Server-side only: uses the Supabase SECRET key (SUPABASE_SECRET_KEY env,
// never shipped to the browser) because the corrections table is write-only
// for the public and the approve/reject functions are revoked from every
// public role. The QGIS plugin holds only the publishable key and can do
// neither of these things.

const SUPABASE_URL = "https://dywixbogcfphybzmimqw.supabase.co";

export interface Correction {
  id: number;
  tiepoint_id: number | null;
  tiepoint_name: string;
  tiepoint_description: string | null;
  province: string | null;
  municipality: string | null;
  current_northing: number | null;
  current_easting: number | null;
  proposed_northing: number | null;
  proposed_easting: number | null;
  remarks: string | null;
  reporter_name: string | null;
  reporter_contact: string | null;
  plugin_version: string | null;
  status: "pending" | "accepted" | "rejected";
  created_at: string;
  reviewed_at: string | null;
}

export class ConfigError extends Error {}

function secretKey(): string {
  const key = process.env.SUPABASE_SECRET_KEY;
  if (!key) {
    throw new ConfigError(
      "SUPABASE_SECRET_KEY is not set. Copy the secret (service_role) key from " +
        "Supabase Dashboard → Project Settings → API Keys into .env.local " +
        "(and the Vercel project env)."
    );
  }
  return key;
}

async function rest(path: string, init?: RequestInit): Promise<Response> {
  const key = secretKey();
  return fetch(`${SUPABASE_URL}/rest/v1${path}`, {
    ...init,
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });
}

export async function listCorrections(): Promise<{
  pending: Correction[];
  reviewed: Correction[];
}> {
  const [pendingRes, reviewedRes] = await Promise.all([
    rest("/tiepoint_corrections?status=eq.pending&order=created_at.asc"),
    rest(
      "/tiepoint_corrections?status=neq.pending&order=reviewed_at.desc&limit=10"
    ),
  ]);
  if (!pendingRes.ok || !reviewedRes.ok) {
    const status = pendingRes.ok ? reviewedRes.status : pendingRes.status;
    throw new Error(`Could not load corrections from Supabase (HTTP ${status}).`);
  }
  return {
    pending: (await pendingRes.json()) as Correction[],
    reviewed: (await reviewedRes.json()) as Correction[],
  };
}

/**
 * Run one review decision through the database's atomic
 * approve_correction / reject_correction function. Approving copies the
 * proposed coordinates into the live tiepoints table in the same
 * transaction that marks the report accepted.
 *
 * Returns null on success, or a human-readable error message.
 */
export async function reviewCorrection(
  decision: "approve" | "reject",
  id: number
): Promise<string | null> {
  const res = await rest(`/rpc/${decision}_correction`, {
    method: "POST",
    body: JSON.stringify({ correction_id: id }),
  });
  if (res.ok) return null;
  try {
    const body = (await res.json()) as { message?: string };
    return body.message ?? `The database rejected the request (HTTP ${res.status}).`;
  } catch {
    return `The database rejected the request (HTTP ${res.status}).`;
  }
}
