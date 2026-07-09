// Hand-drawn, token-colored art for the hub page. Every piece is decorative
// (aria-hidden) — the copy beside it carries the meaning. The art speaks the
// products' own vernacular: dashboard tiles with the cross-filter dim, and a
// surveyed parcel with bearings and a tie point. Editorial rules apply here
// too: hard rectangles only (no rx, no rounding), gray/black/coral palette.

/** The long editorial arrow used inside `.arrow-link` CTAs. */
export function LongArrow() {
  return (
    <svg
      width="30"
      height="12"
      viewBox="0 0 30 12"
      fill="none"
      aria-hidden
      className="arrow-glyph shrink-0"
    >
      <path
        d="M0 6h27M22.5 1.5 27 6l-4.5 4.5"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

/** The hero collage: a mini dashboard mid-filter — indicator, bar chart with
 *  one selected zone, donut, list — plus the plugin's own status-bar line. */
export function HeroBoard() {
  return (
    <div className="tile w-full max-w-md p-3" aria-hidden>
      <div className="grid grid-cols-3 gap-2.5">
        {/* indicator tile — a real number from the plugin */}
        <div className="border border-line bg-paper p-3">
          <p className="text-[0.55rem] font-semibold uppercase tracking-[0.14em] text-faint">
            Chart types
          </p>
          <p className="display mt-1 text-3xl text-ink">23</p>
        </div>
        {/* bar chart — one bar selected, siblings dimmed */}
        <div className="col-span-2 border border-line bg-paper p-3">
          <p className="text-[0.55rem] font-semibold uppercase tracking-[0.14em] text-faint">
            Parcels by zone
          </p>
          <svg viewBox="0 0 124 44" className="mt-1.5 h-12 w-full">
            {[28, 42, 18, 30, 12].map((h, i) => (
              <rect
                key={i}
                x={4 + i * 24}
                y={44 - h}
                width={16}
                height={h}
                fill={i === 1 ? "var(--accent)" : "var(--cat-blue)"}
                opacity={i === 1 ? 1 : 0.3}
              />
            ))}
          </svg>
        </div>
        {/* donut — chart content stays circular; the selected slice stays saturated */}
        <div className="flex items-center justify-center border border-line bg-paper p-3">
          <svg viewBox="0 0 44 44" className="h-14 w-14">
            <g transform="rotate(-90 22 22)">
              <circle
                cx="22"
                cy="22"
                r="15.9"
                fill="none"
                stroke="var(--accent)"
                strokeWidth="8"
                strokeDasharray="40 60"
              />
              <circle
                cx="22"
                cy="22"
                r="15.9"
                fill="none"
                stroke="var(--cat-amber)"
                strokeWidth="8"
                strokeDasharray="25 75"
                strokeDashoffset="-40"
                opacity="0.3"
              />
              <circle
                cx="22"
                cy="22"
                r="15.9"
                fill="none"
                stroke="var(--cat-green)"
                strokeWidth="8"
                strokeDasharray="35 65"
                strokeDashoffset="-65"
                opacity="0.3"
              />
            </g>
          </svg>
        </div>
        {/* list of matching features */}
        <div className="col-span-2 border border-line bg-paper p-3">
          <p className="text-[0.55rem] font-semibold uppercase tracking-[0.14em] text-faint">
            Matching features
          </p>
          <div className="mt-2.5 space-y-2">
            {[82, 58, 70].map((w, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 shrink-0 bg-cat-green" />
                <span className="h-1.5 bg-line" style={{ width: `${w}%` }} />
              </div>
            ))}
          </div>
        </div>
      </div>
      {/* the plugin's status-bar line */}
      <div className="mt-2.5 flex items-center gap-1.5 px-1">
        <span className="h-1.5 w-1.5 bg-accent" />
        <span className="stat text-[0.6rem] font-medium text-muted">
          Filters active: 1
        </span>
      </div>
    </div>
  );
}

/** Split art for QGIS Dashboard: the signature interaction as a still — the
 *  selected tiles stay saturated, the unrelated ones dim. */
export function CrossfilterBoard() {
  const cells = [
    "active", "dim", "dim",
    "dim", "active", "dim",
    "dim", "dim", "dim",
  ];
  return (
    <div className="relative border border-line bg-paper p-5 sm:p-7" aria-hidden>
      <div className="grid aspect-[4/3] grid-cols-3 grid-rows-3 gap-3">
        {cells.map((state, i) =>
          state === "active" ? (
            <div key={i} className="bg-accent" />
          ) : (
            <div key={i} className="border border-line bg-surface opacity-40" />
          ),
        )}
      </div>
      <div className="absolute -bottom-3.5 left-1/2 -translate-x-1/2 whitespace-nowrap border border-line-strong bg-surface px-3.5 py-1.5">
        <span className="stat text-[0.65rem] font-semibold text-accent-ink">
          Filters active: 2
        </span>
      </div>
    </div>
  );
}

/** Split art for Title Plotter PH: a parcel plotted from its technical
 *  description — bearings, corner points, and the tie line back to a BLLM. */
export function ParcelPlot() {
  const corners: [number, number][] = [
    [150, 118],
    [330, 94],
    [356, 216],
    [236, 262],
    [130, 222],
  ];
  return (
    <div className="border border-line bg-paper p-5 sm:p-7" aria-hidden>
      <svg viewBox="0 0 400 300" className="h-auto w-full">
        {/* faint survey grid */}
        {Array.from({ length: 9 }, (_, i) => (
          <line
            key={`v${i}`}
            x1={(i + 1) * 40}
            y1="0"
            x2={(i + 1) * 40}
            y2="300"
            stroke="var(--line)"
            strokeWidth="1"
          />
        ))}
        {Array.from({ length: 7 }, (_, i) => (
          <line
            key={`h${i}`}
            x1="0"
            y1={(i + 1) * 37.5}
            x2="400"
            y2={(i + 1) * 37.5}
            stroke="var(--line)"
            strokeWidth="1"
          />
        ))}
        {/* tie point + dashed tie line to corner 1 */}
        <g stroke="var(--accent)" strokeWidth="1.5" fill="none">
          <circle cx="62" cy="52" r="8" />
          <line x1="50" y1="52" x2="74" y2="52" />
          <line x1="62" y1="40" x2="62" y2="64" />
          <line x1="66" y1="56" x2="150" y2="118" strokeDasharray="5 5" />
        </g>
        <text
          x="80"
          y="40"
          fontFamily="var(--font-sans)"
          fontWeight="600"
          fontSize="11"
          fill="var(--accent-ink)"
        >
          BLLM No. 1
        </text>
        {/* the parcel */}
        <polygon
          points={corners.map((c) => c.join(",")).join(" ")}
          fill="var(--cat-amber)"
          fillOpacity="0.16"
          stroke="var(--cat-amber)"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {corners.map(([x, y], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r="4.5"
            fill="var(--surface)"
            stroke="var(--cat-amber)"
            strokeWidth="2"
          />
        ))}
        {/* bearings + lot label */}
        <text
          x="240"
          y="92"
          fontFamily="var(--font-sans)"
          fontWeight="500"
          fontSize="11"
          fill="var(--muted)"
          textAnchor="middle"
        >
          N 82°30′E · 45.10 m
        </text>
        <text
          x="158"
          y="264"
          fontFamily="var(--font-sans)"
          fontWeight="500"
          fontSize="11"
          fill="var(--muted)"
          textAnchor="middle"
        >
          S 47°15′W · 32.86 m
        </text>
        <text
          x="242"
          y="180"
          fontFamily="var(--font-sans)"
          fontWeight="600"
          fontSize="12"
          fill="var(--accent-ink)"
          textAnchor="middle"
        >
          Lot 4 · 1,248 m²
        </text>
      </svg>
    </div>
  );
}

/* ---------- card glyphs (the big graphic area of each entry card) ---------- */

/** Gallery: a 2×2 mosaic with one tile selected — hard squares. */
export function GalleryGlyph() {
  return (
    <svg viewBox="0 0 112 84" className="h-24 w-auto" aria-hidden>
      <rect x="0" y="0" width="52" height="38" fill="var(--accent)" />
      <rect x="60" y="0" width="52" height="38" fill="var(--cat-blue)" opacity="0.3" />
      <rect x="0" y="46" width="52" height="38" fill="var(--cat-green)" opacity="0.3" />
      <rect x="60" y="46" width="52" height="38" fill="var(--cat-amber)" opacity="0.3" />
    </svg>
  );
}

/** Guide: the portable dashboard file — an ink-outlined plate like the
 *  reference's "OTF" box, badged with its layout version. */
export function QdashFileGlyph() {
  return (
    <span
      className="relative inline-block border-2 border-ink bg-surface px-7 py-5"
      aria-hidden
    >
      <span className="text-3xl font-bold tracking-tight text-ink">.qdash</span>
      <span className="absolute -right-2.5 -top-2.5 border border-ink bg-paper px-1.5 py-0.5">
        <span className="text-[0.6rem] font-bold text-ink">v3</span>
      </span>
    </span>
  );
}

/** Source: a pixel heart for open-source — coral with a light-pink shine,
 *  straight out of the reference. */
export function PixelHeart() {
  const px: [number, number, boolean?][] = [
    [1, 0], [2, 0], [4, 0], [5, 0],
    [0, 1], [1, 1, true], [2, 1], [3, 1], [4, 1], [5, 1], [6, 1],
    [0, 2], [1, 2], [2, 2], [3, 2], [4, 2], [5, 2], [6, 2],
    [1, 3], [2, 3], [3, 3], [4, 3], [5, 3],
    [2, 4], [3, 4], [4, 4],
    [3, 5],
  ];
  return (
    <svg viewBox="0 0 84 72" className="h-24 w-auto" aria-hidden>
      {px.map(([x, y, shine], i) => (
        <rect
          key={i}
          x={x * 12}
          y={y * 12}
          width="11"
          height="11"
          fill={shine ? "var(--cat-amber)" : "var(--accent)"}
          opacity={shine ? 0.9 : 1}
        />
      ))}
    </svg>
  );
}
