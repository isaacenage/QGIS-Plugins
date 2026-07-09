// The tie point review desk — domain/approvals.
//
// Lists pending coordinate-correction reports sent from the Title Plotter PH
// plugin. "Approve" copies the proposed values into the live tiepoints table
// atomically (every plugin user gets them on their next search); "Reject"
// dismisses the report. Access is gated by Basic auth in middleware.ts.

import type { Metadata } from "next";
import { HUB } from "@/lib/site";
import { ConfigError, listCorrections, type Correction } from "@/lib/corrections";
import { approveCorrection, rejectCorrection } from "./actions";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Tie point approvals",
  robots: { index: false, follow: false },
};

const num = new Intl.NumberFormat("en-PH", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

const when = new Intl.DateTimeFormat("en-PH", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Manila",
});

function coord(value: number | null): string {
  return value === null ? "—" : num.format(value);
}

/** One axis of the coordinate ledger: current → proposed, delta emphasized. */
function AxisRow({
  label,
  current,
  proposed,
}: {
  label: string;
  current: number | null;
  proposed: number | null;
}) {
  const changed = proposed !== null && proposed !== current;
  return (
    <div className="flex items-baseline gap-3 py-1.5">
      <span className="eyebrow w-20 shrink-0 text-[0.66rem] before:hidden">
        {label}
      </span>
      <span
        className={`stat text-sm ${
          changed ? "text-muted line-through decoration-1" : "text-ink"
        }`}
      >
        {coord(current)}
      </span>
      {changed ? (
        <>
          <span aria-hidden className="text-faint text-sm">
            →
          </span>
          <span className="stat text-sm font-semibold text-accent-ink">
            {coord(proposed)}
          </span>
        </>
      ) : (
        <span className="text-xs text-faint italic">unchanged</span>
      )}
    </div>
  );
}

function StatusChip({ status }: { status: Correction["status"] }) {
  const look =
    status === "accepted"
      ? "bg-cat-green/15 text-[#2e6f4f]"
      : status === "rejected"
        ? "bg-line/60 text-muted"
        : "bg-cat-amber/15 text-[#9a6224]";
  return (
    <span
      className={`stat rounded-full px-2.5 py-0.5 text-[0.68rem] uppercase tracking-[0.14em] ${look}`}
    >
      {status}
    </span>
  );
}

function PendingCard({ correction }: { correction: Correction }) {
  const hasCoords =
    correction.proposed_northing !== null || correction.proposed_easting !== null;
  const orphaned = correction.tiepoint_id === null;
  return (
    <article className="tile p-6">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="display text-xl">
            {correction.tiepoint_name}
            <span className="ml-3 text-sm font-normal text-muted">
              {[correction.municipality, correction.province]
                .filter(Boolean)
                .join(", ")}
            </span>
          </h2>
          {correction.tiepoint_description && (
            <p className="mt-1 text-sm text-muted">
              {correction.tiepoint_description}
            </p>
          )}
        </div>
        <span className="stat text-xs text-faint">
          {when.format(new Date(correction.created_at))}
          {correction.plugin_version && ` · v${correction.plugin_version}`}
        </span>
      </header>

      {/* The ledger: exactly what Approve will write. */}
      <div className="mt-4 rounded-[10px] border border-line bg-paper px-4 py-2">
        {hasCoords ? (
          <>
            <AxisRow
              label="Northing"
              current={correction.current_northing}
              proposed={correction.proposed_northing}
            />
            <AxisRow
              label="Easting"
              current={correction.current_easting}
              proposed={correction.proposed_easting}
            />
          </>
        ) : (
          <p className="py-1.5 text-sm text-muted">
            No coordinate change proposed — remarks only.
          </p>
        )}
      </div>

      {correction.remarks && (
        <p className="mt-4 border-l-2 border-line-strong pl-3 text-sm text-ink">
          {correction.remarks}
        </p>
      )}

      <footer className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          Reported by{" "}
          <strong className="text-ink">
            {correction.reporter_name ?? "Anonymous"}
          </strong>
          {correction.reporter_contact && (
            <span className="stat ml-2 text-xs text-faint">
              {correction.reporter_contact}
            </span>
          )}
        </p>
        <div className="flex items-center gap-2">
          <form action={rejectCorrection}>
            <input type="hidden" name="id" value={correction.id} />
            <button
              type="submit"
              className="rounded-[10px] border border-line px-4 py-2 text-sm text-muted transition-colors hover:border-[#c2725f] hover:text-[#a84b34]"
            >
              Reject
            </button>
          </form>
          <form action={approveCorrection}>
            <input type="hidden" name="id" value={correction.id} />
            <button
              type="submit"
              className="rounded-[10px] bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-ink"
            >
              {hasCoords && !orphaned
                ? "Approve — update tie point"
                : "Mark reviewed"}
            </button>
          </form>
        </div>
      </footer>

      {orphaned && (
        <p className="mt-3 text-xs text-[#9a6224]">
          The tie point this report referenced no longer exists; approving only
          archives the report.
        </p>
      )}
    </article>
  );
}

