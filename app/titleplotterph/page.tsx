import Link from "next/link";
import { Section } from "@/components/section";
import { ParcelPlot } from "@/components/hub-art";
import { TPPH } from "@/lib/site";

// The Title Plotter PH landing page — same editorial system as the rest of
// the site. Copy is sourced from the plugin's own metadata.txt and README
// (plugins/titleplotter), so figures like the tie-point count stay honest.

const FEATURES = [
  {
    k: "85,000+ tie points",
    v: "An online database of official Philippine tie points, searchable from inside the plugin. Every point you fetch is cached for offline field work.",
  },
  {
    k: "Bearing & distance entry",
    v: "Type the metes-and-bounds straight off the title — one bearing and distance per line, the way the technical description reads.",
  },
  {
    k: "Live preview",
    v: "Watch the parcel take shape as you type and check the closing error before you commit anything to a layer.",
  },
  {
    k: "AI OCR",
    v: "Optionally let OCR read the technical description straight off a scanned title image instead of retyping it.",
  },
  {
    k: "PRS92 & WGS84",
    v: "Plot in the Philippine reference system or WGS84 — the plugin handles the coordinate systems for you.",
  },
  {
    k: "Correction reporting",
    v: "Found a tie point with wrong coordinates? Report the correct easting/northing to the developer from inside the plugin.",
  },
] as const;

const STEPS = [
  {
    n: "01",
    t: "Pick your tie point",
    d: "Search the built-in database for the BLLM or monument named on the title. Previously fetched points work offline.",
  },
  {
    n: "02",
    t: "Enter the technical description",
    d: "Copy the bearings and distances from the TCT or OCT — or point the OCR at a scan and let it read them for you.",
  },
  {
    n: "03",
    t: "Preview and check closure",
    d: "The parcel draws live as you go. A closing error that's off tells you a line was misread before anything is plotted.",
  },
  {
    n: "04",
    t: "Plot to a layer",
    d: "One click writes the parcel as real geometry in your QGIS project, ready to style, measure, or overlay.",
  },
] as const;

