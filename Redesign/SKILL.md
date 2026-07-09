---
name: design-system-typography-nerd
description: Creates implementation-ready design-system guidance with tokens, component behavior, and accessibility standards. Use when creating or updating UI rules, component specifications, or design-system documentation.
---

<!-- TYPEUI_SH_MANAGED_START -->

# Typography Nerd

## Mission
Deliver implementation-ready design-system guidance for Typography Nerd that can be applied consistently across e-commerce storefront interfaces.

## Brand
- Product/brand: Typography Nerd
- URL: https://www.typographynerd.de/?ref=bestwebsite.gallery
- Audience: online shoppers and consumers
- Product surface: e-commerce storefront

## Style Foundations
- Visual style: structured, accessible, implementation-first
- Main font style: `font.family.primary=NeurialGrotesk-Bold`, `font.family.stack=NeurialGrotesk-Bold`, `font.size.base=13px`, `font.weight.base=400`, `font.lineHeight.base=18.2px`
- Typography scale: `font.size.xs=10px`, `font.size.sm=13px`, `font.size.md=16px`, `font.size.lg=23px`, `font.size.xl=25px`, `font.size.2xl=34px`, `font.size.3xl=90px`
- Color palette: `color.text.primary=#232323`, `color.text.secondary=#ff5570`, `color.surface.base=#000000`, `color.text.inverse=#0000ee`, `color.surface.muted=#ffffff`
- Spacing scale: `space.1=10px`, `space.2=11.3px`, `space.3=12.38px`, `space.4=15px`, `space.5=20px`, `space.6=20.39px`, `space.7=30px`, `space.8=35px`
- Radius/shadow/motion tokens: manual token definitions required

## Accessibility
- Target: WCAG 2.2 AA
- Keyboard-first interactions required.
- Focus-visible rules required.
- Contrast constraints required.

## Writing Tone
concise, confident, implementation-focused

## Rules: Do
- Use semantic tokens, not raw hex values in component guidance.
- Every component must define required states: default, hover, focus-visible, active, disabled, loading, error.
- Responsive behavior and edge-case handling should be specified for every component family.
- Accessibility acceptance criteria must be testable in implementation.

## Rules: Don't
- Do not allow low-contrast text or hidden focus indicators.
- Do not introduce one-off spacing or typography exceptions.
- Do not use ambiguous labels or non-descriptive actions.

## Guideline Authoring Workflow
1. Restate design intent in one sentence.
2. Define foundations and tokens.
3. Define component anatomy, variants, and interactions.
4. Add accessibility acceptance criteria.
5. Add anti-patterns and migration notes.
6. End with QA checklist.

## Required Output Structure
- Context and goals
- Design tokens and foundations
- Component-level rules (anatomy, variants, states, responsive behavior)
- Accessibility requirements and testable acceptance criteria
- Content and tone standards with examples
- Anti-patterns and prohibited implementations
- QA checklist

## Component Rule Expectations
- Include keyboard, pointer, and touch behavior.
- Include spacing and typography token requirements.
- Include long-content, overflow, and empty-state handling.

## Quality Gates
- Every non-negotiable rule must use "must".
- Every recommendation should use "should".
- Every accessibility rule must be testable in implementation.
- Prefer system consistency over local visual exceptions.

<!-- TYPEUI_SH_MANAGED_END -->
