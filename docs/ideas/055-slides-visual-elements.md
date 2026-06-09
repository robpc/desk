---
id: 055
title: Slides Phase 2 — Visual Elements
status: idea
effort: M
value: Agents can add images, tables, and shapes/text boxes to slides
created: 2026-06-09
updated: 2026-06-09
adr: null
---

# Idea 055: Slides Phase 2 — Visual Elements

## Problem

Phase 1 (Idea 054) gives agents text on slides via existing placeholders, but a real deck
needs images, tables, and free-standing shapes/text boxes. Without these, agents can edit
text but can't compose a slide's visual content from scratch.

## Sketch

Add element-creation commands to the `desk slides` group:

- `insert-image` — `createImage` from a public URL or Drive file ID, with optional
  position/size
- `insert-table` — `createTable` (rows × cols), addressable for later text insertion
- `insert-shape` / `insert-textbox` — `createShape` (text box, rectangle, etc.), so
  `insert-text` (Phase 1) can then target it
- `delete-object` already exists (Phase 1) and covers removal

Positioning uses the Slides transform model (EMU/point translate + scale). Provide
sensible defaults so agents can place an element without computing a transform, with
optional `--x/--y/--width/--height` flags.

## Open Questions

- [ ] Image source: URL only, or also Drive file ID? Drive IDs need a resolvable URL or
      `createImage` with a Drive reference — confirm what the API accepts.
- [ ] How to express position/size ergonomically without forcing agents to think in EMU?
      Consider point-based flags with a default placement.
- [ ] Table cell text insertion — reuse `insert-text` with a cell-addressing scheme
      (`objectId` + row/col)?
- [ ] Shape type enum surface — expose the full set or a curated subset (text box,
      rectangle, ellipse, line)?

## Value Signal

Tables and images are core to most real presentations. Depends on Phase 1's primitives
existing first.

## Effort Guess

M — Several create commands plus a usable positioning story. The transform/EMU model is
the main complexity driver.

## Notes

- Follows Idea 054; will graduate via its own ADR (or an amendment to ADR-026)
- `insert-text` (Phase 1) is the consumer of shapes/tables created here
