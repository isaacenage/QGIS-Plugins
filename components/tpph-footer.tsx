import Link from "next/link";
import { Logo } from "./logo";
import { TPPH } from "@/lib/site";

// The Title Plotter PH section footer — the same sitemap-wall language as the
// hub and dashboard footers: coral spaced-caps headers, small underlined ink
// links, flat.
export function TpphFooter() {
  return (
    <footer className="border-t border-line bg-paper">
      <div className="mx-auto grid max-w-6xl gap-x-8 gap-y-10 px-5 py-14 sm:grid-cols-2 md:grid-cols-4">
        <div className="sm:col-span-2 md:col-span-1">
          <div className="flex items-center gap-2.5">
            <Logo size={28} />
            <span className="display text-base">Title Plotter PH</span>
          </div>
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-muted">
            {TPPH.tagline}
          </p>
        </div>

        <FooterCol
          title="Product"
          links={[
            { href: "/titleplotterph#features", label: "Features" },
            { href: "/titleplotterph#how", label: "How it works" },
            { href: "/titleplotterph#install", label: "Install" },
          ]}
        />
        <FooterCol
          title="Plugins"
          links={[
            { href: "/", label: "All plugins" },
            { href: "/qdashboards", label: "QGIS Dashboard" },
          ]}
        />
        <FooterCol
          title="Project"
          external
          links={[
            { href: TPPH.repo, label: "Source on GitHub" },
            { href: TPPH.issues, label: "Report an issue" },
            { href: `mailto:${TPPH.authorEmail}`, label: "Contact" },
          ]}
        />
      </div>
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-5 pb-8 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-ink">
          Built by {TPPH.author} — free &amp; open-source
        </span>
        <span className="text-xs font-medium text-faint">
          {TPPH.domain}
          {TPPH.basePath}
        </span>
      </div>
    </footer>
  );
}

function FooterCol({
  title,
  links,
  external,
}: {
  title: string;
  links: { href: string; label: string }[];
  external?: boolean;
}) {
  return (
    <div>
      <h3 className="text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-accent-ink">
        {title}
      </h3>
      <ul className="mt-5 space-y-3">
        {links.map((l) => (
          <li key={l.label}>
            {external ? (
              <a
                href={l.href}
                target="_blank"
                rel="noreferrer"
                className="sitemap-link"
              >
                {l.label}
              </a>
            ) : (
              <Link href={l.href} className="sitemap-link">
                {l.label}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
