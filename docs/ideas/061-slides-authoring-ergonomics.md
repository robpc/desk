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

Surfaced by real-world Slides testing. **Pain confirmed by an 11-slide build (2026-06-09):
~30+ API calls for the deck, and the placeholder objectIds are unguessable
(`SLIDES_API1981612515_2`), so `inspect` is *mandatory* between every create and fill.**

## Sketch

Three options, in rough order of ADR cleanliness / increasing scope:

**(a) Emit placeholder ids at creation** (cheapest; see Idea 062) — have `add-slide --json`
return the new slide's placeholder objectIds + types, so the mandatory `inspect` disappears.
Doesn't reduce the *number* of `insert-text` calls, but removes a round-trip per slide and
the bookkeeping. Lowest risk; do this first.

**(b) Inline placeholders on `add-slide`** — `--title` / `--body` (and maybe `--subtitle`):
create the slide and fill its layout's named placeholders in one batchUpdate, resolving the
placeholder objectIds internally. Collapses 3 steps → 1 for the common slide. Stays a
single-service primitive mapping to the layout's own placeholder types — clean, low ADR
tension.

**(c) Logical text targets** — let `insert-text` accept a logical target like `TITLE`/`BODY`
against "the current/last slide" (or a given slide), so the agent never handles objectIds
for the common case. Convenient, but introduces a small "current slide" notion to reason
about; weigh against (b), which may subsume the need.

**(d) Batch deck build** — a `--stdin` JSON form building a whole deck (title + layout + body
per slide) in one call. Highest value for big decks, but edges toward the "make me a deck
from a spec" territory parked in Idea 057 under ADR-003. Distinct, later decision; don't
fold in with (a)–(c).

## Open Questions

- [x] **Confirm the pain.** Done — 11-slide build = ~30+ calls, inspect mandatory between
      create and fill.
- [ ] For (b): which placeholder names to expose (`--title`/`--body`/`--subtitle`)? Map to
      the chosen layout's placeholder types; error clearly if the layout lacks one.
- [ ] (b) vs (c): does inline `add-slide` fill remove the need for logical `insert-text`
      targets, or are both worth having (edit-after-create still wants (c))?
- [ ] Does (d) cross the ADR-003 line, or is a flat "list of slides with title/body" still a
      primitive rather than a workflow? Needs an explicit call (and probably its own ADR).

## Value Signal

Real 11-slide build: ~30+ calls with a forced `inspect` per slide. Concrete, not speculative.

## Effort Guess

M — (a) is small-to-medium (placeholder resolution + create-then-fill in one batch);
(b) is larger and entangled with the outline-authoring question.

## Notes

- Related: [[slides-phased-rollout]]; Idea 062 (emit placeholder ids — the (a) above);
  Idea 057 (outline authoring, questioned under ADR-003); Idea 056 (Phase 3 styling/layout).
- Suggested sequence: 062 (a) → (b) inline fill → reassess (c)/(d) with more usage.
