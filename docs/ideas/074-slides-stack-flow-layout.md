---
id: 074
title: Slides stack — flow layout over a set of elements
status: implemented
effort: M
value: "These N, centered, stacked vertically (evenly spaced)" without coordinates
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/031-slides-stack-flow-layout.md
---

# Idea 074: Slides `stack` — flow layout

## Problem

`arrange` tiles (stretches elements to fill a grid). There was no way to express the common
composability intent the maintainer described — "these five items, centered, stacked
vertically, evenly spaced" — i.e. flow elements at their **natural size** with alignment +
gap. (Considered as the agnostic alternative to relative anchoring, Idea 065.)

## What was implemented

`desk slides stack <id> <obj>... --dir vertical|horizontal [--align start|center|end]
[--gap PT] [--region R]`. Flexbox-style vocabulary; move-only transform (preserves size,
safe for tables). See ADR-031 for the design and the `arrange` (fill) vs `stack` (flow)
split.

## Notes

- Live-verified: 3 shapes of different sizes, `--dir vertical --align center --gap 12` →
  sizes preserved, all centered (same center_x = slide center), stacked with the gap.
- Future: `--justify` for main-axis distribution (center/space-between the whole run).
- Related: [[slides-phased-rollout]]; Idea 065 (relative anchoring, held); object
  grouping (`groupObjects`) deferred.
