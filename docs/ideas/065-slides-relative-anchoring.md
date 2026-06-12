---
id: 065
title: Slides Relative Anchoring — position an element relative to another
status: idea
effort: M
value: Express "directly under the title" instead of slide-absolute regions
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 065: Slides Relative Anchoring — position an element relative to another

## Problem

Regions (ADR-028/029) are **slide-absolute** (`bottom`, `right-half`). Real-deck feedback
(2026-06-09) surfaced a case they can't express:

> "What I actually wanted was 'directly under the title,' not 'at the bottom of the slide.'
> Regions are slide-absolute; I had no way to anchor one element relative to another."

The agent's mental model was a *relationship between two elements*, not a fixed slide
location — exactly the kind of intent the math-free philosophy aims to serve, but one step
beyond what regions cover.

## Sketch

Let an element be positioned relative to another by objectId, e.g.:

```
desk slides place <id> <object-id> --below <other-object-id> [--gap <pt>]
desk slides place <id> <object-id> --right-of <other-object-id>
```

Edges: `--below`/`--above`/`--left-of`/`--right-of`, aligning to the anchor's box and
offsetting by a small default gap. The command reads both elements' computed boxes (see
Idea 064) and sets the target's transform — the agent never does arithmetic.

## Open Questions

- [ ] Vocabulary: edge flags (`--below`) vs a single `--anchor <id> --edge below`. Keep the
      set small (below/above/left-of/right-of); width/alignment behavior TBD.
- [ ] Does this stay a single-service positioning primitive (on the right side of ADR-003),
      or start to feel like a layout engine? Lean: a few relations = primitive; a constraint
      solver = too far.
- [ ] Depends on computed bounding boxes (Idea 064) — build that first.
- [ ] ADR-002 tension: more invented vocabulary. Justify only if real demand persists beyond
      this single data point (per [[agent-first-vs-invented-vocabulary]] — narrow, demand-led).

## Value Signal

One real instance so far. Promising and on-philosophy, but a single occurrence — hold for
more demand before committing, especially given the ADR-002 cost.

## Effort Guess

M — builds on Idea 064's box computation; mostly edge/offset math + a small CLI surface.

## Notes

- Related: [[slides-phased-rollout]]; Idea 064 (prerequisite); ADR-028/029.
- The SECTION_HEADER tagline that drove the original `--region bottom` workaround is already
  addressed by using SECTION_TITLE_AND_DESCRIPTION (Idea 063) — so the *need* for this is
  weaker than the feedback implies; capture, don't rush.
