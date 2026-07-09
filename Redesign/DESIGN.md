# QGIS Plugins — Site Design System

## Mission
Create implementation-ready, token-driven UI guidance for the QGIS Plugins website that is optimized for consistency, accessibility, and fast delivery across the plugin hub and every plugin section.

## Brand
- Product/brand: QGIS Plugins (umbrella hub) · QGIS Dashboard, Title Plotter PH (plugins)
- URL: https://qgis.byzenterra.org
- Author: Isaac Enage — free & open-source, repo: https://github.com/isaacenage/QGIS-Plugins
- Audience: GIS professionals and QGIS desktop users
- Product surface: plugin hub landing (`/`), plugin sections (`/qdashboards` landing, gallery, guide, dashboard viewer)
- Identity anchor: the gradient parallelogram logo (blue → amber → green). The dashboard **tile** is the structural unit; the signature interaction is the **cross-filter** ("dim the unrelated").

## Style Foundations
- Visual style: **editorial magazine, traced from the Typography-Nerd reference** — pure white paper, hard rectangles (zero border radius, enforced globally), flat (no shadows), hairline rules, coral underlines as the labeling device, long arrows as the CTA device. Never heavy or dark chrome; the only dark strokes allowed are inside *art/graphics* (e.g. the `.qdash` plate), mirroring the reference's outlined glyphs.
- Font roles (loaded via `next/font/google` in `app/layout.tsx`, exposed as CSS vars in `app/globals.css`):
  - `font.display=Poppins` and `font.sans=Poppins` — one bold geometric grotesque carries the whole site (the reference's Campton stand-in; weights 400/500/600/700). `.display` = weight 700, letter-spacing −0.015em, line-height 1.08.
  - `font.mono=JetBrains Mono` (`--font-mono`) — reserved for **real code only** (the guide's `Code`/`Pre`), never chrome or labels. `.stat` is sans with tabular numerals.
- Typography scale (Tailwind classes in live use):
  - `.eyebrow` / `.tag` = 0.85rem sans semibold, sentence case, `accent-ink` text over a 1px `accent` underline — the reference's category-tag device (no gradient dash, no mono)
  - captions `text-xs`, secondary copy `text-sm`, body `text-base`, section leads `text-lg leading-relaxed`
  - card titles `text-[1.35rem]` bold, split titles `text-2xl sm:text-3xl`, section `h2` `text-3xl sm:text-4xl`, hero `h1` `text-4xl sm:text-5xl lg:text-[3.6rem]` bold white on the coral block
- Color palette (CSS custom properties in `:root`, mapped to Tailwind via `@theme inline` — use the token names, never raw hex):
  - `color.paper=#ffffff` and `color.surface=#ffffff` — **everything is white**; structure comes from hairlines and type, not background tints
  - `color.ink=#1c1c21` primary text · `color.muted=#55555d` secondary · `color.faint=#97979f` tertiary/placeholder
  - `color.accent=#ef4b6c` watermelon coral (hero block, tags, nav links, outlined boxes/badges) · `color.accent-ink=#c9184a` deep coral for text/links on white (AA)
  - `color.line=#e6e6e9` default hairline border · `color.line-strong=#d5d5da` emphasized hairline
  - Categorical trio (art only): `color.cat-blue=#a3a3ad` gray, `color.cat-amber=#f27d92` light pink, `color.cat-green=#2b2b33` near-black — the art reads gray/black/coral like the reference
- Spacing & layout: Tailwind default scale. Containers `max-w-6xl px-5`; sections `py-20`; sticky header `h-16`, solid white with hairline base (no blur/transparency); card grids `gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-3`; the hub keeps a fixed left side-rail at xl+ (rotated brand line + coral back-to-top arrow).
- Radius / shadow / motion tokens:
  - **Radius = 0 everywhere.** `--radius`/`--radius-lg` are 0px and a global `* { border-radius: 0 !important }` rule flattens every legacy `rounded-*` utility. Do not add rounded corners anywhere.
  - **No shadows** (`--shadow-tile: none`). Depth is expressed with hairlines only.
  - Motion: micro-transitions 0.15–0.28s ease; arrow glyph slides `translateX(4px)` on link/card hover; cross-filter dim `opacity 0.28s ease`; all disabled under `prefers-reduced-motion`. No hover lifts.
- Signature component classes (defined in `app/globals.css @layer components`):
  - `.tile` — flat white rectangle with a hairline edge; the structural unit for previews/cards that need a frame
  - `.eyebrow` / `.tag` — the coral underlined kicker (see scale above); `.eyebrow` opens sections, `.tag` labels one card/box
  - `.btn .btn-primary` (square ink block, white text, hover → accent-ink) / `.btn .btn-ghost` (square, `line-strong` hairline, hover → accent)
  - `.arrow-link` — ink semibold text + long-arrow SVG, hover → accent-ink; the editorial CTA
  - `.sitemap-link` — small ink text on a thin underline (offset 4px), hover → coral; the footer sitemap-wall link
  - `.stat` — sans tabular numerals for figures, domains, counts
  - `.crossfilter [data-dim="true"]` — non-active siblings drop to opacity 0.32 / saturate 0.6; the site-wide interaction motif

## Accessibility
- Target: WCAG 2.2 AA
- Keyboard-first interactions required.
- Focus-visible rules required: global `:focus-visible` = 2px `accent` outline, 2px offset, 4px radius — never suppressed.
- Contrast constraints required: body text uses `ink`/`muted` on `paper`/`surface`; `faint` is decorative-only, never for essential copy.
- `prefers-reduced-motion: reduce` must zero out all animation and smooth scrolling (already global — do not opt out).

## Writing Tone
Plain, confident, maker-voiced. First person from Isaac where personal ("I build free QGIS tools to fill gaps I kept hitting in real GIS work"). Lead with what the tool does; no marketing fluff, no subscriptions-speak. Sentence case everywhere except `.eyebrow` kickers. CTAs are short and verb-led with directional glyphs: "Explore →", "Visit ↗", "Open QGIS Dashboard →". Recurring value line: "Free & open-source · built for QGIS".

## Rules: Do
- Use semantic tokens (`ink`, `muted`, `accent`, `line`, `surface`, `paper`, `cat-*`), not raw hex values, in component guidance and code.
- Every component must define states for default, hover, focus-visible, active, disabled, loading, and error.
- Borders are always soft hairlines (`line`, `line-strong`); use subtle fills (`accent/8`, `bg-surface/40`) rather than outlines for emphasis.
- Open every content block with the Section skeleton: `.eyebrow` kicker → `.display` heading (accent-highlight a key phrase with `text-accent`) → `text-muted` lead.
- Use the cross-filter dim language for any selection/filter interaction — active element stays saturated, siblings dim.
- Use `.stat`/mono for every number, count, domain, or code-ish string.
- Interactive components must document keyboard, pointer, and touch behavior.
- Accessibility acceptance criteria must be testable in implementation.

## Rules: Don't
- Do not allow low-contrast text or hidden focus indicators.
- Do not introduce one-off spacing, typography, radius, or shadow exceptions — extend the tokens instead.
- Do not use dark/heavy borders or near-black outlines; the hairline `line` tokens are the only edges.
- Do not introduce new fonts, gradients (beyond the logo trio), or a dark theme ad hoc — the site is a light, single-theme system.
- Do not use ambiguous labels or non-descriptive actions ("Click here", "Learn more" without an object).
- Do not ship component guidance without explicit state rules.

## Guideline Authoring Workflow
1. Restate design intent in one sentence.
2. Define foundations and semantic tokens (reuse `app/globals.css`; add tokens there, never inline).
3. Define component anatomy, variants, interactions, and state behavior.
4. Add accessibility acceptance criteria with pass/fail checks.
5. Add anti-patterns, migration notes, and edge-case handling.
6. End with a QA checklist.

## Required Output Structure
- Context and goals.
- Design tokens and foundations.
- Component-level rules (anatomy, variants, states, responsive behavior).
- Accessibility requirements and testable acceptance criteria.
- Content and tone standards with examples.
- Anti-patterns and prohibited implementations.
- QA checklist.

## Component Rule Expectations
- Include keyboard, pointer, and touch behavior.
- Include spacing and typography token requirements.
- Include long-content, overflow, and empty-state handling (e.g. the dashed `ComingSoonCard` keeps grids from feeling empty).
- Known component inventory (hub page): sticky `HubHeader` (wordmark, pill nav, primary CTA) · centered hero with ambient `cat-*` glows · `Section` (eyebrow/title/lead) · `PluginSpotlight` (`.tile` split: cross-filter preview board + pitch + feature chips `bg-accent/8 text-accent-ink`) · `PluginCard` grid + `ComingSoonCard` · about/maker section · `HubFooter` (link columns, `.stat` domain line).

## Editorial Skin Is Site-Wide (no scoped `.theme-editorial`)
The Typography-Nerd-derived editorial system above **is the whole site's single theme** — the former scoped `.theme-editorial` wrapper and the old blue system are gone; the hub ("/"), the `/qdashboards` section, Gallery and Guide all resolve through the same `:root` tokens. Layout grammar inherited from the reference:
- **Hub flow** mirrors the reference exactly: coral hero block (bold white headline, ink body copy, ink arrow, art collage overflowing the block's bottom corner) → three borderless entry cards immediately after (graphic plate → coral underlined tag → bold title → body → arrow; no section header between) → coral-outlined (`border-accent`) feature boxes beside art, alternating sides → about → the dense sitemap footer.
- **Headers** are deliberately *not* the reference's arrangement (its nav-left / stacked-wordmark-right was explicitly rejected): mark + one-line bold wordmark left, coral semibold underline-on-hover nav + a square ink button right.
- **Footer** is the reference's sitemap wall: pure link columns (hub: five, no brand column), coral spaced-caps headers (`text-[0.7rem] tracking-[0.18em] text-accent-ink`), stacks of `.sitemap-link` entries; bottom row = spaced-caps maker line + the coral-outlined square badge ("No subscriptions · no accounts").
- Contrast rules baked in: white on `accent` is large-text-only (hero `h1`); body copy on the coral block uses `ink` (≥4.5:1); `.btn-primary` is `ink` (square black block, `accent-ink` hover) because white-on-coral fails AA at button size.

## Quality Gates
- Every non-negotiable rule must use "must".
- Every recommendation should use "should".
- Every accessibility rule must be testable in implementation.
- Teams should prefer system consistency over local visual exceptions.
