"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { DashboardEntry, dashboardSrc, downloadSrc, loadManifest } from "@/lib/manifest";
import { withBase } from "@/lib/site";
import { DashboardFrame } from "./dashboard-frame";

export function DashboardViewer() {
  const slug = useSearchParams().get("d");
  const [state, setState] = useState<"loading" | "ready">("loading");
  const [entry, setEntry] = useState<DashboardEntry | null>(null);

  useEffect(() => {
    let alive = true;
    loadManifest().then((data) => {
      if (!alive) return;
      setEntry(data.find((e) => e.slug === slug) ?? null);
      setState("ready");
    });
    return () => {
      alive = false;
    };
  }, [slug]);

  return (
    <div className="mx-auto flex h-[calc(100vh-4rem)] max-w-7xl flex-col px-5 py-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <Link
          href={withBase("/gallery")}
          className="rounded-full px-3 py-1.5 text-sm font-medium text-muted transition-colors hover:bg-accent/8 hover:text-accent-ink"
        >
          ← Gallery
        </Link>
        {entry && (
          <span className="stat truncate text-xs text-faint">
            {entry.author} · {entry.date}
          </span>
        )}
      </div>

      {state === "loading" ? (
        <div className="tile flex-1 animate-pulse opacity-60" />
      ) : entry ? (
        <DashboardFrame
          src={dashboardSrc(entry)}
          title={entry.title}
          downloadHref={downloadSrc(entry)}
        />
      ) : (
        <NotFound slug={slug} />
      )}
    </div>
  );
}

function NotFound({ slug }: { slug: string | null }) {
  return (
    <div className="tile flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="eyebrow">Not found</div>
      <h1 className="display text-2xl">
        {slug ? `No dashboard named "${slug}"` : "No dashboard specified"}
      </h1>
      <p className="max-w-md text-muted">
        It may have been unpublished or renamed. Browse the gallery to find what
        you&rsquo;re looking for.
      </p>
      <Link href={withBase("/gallery")} className="btn btn-ghost mt-2">
        Back to gallery
      </Link>
    </div>
  );
}
