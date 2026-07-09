import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { HubHeader } from "@/components/hub-header";
import { HubFooter } from "@/components/hub-footer";
import { Section } from "@/components/section";
import { Logo } from "@/components/logo";
import {
  LongArrow,
  HeroBoard,
  CrossfilterBoard,
  ParcelPlot,
  GalleryGlyph,
  PixelHeart,
} from "@/components/hub-art";
import { PLUGINS, pluginCount, type Plugin } from "@/lib/plugins";
import { HUB } from "@/lib/site";

// The root QGIS Plugins hub — the editorial magazine layout, traced from the
// Typography-Nerd reference: coral hero block with art overflowing its corner,
// straight into three borderless entry cards, then coral-outlined feature
// splits per plugin, and the dense sitemap footer. All white, all rectangles.
// This page sells the whole byZenterra.org collection, never one plugin:
// plugin-specific pages (Gallery, Guide) live inside their own sections, and
// every plugin count on the page derives from lib/plugins.ts.

const COUNT = pluginCount();

const ENTRY_CARDS: {
  tag: string;
  title: string;
  body: string;
  cta: string;
  href: string;
  art: ReactNode;
}[] = [
  {
    tag: "The collection",
    title: `${COUNT} plugins today — and counting`,
    body: "Dashboards, land-title plotting, and whatever gap real GIS work exposes next. Each plugin gets its own section with docs and downloads.",
    cta: "Browse the plugins",
    href: "#plugins",
    art: <GalleryGlyph />,
  },
  {
    tag: "The firm",
    title: "Built by byZenterra.org",
    body: `${HUB.org} is ${HUB.orgLine}, owned by ${HUB.author}. The plugins are its free, open-source side of the practice.`,
    cta: "Meet the firm",
    href: "#about",
    art: <Logo size={88} />,
  },
  {
    tag: "Source",
    title: "Open code, open issues",
    body: "Everything lives in public repos. Read the code, report a bug, or fork a plugin and make it yours.",
    cta: "View on GitHub",
    href: HUB.repo,
    art: <PixelHeart />,
  },
];

const SPLIT_HEADLINES: Record<string, string> = {
  qdashboards: "Cross-filtering dashboards, right inside your project.",
  titleplotterph: "From technical description to plotted parcel.",
};

const SPLIT_ART: Record<string, ReactNode> = {
  qdashboards: <CrossfilterBoard />,
  titleplotterph: <ParcelPlot />,
};

