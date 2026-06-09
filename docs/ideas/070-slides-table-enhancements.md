---
id: 070
title: Slides Table Enhancements — reposition, bulk fill, region sizing
status: idea
effort: M
value: Make tables first-class: movable, bulk-fillable, and region-sizable
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 070: Slides Table Enhancements

## Problem

After `set-cell` (Idea 066) tables are fillable, but the styling pass surfaced three more
table gaps:

1. **Reposition** — `place` on a table is rejected by the API ("transform is not applicable
   for the page element"). It now errors cleanly (exit 1) rather than silently no-op'ing,
   but you still can't move a table.
2. **Bulk fill** — filling a grid one `set-cell` at a time is many calls; `insert-table
   --data` (rows of values) would build a populated table in one go.
3. **Region sizing** — `insert-table --region <r>` places but does not SIZE the table to
   the region, so a region-placed table can run off-slide.

## Sketch

- Reposition: tables may need `updatePageElementTransform` with translate-only (no scale),
  or a different request; investigate what the API accepts for tables specifically.
- Bulk: `insert-table --data '[["Q","Rev"],["Q1","12"]]'` (or --stdin) → createTable +
  per-cell insertText in one batch; rows/cols inferred from the data.
- Region sizing: after createTable in a region, set column widths / row heights or a
  transform so the table fits the computed box (see Idea 064's box math).

## Open Questions

- [ ] What transform/property actually moves a table? (place currently rejected.)
- [ ] Bulk `--data` format: inline JSON vs --stdin TSV/CSV. Keep it a primitive, not a
      spreadsheet importer.
- [ ] Region sizing interacts with content-driven table size — may need explicit col widths.

## Value Signal

From the styling/graphics pass: tables called "the weak link" even after set-cell.

## Effort Guess

M — three related but separable pieces; reposition needs API spelunking.

## Notes

- Related: [[slides-phased-rollout]]; Idea 066 (set-cell, shipped); Idea 064 (box math).
