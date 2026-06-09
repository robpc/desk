---
id: 073
title: Slides set-background (page background color)
status: implemented
effort: S
value: Set a slide's real page background — no rectangle-behind-everything hack
created: 2026-06-09
updated: 2026-06-09
adr: docs/decisions/030-slides-authoring-refinements-and-scope-ux.md
---

# Idea 073: Slides set-background

## Problem

From the test session's deck rebuild: the only way to get a colored / full-bleed slide
background was to lay a full-bleed rectangle behind everything — and since the **Slides API
has no z-order/reorder request at all**, that rectangle had to be inserted *first*, before
any content. Awkward and error-prone.

## What was implemented

`desk slides set-background <id> <slide> <color>` — sets the actual page background via
`updatePageProperties.pageBackgroundFill.solidFill.color`. `<slide>` is a 0-based index or
objectId; `<color>` is hex (#RRGGBB) or a theme name (ACCENT1, DARK1, …). No rectangle, no
z-order dance.

## Notes

- Live-verified (hex + theme; raw `get` confirms `pageBackgroundFill` set). 6 tests.
- Pairs with `--region full-bleed` (Idea 072) for full-bleed *images*; this is for solid
  background *color*. A `--image-url` background (`stretchedPictureFill`) is an easy
  follow-up if needed.
- Z-order remains a hard API limitation (no reorder request) — `set-background` removes the
  main reason agents wanted it.
- Related: [[slides-phased-rollout]]; Phase 3b backlog (Idea 056) listed slide backgrounds.
