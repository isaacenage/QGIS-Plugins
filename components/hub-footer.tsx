import Link from "next/link";
import { HUB } from "@/lib/site";
import { PLUGINS } from "@/lib/plugins";

// The hub footer as the reference's sitemap wall: five pure link columns —
// coral spaced-caps headers over stacks of small underlined ink links — then a
// bottom row with the maker line and the coral-outlined "guarantee" badge.

type FooterLink = { href: string; label: string };

// Gallery/Guide stay nested under the QGIS Dashboard column — they are that
// plugin's pages, not hub destinations. Plugin columns come straight after the
// dynamic plugin list, then the firm and the repo.
const COLUMNS: { title: string; links: FooterLink[] }[] = [
  {
    title: "Plugins",
    links: PLUGINS.map((p) => ({ href: p.href, label: p.name })),
  },
  {
    title: "QGIS Dashboard",
    links: [
      { href: "/qdashboards", label: "Overview" },
      { href: "/qdashboards/gallery", label: "Gallery" },
      { href: "/qdashboards/guide", label: "Guide" },
    ],
  },
  {
    title: "Title Plotter PH",
    links: [
      { href: "/titleplotterph", label: "Overview" },
      { href: "https://github.com/isaacenage/TitlePlotterPH", label: "Plugin source" },
    ],
  },
  {
    title: "byZenterra.org",
    links: [
      { href: "/#about", label: "About the firm" },
      { href: HUB.orgUrl, label: HUB.org },
      { href: `mailto:${HUB.authorEmail}`, label: "Email Isaac" },
      { href: HUB.github, label: "GitHub profile" },
    ],
  },
  {
    title: "Project",
    links: [
      { href: HUB.repo, label: "Source on GitHub" },
      { href: `${HUB.repo}/issues`, label: "Report an issue" },
      { href: HUB.github, label: "More by Isaac" },
    ],
  },
];

export function HubFooter() {
  return (
    <footer className="border-t border-line bg-paper">
      <div className="mx-auto grid max-w-6xl gap-x-8 gap-y-10 px-5 py-16 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
        {COLUMNS.map((col) => (
          <FooterCol key={col.title} {...col} />
        ))}
      </div>
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 pb-10 sm:flex-row sm:items-center">
        <span className="text-[0.7rem] font-semibold uppercase tracking-[0.14em] text-ink">
          © {HUB.org} · built by {HUB.author} — free &amp; open-source
        </span>
        <span className="self-start border border-accent px-3 py-1.5 sm:self-auto">
          <span className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-accent-ink">
            DTI-registered · Philippines
          </span>
        </span>
        <span className="text-xs font-medium text-faint sm:ml-auto">
          {HUB.domain}
        </span>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: FooterLink[] }) {
  return (
    <div>
      <h3 className="text-[0.7rem] font-semibold uppercase tracking-[0.18em] text-accent-ink">
        {title}
      </h3>
      <ul className="mt-5 space-y-3">
        {links.map((l) => {
          const external = /^(https?:|mailto:)/.test(l.href);
          return (
            <li key={l.label}>
              {external ? (
                <a
                  href={l.href}
                  {...(l.href.startsWith("http")
                    ? { target: "_blank", rel: "noreferrer" }
                    : {})}
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
          );
        })}
      </ul>
    </div>
  );
}
