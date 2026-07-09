import type { Metadata } from "next";
import Link from "next/link";
import { SITE, withBase } from "@/lib/site";

export const metadata: Metadata = {
  title: "Guide",
  description:
    "Install QGIS Dashboard, build your first cross-filtering dashboard, theme it, and publish it to the public gallery.",
};

const STEPS = [
  { id: "install", n: "01", t: "Install" },
  { id: "build", n: "02", t: "Build a dashboard" },
  { id: "elements", n: "03", t: "Add elements" },
  { id: "wire", n: "04", t: "Wire cross-filters" },
  { id: "theme", n: "05", t: "Theme & lay out" },
  { id: "export", n: "06", t: "Export" },
  { id: "publish", n: "07", t: "Publish to public" },
];

export default function GuidePage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-16">
      <header className="max-w-2xl">
        <p className="eyebrow">Guide</p>
        <h1 className="display mt-4 text-4xl text-ink sm:text-5xl">
          From install to a published dashboard
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          Seven steps, in order. By the end you&rsquo;ll have an interactive,
          cross-filtering dashboard living in your QGIS project — and optionally
          shared to the public gallery.
        </p>
      </header>

      <div className="mt-12 grid gap-12 lg:grid-cols-[200px_1fr]">
        {/* sticky step nav */}
        <nav className="hidden lg:block">
          <ol className="sticky top-24 space-y-1">
            {STEPS.map((s) => (
              <li key={s.id}>
                <a
                  href={`#${s.id}`}
                  className="flex items-baseline gap-3 px-1 py-2 text-sm font-medium text-muted underline-offset-4 transition-colors hover:text-accent-ink hover:underline"
                >
                  <span className="stat text-xs font-semibold text-faint">
                    {s.n}
                  </span>
                  {s.t}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <div className="max-w-2xl space-y-16">
          <Step id="install" n="01" title="Install the plugin">
            <p>
              QGIS Dashboard installs with no build step. Copy the{" "}
              <Code>plugins/qgis_dashboards</Code> folder from the repository
              into your QGIS profile&rsquo;s plugins directory, then enable it
              under{" "}
              <em>Plugins → Manage and Install Plugins</em>.
            </p>
            <Pre>
              {`# Windows
%APPDATA%\\QGIS\\QGIS3\\profiles\\default\\python\\plugins\\

# Linux
~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/

# macOS
~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`}
            </Pre>
            <Callout>
              Works on QGIS 3.22 through 4.x (Qt5 and Qt6). A toolbar button and a{" "}
              <em>Plugins</em> menu entry open the dashboard window.
            </Callout>
            <p>
              Prefer a zip? Grab the packaged release from{" "}
              <A href={SITE.repo}>the repository</A> and install it via{" "}
              <em>Install from ZIP</em>.
            </p>
          </Step>

          <Step id="build" n="02" title="Open the window and start a dashboard">
            <p>
              Click the toolbar button to open the dashboard window. From the
              Start screen choose <strong>New Dashboard</strong> (or continue an
              existing one). You get a framed canvas — the page your dashboard is
              laid out on, and the exact region that exports.
            </p>
            <p>
              The left icon rail is your toolkit: add elements, add pages, zoom,
              clear filters, save, and open Settings. A dashboard can hold several
              pages, each with its own tabs and its own cross-filter wiring.
            </p>
          </Step>

          <Step id="elements" n="03" title="Add and configure tiles">
            <p>
              Press <strong>Add element</strong> and pick a tile type from the
              icon picker — indicator, chart, pivot, list, live map, selector,
              text, image or header. The tile drops onto the canvas with sensible
              defaults.
            </p>
            <p>
              Right-click any tile for <Code>Configure…</Code> (bind it to a layer
              and a field), <Code>Tile appearance…</Code> (per-tile color/size
              overrides) and <Code>Connections…</Code> (its cross-filter wiring).
              Drag the top strip to move a tile; use the handles to resize. Tiles
              snap to the grid.
            </p>
          </Step>

          <Step id="wire" n="04" title="Wire the cross-filters">
            <p>
              Open <Code>Connections…</Code> on a source tile (a chart, pivot,
              selector or the map) and tick which tiles it should filter.
              Selecting a value then re-queries every connected tile in real time.
            </p>
            <Callout>
              Wiring is explicit and page-local: you decide the links, and they
              only connect tiles on the same page. Filtering never alters your
              project layers.
            </Callout>
          </Step>

          <Step id="theme" n="05" title="Theme, size and lock">
            <p>
              Open <strong>Settings</strong> to theme the canvas — pick one of
              twelve presets or fine-tune colors, the chart palette and fonts —
              and to set the page size, corner radius, spacing and text sizes.
            </p>
            <p>
              When you&rsquo;re done arranging, flip the <strong>lock</strong> on
              the tab strip: <em>Build mode</em> moves and resizes tiles;{" "}
              <em>Use mode</em> locks the layout and turns interaction on, so
              clicks cross-filter and the map pans and identifies.
            </p>
          </Step>

          <Step id="export" n="06" title="Export to a self-contained file">
            <p>
              From the export menu, choose <strong>Export to HTML</strong> for a
              single self-contained <Code>index.html</Code> that opens offline by
              double-click, with cross-filtering reproduced in the browser. PNG
              and PDF export the exact page region too.
            </p>
          </Step>

          <Step id="publish" n="07" title="Publish to the public gallery">
            <p>
              <strong>Publish to public</strong> sends your dashboard straight to
              this website&rsquo;s gallery. The plugin exports the interactive
              HTML, renders a thumbnail, and commits both to the gallery
              repository in one step — your dashboard appears as a card at{" "}
              <Code>{SITE.domain}/qdashboards/gallery</Code> within a minute.
            </p>
            <ol className="ml-1 space-y-2">
              <ListNum n="1">
                Create a fine-grained GitHub token scoped to only the gallery repo
                with <em>Contents: read &amp; write</em>.
              </ListNum>
              <ListNum n="2">
                Paste it into the Publish dialog (stored locally on your machine).
              </ListNum>
              <ListNum n="3">
                Click <strong>Publish</strong> — you&rsquo;ll get the public link
                when it&rsquo;s live.
              </ListNum>
            </ol>
            <Callout>
              Re-publishing the same dashboard updates its existing gallery entry
              rather than creating a duplicate.
            </Callout>
            <div className="pt-2">
              <Link href={withBase("/gallery")} className="btn btn-ghost">
                See the gallery
              </Link>
            </div>
          </Step>
        </div>
      </div>
    </div>
  );
}

function Step({
  id,
  n,
  title,
  children,
}: {
  id: string;
  n: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24">
      <div className="flex items-baseline gap-3">
        <span className="stat text-sm font-bold text-accent">{n}</span>
        <h2 className="display text-2xl text-ink">{title}</h2>
      </div>
      <div className="mt-4 space-y-4 leading-relaxed text-muted [&_strong]:text-ink [&_em]:text-ink">
        {children}
      </div>
    </section>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="bg-accent/8 px-1.5 py-0.5 font-mono text-[0.85em] text-accent-ink">
      {children}
    </code>
  );
}

function Pre({ children }: { children: React.ReactNode }) {
  return (
    <pre className="overflow-x-auto border border-line bg-surface p-4 font-mono text-xs leading-relaxed text-ink">
      {children}
    </pre>
  );
}

// The reference's outlined content box: a coral hairline frame on white.
function Callout({ children }: { children: React.ReactNode }) {
  return (
    <div className="border border-accent p-4 text-sm text-muted">
      {children}
    </div>
  );
}

function A({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="font-semibold text-accent-ink underline underline-offset-4 hover:decoration-accent"
    >
      {children}
    </a>
  );
}

function ListNum({ n, children }: { n: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="stat shrink-0 font-bold text-accent-ink">{n}.</span>
      <span>{children}</span>
    </li>
  );
}