export default function HubPage() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <HubHeader />
      <SideRail />
      <main id="top" className="scroll-mt-16">
        {/* ---------- hero: flat coral block, collage overflowing its corner ---------- */}
        <section className="mx-auto max-w-6xl px-5 pt-10 lg:pt-14">
          <div className="bg-accent lg:mb-32">
            <div className="grid gap-10 p-8 sm:p-12 lg:grid-cols-[1.05fr_0.95fr] lg:gap-6 lg:p-14">
              <div>
                <h1 className="display text-4xl text-white sm:text-5xl lg:text-[3.6rem]">
                  Tools that make
                  <br />
                  QGIS do more.
                </h1>
                <p className="mt-6 max-w-lg text-lg font-medium leading-relaxed text-ink">
                  A growing collection of free, open-source QGIS plugins from{" "}
                  {HUB.org}, {HUB.orgLine} — practical tools that extend the
                  desktop GIS you already use. No subscriptions, no separate
                  apps.
                </p>
                <p className="mt-7 flex items-baseline gap-3">
                  <span className="display stat text-4xl text-white">
                    {COUNT}
                  </span>
                  <span className="text-sm font-semibold uppercase tracking-[0.14em] text-ink">
                    plugins &amp; growing
                  </span>
                </p>
                <Link
                  href="#plugins"
                  className="arrow-link mt-7 hover:text-white focus-visible:outline-white"
                >
                  Explore the plugins
                  <LongArrow />
                </Link>
              </div>
              <div className="flex lg:-mb-40 lg:items-end lg:justify-end">
                <HeroBoard />
              </div>
            </div>
          </div>
        </section>

        {/* ---------- three ways in: straight after the hero, no section header ---------- */}
        <section
          aria-label="Three ways in"
          className="mx-auto max-w-6xl px-5 pt-16 lg:pt-8"
        >
          <div className="grid gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
            {ENTRY_CARDS.map((card) => (
              <EntryCard key={card.tag} {...card} />
            ))}
          </div>
        </section>

        {/* ---------- the collection: one coral-outlined split per plugin ---------- */}
        <Section
          id="plugins"
          className="scroll-mt-16"
          eyebrow="The collection"
          title={
            <>
              <span className="text-accent">{COUNT} plugins</span> in the
              toolbox today.
            </>
          }
          lead="Every plugin starts as a gap in real consulting work and ships free for everyone. New ones join this list as they're released."
        >
          <div className="mt-14 space-y-16 lg:mt-20 lg:space-y-24">
            {PLUGINS.map((plugin, i) => (
              <FeatureSplit
                key={plugin.slug}
                plugin={plugin}
                reverse={i % 2 === 1}
              />
            ))}
          </div>
        </Section>

        {/* ---------- about the firm ---------- */}
        <Section
          id="about"
          className="scroll-mt-16 !pt-0"
          eyebrow="Who's behind this"
          title={
            <>
              <span className="text-accent">{HUB.org}</span> — a GIS
              consultancy from the Philippines
            </>
          }
          lead={
            <>
              {HUB.org} is a DTI-registered GIS consultancy firm based in the
              Philippines, owned and run by {HUB.author}. The consultancy pays
              the bills; these plugins are its open side — tools built to fill
              gaps Isaac kept hitting in real GIS work, released free for
              everyone.
            </>
          }
        >
          <div className="mt-10 grid items-start gap-10 lg:grid-cols-[0.42fr_0.58fr]">
            <figure className="max-w-sm">
              <Image
                src={HUB.ownerPhoto}
                alt={`${HUB.author}, owner of ${HUB.org}`}
                width={640}
                height={641}
                className="w-full border border-line"
              />
              <figcaption className="mt-3 border border-accent px-3 py-1.5">
                <span className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-accent-ink">
                  {HUB.author} · Owner, {HUB.org}
                </span>
              </figcaption>
            </figure>
            <div>
              <p className="leading-relaxed text-muted">
                &ldquo;I build free QGIS tools to fill gaps I kept hitting in
                real GIS work. Everything here is open-source — use it, fork
                it, suggest features.&rdquo;
              </p>
              <dl className="mt-8 grid gap-4 sm:grid-cols-3">
                {[
                  { k: "Registration", v: "DTI-registered" },
                  { k: "Based in", v: "Philippines" },
                  { k: "License", v: "Free & open-source" },
                ].map((f) => (
                  <div key={f.k} className="border-t border-line-strong pt-3">
                    <dt className="text-[0.65rem] font-semibold uppercase tracking-[0.14em] text-faint">
                      {f.k}
                    </dt>
                    <dd className="mt-1 text-sm font-semibold text-ink">
                      {f.v}
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-center">
                <a
                  href={HUB.orgUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-primary"
                >
                  Visit {HUB.org}
                </a>
                <a
                  href={HUB.github}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-ghost"
                >
                  GitHub profile
                </a>
                <a
                  href={`mailto:${HUB.authorEmail}`}
                  className="text-sm font-medium text-muted underline decoration-line-strong underline-offset-4 hover:text-accent-ink hover:decoration-accent"
                >
                  {HUB.authorEmail}
                </a>
              </div>
            </div>
          </div>
        </Section>
      </main>
      <HubFooter />
    </div>
  );
}

/* ---------- page-local pieces ---------- */

// The fixed vertical rail on wide screens — the reference's slim left column:
// rotated brand line up top, coral back-to-top arrow at the foot. Only shown
// at xl+, where the centered container leaves room for it.
function SideRail() {
  return (
    <aside className="fixed bottom-0 left-0 top-16 z-40 hidden w-12 flex-col items-center justify-between border-r border-line bg-paper py-6 xl:flex">
      <span
        aria-hidden
        className="rotate-180 text-[0.62rem] font-semibold uppercase tracking-[0.3em] text-faint [writing-mode:vertical-rl]"
      >
        QGIS Plugins by {HUB.org} — free &amp; open-source
      </span>
      <a
        href="#top"
        aria-label="Back to top"
        className="text-accent transition-colors hover:text-accent-ink"
      >
        <svg width="12" height="30" viewBox="0 0 12 30" fill="none" aria-hidden>
          <path
            d="M6 30V3M1.5 7.5 6 3l4.5 4.5"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        </svg>
      </a>
    </aside>
  );
}

// An entry card, borderless like the reference: graphic plate up top, then the
// coral underlined tag, bold title, body and a long-arrow CTA — the whole card
// is one link.
function EntryCard({
  tag,
  title,
  body,
  cta,
  href,
  art,
}: (typeof ENTRY_CARDS)[number]) {
  const external = /^https?:\/\//.test(href);
  const className = "group flex flex-col";
  const content = (
    <>
      <div className="flex h-48 items-center justify-center bg-paper">
        {art}
      </div>
      <div className="flex flex-1 flex-col pt-6">
        <span className="tag self-start">{tag}</span>
        <h3 className="display mt-4 text-[1.35rem] text-ink">{title}</h3>
        <p className="mt-2 flex-1 text-sm leading-relaxed text-muted">{body}</p>
        <span className="arrow-link mt-6 text-sm">
          {cta}
          {external ? <span aria-hidden>↗</span> : <LongArrow />}
        </span>
      </div>
    </>
  );

  return external ? (
    <a href={href} target="_blank" rel="noreferrer" className={className}>
      {content}
    </a>
  ) : (
    <Link href={href} className={className}>
      {content}
    </Link>
  );
}

// A feature split: the coral-outlined pitch box beside the plugin's art,
// alternating sides down the page — the reference's outlined content boxes.
function FeatureSplit({
  plugin,
  reverse,
}: {
  plugin: Plugin;
  reverse?: boolean;
}) {
  const external = /^https?:\/\//.test(plugin.href);
  return (
    <div className="grid items-center gap-8 lg:grid-cols-2 lg:gap-12">
      <div className={reverse ? "lg:order-2" : undefined}>
        <div className="border border-accent bg-paper p-8 sm:p-10">
          <span className="tag">{plugin.name}</span>
          <h3 className="display mt-5 text-2xl text-ink sm:text-3xl">
            {SPLIT_HEADLINES[plugin.slug] ?? plugin.blurb}
          </h3>
          <p className="mt-4 leading-relaxed text-muted">{plugin.pitch}</p>
          <p className="mt-5 text-sm font-medium text-faint">
            {plugin.features.join(" · ")}
          </p>
          {external ? (
            <a
              href={plugin.href}
              target="_blank"
              rel="noreferrer"
              className="arrow-link mt-8"
            >
              Visit {plugin.name}
              <span aria-hidden>↗</span>
            </a>
          ) : (
            <Link href={plugin.href} className="arrow-link mt-8">
              Open {plugin.name}
              <LongArrow />
            </Link>
          )}
        </div>
      </div>
      <div className={reverse ? "lg:order-1" : undefined}>
        {SPLIT_ART[plugin.slug] ?? <CrossfilterBoard />}
      </div>
    </div>
  );
}
