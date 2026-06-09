---
id: 062
title: add-slide should emit placeholder objectIds + types
status: idea
effort: S
value: Removes the mandatory `inspect` round-trip between add-slide and insert-text
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 062: add-slide should emit placeholder objectIds + types

## Problem

To fill a freshly added slide an agent must call `inspect` first, purely to learn the new
slide's placeholder objectIds (which are API-assigned and unguessable, e.g.
`SLIDES_API1981612515_2`). That's a forced extra round-trip per slide — a big chunk of the
~30+ calls observed building an 11-slide deck (Idea 061).

Note on the original feedback framing: `--quiet` does **not** actually hide the slide
objectId when `--json` is set — in `output_result`, the `as_json` branch prints and returns
*before* the `quiet` check, so `add-slide --quiet --json` already emits the new slide id.
The real gap is that the receipt only includes the **slide** objectId, not its
**placeholder** objectIds/types — and placeholders are what `insert-text` needs.

## Sketch

Have `add-slide` return the new slide's placeholders in its receipt/JSON, e.g.:

```json
"placeholders": [
  {"type": "TITLE", "objectId": "SLIDES_API..._1"},
  {"type": "BODY",  "objectId": "SLIDES_API..._2"}
]
```

Two ways to get them:

- **Post-create get** (simplest): after `createSlide`, fetch the new slide and read its
  `pageElements[].shape.placeholder` — one extra internal call, but the agent saves its own.
- **`placeholderIdMappings`** on the `createSlide` request: assign deterministic, agent-chosen
  objectIds to the layout's placeholders up front, so no lookup is needed at all. Cleaner but
  requires knowing the layout's placeholder set.

Either way the agent goes add-slide → insert-text directly, no `inspect`.

## Open Questions

- [ ] Post-create get vs `placeholderIdMappings` — the mapping approach removes the extra
      internal round-trip entirely; confirm it's ergonomic for the predefined layouts.
- [ ] Emit placeholders only when present (BLANK has none); keep the field optional.

## Value Signal

Real 11-slide build: `inspect` was mandatory after every `add-slide`. This deletes that
step with a tiny change. Highest ROI of the authoring-ergonomics options (Idea 061a).

## Effort Guess

S — Augment `add-slide`'s result with placeholder info; no new command.

## Notes

- Implements option (a) of [[slides-phased-rollout]] Idea 061; cleanest first step there.
