---
id: 064
title: Slides Placement Verification — bounding boxes in inspect
status: idea
effort: M
value: Let an agent trust positioning sight-unseen instead of exporting to look
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 064: Slides Placement Verification — bounding boxes in inspect

## Problem

After positioning an element (e.g. `insert-shape --region bottom`), an agent has **no way
to confirm where it actually landed** — whether it overlaps the title or runs off the slide
— without exporting and visually rendering. Real-deck feedback (2026-06-09):

> "A region is 'good enough' only if I can trust it sight-unseen; I'd have wanted either a
> safe-by-construction guarantee or a quick way to verify placement."

This is the trust gap under the whole math-free layout idea (ADR-028/029): the vocabulary is
only useful if the agent can believe the result without eyes on it. Aligns with the repo's
"build verification capabilities so agents can self-verify" principle (CLAUDE.md).

## Sketch

Have `inspect` report each element's **computed bounding box** in points — `x, y, width,
height` derived from `size` × `transform` — plus the slide's own dimensions, so an agent can
reason about placement directly. Optionally flag:

- `offSlide`: any part outside the slide bounds
- `overlaps`: ids of other elements whose boxes intersect

The geometry already lives in the service (`_dimension_pt`, transform math from `place`).
This surfaces it rather than inventing anything — no vocabulary tension.

## Open Questions

- [ ] Compute effective box from `size.{width,height}` × `transform.{scaleX,scaleY}` +
      `translate{X,Y}`; confirm rotation/shear are rare enough to ignore (or report a flag).
- [ ] Always include boxes in `inspect`, or behind a `--bounds` flag to keep default output
      lean? (Probably always in `--json`, summarized in human output.)
- [ ] Is an overlap/off-slide *warning* on `insert-*`/`place`/`arrange` itself worth it, or
      is inspect-on-demand enough? (Start with inspect; warnings later.)

## Value Signal

Directly from real use: the one thing that made the agent distrust a region was not being
able to verify it. Unblocks confident use of the positioning vocabulary we already shipped.

## Effort Guess

M — bounding-box computation + plumbing into `inspect` output; overlap detection is a small
extra. No new API calls.

## Notes

- Related: [[slides-phased-rollout]]; ADR-028/029 (the positioning vocabulary this verifies);
  Idea 065 (relative anchoring) would also benefit from computed boxes.
