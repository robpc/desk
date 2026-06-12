---
id: 066
title: Slides Table Cell Fill (set-cell)
status: implemented
effort: S
value: Tables were write-only shells; cells are now fillable
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/030-slides-authoring-refinements-and-scope-ux.md
---

# Idea 066: Slides Table Cell Fill (set-cell)

## Problem

`insert-table` created a table but its cells were unfillable: cells aren't separate
objects, `insert-text` against the bare table objectId is rejected by the API, and the
deck-builder had to delete the table and fall back to a text box. Tables were write-only
shells. Reported as the biggest functional gap from the styling/graphics test pass.

## What was implemented

`desk slides set-cell <id> <table-object-id> "<text>" --row R --col C [--mode replace|append]`.

The Slides API addresses cells via a `cellLocation` (rowIndex/columnIndex) on the table's
objectId — `set_cell` resolves the table, validates the cell is in range, and issues
`insertText` (replace clears the cell with `deleteText` first). No per-cell objectIds
needed; the agent uses the table objectId from `inspect` + row/col.

## Notes

- Live-verified: filled a 2x2 table, `read` shows `Quarter | Revenue / Q1 |`.
- Out-of-range / non-table targets raise INVALID_INPUT with a clear message.
- Bulk fill (`insert-table --data`) and table repositioning are separate wants — Idea 070.
- Related: [[slides-phased-rollout]].
