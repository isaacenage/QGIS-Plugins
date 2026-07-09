import Link from "next/link";
import { Logo } from "./logo";
import { HUB } from "@/lib/site";

// The root hub's header. Deliberately NOT the reference's arrangement (nav
// left, stacked wordmark right): here the gradient mark + a one-line bold
// wordmark anchor the left, and the coral nav + a square GitHub button sit
// flush right. White, flat, hairline base.
// Gallery and Guide are QGIS Dashboard pages, so they live in that section's
// own nav (site-header.tsx) — the hub only points at whole plugins.
const NAV = [
  { href: "/#plugins", label: "Plugins" },
  { href: "/qdashboards", label: "QGIS Dashboard" },
  { href: "/titleplotterph", label: "Title Plotter PH" },
  { href: "/#about", label: "About" },
];

export function HubHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-line bg-paper">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <Link
          href="/"
          aria-label="QGIS Plugins home"
          className="flex items-center gap-3"
        >
          <Logo size={30} />
          <span className="text-[1.05rem] font-bold uppercase tracking-tight text-ink">
            QGIS Plugins
          </span>
          <span className="mt-0.5 hidden text-[0.62rem] font-semibold uppercase tracking-[0.14em] text-faint sm:block">
            free · open-source
          </span>
        </Link>
        <div className="flex items-center gap-6">
          <nav className="hidden items-center gap-6 md:flex">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-sm font-semibold text-accent-ink underline-offset-4 transition-colors hover:text-accent hover:underline"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <a
            href={HUB.repo}
            target="_blank"
            rel="noreferrer"
            className="btn btn-primary px-4 py-2 text-sm"
          >
            GitHub
          </a>
        </div>
      </div>
    </header>
  );
}