export default async function ApprovalsPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  let pending: Correction[] = [];
  let reviewed: Correction[] = [];
  let loadError: string | null = null;
  let configError: string | null = null;
  try {
    ({ pending, reviewed } = await listCorrections());
  } catch (cause) {
    if (cause instanceof ConfigError) configError = cause.message;
    else loadError = cause instanceof Error ? cause.message : "Unexpected error.";
  }

  return (
    <main className="mx-auto max-w-3xl px-5 py-12">
      <header className="mb-8">
        <p className="eyebrow">Title Plotter PH · Review desk</p>
        <h1 className="display mt-3 text-4xl">Tie point approvals</h1>
        <p className="mt-3 text-muted">
          Coordinate corrections sent by surveyors from the plugin. Approving
          updates the live tie point database instantly — every user gets the
          corrected values on their next search.
        </p>
      </header>

      {error && (
        <div className="tile mb-6 border-[#c2725f] p-4 text-sm text-[#a84b34]">
          {error}
        </div>
      )}

      {configError && (
        <div className="tile p-6 text-sm leading-relaxed text-muted">
          <p className="font-medium text-ink">Almost there — one secret to set.</p>
          <p className="mt-2">{configError}</p>
        </div>
      )}
      {loadError && (
        <div className="tile border-[#c2725f] p-6 text-sm text-[#a84b34]">
          {loadError}
        </div>
      )}

      {!configError && !loadError && (
        <>
          <p className="stat mb-4 text-sm text-muted">
            {pending.length === 0
              ? "Queue is clear."
              : `${pending.length} pending ${pending.length === 1 ? "report" : "reports"}`}
          </p>

          <div className="flex flex-col gap-5">
            {pending.map((c) => (
              <PendingCard key={c.id} correction={c} />
            ))}
            {pending.length === 0 && (
              <div className="tile p-8 text-center text-sm text-muted">
                No corrections waiting. New reports from the plugin&apos;s
                &ldquo;Report Correction&rdquo; form land here.
              </div>
            )}
          </div>

          {reviewed.length > 0 && (
            <section className="mt-12">
              <h2 className="eyebrow mb-4">Recently reviewed</h2>
              <ul className="flex flex-col divide-y divide-line">
                {reviewed.map((c) => (
                  <li
                    key={c.id}
                    className="flex flex-wrap items-baseline justify-between gap-2 py-3 text-sm"
                  >
                    <span>
                      <strong className="font-medium">{c.tiepoint_name}</strong>
                      <span className="ml-2 text-muted">
                        {[c.municipality, c.province].filter(Boolean).join(", ")}
                      </span>
                      <span className="ml-2 text-faint">
                        by {c.reporter_name ?? "Anonymous"}
                      </span>
                    </span>
                    <span className="flex items-center gap-2">
                      <StatusChip status={c.status} />
                      {c.reviewed_at && (
                        <span className="stat text-xs text-faint">
                          {when.format(new Date(c.reviewed_at))}
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <footer className="mt-16 border-t border-line pt-5 text-xs text-faint">
        {HUB.name} · private review desk — reports are write-only for plugin
        users; only this desk can change the tie point database.
      </footer>
    </main>
  );
}
