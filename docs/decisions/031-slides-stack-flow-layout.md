---
id: 031
title: Slides `stack` — flow layout (natural size, align, gap)
status: accepted
date: 2026-06-09
supersedes: []
superseded_by: null
tags: [slides, api, layout]
---

# ADR-031: Slides `stack` — flow layout

## Context

`arrange` (ADR-029) distributes elements into a grid by **stretching each to fill its
cell** — right for cards/panels. But a common compositional intent it can't express is
"these N elements, at their natural size, in a line, evenly spaced, aligned" — e.g. "five
callouts, centered, stacked vertically." That's a **flow**, not a tile. The maintainer
asked for the agnostic, composability-oriented version of this rather than per-element
relative anchoring (Idea 065).

## Decision

Add a sibling command:

```
desk slides stack <id> <object-id>... --dir vertical|horizontal [--align start|center|end] [--gap PT] [--region R]
```

- Lays the elements along `--dir`, **preserving each element's size**, with `--gap` between
  them (default 12 pt), aligned on the cross-axis by `--align` (vertical → left/center/right;
  horizontal → top/middle/bottom), within `--region` (default the slide content area).
- Implemented as **move-only** `updatePageElementTransform` (ABSOLUTE) that preserves each
  element's existing scale/shear and only changes translate — so it never resizes, and is
  safe for tables (which reject scaled transforms). All geometry is internal.

This uses **flexbox vocabulary** (direction / align / gap) — universal, portable terms, not
desk-coined jargon — consistent with ADR-028's narrow agent-first > no-invented-vocabulary
precedence (it serves the math-avoidance agent need).

`arrange` and `stack` split cleanly by intent:
- **`arrange --as columns|rows|grid`** → fill a region (stretch to cells).
- **`stack --dir … --align … --gap`** → flow at natural size, aligned.

## Alternatives Considered

- **Overload `arrange` with `--fit none`/`--align`** — one command, but "arrange as rows,
  fit none, align center" muddies arrange's clear "tile to fill" meaning. Two short verbs,
  each meaning one thing, is more agent-legible.
- **Relative anchoring (`place --below <other>`, Idea 065)** — solves a narrower case
  (one element vs another) and carries more invented vocabulary. `stack` covers the
  set-composition need the maintainer actually described; 065 stays held.
- **Persistent object grouping (`groupObjects`)** — a real, separate capability (move/scale
  N elements as one unit). Deliberately deferred — `stack` is a one-time layout pass, which
  is what was asked for; add `group`/`ungroup` only if "manipulate as one unit" is needed.

## Consequences

### Positive
- Agents express "centered, stacked, evenly spaced" directly; no coordinates.
- Move-only transform preserves sizes and works for tables.
- Complements `arrange` without overloading it.

### Negative
- Main-axis packs from the region's start edge; there's no `--justify` (center/space-between
  the whole run) yet — a clean future add if needed.
- A stack taller/wider than its region overflows (surfaced by `inspect` `offSlide`), rather
  than auto-shrinking — intentional (stack preserves natural size).

## Implementation Notes

- `src/desk/services/slides.py`: `STACK_DIRECTIONS`/`STACK_ALIGN`, `_move_transform_request`,
  `stack_elements` (reuses `_element_box`, `_region_box`).
- `src/desk/commands/slides.py`: `stack` command. Live-verified.

## References

- ADR-028 (math-free layout / vocabulary precedence), ADR-029 (`arrange`)
- [Idea 074](../ideas/074-slides-stack-flow-layout.md); Idea 065 (relative anchoring — held)
