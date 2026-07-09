"use client";

import { useEffect, useRef, useState } from "react";

// Wraps a published dashboard's self-contained index.html in an iframe.
//
// The HTML lives in Supabase Storage, which serves it as text/plain on the
// shared domain (deliberate anti-phishing), so we FETCH the bytes and load
// them through a Blob URL instead of iframing the storage URL directly.
//
// SECURITY: dashboards are untrusted third-party HTML. The iframe withholds
// allow-same-origin, so the content runs in an opaque origin with no access
// to this site's cookies/storage — the Blob URL's nominal origin never takes
// effect. Never expose the Blob URL as a top-level navigation (that WOULD
// run the dashboard's scripts on this site's origin); downloads use the
// storage URL's ?download parameter instead.

export function DashboardFrame({
  src,
  title,
  downloadHref,
}: {
  src: string;
  title: string;
  downloadHref?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState(false);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let alive = true;
    let url: string | null = null;
    setState("loading");
    setBlobUrl(null);
    fetch(src)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.text();
      })
      .then((html) => {
        if (!alive) return;
        url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
        setBlobUrl(url);
        setState("ready");
      })
      .catch(() => {
        if (alive) setState("error");
      });
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [src]);

  const fullscreen = () => ref.current?.requestFullscreen?.();

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — no-op */
    }
  };

  return (
    <div ref={ref} className="tile flex h-full flex-col overflow-hidden bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-accent" />
          <span className="truncate text-sm font-semibold">{title}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={copyLink}
            className="rounded-full px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-accent/8 hover:text-accent-ink"
          >
            {copied ? "Link copied" : "Copy link"}
          </button>
          {downloadHref && (
            <a
              href={downloadHref}
              className="rounded-full px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-accent/8 hover:text-accent-ink"
            >
              Download
            </a>
          )}
          <button
            type="button"
            onClick={fullscreen}
            className="rounded-full px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-accent/8 hover:text-accent-ink"
          >
            Fullscreen
          </button>
        </div>
      </div>
      {state === "ready" && blobUrl ? (
        <iframe
          src={blobUrl}
          title={title}
          className="h-full w-full flex-1 bg-white"
          sandbox="allow-scripts allow-popups"
        />
      ) : state === "error" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="font-medium">This dashboard couldn&apos;t be loaded.</p>
          <p className="max-w-md text-sm text-muted">
            Check your connection and reload the page. If it keeps failing,
            the dashboard may have been unpublished.
          </p>
        </div>
      ) : (
        <div className="flex-1 animate-pulse bg-paper" />
      )}
    </div>
  );
}
