---
id: 078
title: 1-based slide numbers (match the Slides UI)
status: implemented
effort: M
value: Removes the human/agent off-by-one bug class by making Desk speak the UI's 1-based slide numbers
created: 2026-06-12
updated: 2026-06-12
adr: 033
---

# Idea 078: 1-based slide numbers

## Problem

Desk addressed slides 0-based everywhere (`inspect` printed `Slide 0`; `--slide`, the `<slide>`
positional arg, `add-slide --index`, `move-slide --to` all 0-based). The Slides **UI** numbers
slides 1, 2, 3 — so the human says "slide 3", the agent reads `Slide 2`, and they talk past each
other. This bit both the maintainer and `deck-builder` repeatedly.

## What was implemented

**Slide numbers are now 1-based across Desk** (matches the UI). Atomic flip, scoped to slide
numbers only. See [ADR-033](../decisions/033-slides-1-based-numbering.md).

- `inspect`/`read`: JSON field `index` → **`number`** (1-based, fail-loud rename); human output
  prints `Slide 1…N`.
- `<slide>` positional (read, delete/duplicate/move-slide, set-notes, set-background,
  insert-shape/table/image) → 1-based, via the single `_resolve_slide_object_id` choke point
  (rejects `0`/`<1`; objectIds still pass through).
- `add-slide --index` / `move-slide --to` → 1-based insertion positions.
- `slides-fit fit_check.py --slide N` → 1-based, reads `number`.
- **Version 0.2.0 → 0.3.0** as the loud signal of the breaking change.

**Left 0-based (NOT slide numbers):** `insert-text --at`, `style --start/--end` (char offsets),
`set-cell --row/--col` (table indices), placeholder `index`. Computational offsets, not UI labels.

## Notes

- Live-verified: inspect shows Slide 1/2/3; `add-slide --index 2` inserts as the new slide 2;
  `move-slide 4 --to 1` reorders correctly; `delete-slide 1` and `set-background 4` work by
  number; `fit_check --slide 1` checks slide 1 and prints full objectIds.
- Bundled fix (deck-builder's separate snag): slides-fit human summary now prints the **full**
  objectId (was truncated to ~18 chars, breaking copy-paste into fix commands).
- `deck-builder`'s guardrails drove the scope: atomic, slide-numbers-only, self-announcing
  (help says "1-based, matches the UI"), loud version bump. Related: [[slides-phased-rollout]],
  Idea 076 (slides-fit), ADR-032.
