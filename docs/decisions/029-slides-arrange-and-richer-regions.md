---
id: 029
title: Slides Multi-Element Arrange and Richer Regions (Phase 3b-i)
status: accepted
date: 2026-06-09
supersedes: []
superseded_by: null
tags: [slides, api, layout]
---

# ADR-029: Slides Multi-Element Arrange and Richer Regions (Phase 3b-i)

## Context

ADR-028 (Phase 3a) introduced math-free layout: an agent names a region
(`top-right`, `left-half`, …) and the command computes the geometry. Single-element
placement (`place`, `--region` on inserts) is covered.

The next gap is **laying out several elements together** — "put these three charts across
the slide as columns", "stack these two boxes". Today an agent would `place` each one into
a hand-picked region, but the region set doesn't include even N-way splits, and the agent
still has to reason about which region each element goes in and whether they'll align. That
reintroduces exactly the spatial bookkeeping ADR-028 set out to remove.

This is the part of layout where the math-free principle pays off most: the agent knows the
*relationship* it wants ("these, as columns"), not the coordinates.

## Decision

Two additions, both math-free.

### 1. Richer region vocabulary

Add full-height column thirds and full-width row thirds to the existing regions:

- columns: `left-third`, `center-third`, `right-third`
- rows: `top-third`, `middle-third`, `bottom-third`

These compose with everything that already takes a region (`--region` on inserts, `place`).
2×2 "quadrants" are intentionally **not** added — they're better served by `arrange --as
grid` with four elements (below), and adding them as named regions would overlap confusingly
with the existing 3×3 grid cells.

### 2. `desk slides arrange`

```
desk slides arrange <presentation-id> <object-id>... --as columns|rows|grid [--region <name>]
```

Distributes the given **existing** elements into evenly-sized cells within a target area —
the slide's content area by default, or a named region if `--region` is passed — fitting
each element to its cell and preserving argument order (row-major for `grid`):

- `columns`: N side-by-side columns (N = element count)
- `rows`: N stacked rows
- `grid`: a near-square grid (`ceil(sqrt(N))` columns), filled row-major

All geometry — cell sizing, gutters, EMU↔PT, the fit transform — lives in shared helpers
(reused from `place`). The agent only names the elements and the arrangement.

## Alternatives Considered

### Alternative 1: Leave multi-element layout to repeated `place`

**Why rejected**: Forces the agent to pick a distinct region per element and mentally
verify they tile without gaps/overlaps — the bookkeeping ADR-028 removes for one element
returns for many.

### Alternative 2: A full grid/flow spec (spans, gaps, alignment, wrapping)

**Why rejected**: Large surface for speculative value. `columns`/`rows`/`grid` over an
optional region covers the overwhelmingly common asks and can grow (spans, explicit counts)
without breaking callers.

### Alternative 3: Add 2×2 quadrant regions

**Why rejected**: Redundant with `arrange --as grid` for four elements and naming-confusing
against the 3×3 grid cells.

## Consequences

### Positive

- Agents lay out multiple elements by intent ("as columns"), no coordinates
- Region vocabulary now covers thirds, the common "three across / three down" case
- One batchUpdate positions all arranged elements

### Negative

- `arrange` (like `place`) fits each element to its cell with independent x/y scale, so
  non-matching aspect ratios distort (most visible on images)
  - *Mitigation*: documented; an aspect-preserving `--fit contain` option is a clean future
    add. Text boxes (the common case) are unaffected.
- `--region` cells get subdivided again by `arrange`, which can yield small cells
  - *Mitigation*: that's the intent; agents pick the area deliberately

### Neutral

- `arrange` only positions existing elements; it does not create them (compose with the
  insert commands)

## Implementation Notes

- `src/desk/services/slides.py`: extend `REGIONS`; add `_fit_transform` (extracted from
  `place_element`), `_grid_cells(area, n, mode)`, and `arrange_elements`
- `src/desk/commands/slides.py`: `arrange` command (variadic object-id args, `--as`,
  `--region`)
- Reuses `_region_box`, `_page_size_pt`, `_find_element`, `_dimension_pt`

## References

- ADR-028 (math-free layout, regions, `place`)
- [Idea 056: Slides Phase 3 — Styling & Layout](../ideas/056-slides-styling-layout.md) (3b backlog)
