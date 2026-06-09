---
id: 071
title: Slides — text alignment inside a shape (h/v)
status: idea
effort: S
value: Center/align text in a shape or cell, not just character-level styling
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 071: Slides — text alignment inside a shape (h/v)

## Problem

`style` is character-level only (bold/size/color). There's no way to set paragraph
alignment (left/center/right) or vertical alignment within a shape — the styling pass noted
cards "would look better centered." Part of the deferred Phase 3b paragraph-styling slice
(Idea 056), surfaced concretely by real use.

## Sketch

- Horizontal: `updateParagraphStyle` with `alignment` (START/CENTER/END/JUSTIFIED) over the
  shape's text range — a `--align` flag on `style` (or a `paragraph-style` command parallel
  to docs).
- Vertical: `updateShapeProperties` `contentAlignment` (TOP/MIDDLE/BOTTOM) — a `--valign`
  flag, likely on `format` (it's a shape property, not text).

## Open Questions

- [ ] Put `--align` on `style` (text) and `--valign` on `format` (shape), or a dedicated
      `paragraph-style`? Lean: extend the existing two commands.
- [ ] Bullets/lists in shapes (also Phase 3b) — bundle or keep separate?

## Value Signal

Direct from the styling pass; small and high polish-value for cards/callouts.

## Effort Guess

S — two well-understood requests (updateParagraphStyle / contentAlignment).

## Notes

- Related: [[slides-phased-rollout]]; Idea 056 (Phase 3b styling remainder).
