---
id: 059
title: Slides Speaker Notes
status: idea
effort: S
value: Set per-slide speaker notes — a core deck use case currently impossible
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 059: Slides Speaker Notes

## Problem

Desk's Slides commands can create slides and put text in body placeholders, but there is
**no way to set speaker notes**. Notes are a core part of real presentations (talk track,
per-slide cues), and an agent building a deck currently can't write them at all. This is a
content-CRUD gap that should arguably have been in Phase 1 (ADR-026).

Surfaced by real-world testing of the Slides feature (2026-06-09).

## Sketch

Add a command targeting the slide's notes page:

```
desk slides set-notes <presentation-id> <slide> "<text>"
```

- `<slide>` accepts a 0-based index or slide objectId (consistent with the rest of the
  Slides commands).
- The Slides API exposes notes via the slide's `slideProperties.notesPage`, whose notes
  text box has a `notesProperties.speakerNotesObjectId`. Resolve that objectId, then
  `insertText` into it (optionally `deleteText` first for replace semantics).
- Maps to a real Slides concept — no invented vocabulary, no ADR-002 tension.

Consider a `--mode append|replace` flag and surfacing existing notes in `read`/`inspect`.

## Open Questions

- [ ] Does the default/blank notes page already have a `speakerNotesObjectId`, or must it
      be created first? (If absent, may need `createParagraphBullets`-style provisioning or
      it may be auto-present.)
- [ ] Should `read` include notes text per slide? Likely yes (round-trips the talk track).
- [ ] Replace vs append default — append is safer; replace is the common authoring case.

## Value Signal

Direct user feedback calling this the biggest gap. Notes are table-stakes for decks.

## Effort Guess

S — One command + notes-objectId resolution; reuses existing insert/delete-text plumbing.

## Notes

- Belongs with Phase 1 content CRUD (ADR-026) in spirit; landing as a follow-up.
- Related: [[slides-phased-rollout]]; Ideas 054 (content CRUD), 056 (styling/layout).
