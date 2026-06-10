---
id: 075
title: Slides place by exact coords — reposition + resize
status: implemented
effort: S
value: Nudge/resize an element to exact x/y/width/height, not just named regions
created: 2026-06-10
updated: 2026-06-10
adr: docs/decisions/028-slides-styling-and-relative-layout.md
---

# Idea 075: Slides place by exact coords (reposition + resize)

## Problem

From the visual-polish feedback: (#1) no way to **resize** a shape after creation —
changing width/height meant delete + re-insert (colliding with z-order + the delete flow);
(#2) no way to **reposition to exact coordinates** — `place` only snapped to named regions,
`stack` distributes at natural size. Neither nudged one element to an exact x/y.

## What was implemented

Extended `place` to accept explicit points as an alternative to `--region`:
- `place <id> <obj> --x X --y Y` → **move** (size preserved, move-only transform)
- `place <id> <obj> --width W --height H` → **resize** (fit transform; position kept)
- omitted coords keep the current value; `--region` and coords are mutually exclusive.

Mirrors `insert-shape`'s positioning flags. Covers feedback #1 + #2 in one change.

## Notes

- Live-verified: move keeps size, resize keeps position, inspect confirms.
- **Tables can't be resized** (the API rejects scaled transforms) → passing `--width/--height`
  for a table raises INVALID_INPUT with guidance to move via `--x/--y`. Move works on tables.
- **No fit-to-text/autofit**: the API rejects setting any autofit type ("Autofit types other
  than NONE are not supported"), so resize is explicit-W/H only.
- Related: [[slides-phased-rollout]]; feedback #3 (text-fit/overflow) is a separate, harder
  question — see Idea 076.
