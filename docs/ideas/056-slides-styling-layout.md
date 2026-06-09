---
id: 056
title: Slides Phase 3 — Styling & Layout
status: adr-created
effort: L
value: Agents can style text and elements, set backgrounds, and apply layouts
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/028-slides-styling-and-relative-layout.md
---

> **Phase 3a shipped** (ADR-028): text styling (`style`), shape/image fill+outline
> (`format`), and a math-free relative-layout vocabulary (`--region` on inserts +
> `place`). **Phase 3b remains** (see Open Questions / Notes): paragraph bullets,
> element transforms beyond region-fit, slide backgrounds, layout/master apply, and
> table-cell styling.

# Idea 056: Slides Phase 3 — Styling & Layout

## Problem

After Phases 1–2, agents can build structurally complete decks, but they're visually
plain — no bold/color/font control, no element fill or outline, no positioning refinement,
no background or layout choices. This is the highest-complexity, lowest-per-feature-value
slice of the Slides API, which is exactly why it's deferred to last among the
primitive-level phases.

## Sketch

Add styling commands, mirroring the Docs styling split (ADR-008, ADR-017):

- `style` — text run styling (bold, italic, underline, color, font family, size) over a
  text range in a shape/cell
- `paragraph-style` — alignment, bullets/numbered lists, line spacing, indent
- element styling — fill color, outline, and `updatePageElementTransform`
  (move/resize/rotate) for existing elements
- `set-background` — slide background color/image
- `apply-layout` — apply a predefined layout/master to a slide

## Open Questions

- [ ] Range addressing for text styling — `objectId` + start/end index, consistent with
      `desk docs style`?
- [ ] Color input format — hex? named theme colors (`ACCENT1`, etc.)? Support both.
- [ ] How much of the transform surface to expose vs. defaulting — rotation and skew are
      rarely needed by agents.
- [ ] Lists/bullets in Slides differ from Docs — confirm the `createParagraphBullets`
      request shape and presets.
- [ ] Should theme/master selection be exposed at all, or is per-element styling enough?

## Value Signal

Polish matters for presentation-quality output, but each individual styling feature is
lower-value than the content primitives. Worth doing once the foundation is proven and
demand for nicer-looking decks is clear.

## Effort Guess

L — Large surface (text + paragraph + element + background + layout), several distinct
request types, and a color/range/transform model that needs to stay ergonomic. Likely
split into sub-PRs.

## Notes

- Follows Ideas 054–055
- Parallels the Docs styling work: ADR-008, ADR-017, ADR-024
- Sub-phased: **3a** (text styling + element fill/outline + relative layout) shipped via
  ADR-028 on branch `feat/slides-support`; **3b** carries the remainder below.
- Phase 3a notable design win: layout-by-named-region (`top-right`, `left-half`, …) so
  agents describe placement in words and the command does the geometry — no EMU/point math.
- Phase 3b backlog: paragraph bullets/alignment in shapes; element move/resize/rotate
  beyond `place`'s region-fit; slide backgrounds; layout/master apply; table-cell fill and
  table-cell text styling (needs a cell-range addressing scheme).