export default function TitlePlotterPage() {
  return (
    <>
      {/* ---------- hero ---------- */}
      <section className="border-b border-line">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-20 lg:grid-cols-[1.05fr_1.1fr] lg:py-28">
          <div>
            <p className="eyebrow">Free QGIS plugin · Philippine land titles</p>
            <h1 className="display mt-5 text-4xl text-ink sm:text-5xl lg:text-[3.4rem]">
              From technical description
              <br />
              to <span className="text-accent">plotted parcel</span>.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted">
              Turn the bearing-and-distance technical descriptions on
              Philippine TCTs and OCTs into accurate parcel geometry, right
              inside QGIS. Tie-point based, live-previewed — and it requires no
              GIS background at all.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <a href="#install" className="btn btn-primary">
                Install the plugin
              </a>
              <a
                href={TPPH.repo}
                target="_blank"
                rel="noreferrer"
                className="btn btn-ghost"
              >
                View on GitHub
              </a>
            </div>
            <p className="stat mt-6 text-xs text-faint">
              QGIS 3.22+ · GPL-3.0 · v2.1
            </p>
          </div>
          <div className="lg:pl-4">
            <ParcelPlot />
          </div>
        </div>
      </section>

      {/* ---------- what it is ---------- */}
      <Section
        eyebrow="What it is"
        title="Land titles, without the surveyor's toolchain"
        lead={
          <>
            Every Philippine land title carries its lot's shape as text — a
            tie point and a list of bearings and distances. Reading that into
            a map used to take survey software or a GIS specialist. Title
            Plotter PH does it inside QGIS: pick the tie point, type the
            lines, and the parcel appears.
          </>
        }
      >
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          {[
            {
              k: "No GIS background",
              v: "Built for lawyers, brokers, assessors and owners as much as for GIS professionals — the workflow mirrors the title itself.",
            },
            {
              k: "Tie-point based",
              v: "Parcels anchor to official reference monuments, the same way the original survey did — not to a guessed location.",
            },
            {
              k: "Made for PH titles",
              v: "TCT and OCT technical descriptions, BLLM tie points, PRS92 — the plugin speaks the local format natively.",
            },
          ].map((c) => (
            <div key={c.k} className="tile p-5">
              <div className="display text-lg text-accent">{c.k}</div>
              <p className="mt-2 text-sm leading-relaxed text-muted">{c.v}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ---------- features ---------- */}
      <div className="border-y border-line bg-surface/40">
        <Section
          id="features"
          eyebrow="The toolbox"
          title="Everything between the paper title and the map"
          lead="Six pieces that carry a technical description from text to geometry — with checks along the way so a misread line never becomes a wrong parcel."
        >
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.k} className="tile p-5">
                <div className="display text-lg text-accent">{f.k}</div>
                <p className="mt-2 text-sm leading-relaxed text-muted">{f.v}</p>
              </div>
            ))}
          </div>
        </Section>
      </div>

      {/* ---------- how it works ---------- */}
      <Section
        id="how"
        eyebrow="How it works"
        title={
          <>
            Four steps from <span className="text-accent">paper to parcel</span>
          </>
        }
        lead="The workflow follows the title itself: anchor at the tie point, walk the boundary line by line, verify the loop closes, then plot."
      >
        <div className="mt-10 grid items-start gap-8 lg:grid-cols-2">
          <ol className="space-y-5">
            {STEPS.map((s) => (
              <li key={s.n} className="flex gap-4">
                <span className="stat text-sm text-faint">{s.n}</span>
                <div>
                  <div className="font-semibold">{s.t}</div>
                  <p className="text-sm text-muted">{s.d}</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="tile p-6">
            <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-accent-ink">
              A technical description, as the title prints it
            </p>
            <div className="stat mt-4 space-y-2 text-sm text-muted">
              <p>Beginning at a point marked &ldquo;1&rdquo;,</p>
              <p>being S 48°12′W, 1,231.50 m from BLLM No. 1;</p>
              <p className="text-ink">thence N 82°30′E, 45.10 m to point 2;</p>
              <p className="text-ink">thence S 12°45′E, 38.20 m to point 3;</p>
              <p className="text-ink">thence S 47°15′W, 32.86 m to point 4;</p>
              <p>… back to the point of beginning.</p>
            </div>
            <p className="mt-5 text-sm leading-relaxed text-muted">
              Those lines are all the plugin needs — each &ldquo;thence&rdquo;
              becomes one row of bearing and distance.
            </p>
          </div>
        </div>
      </Section>

      {/* ---------- install ---------- */}
      <div className="border-y border-line bg-surface/40">
        <Section
          id="install"
          eyebrow="Get started"
          title="Install in a minute"
          lead="Title Plotter PH installs like any QGIS plugin. OCR is optional — the core plotting workflow needs nothing beyond QGIS itself."
        >
          <div className="mt-10 grid items-start gap-8 lg:grid-cols-2">
            <ol className="space-y-5">
              {[
                {
                  n: "01",
                  t: "Get the plugin",
                  d: (
                    <>
                      Install from the QGIS Plugin Repository (Plugins →
                      Manage and Install Plugins → search &ldquo;Title Plotter
                      PH&rdquo;), or download it from{" "}
                      <a
                        href={TPPH.repo}
                        target="_blank"
                        rel="noreferrer"
                        className="font-medium text-accent-ink underline underline-offset-4 hover:text-accent"
                      >
                        GitHub
                      </a>
                      .
                    </>
                  ),
                },
                {
                  n: "02",
                  t: "Enable it",
                  d: "Tick Title Plotter PH in Plugins → Manage and Install Plugins, then find its icon on the QGIS toolbar.",
                },
                {
                  n: "03",
                  t: "Plot your first title",
                  d: "Open the plugin, search your tie point, and enter the technical description — the preview does the rest.",
                },
              ].map((s) => (
                <li key={s.n} className="flex gap-4">
                  <span className="stat text-sm text-faint">{s.n}</span>
                  <div>
                    <div className="font-semibold">{s.t}</div>
                    <p className="text-sm text-muted">{s.d}</p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="tile p-6">
              <p className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-accent-ink">
                Requirements
              </p>
              <ul className="mt-4 space-y-3 text-sm leading-relaxed text-muted">
                <li>
                  <span className="font-semibold text-ink">QGIS 3.22+</span> —
                  works up through QGIS 4.
                </li>
                <li>
                  <span className="font-semibold text-ink">Internet</span> for
                  tie-point search and correction reports; fetched tie points
                  are cached for offline use.
                </li>
                <li>
                  <span className="font-semibold text-ink">
                    Optional, for OCR:
                  </span>{" "}
                  Tesseract plus{" "}
                  <span className="stat text-ink">
                    pytesseract · Pillow · opencv-python
                  </span>
                  .
                </li>
              </ul>
            </div>
          </div>
        </Section>
      </div>

      {/* ---------- who made it + CTA ---------- */}
      <Section
        eyebrow="Who made it"
        title="Built where the titles are"
        lead={
          <>
            {TPPH.author} built Title Plotter PH so that seeing a Philippine
            land title on a map wouldn&rsquo;t require survey software or a
            GIS specialist. It&rsquo;s free and open-source under GPL-3.0 —
            one of the QGIS plugins from byZenterra.org.
          </>
        }
      >
        <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:items-center">
          <a href="#install" className="btn btn-primary">
            Get started
          </a>
          <Link href="/" className="btn btn-ghost">
            See all plugins
          </Link>
          <a
            href={`mailto:${TPPH.authorEmail}`}
            className="stat text-sm text-muted hover:text-accent-ink"
          >
            {TPPH.authorEmail}
          </a>
        </div>
      </Section>
    </>
  );
}
