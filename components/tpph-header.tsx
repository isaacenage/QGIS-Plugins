import Link from "next/link";
import { TpphWordmark } from "./logo";
import { TPPH } from "@/lib/site";

// The Title Plotter PH section header — same editorial system as the hub and
// the dashboard section: white, flat, hairline base; coral semibold nav;
// square ink Install button.
const NAV = [
  { href: "/", label: "All plugins" },
  { href: "/titleplotterph#features", label: "Features" },
  { href: "/titleplotterph#how", label: "How it works" },
];

export function TpphHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-line bg-paper">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <Link href="/titleplotterph" aria-label="Title Plotter PH home">
          <TpphWordmark size={30} />
        </Link>
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
        <div className="flex items-center gap-5">
          <a
            href={TPPH.repo}
            target="_blank"
            rel="noreferrer"
            className="hidden text-sm font-semibold text-accent-ink underline-offset-4 transition-colors hover:text-accent hover:underline sm:inline-flex"
          >
            GitHub
          </a>
          <a
            href="/titleplotterph#install"
            className="btn btn-primary px-4 py-2 text-sm"
          >
            Install
          </a>
        </div>
      </div>
    </header>
  );
}
