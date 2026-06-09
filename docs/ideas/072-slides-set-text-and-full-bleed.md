---
id: 072
title: Slides set-text (replace shape text) + full-bleed region
status: implemented
effort: S
value: Change a shape's text without delete+reinsert; true edge-to-edge placement
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/030-slides-authoring-refinements-and-scope-ux.md
---

# Idea 072: Slides set-text + full-bleed region

## Problem

From a real 12-slide content rebuild (test session): there was **no way to replace an
existing shape's full text**. `insert-text` only inserts/appends; `replace-text` is
find/replace. To change a shape's text the agent had to `delete-object` + re-insert +
re-style — done ~15× during the rebuild, the single biggest source of churn. Separately,
`--region full` insets by the standard 24 pt margin, so there was no true edge-to-edge
(full-bleed) placement for background images/shapes.

## What was implemented

- **`desk slides set-text <id> <object-id> "<text>"`** — clears a shape's text and sets a
  new value in one batchUpdate (deleteText ALL when non-empty, then insertText@0), keeping
  the shape and its styling target. Errors on non-shape targets (use `set-cell` for tables).
- **`--region full-bleed`** — a new region resolving to `(0, 0, pageW, pageH)` (no margin),
  for backgrounds / edge-to-edge elements. `full` still insets 24 pt.

## Notes

- Live-verified: set-text replaced a title's text; full-bleed box = `0,0 720x405`, not
  flagged offSlide.
- Confirmed-working from the same test pass: inline `add-slide`, `insert-shape` object_id
  in --json, `set-notes`, `set-cell`. Text alignment (`style --align` / `format --valign`)
  already shipped (069/071) — the tester had missed it.
- Related: [[slides-phased-rollout]].
