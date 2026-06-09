---
id: 061
title: Slides Authoring Ergonomics — fewer round-trips per slide
status: idea
effort: M
value: Cut the add-slide → inspect → insert-text-per-placeholder loop down for multi-slide decks
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 061: Slides Authoring Ergonomics — fewer round-trips per slide

## Problem

Populating a slide today is three steps: `add-slide` → `inspect` (to discover the new
slide's placeholder objectIds) → one `insert-text` per placeholder. For an N-slide deck
that's a lot of round-trips and a lot of objectId bookkeeping for the agent.

Surfaced by real-world Slides testing (2026-06-09). The user flagged it as real but
**pending confirmation of how painful it actually is once a full deck build is run** — so
this is logged with that caveat, not yet scoped for build.

## Sketch

Two options, deliberately separated because they sit differently against ADR-003:

**(a) Inline placeholders on `add-slide`** — `--title` / `--body` (and maybe `--subtitle`):
create the slide and fill its layout's named placeholders in one batchUpdate, resolving the
placeholder objectIds internally. This stays a single-service primitive that maps to the
layout's own placeholder types — clean, low ADR tension. Likely the right first step.

**(b) Batch deck build** — a `--stdin` JSON form describing multiple slides/content built
in one call. Higher value for big decks, but edges toward the "make me a deck from a spec"
territory parked in Idea 057 (outline authoring) under ADR-003. Treat as a distinct,
later decision; don't fold it in with (a).

## Open Questions

- [ ] **First: confirm the pain.** Get the real-build numbers (round-trips, where the agent
      stalls) before committing — the user is gathering this.
- [ ] For (a): which placeholder names to expose (`--title`/`--body`/`--subtitle`)? Map to
      the chosen layout's placeholder types; error clearly if the layout lacks one.
- [ ] Does (b) cross the ADR-003 line, or is a flat "list of slides with title/body" still a
      primitive rather than a workflow? Needs an explicit call (and probably its own ADR).

## Value Signal

Direct user feedback during real authoring. Magnitude TBD — explicitly awaiting evidence.

## Effort Guess

M — (a) is small-to-medium (placeholder resolution + create-then-fill in one batch);
(b) is larger and entangled with the outline-authoring question.

## Notes

- Related: [[slides-phased-rollout]]; Idea 057 (outline authoring, questioned under
  ADR-003); Idea 056 (Phase 3 styling/layout).
- Hold until real-build feedback lands.
