---
id: 077
title: Slides group / ungroup (persistent element grouping)
status: implemented
effort: S
value: Manipulate a composed cluster of elements as one unit (move/resize/center) across steps
created: 2026-06-10
updated: 2026-06-10
adr: 032
---

# Idea 077: Slides group / ungroup

## Problem

`stack`/`arrange` are one-time layout passes — once placed, the set's relationship is lost, so
moving a composed cluster (logo + label, chart + caption) later means re-listing every member.
ADR-031 deferred persistent grouping until the "manipulate as one unit" need appeared. It did.

## What was implemented

`desk slides group <id> <obj> <obj>...` → one `groupObjects` request (≥2 ids, returns a
`group_<uuid16>` objectId) and `desk slides ungroup <id> <group-id>` → `ungroupObjects`. The
group id is a real page element, so `place`/`arrange`/`stack`/`inspect` all accept it as a
single unit. `inspect` now reports a group as `{"type": "group", "children": N}`.

See [ADR-032](../decisions/032-slides-group-ungroup.md).

## Notes

- Google's own vocabulary (`groupObjects`) — no invented terms; a real persistent capability,
  not a composition.
- Live-verified: group shapes → center the group via `place --region center` → ungroup.
- **Live-caught:** a group has no `size` of its own, so `place` first failed with "no resolvable
  size." Fixed by deriving the group's box from the union of its children (mapped through the
  group transform) and offsetting the placement translate by the group's local origin — so
  `place` fits the group's rendered box to the region exactly.
- Limits: API rejects some cross-kind groupings (surfaced as an API error); `inspect` reports
  immediate child count only, not nested trees.
- Related: [[slides-phased-rollout]]; ADR-031 (`stack`), Idea 074.
