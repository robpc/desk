---
id: 032
title: Slides `group` / `ungroup` — persistent element grouping
status: accepted
date: 2026-06-10
supersedes: []
superseded_by: null
tags: [slides, api, layout]
---

# ADR-032: Slides `group` / `ungroup`

## Context

`stack` (ADR-031) and `arrange` (ADR-029) are **one-time layout passes** — they move/size
elements once, then forget the relationship. ADR-031 explicitly deferred persistent grouping
("add `group`/`ungroup` only if 'manipulate as one unit' is needed"). That need showed up:
once a set of elements is composed (a logo + label, a chart + caption, a cluster of callouts),
the agent wants to **move/resize/center the whole cluster as one unit** in later steps without
re-listing every member. The Slides API exposes exactly this via `groupObjects` /
`ungroupObjects`, and a group's `objectId` is a first-class page element — so it already works
with `place`, `arrange`, `stack`, and `inspect`.

## Decision

Add two commands:

```
desk slides group   <id> <object-id> <object-id> [<object-id>...]
desk slides ungroup <id> <group-id>
```

- `group` issues one `groupObjects` request (`childrenObjectIds`, generated
  `groupObjectId = group_<uuid16>`), requires **≥2** objects, and returns the new
  `groupObjectId`. That id is then usable anywhere an objectId is — `place <id> <group-id>
  --region center` moves/fits the whole cluster.
- `ungroup` issues `ungroupObjects` (`objectIds: [group-id]`), dissolving the group back into
  its members (members survive; only the grouping is removed).
- `inspect` now classifies a group element as `{"type": "group", "children": N}` so agents can
  discover and target existing groups.

This is **Google's own vocabulary** (`groupObjects`) — no invented terms (ADR-002) — and a
genuine capability, not a workflow composition (ADR-003): grouping persists in the document and
changes how every later transform behaves.

## Alternatives Considered

- **Re-list members each time** (status quo) — works, but the agent must track the membership
  set across steps and re-pass it to every `place`/`stack`. Brittle for clusters touched
  repeatedly. Grouping makes the set a single durable handle.
- **A desk-side "virtual group"** (store membership locally, expand on each command) — invents
  state the API already keeps, and wouldn't survive outside desk or render as a real group in
  Slides. Rejected for the native `groupObjects`.

## Consequences

### Positive
- Compose once, then manipulate the cluster as one unit (center, move, resize) by its id.
- Pure Google vocabulary; the group id composes with all existing element commands.
- `inspect` surfaces groups, so agents can find and reuse them.

### Negative
- The API rejects grouping across incompatible element kinds in some cases (e.g. mixing certain
  placeholder types) — surfaced as a Slides API error, not pre-validated by desk.
- Nested groups are possible but `inspect` reports only the immediate child count, not the
  full tree (a future enrichment if needed).

## Implementation Notes

- `src/desk/services/slides.py`: `group_elements` (≥2 guard, `groupObjects`), `ungroup_elements`
  (`ungroupObjects`); `inspect` group-classification branch.
- **Group box resolution.** A group reports *no `size`* of its own (verified live) — its
  geometry is the union of its children's boxes in group-local space, mapped through the group's
  own transform. Added `_group_local_extent` / `_group_box` so `inspect` shows a group's real box
  and `place`/`fit`/`move` work on it. The transform builders offset the translate by the group's
  local origin (children aren't at local 0,0). Without this, `place` failed with "no resolvable
  size."
- **`place <group> --region` = translate, not scale** (bug fix, deck-builder live report).
  For a normal element `--region` fits-to-fill the region cell. A group, however, is a *fixed
  composition with no intrinsic size* — scaling it to fill an arbitrary grid cell squashes the
  cluster (a 672×122 group collapsed into a 216×111 cell, children shrunk, text overflowing).
  So for a group, `--region R` now **centers the group's union bbox within R, preserving child
  sizes**; resizing a group happens only when `--width/--height` is passed explicitly. This is a
  deliberate, documented exception to the single-element fit-to-fill semantics. Live-verified: a
  630×90 cluster `place --region center` → still 630×90, centered on the slide; ungroup leaves
  the (un-squashed) children in place.
- `src/desk/commands/slides.py`: `group` (variadic object ids, emits `undo_command` =
  `ungroup …`) and `ungroup` commands. Live-verified: group 3 shapes → `place --region center`
  the group → `ungroup`.

## References

- ADR-029 (`arrange`), ADR-031 (`stack` — deferred grouping to here), ADR-002 (no invented
  vocabulary), ADR-003 (toolkit not workflows)
- [Idea 077](../ideas/077-slides-group-ungroup.md)
