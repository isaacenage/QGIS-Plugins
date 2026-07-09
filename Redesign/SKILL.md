---
name: qgis-plugins-site-design
description: Use when building, redesigning, restyling, or reviewing any page or component of the QGIS Plugins website — the hub at "/" (app/page.tsx) or a plugin section like /qdashboards — including new pages, hero/section/card work, buttons, headers, footers, or any change to app/ and components/ that touches visual style.
---

# QGIS Plugins Site Design

## Overview

The QGIS Plugins site is a token-driven design system grounded in the plugin's own identity: the gradient parallelogram logo (blue → amber → green), accent blue `#2b7de9`, soft hairlines, light neutral chrome. The dashboard **tile** is the structural unit; the **cross-filter dim** ("dim the unrelated") is the signature interaction.

**All tokens, scales, and component rules live in `DESIGN.md` in this folder. Read it before writing any UI code.** The tokens are implemented in `app/globals.css` (CSS custom properties + Tailwind `@theme inline` + `@layer components`).

## Workflow

1. Read `DESIGN.md` (same folder) for tokens, type roles, and component rules.
2. Compose from the existing primitives before inventing new ones: `.tile`, `.eyebrow`, `.display`, `.stat`, `.btn-primary` / `.btn-ghost`, `.crossfilter`, and the `Section` component (eyebrow → display heading → muted lead).
3. Style only with semantic Tailwind tokens (`ink`, `muted`, `faint`, `accent`, `accent-ink`, `line`, `line-strong`, `surface`, `paper`, `cat-blue|amber|green`) — never raw hex, never new fonts.
4. New tokens or component classes go into `app/globals.css`, then get used — no inline one-offs.
5. Verify the quality floor: visible `:focus-visible`, WCAG 2.2 AA contrast, `prefers-reduced-motion` respected, all interactive states defined.

## Quick Reference

| Element | Rule |
|---|---|
| Headings | `.display` (Space Grotesk); accent-highlight a key phrase with `text-accent` |
| Kickers | `.eyebrow` (JetBrains Mono, gradient dash) above every section title |
| Body | Inter via body default; leads `text-lg leading-relaxed text-muted` |
| Numbers/domains | `.stat` (mono, tabular-nums) |
| Cards | `.tile` (surface, hairline, 18px radius, soft shadow); hover `-translate-y-0.5` |
| Buttons | Pills only: `.btn-primary` (accent) / `.btn-ghost` (hairline outline) |
| Borders | Hairlines only (`line`, `line-strong`) — never dark/heavy outlines |
| Emphasis | Soft fills (`bg-accent/8`, `bg-surface/40`), not outlines |
| Selection/filter UI | Cross-filter language: active stays saturated, siblings dim (opacity 0.32) |
| Layout | `max-w-6xl px-5`, sections `py-20`, sticky `h-16` blurred header |

## Common Mistakes

- Raw hex or arbitrary colors instead of the semantic tokens.
- Dark borders or heavy shadows — the system is hairline + one soft tile shadow.
- Skipping the eyebrow/display/lead section skeleton, which makes pages read off-brand.
- Adding a dark mode, new font, or one-off spacing instead of extending `globals.css`.
- Marketing-fluff copy — the voice is plain, confident, maker-first ("Free & open-source · built for QGIS").
