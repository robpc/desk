---
id: 033
title: Slides use 1-based slide numbers (match the Slides UI)
status: accepted
date: 2026-06-12
supersedes: []
superseded_by: null
tags: [slides, ux, breaking-change, agent-first]
---

# ADR-033: 1-based slide numbers

## Context

Desk addressed slides by **0-based** index everywhere: `inspect`/`read` emitted
`"index": 0` for the first slide and printed `Slide 0`; the `<slide>` positional arg, `--slide`,
`add-slide --index`, and `move-slide --to` all took 0-based values. But the Google Slides **UI**
— the surface the human is actually looking at — numbers slides **1, 2, 3…**.

This produced a recurring, multi-turn off-by-one between the human and the agent: the maintainer
says "slide 3" (UI), the agent reads `Slide 2` off `inspect` (0-based), and they talk past each
other. It bit both the maintainer and the test agent (`deck-builder`) repeatedly. The CLI is the
agent's interface to an artifact the human is *also* viewing, so it should speak the **UI's**
language, not an internal array convention. (This is squarely ADR-002: map to the *service's*
user-facing vocabulary — Google shows 1-based slide numbers.)

## Decision

**Slide numbers are 1-based across all of Desk's slide surfaces**, matching the UI. The Slides
API is 0-based; Desk converts at its single resolution choke point. The flip is **atomic** and
scoped **only to slide numbers** — not to other indices.

**Flipped to 1-based (one change):**
- `inspect` / `read` JSON: the slide's positional field is renamed `index` → **`number`** (1-based).
  The rename is deliberate fail-loud signalling — a stale consumer reading `index` gets a
  `KeyError`, not a silently-wrong 0-based value.
- `inspect` / `read` human output: prints `Slide 1 … Slide N` (matches the UI).
- The `<slide>` positional arg on `read`, `delete-slide`, `duplicate-slide`, `move-slide`,
  `set-notes`, `set-background`, `insert-shape`, `insert-table`, `insert-image` — all resolve
  through `_resolve_slide_object_id`, so one edit there covers them (a 1-based number or an
  objectId; objectIds still pass through untouched).
- `add-slide --index` (insertion position) and `move-slide --to` (target position) → 1-based.
- `slides-fit` `fit_check.py --slide N` → 1-based; reads the new `number` field.

**Left 0-based (NOT slide numbers — guardrail):** `insert-text --at` (character offset),
`style --start/--end` (character offsets), `set-cell --row/--col` (table indices), and the Google
placeholder `index` field. These are computational offsets, not UI labels; flipping them to
"match" would manufacture a new class of confusion.

**Self-announcing + loud signal:**
- Help text for every slide-number input says "1-based (matches the Slides UI)".
- `inspect`/`read` print `Slide 1…`, so the convention is visible in output, not a rule to recall.
- **Version bump 0.2.0 → 0.3.0** marks the breaking change so an agent switches its mental model
  in lockstep rather than discovering the flip via a wrong edit.

## Alternatives Considered

- **Keep 0-based, label it ("Slide 1 of 5 (index 0)")** — non-breaking, but leaves a permanent
  translation layer between the human's view and the tool, i.e. the exact bug we're removing.
  Rejected: clarity-by-annotation doesn't remove the off-by-one, it just documents it.
- **Dual fields (`index` 0-based + `number` 1-based), inputs accept both** — more surface and a
  standing ambiguity about which a given flag wants. A *mixed* convention is worse than either
  pure one (per `deck-builder`'s "all-or-nothing" guardrail). Rejected.
- **Flip all `index`-named things** — would sweep in character offsets and table row/col indices,
  which are genuinely 0-based computational offsets, not UI labels. Explicitly out of scope.

## Consequences

### Positive
- The human and the agent share one reference (the UI). The whole off-by-one bug class disappears.
- objectIds remain the unambiguous, stable handle; most mutating commands already key off them,
  so the migrated surface is bounded.

### Negative
- **Breaking change.** Existing 0-based callers/scripts and the renamed `index`→`number` field
  must update. The version bump + fail-loud rename are the mitigations.
- A two-numbering mental split now exists *within* Desk (slide numbers 1-based; char/table offsets
  0-based) — but it mirrors the real distinction (UI labels vs computational offsets) and each is
  internally consistent and documented in help.

## Implementation Notes

- `src/desk/services/slides.py`: `_resolve_slide_object_id` converts a 1-based number to the
  0-based array position (rejects `< 1`); `add_slide`/`move_slide` convert insertion positions;
  `inspect`/`read` emit `number`.
- `src/desk/commands/slides.py`: help text, validation (`>= 1`), human labels.
- `~/.claude/skills/slides-fit/fit_check.py`: 1-based `--slide`, reads `number`. (Also fixes the
  separate truncated-objectId-in-summary snag `deck-builder` flagged — prints full objectIds.)
- Version → 0.3.0.

## References

- ADR-002 (no invented vocabulary — map to the service's user-facing terms), ADR-026 (Slides),
  ADR-032 (group/ungroup). [Idea 078](../ideas/078-slides-1-based-numbering.md).
- `deck-builder` relay opinion (desk-slides, 2026-06-12): 1-based, atomic, slide-numbers-only,
  self-announcing, loud signal on the flip.
